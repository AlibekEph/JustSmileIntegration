"""Database models for IDENT system."""

from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class Gender(Enum):
    """Gender enum."""
    UNKNOWN = 0
    MALE = 1
    FEMALE = 2


class PatientStatus(Enum):
    """Patient status enum."""
    ACTIVE = 1
    ARCHIVED = 2
    DELETED = 3


@dataclass
class Person:
    """Person model from IDENT database."""
    id: int
    surname: str
    name: str
    patronymic: Optional[str]
    sex: Gender
    birthday: Optional[datetime]
    phone: Optional[str]
    mobile_phone: Optional[str]
    email: Optional[str]
    city: Optional[str]
    inn: Optional[str]
    snils: Optional[str]
    passport: Optional[str]
    age: Optional[int]
    date_time_changed: Optional[datetime]


@dataclass
class Patient:
    """Patient model from IDENT database."""
    id_patient: int
    id_persons: int
    first_visit: Optional[datetime]
    card_number: Optional[str]
    comment: Optional[str]
    patient_number: Optional[str]
    status: PatientStatus
    archive_reason: Optional[str]
    branch: Optional[str]
    discount: Optional[float]
    sms_opt_out: bool = False
    advance: Optional[float] = 0.0
    debt: Optional[float] = 0.0
    total_visits: Optional[int] = 0
    last_updated: Optional[datetime] = None
    
    # Related person data
    person: Optional[Person] = None
    
    def to_amocrm_format(self) -> Dict[str, Any]:
        """Convert patient data to AmoCRM contact format."""
        data = {
            "name": self._format_name(),
            "custom_fields_values": []
        }
        
        # Add phone if available
        if self.person and (self.person.mobile_phone or self.person.phone):
            phone = self.person.mobile_phone or self.person.phone
            data["custom_fields_values"].append({
                "field_id": 2,  # Phone field ID in AmoCRM
                "values": [{"value": phone}]
            })
        
        # Add other custom fields
        custom_fields = {
            25: str(self.id_patient),  # IDENT patient ID
            3: self.person.age if self.person else None,  # Age
            4: self._format_gender(),  # Gender
            5: self._format_appointments(),  # Appointments (to be implemented)
            6: self.total_visits,  # Total visits
            7: self.card_number,  # Card number
            8: self.person.birthday.isoformat() if self.person and self.person.birthday else None,  # Birthdate
            9: self.comment,  # Comment
            10: self.discount,  # Discount
            11: self.sms_opt_out,  # SMS opt-out
            12: self.archive_reason,  # Archive reason
            13: self.status.value,  # Status
            14: self.person.snils if self.person else None,  # SNILS
            15: self.person.inn if self.person else None,  # INN
            16: self.branch,  # Branch
            17: self.patient_number,  # Patient number
            18: self.advance,  # Advance
            19: self.debt,  # Debt
        }
        
        for field_id, value in custom_fields.items():
            if value is not None:
                data["custom_fields_values"].append({
                    "field_id": field_id,
                    "values": [{"value": str(value)}]
                })
        
        return data
    
    def _format_name(self) -> str:
        """Format patient full name."""
        if not self.person:
            return f"Patient #{self.id_patient}"
        
        parts = [self.person.surname, self.person.name]
        if self.person.patronymic:
            parts.append(self.person.patronymic)
        
        return " ".join(filter(None, parts))
    
    def _format_gender(self) -> str:
        """Format gender for AmoCRM."""
        if not self.person:
            return "Не указан"
        
        return {
            Gender.MALE: "Мужской",
            Gender.FEMALE: "Женский",
            Gender.UNKNOWN: "Не указан"
        }.get(self.person.sex, "Не указан")
    
    def _format_appointments(self) -> str:
        """Format appointments data (placeholder)."""
        # This will be implemented when we have access to appointments data
        return ""


@dataclass
class SyncState:
    """Synchronization state tracking."""
    patient_id: int
    last_sync: datetime
    amocrm_contact_id: Optional[int] = None
    sync_status: str = "pending"
    error_message: Optional[str] = None
    retry_count: int = 0 