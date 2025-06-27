"""Reception synchronization module for IDENT to AmoCRM integration."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from loguru import logger

from config import AMOCRM_CONFIG, FIELD_MAPPING
from src.database import IdentDatabase
from src.amocrm import AmoCRMClient
from src.models import (
    Reception, Patient, SyncResult, FunnelType, ContactSearchResult,
    ReceptionStatus
)


class ReceptionSyncManager:
    """Manages synchronization of receptions between IDENT and AmoCRM."""
    
    def __init__(self, use_mock: bool = False):
        """Initialize reception sync manager."""
        self.db = IdentDatabase()
        
        if use_mock:
            from src.test_amocrm import MockAmoCRMClient
            self.amocrm = MockAmoCRMClient()
            logger.info("Using Mock AmoCRM Client for reception sync")
        else:
            self.amocrm = AmoCRMClient()
            logger.info("Using Real AmoCRM Client for reception sync")
    
    def sync_receptions(self, since: Optional[datetime] = None) -> List[SyncResult]:
        """Synchronize receptions from IDENT to AmoCRM."""
        logger.info("Starting reception synchronization")
        results = []
        
        try:
            with self.db as db:
                # Get receptions to sync
                receptions = db.get_receptions(since)
                logger.info(f"Found {len(receptions)} receptions to sync")
                
                for reception in receptions:
                    try:
                        result = self._sync_single_reception(reception, db)
                        results.append(result)
                        
                        # Log progress
                        if len(results) % 10 == 0:
                            logger.info(f"Processed {len(results)} receptions")
                            
                    except Exception as e:
                        logger.error(f"Failed to sync reception {reception.id_reception}: {e}")
                        results.append(SyncResult(
                            success=False,
                            patient_id=reception.id_patient,
                            reception_id=reception.id_reception,
                            error=str(e)
                        ))
            
            # Log summary
            successful = sum(1 for r in results if r.success)
            failed = len(results) - successful
            logger.info(f"Reception sync completed: {successful} successful, {failed} failed")
            
        except Exception as e:
            logger.error(f"Reception sync failed: {e}")
            raise
        
        return results
    
    def _sync_single_reception(self, reception: Reception, db: IdentDatabase) -> SyncResult:
        """Synchronize a single reception."""
        logger.debug(f"Syncing reception {reception.id_reception} for patient {reception.id_patient}")
        
        try:
            # Step 1: Find existing deal/contact using search hierarchy
            search_result = self._find_existing_deal_or_contact(reception)
            
            # Step 2: Get patient data for funnel determination
            patient = self._get_patient_data(reception.id_patient, db)
            if not patient:
                return SyncResult(
                    success=False,
                    patient_id=reception.id_patient,
                    reception_id=reception.id_reception,
                    error="Patient not found"
                )
            
            # Step 3: Determine target funnel
            funnel_type = patient.get_funnel_type()
            pipeline_id = self._get_pipeline_id(funnel_type)
            
            # Step 4: Create or update contact and deal
            if search_result:
                # Found existing deal or contact
                return self._update_existing_deal(reception, patient, search_result, pipeline_id)
            else:
                # Create new contact and deal
                return self._create_new_deal(reception, patient, pipeline_id)
                
        except Exception as e:
            logger.error(f"Error syncing reception {reception.id_reception}: {e}")
            return SyncResult(
                success=False,
                patient_id=reception.id_patient,
                reception_id=reception.id_reception,
                error=str(e)
            )
    
    def _find_existing_deal_or_contact(self, reception: Reception) -> Optional[ContactSearchResult]:
        """Find existing deal or contact using search hierarchy."""
        search_keys = reception.get_search_keys()
        
        # 1. Search by ID Приёма (highest priority)
        if "reception_id" in search_keys:
            result = self.amocrm.find_deal_by_reception_id(search_keys["reception_id"])
            if result:
                logger.debug(f"Found deal by reception ID: {search_keys['reception_id']}")
                return result
        
        # 2. Search by порядковый номер в МИС (medium priority)
        if "patient_number" in search_keys:
            result = self.amocrm.find_deal_by_patient_number(search_keys["patient_number"])
            if result:
                logger.debug(f"Found deal by patient number: {search_keys['patient_number']}")
                return result
        
        # 3. Search by номер телефона (lowest priority)
        if "phone" in search_keys:
            result = self.amocrm.find_contact_by_phone(search_keys["phone"])
            if result:
                logger.debug(f"Found contact by phone: {search_keys['phone']}")
                return result
        
        logger.debug(f"No existing deal or contact found for reception {reception.id_reception}")
        return None
    
    def _get_patient_data(self, patient_id: int, db: IdentDatabase) -> Optional[Patient]:
        """Get patient data from database."""
        try:
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
                return None
            
            # Create patient object manually
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
                date_time_changed=getattr(row, 'DateTimeChanged', None)
            )
            
            patient = Patient(
                id_patient=row.ID_Patients,
                id_persons=row.ID_Persons,
                first_visit=row.FirstVisit,
                card_number=row.CardNumber,
                comment=row.Comment,
                patient_number=row.PatientNumber,
                status=PatientStatus(row.Status or 1),
                archive_reason=db._get_archive_reason(getattr(row, 'ID_ArchiveReasons', None)),
                branch=db._get_branch_name(getattr(row, 'ID_Branches', None)),
                person=person,
                last_updated=getattr(row, 'DateTimeChanged', None)
            )
            
            # Get additional calculated fields
            patient.discount = db._get_patient_discount(row.ID_Patients)
            patient.total_visits = db._get_patient_visits_count(row.ID_Patients)
            patient.advance, patient.debt = db._get_patient_balance(row.ID_Patients)
            patient.completed_receptions_count = db.get_patient_completed_receptions_count(row.ID_Patients)
            
            return patient
            
        except Exception as e:
            logger.error(f"Failed to get patient data for {patient_id}: {e}")
            return None
    
    def _get_pipeline_id(self, funnel_type: FunnelType) -> int:
        """Get pipeline ID based on funnel type."""
        if funnel_type == FunnelType.PRIMARY:
            return AMOCRM_CONFIG["primary_pipeline_id"]
        else:
            return AMOCRM_CONFIG["secondary_pipeline_id"]
    
    def _update_existing_deal(self, reception: Reception, patient: Patient, 
                            search_result: ContactSearchResult, pipeline_id: int) -> SyncResult:
        """Update existing deal with reception data."""
        try:
            # Update contact if needed
            if search_result.contact_id:
                contact_data = patient.to_amocrm_format()
                self.amocrm.update_contact(search_result.contact_id, contact_data)
            
            # Update deal if it exists
            if search_result.deal_id:
                deal_data = reception.to_amocrm_deal_format(pipeline_id, search_result.stage_id or AMOCRM_CONFIG["default_stage_id"])
                self.amocrm.update_deal(search_result.deal_id, deal_data)
                
                return SyncResult(
                    success=True,
                    patient_id=reception.id_patient,
                    reception_id=reception.id_reception,
                    amocrm_contact_id=search_result.contact_id,
                    amocrm_deal_id=search_result.deal_id,
                    funnel_type=patient.get_funnel_type(),
                    action="updated"
                )
            else:
                # Contact exists but no deal - create deal
                deal_data = reception.to_amocrm_deal_format(pipeline_id, AMOCRM_CONFIG["default_stage_id"])
                deal_id = self.amocrm.create_deal(deal_data, search_result.contact_id)
                
                if deal_id:
                    return SyncResult(
                        success=True,
                        patient_id=reception.id_patient,
                        reception_id=reception.id_reception,
                        amocrm_contact_id=search_result.contact_id,
                        amocrm_deal_id=deal_id,
                        funnel_type=patient.get_funnel_type(),
                        action="created_deal"
                    )
                else:
                    return SyncResult(
                        success=False,
                        patient_id=reception.id_patient,
                        reception_id=reception.id_reception,
                        error="Failed to create deal"
                    )
                    
        except Exception as e:
            return SyncResult(
                success=False,
                patient_id=reception.id_patient,
                reception_id=reception.id_reception,
                error=f"Failed to update existing deal: {e}"
            )
    
    def _create_new_deal(self, reception: Reception, patient: Patient, pipeline_id: int) -> SyncResult:
        """Create new contact and deal."""
        try:
            # Create contact
            contact_data = patient.to_amocrm_format()
            contact_id = self.amocrm.create_contact(contact_data)
            
            if not contact_id:
                return SyncResult(
                    success=False,
                    patient_id=reception.id_patient,
                    reception_id=reception.id_reception,
                    error="Failed to create contact"
                )
            
            # Create deal
            deal_data = reception.to_amocrm_deal_format(pipeline_id, AMOCRM_CONFIG["default_stage_id"])
            deal_id = self.amocrm.create_deal(deal_data, contact_id)
            
            if deal_id:
                return SyncResult(
                    success=True,
                    patient_id=reception.id_patient,
                    reception_id=reception.id_reception,
                    amocrm_contact_id=contact_id,
                    amocrm_deal_id=deal_id,
                    funnel_type=patient.get_funnel_type(),
                    action="created"
                )
            else:
                return SyncResult(
                    success=False,
                    patient_id=reception.id_patient,
                    reception_id=reception.id_reception,
                    amocrm_contact_id=contact_id,
                    error="Failed to create deal"
                )
                
        except Exception as e:
            return SyncResult(
                success=False,
                patient_id=reception.id_patient,
                reception_id=reception.id_reception,
                error=f"Failed to create new deal: {e}"
            )
    
    def sync_single_reception_by_id(self, reception_id: int) -> SyncResult:
        """Sync a single reception by ID (useful for testing)."""
        logger.info(f"Syncing single reception: {reception_id}")
        
        try:
            with self.db as db:
                # Get specific reception
                receptions = db.get_receptions()
                reception = next((r for r in receptions if r.id_reception == reception_id), None)
                
                if not reception:
                    return SyncResult(
                        success=False,
                        patient_id=0,
                        reception_id=reception_id,
                        error="Reception not found"
                    )
                
                result = self._sync_single_reception(reception, db)
                
                # Log result
                if result.success:
                    logger.info(f"Successfully synced reception {reception_id}: "
                              f"Contact {result.amocrm_contact_id}, Deal {result.amocrm_deal_id}, "
                              f"Funnel {result.funnel_type.name if result.funnel_type else 'Unknown'}")
                else:
                    logger.error(f"Failed to sync reception {reception_id}: {result.error}")
                
                return result
                
        except Exception as e:
            logger.error(f"Error syncing reception {reception_id}: {e}")
            return SyncResult(
                success=False,
                patient_id=0,
                reception_id=reception_id,
                error=str(e)
            )
    
    def get_sync_statistics(self) -> Dict[str, Any]:
        """Get synchronization statistics."""
        # This could be enhanced to track sync history
        stats = {
            "last_sync": datetime.now(),
            "total_receptions": 0,
            "primary_funnel_count": 0,
            "secondary_funnel_count": 0,
            "sync_errors": []
        }
        
        try:
            with self.db as db:
                receptions = db.get_receptions()
                stats["total_receptions"] = len(receptions)
                
                # Count by funnel type (would need patient data for accurate count)
                # This is a simplified implementation
                
        except Exception as e:
            logger.error(f"Failed to get sync statistics: {e}")
            stats["error"] = str(e)
        
        return stats 