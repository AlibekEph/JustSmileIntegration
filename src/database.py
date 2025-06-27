"""Database connection and operations for IDENT system."""

import pyodbc
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from loguru import logger

from config import db_config
from src.models import Patient, Person, Gender, PatientStatus, Reception, ReceptionStatus


class IdentDatabase:
    """IDENT database operations."""
    
    def __init__(self):
        """Initialize database connection."""
        self.connection_string = db_config.connection_string
        self._connection = None
        self._cursor = None
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
    
    def connect(self):
        """Establish database connection."""
        try:
            self._connection = pyodbc.connect(self.connection_string)
            self._cursor = self._connection.cursor()
            logger.info("Connected to IDENT database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def disconnect(self):
        """Close database connection."""
        if self._cursor:
            self._cursor.close()
        if self._connection:
            self._connection.close()
        logger.info("Disconnected from IDENT database")
    
    def get_all_patients(self, limit: Optional[int] = None) -> List[Patient]:
        """Get all patients for initial sync."""
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
        WHERE p.Status != 3  -- Exclude deleted patients
        """
        
        if limit:
            query += f" ORDER BY p.ID_Patients OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
        
        self._cursor.execute(query)
        patients = []
        
        for row in self._cursor.fetchall():
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
                archive_reason=self._get_archive_reason(row.ID_ArchiveReasons),
                branch=self._get_branch_name(row.ID_Branches),
                person=person,
                last_updated=row.DateTimeChanged
            )
            
            # Get additional patient data
            patient.discount = self._get_patient_discount(row.ID_Patients)
            patient.total_visits = self._get_patient_visits_count(row.ID_Patients)
            patient.advance, patient.debt = self._get_patient_balance(row.ID_Patients)
            patient.completed_receptions_count = self.get_patient_completed_receptions_count(row.ID_Patients)
            
            patients.append(patient)
        
        logger.info(f"Fetched {len(patients)} patients from database")
        return patients
    
    def get_changed_patients(self, since: datetime, limit: Optional[int] = None) -> List[Patient]:
        """Get patients changed since specified date."""
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
            per.Age,
            per.DateTimeChanged as PersonChanged
        FROM Patients p
        LEFT JOIN Persons per ON p.ID_Persons = per.ID
        WHERE (p.DateTimeChanged >= ? OR per.DateTimeChanged >= ?)
        AND p.Status != 3  -- Exclude deleted patients
        """
        
        if limit:
            query += f" ORDER BY p.DateTimeChanged DESC OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
        
        self._cursor.execute(query, since, since)
        patients = []
        
        for row in self._cursor.fetchall():
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
                date_time_changed=row.PersonChanged
            )
            
            patient = Patient(
                id_patient=row.ID_Patients,
                id_persons=row.ID_Persons,
                first_visit=row.FirstVisit,
                card_number=row.CardNumber,
                comment=row.Comment,
                patient_number=row.PatientNumber,
                status=PatientStatus(row.Status or 1),
                archive_reason=self._get_archive_reason(row.ID_ArchiveReasons),
                branch=self._get_branch_name(row.ID_Branches),
                person=person,
                last_updated=max(row.DateTimeChanged or datetime.min, row.PersonChanged or datetime.min)
            )
            
            # Get additional patient data
            patient.discount = self._get_patient_discount(row.ID_Patients)
            patient.total_visits = self._get_patient_visits_count(row.ID_Patients)
            patient.advance, patient.debt = self._get_patient_balance(row.ID_Patients)
            patient.completed_receptions_count = self.get_patient_completed_receptions_count(row.ID_Patients)
            
            patients.append(patient)
        
        logger.info(f"Fetched {len(patients)} changed patients since {since}")
        return patients
    
    def get_receptions(self, since: Optional[datetime] = None) -> List[Reception]:
        """Get receptions from both Receptions and ScheduledReceptions tables."""
        completed_receptions = self._get_completed_receptions(since)
        scheduled_receptions = self._get_scheduled_receptions(since)
        
        all_receptions = completed_receptions + scheduled_receptions
        logger.info(f"Retrieved {len(all_receptions)} total receptions ({len(completed_receptions)} completed, {len(scheduled_receptions)} scheduled)")
        
        return all_receptions
    
    def _get_completed_receptions(self, since: Optional[datetime] = None) -> List[Reception]:
        """Get completed receptions from Receptions table."""
        query = """
        SELECT 
            r.ID,
            r.ID_Patients,
            r.ID_Staffs,
            r.DateTimeChanged,
            r.Comment,
            p.PatientNumber,
            per.MobilePhone,
            per.Phone,
            s.Surname + ' ' + s.Name as StaffName
        FROM Receptions r
        LEFT JOIN Patients p ON r.ID_Patients = p.ID_Patients
        LEFT JOIN Persons per ON p.ID_Persons = per.ID
        LEFT JOIN Staffs s ON r.ID_Staffs = s.ID
        WHERE 1=1
        """
        
        params = []
        if since:
            query += " AND r.DateTimeChanged >= ?"
            params.append(since)
        
        query += " ORDER BY r.DateTimeChanged DESC"
        
        try:
            self._cursor.execute(query, *params)
            receptions = []
            
            for row in self._cursor.fetchall():
                reception = Reception(
                    id_reception=row.ID,
                    id_patient=row.ID_Patients,
                    patient_number=row.PatientNumber,
                    phone=row.MobilePhone or row.Phone,
                    staff_id=row.ID_Staffs,
                    staff_name=row.StaffName,
                    appointment_date=row.DateTimeChanged,
                    comment=row.Comment,
                    status=ReceptionStatus.COMPLETED,
                    date_changed=row.DateTimeChanged
                )
                receptions.append(reception)
            
            logger.debug(f"Retrieved {len(receptions)} completed receptions")
            return receptions
            
        except Exception as e:
            logger.error(f"Failed to get completed receptions: {e}")
            raise
    
    def _get_scheduled_receptions(self, since: Optional[datetime] = None) -> List[Reception]:
        """Get scheduled receptions from ScheduledReceptions table."""
        query = """
        SELECT 
            sr.ID_Receptions,
            sr.ID_Patients,
            sr.ID_Staffs,
            sr.DateTimeAdded,
            sr.DateTimeChanged,
            sr.Comment,
            sr.Length,
            p.PatientNumber,
            per.MobilePhone,
            per.Phone,
            s.Surname + ' ' + s.Name as StaffName
        FROM ScheduledReceptions sr
        LEFT JOIN Patients p ON sr.ID_Patients = p.ID_Patients
        LEFT JOIN Persons per ON p.ID_Persons = per.ID
        LEFT JOIN Staffs s ON sr.ID_Staffs = s.ID
        WHERE sr.ID_ReceptionCancelReasons IS NULL  -- Not cancelled
        """
        
        params = []
        if since:
            query += " AND (sr.DateTimeAdded >= ? OR sr.DateTimeChanged >= ?)"
            params.extend([since, since])
        
        query += " ORDER BY sr.DateTimeChanged DESC"
        
        try:
            self._cursor.execute(query, *params)
            receptions = []
            
            for row in self._cursor.fetchall():
                reception = Reception(
                    id_reception=row.ID_Receptions,
                    id_patient=row.ID_Patients,
                    patient_number=row.PatientNumber,
                    phone=row.MobilePhone or row.Phone,
                    staff_id=row.ID_Staffs,
                    staff_name=row.StaffName,
                    appointment_date=row.DateTimeAdded,
                    duration=row.Length,
                    comment=row.Comment,
                    status=ReceptionStatus.SCHEDULED,
                    date_added=row.DateTimeAdded,
                    date_changed=row.DateTimeChanged
                )
                receptions.append(reception)
            
            logger.debug(f"Retrieved {len(receptions)} scheduled receptions")
            return receptions
            
        except Exception as e:
            logger.error(f"Failed to get scheduled receptions: {e}")
            raise
    
    def get_patient_completed_receptions_count(self, patient_id: int) -> int:
        """Get count of completed receptions for a patient."""
        query = """
        SELECT COUNT(*) as reception_count
        FROM Receptions 
        WHERE ID_Patients = ?
        """
        
        try:
            self._cursor.execute(query, patient_id)
            row = self._cursor.fetchone()
            count = row.reception_count if row else 0
            logger.debug(f"Patient {patient_id} has {count} completed receptions")
            return count
            
        except Exception as e:
            logger.error(f"Failed to get completed receptions count for patient {patient_id}: {e}")
            return 0
    
    def _get_archive_reason(self, reason_id: Optional[int]) -> Optional[str]:
        """Get archive reason by ID."""
        if not reason_id:
            return None
        
        self._cursor.execute("SELECT Name FROM ArchiveReasons WHERE ID = ?", reason_id)
        row = self._cursor.fetchone()
        return row.Name if row else None
    
    def _get_branch_name(self, branch_id: Optional[int]) -> Optional[str]:
        """Get branch name by ID."""
        if not branch_id:
            return None
        
        self._cursor.execute("SELECT Name FROM Branches WHERE ID = ?", branch_id)
        row = self._cursor.fetchone()
        return row.Name if row else None
    
    def _get_patient_discount(self, patient_id: int) -> float:
        """Get patient discount percentage."""
        self._cursor.execute("""
            SELECT TOP 1 DiscountPercent 
            FROM PatientDiscounts 
            WHERE ID_Patients = ? 
            ORDER BY DateCreated DESC
        """, patient_id)
        
        row = self._cursor.fetchone()
        return float(row.DiscountPercent) if row and row.DiscountPercent else 0.0
    
    def _get_patient_visits_count(self, patient_id: int) -> int:
        """Get total visits count for patient."""
        self._cursor.execute("""
            SELECT COUNT(*) as VisitCount
            FROM Receptions
            WHERE ID_Patients = ?
            AND Status IN (2, 3, 4)  -- Completed statuses
        """, patient_id)
        
        row = self._cursor.fetchone()
        return row.VisitCount if row else 0
    
    def _get_patient_balance(self, patient_id: int) -> Tuple[float, float]:
        """Get patient financial balance (advance, debt)."""
        # Get total payments
        self._cursor.execute("""
            SELECT SUM(Amount) as TotalPayments
            FROM Payments
            WHERE ID_Patients = ?
            AND Status = 1  -- Confirmed payments
        """, patient_id)
        
        payments_row = self._cursor.fetchone()
        total_payments = float(payments_row.TotalPayments) if payments_row and payments_row.TotalPayments else 0.0
        
        # Get total treatment costs
        self._cursor.execute("""
            SELECT SUM(t.Cost) as TotalCost
            FROM Treatments t
            INNER JOIN Receptions r ON t.ID_Receptions = r.ID
            WHERE r.ID_Patients = ?
            AND t.Status = 1  -- Completed treatments
        """, patient_id)
        
        costs_row = self._cursor.fetchone()
        total_costs = float(costs_row.TotalCost) if costs_row and costs_row.TotalCost else 0.0
        
        balance = total_payments - total_costs
        
        if balance > 0:
            return balance, 0.0  # advance, no debt
        else:
            return 0.0, abs(balance)  # no advance, debt
    
    def get_sync_state(self) -> Dict[int, Dict[str, Any]]:
        """Get synchronization state from database."""
        try:
            self._cursor.execute("""
                SELECT patient_id, last_sync, amocrm_contact_id, sync_status
                FROM SyncState
            """)
            
            state = {}
            for row in self._cursor.fetchall():
                state[row.patient_id] = {
                    'last_sync': row.last_sync,
                    'amocrm_contact_id': row.amocrm_contact_id,
                    'sync_status': row.sync_status
                }
            
            return state
        except pyodbc.ProgrammingError:
            # Table doesn't exist, create it
            self._create_sync_state_table()
            return {}
    
    def update_sync_state(self, patient_id: int, amocrm_contact_id: int, status: str = "success"):
        """Update synchronization state."""
        try:
            self._cursor.execute("""
                MERGE SyncState AS target
                USING (SELECT ? AS patient_id) AS source
                ON target.patient_id = source.patient_id
                WHEN MATCHED THEN
                    UPDATE SET 
                        last_sync = GETDATE(),
                        amocrm_contact_id = ?,
                        sync_status = ?
                WHEN NOT MATCHED THEN
                    INSERT (patient_id, last_sync, amocrm_contact_id, sync_status)
                    VALUES (?, GETDATE(), ?, ?);
            """, patient_id, amocrm_contact_id, status, patient_id, amocrm_contact_id, status)
            
            self._connection.commit()
        except Exception as e:
            logger.error(f"Failed to update sync state: {e}")
            self._connection.rollback()
    
    def _create_sync_state_table(self):
        """Create sync state table if it doesn't exist."""
        self._cursor.execute("""
            CREATE TABLE SyncState (
                patient_id INT PRIMARY KEY,
                last_sync DATETIME NOT NULL,
                amocrm_contact_id INT,
                sync_status VARCHAR(50),
                error_message NVARCHAR(MAX),
                retry_count INT DEFAULT 0
            )
        """)
        self._connection.commit()
        logger.info("Created SyncState table") 