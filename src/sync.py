"""Main synchronization module."""

import time
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import schedule
from loguru import logger
import pytz

from config import sync_config, app_config
from src.database import IdentDatabase
from src.amocrm import AmoCRMClient
from src.test_amocrm import MockAmoCRMClient
from src.models import Patient
from src.reception_sync import ReceptionSyncManager


class SyncManager:
    """Manages synchronization between IDENT and AmoCRM."""
    
    def __init__(self, use_mock: bool = False):
        """Initialize sync manager."""
        self.db = IdentDatabase()
        
        # Use mock client for testing
        if use_mock or os.getenv('USE_MOCK_AMOCRM', 'false').lower() == 'true':
            self.amocrm = MockAmoCRMClient()
            logger.info("Using Mock AmoCRM Client for testing")
        else:
            self.amocrm = AmoCRMClient()
            logger.info("Using Real AmoCRM Client")
            
        # Initialize reception sync manager
        self.reception_sync = ReceptionSyncManager(use_mock)
            
        self.timezone = pytz.timezone(app_config.timezone)
        self.batch_size = sync_config.batch_size
        
        # Track sync state
        self.last_incremental_sync = None
        self.last_reception_sync = None
        self.initial_sync_completed = False
    
    def run(self):
        """Run the synchronization service."""
        logger.info("Starting IDENT to AmoCRM synchronization service")
        
        # Check if initial sync is needed
        if not self._check_initial_sync_status():
            logger.info("Running initial full synchronization")
            self.full_sync()
            self.initial_sync_completed = True
        
        # Schedule patient syncs
        schedule.every(sync_config.interval_minutes).minutes.do(self.incremental_sync)
        
        # Schedule reception syncs (more frequent)
        schedule.every(1).minutes.do(self.incremental_reception_sync)
        
        # Schedule deep syncs
        schedule.every().day.at(f"{sync_config.deep_sync_hour_morning:02d}:00").do(self.deep_sync)
        schedule.every().day.at(f"{sync_config.deep_sync_hour_evening:02d}:00").do(self.deep_sync)
        
        logger.info(f"Scheduled patient sync every {sync_config.interval_minutes} minutes")
        logger.info(f"Scheduled reception sync every 1 minute")
        logger.info(f"Scheduled deep sync at {sync_config.deep_sync_hour_morning}:00 and {sync_config.deep_sync_hour_evening}:00")
        
        # Run the scheduler
        while True:
            try:
                schedule.run_pending()
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Synchronization service stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error in sync loop: {e}")
                time.sleep(60)  # Wait before retrying
    
    def full_sync(self):
        """Perform full synchronization of all patients and receptions."""
        logger.info("Starting full synchronization")
        start_time = datetime.now()
        
        try:
            # Sync patients first
            self._full_patient_sync()
            
            # Then sync receptions
            self._full_reception_sync()
            
            duration = datetime.now() - start_time
            logger.info(f"Full synchronization completed in {duration}")
            
            # Log mock statistics if using mock client
            if hasattr(self.amocrm, 'get_stats'):
                stats = self.amocrm.get_stats()
                logger.info(f"Mock AmoCRM Stats: {stats}")
            
        except Exception as e:
            logger.error(f"Full sync failed: {e}")
            raise
    
    def _full_patient_sync(self):
        """Perform full patient synchronization."""
        logger.info("Starting full patient synchronization")
        
        with self.db as db:
            # Get sync state
            sync_state = db.get_sync_state()
            
            # Get all patients
            patients = db.get_all_patients()
            logger.info(f"Found {len(patients)} patients to sync")
            
            # Process in batches
            for i in range(0, len(patients), self.batch_size):
                batch = patients[i:i + self.batch_size]
                self._process_patient_batch(batch, sync_state, db)
                
                # Log progress
                progress = min(i + self.batch_size, len(patients))
                logger.info(f"Processed {progress}/{len(patients)} patients")
    
    def _full_reception_sync(self):
        """Perform full reception synchronization."""
        logger.info("Starting full reception synchronization")
        
        results = self.reception_sync.sync_receptions()
        
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        logger.info(f"Reception sync completed: {successful} successful, {failed} failed")
        
        # Log funnel distribution
        primary_count = sum(1 for r in results if r.success and r.funnel_type and r.funnel_type.name == 'PRIMARY')
        secondary_count = sum(1 for r in results if r.success and r.funnel_type and r.funnel_type.name == 'SECONDARY')
        logger.info(f"Funnel distribution: {primary_count} primary, {secondary_count} secondary")
    
    def incremental_sync(self):
        """Perform incremental synchronization of changed patient records."""
        logger.info("Starting incremental patient synchronization")
        start_time = datetime.now()
        
        try:
            # Determine the time range for changes
            if self.last_incremental_sync:
                since = self.last_incremental_sync
            else:
                # Default to last 24 hours for first incremental sync
                since = datetime.now() - timedelta(hours=24)
            
            with self.db as db:
                # Get sync state
                sync_state = db.get_sync_state()
                
                # Get changed patients
                patients = db.get_changed_patients(since)
                logger.info(f"Found {len(patients)} changed patients since {since}")
                
                if patients:
                    # Process in batches
                    for i in range(0, len(patients), self.batch_size):
                        batch = patients[i:i + self.batch_size]
                        self._process_patient_batch(batch, sync_state, db)
            
            self.last_incremental_sync = start_time
            duration = datetime.now() - start_time
            logger.info(f"Incremental patient synchronization completed in {duration}")
            
        except Exception as e:
            logger.error(f"Incremental patient sync failed: {e}")
    
    def incremental_reception_sync(self):
        """Perform incremental synchronization of reception changes."""
        try:
            # Determine the time range for changes
            if self.last_reception_sync:
                since = self.last_reception_sync
            else:
                # Default to last hour for first reception sync
                since = datetime.now() - timedelta(hours=1)
            
            start_time = datetime.now()
            
            results = self.reception_sync.sync_receptions(since)
            
            if results:
                successful = sum(1 for r in results if r.success)
                failed = len(results) - successful
                logger.info(f"Incremental reception sync: {successful} successful, {failed} failed since {since}")
            
            self.last_reception_sync = start_time
            
        except Exception as e:
            logger.error(f"Incremental reception sync failed: {e}")
    
    def deep_sync(self):
        """Perform deep synchronization (similar to full sync but scheduled)."""
        logger.info("Starting deep synchronization")
        current_time = datetime.now(self.timezone)
        
        # Log which deep sync this is
        if current_time.hour < 12:
            logger.info("Running morning deep sync")
        else:
            logger.info("Running evening deep sync")
        
        # Run full sync
        self.full_sync()
    
    def _process_patient_batch(self, patients: List[Patient], sync_state: Dict[int, Dict[str, Any]], db: IdentDatabase):
        """Process a batch of patients."""
        # Convert patients to AmoCRM format
        contacts_data = []
        patient_map = {}
        
        for patient in patients:
            try:
                amocrm_data = patient.to_amocrm_format()
                contacts_data.append(amocrm_data)
                
                # Store mapping for later
                patient_id = patient.id_patient
                patient_map[patient_id] = amocrm_data
                
                logger.debug(f"Prepared patient {patient_id} for sync: {patient._format_name()}")
                
            except Exception as e:
                logger.error(f"Failed to prepare patient {patient.id_patient}: {e}")
        
        if not contacts_data:
            logger.warning("No valid contacts to sync in this batch")
            return
        
        # Send to AmoCRM (real or mock)
        try:
            results = self.amocrm.batch_create_or_update_contacts(contacts_data)
            
            # Update sync state for successful syncs
            for contact_id in results['created'] + results['updated']:
                # Find the patient ID for this contact (simplified mapping)
                for patient_id in patient_map.keys():
                    try:
                        db.update_sync_state(patient_id, contact_id, 'success')
                        break
                    except Exception as e:
                        logger.error(f"Failed to update sync state for patient {patient_id}: {e}")
            
            # Log results
            logger.info(f"Batch results - Created: {len(results['created'])}, "
                       f"Updated: {len(results['updated'])}, Failed: {len(results['failed'])}")
            
            # Handle failures
            if results['failed']:
                logger.warning(f"Failed to sync {len(results['failed'])} contacts")
                # Could implement retry logic here
                
        except Exception as e:
            logger.error(f"Failed to process batch: {e}")
    
    def _check_initial_sync_status(self) -> bool:
        """Check if initial sync has been completed."""
        try:
            with self.db as db:
                sync_state = db.get_sync_state()
                # If we have any sync state, assume initial sync is done
                return len(sync_state) > 0
        except Exception as e:
            logger.error(f"Failed to check initial sync status: {e}")
            return False
    
    def sync_single_patient(self, patient_id: int) -> bool:
        """Sync a single patient (useful for testing or manual sync)."""
        logger.info(f"Syncing single patient: {patient_id}")
        
        try:
            with self.db as db:
                # Get specific patient by ID
                query = """
                SELECT 
                    p.ID_Patients,
                    p.ID_Persons,
                    p.FirstVisit,
                    p.CardNumber,
                    p.Comment,
                    p.PatientNumber,
                    p.Status,
                    p.ID_ArchiveReasons,
                    p.ID_Branches,
                    p.DateTimeChanged,
                    per.Surname,
                    per.Name,
                    per.Patronymic,
                    per.Sex,
                    per.Birthday,
                    per.Phone,
                    per.MobilePhone,
                    per.Email,
                    per.City,
                    per.INN,
                    per.SNILS,
                    per.Passport,
                    per.Age
                FROM Patients p
                LEFT JOIN Persons per ON p.ID_Persons = per.ID
                WHERE p.ID_Patients = ?
                """
                
                db._cursor.execute(query, patient_id)
                row = db._cursor.fetchone()
                
                if not row:
                    logger.error(f"Patient {patient_id} not found")
                    return False
                
                # Create Patient object
                from src.models import Person, PatientStatus, Gender
                
                person = Person(
                    id=row.ID_Persons,
                    surname=row.Surname or "",
                    name=row.Name or "",
                    patronymic=row.Patronymic,
                    sex=Gender(row.Sex or 0),
                    birthday=row.Birthday,
                    phone=row.Phone,
                    mobile_phone=row.MobilePhone,
                    email=row.Email,
                    city=row.City,
                    inn=row.INN,
                    snils=row.SNILS,
                    passport=row.Passport,
                    age=row.Age,
                    date_time_changed=row.DateTimeChanged
                )
                
                patient = Patient(
                    id_patient=row.ID_Patients,
                    id_persons=row.ID_Persons,
                    first_visit=row.FirstVisit,
                    card_number=row.CardNumber,
                    comment=row.Comment,
                    patient_number=row.PatientNumber,
                    status=PatientStatus(row.Status or 1),
                    archive_reason=db._get_archive_reason(row.ID_ArchiveReasons),
                    branch=db._get_branch_name(row.ID_Branches),
                    person=person,
                    last_updated=row.DateTimeChanged
                )
                
                # Get additional patient data
                patient.discount = db._get_patient_discount(row.ID_Patients)
                patient.total_visits = db._get_patient_visits_count(row.ID_Patients)
                patient.advance, patient.debt = db._get_patient_balance(row.ID_Patients)
                patient.completed_receptions_count = db.get_patient_completed_receptions_count(row.ID_Patients)
                
                # Convert to AmoCRM format
                amocrm_data = patient.to_amocrm_format()
                logger.info(f"Patient data: {patient._format_name()}")
                logger.debug(f"AmoCRM data: {amocrm_data}")
                
                # Send to AmoCRM
                contact_id = self.amocrm.create_or_update_contact(amocrm_data)
                
                if contact_id:
                    # Update sync state
                    db.update_sync_state(patient_id, contact_id, 'success')
                    logger.info(f"Successfully synced patient {patient_id} to contact {contact_id}")
                    
                    # Log mock statistics if using mock client
                    if hasattr(self.amocrm, 'get_stats'):
                        stats = self.amocrm.get_stats()
                        logger.info(f"Mock AmoCRM Stats: {stats}")
                    
                    return True
                else:
                    logger.error(f"Failed to sync patient {patient_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error syncing patient {patient_id}: {e}")
            return False
    
    def sync_single_reception(self, reception_id: int) -> bool:
        """Sync a single reception (useful for testing or manual sync)."""
        logger.info(f"Syncing single reception: {reception_id}")
        
        try:
            result = self.reception_sync.sync_single_reception_by_id(reception_id)
            
            if result.success:
                logger.info(f"Successfully synced reception {reception_id}: "
                          f"Contact {result.amocrm_contact_id}, Deal {result.amocrm_deal_id}, "
                          f"Funnel {result.funnel_type.name if result.funnel_type else 'Unknown'}")
                return True
            else:
                logger.error(f"Failed to sync reception {reception_id}: {result.error}")
                return False
                
        except Exception as e:
            logger.error(f"Error syncing reception {reception_id}: {e}")
            return False
    
    def get_sync_statistics(self) -> Dict[str, Any]:
        """Get comprehensive synchronization statistics."""
        stats = {
            "last_patient_sync": self.last_incremental_sync,
            "last_reception_sync": self.last_reception_sync,
            "initial_sync_completed": self.initial_sync_completed
        }
        
        try:
            # Get reception sync statistics
            reception_stats = self.reception_sync.get_sync_statistics()
            stats.update(reception_stats)
            
            # Get patient statistics
            with self.db as db:
                patients = db.get_all_patients()
                stats["total_patients"] = len(patients)
                
                # Count funnel distribution
                primary_count = sum(1 for p in patients if p.completed_receptions_count == 0)
                secondary_count = len(patients) - primary_count
                
                stats["primary_funnel_patients"] = primary_count
                stats["secondary_funnel_patients"] = secondary_count
                
        except Exception as e:
            logger.error(f"Failed to get sync statistics: {e}")
            stats["error"] = str(e)
        
        return stats 