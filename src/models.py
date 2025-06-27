"""Data models for IDENT and AmoCRM integration."""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Union
from enum import Enum

from config import FIELD_MAPPING


class Gender(Enum):
    """Patient gender enumeration."""
    UNKNOWN = 0
    MALE = 1
    FEMALE = 2


class PatientStatus(Enum):
    """Patient status enumeration."""
    ACTIVE = 1
    ARCHIVED = 2
    DRAFT = 3


class ReceptionStatus(Enum):
    """Reception status enumeration."""
    SCHEDULED = 1
    COMPLETED = 2
    CANCELLED = 3
    NO_SHOW = 4


class FunnelType(Enum):
    """AmoCRM funnel types."""
    PRIMARY = 1  # Первичные приёмы
    SECONDARY = 2  # Повторные приёмы


class PipelineStage(Enum):
    """AmoCRM pipeline stages."""
    # Общие этапы для обеих воронок
    NEW_LEAD = 1
    CONSULTATION = 2
    TREATMENT_PLAN = 3
    TREATMENT_IN_PROGRESS = 4
    
    # Финальные этапы (исключаются из поиска)
    SUCCESS = 5  # Успешно завершена
    NOT_REALIZED = 6  # Не реализована


@dataclass
class Person:
    """Person (contact) data."""
    id: int
    surname: str
    name: str
    patronymic: Optional[str] = None
    sex: Gender = Gender.UNKNOWN
    birthday: Optional[date] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    inn: Optional[str] = None
    snils: Optional[str] = None
    passport: Optional[str] = None
    age: Optional[int] = None
    date_time_changed: Optional[datetime] = None


@dataclass 
class Patient:
    """Patient data model."""
    id_patient: int
    id_persons: int
    first_visit: Optional[datetime] = None
    card_number: Optional[str] = None
    comment: Optional[str] = None
    patient_number: Optional[str] = None
    status: PatientStatus = PatientStatus.ACTIVE
    archive_reason: Optional[str] = None
    branch: Optional[str] = None
    person: Optional[Person] = None
    last_updated: Optional[datetime] = None
    
    # Calculated fields
    discount: float = 0.0
    total_visits: int = 0
    advance: float = 0.0
    debt: float = 0.0
    completed_receptions_count: int = 0
    
    def _format_name(self) -> str:
        """Format patient's full name."""
        if not self.person:
            return f"Patient {self.id_patient}"
        
        parts = [self.person.surname, self.person.name, self.person.patronymic]
        return " ".join(filter(None, parts))
    
    def _get_primary_phone(self) -> Optional[str]:
        """Get primary phone number."""
        if not self.person:
            return None
        
        # Prefer mobile phone over landline
        return self.person.mobile_phone or self.person.phone
    
    def get_funnel_type(self) -> FunnelType:
        """Determine which funnel the patient belongs to."""
        if self.completed_receptions_count == 0:
            return FunnelType.PRIMARY
        else:
            return FunnelType.SECONDARY
    
    def to_amocrm_format(self) -> Dict[str, Any]:
        """Convert patient to AmoCRM contact format."""
        contact_data = {
            "name": self._format_name(),
            "custom_fields_values": []
        }
        
        # Add phone number
        phone = self._get_primary_phone()
        if phone:
            contact_data["custom_fields_values"].append({
                "field_id": FIELD_MAPPING["phone"],
                "values": [{"value": phone}]
            })
        
        # Add email
        if self.person and self.person.email:
            contact_data["custom_fields_values"].append({
                "field_id": FIELD_MAPPING.get("email", 1),
                "values": [{"value": self.person.email}]
            })
        
        # Add custom fields
        custom_fields = [
            ("patient_id", self.id_patient),
            ("patient_number", self.patient_number),
            ("card_number", self.card_number),
            ("total_visits", self.total_visits),
            ("completed_receptions", self.completed_receptions_count),
            ("advance", self.advance),
            ("debt", self.debt),
            ("discount", self.discount),
            ("status", self.status.value),
        ]
        
        if self.person:
            custom_fields.extend([
                ("age", self.person.age),
                ("gender", self.person.sex.value),
                ("birthdate", self.person.birthday.isoformat() if self.person.birthday else None),
                ("snils", self.person.snils),
                ("inn", self.person.inn),
            ])
        
        for field_name, value in custom_fields:
            if value is not None and field_name in FIELD_MAPPING:
                contact_data["custom_fields_values"].append({
                    "field_id": FIELD_MAPPING[field_name],
                    "values": [{"value": value}]
                })
        
        # Add comment/notes
        if self.comment:
            contact_data["custom_fields_values"].append({
                "field_id": FIELD_MAPPING.get("comment", 9),
                "values": [{"value": self.comment}]
            })
        
        return contact_data


@dataclass
class Reception:
    """Reception (appointment) data model."""
    id_reception: Optional[int]  # ID приёма (может быть None для запланированных)
    id_patient: int
    patient_number: Optional[str]  # Порядковый номер в МИС
    phone: Optional[str]  # Номер телефона для поиска
    
    # Reception details
    staff_id: Optional[int] = None
    staff_name: Optional[str] = None
    appointment_date: Optional[datetime] = None
    duration: Optional[int] = None  # В минутах
    comment: Optional[str] = None
    status: ReceptionStatus = ReceptionStatus.SCHEDULED
    
    # Tracking fields
    date_added: Optional[datetime] = None
    date_changed: Optional[datetime] = None
    
    # AmoCRM integration fields
    amocrm_deal_id: Optional[int] = None
    amocrm_contact_id: Optional[int] = None
    last_synced: Optional[datetime] = None
    
    def get_search_keys(self) -> Dict[str, Any]:
        """Get search keys in order of priority."""
        keys = {}
        
        # 1. ID Приёма (highest priority)
        if self.id_reception:
            keys["reception_id"] = self.id_reception
        
        # 2. Порядковый номер в МИС (medium priority)
        if self.patient_number:
            keys["patient_number"] = self.patient_number
        
        # 3. Номер телефона (lowest priority)
        if self.phone:
            keys["phone"] = self.phone
        
        return keys
    
    def to_amocrm_deal_format(self, pipeline_id: int, stage_id: int) -> Dict[str, Any]:
        """Convert reception to AmoCRM deal format."""
        deal_data = {
            "name": f"Приём #{self.id_reception or 'NEW'}",
            "pipeline_id": pipeline_id,
            "status_id": stage_id,
            "custom_fields_values": []
        }
        
        # Add reception ID if available
        if self.id_reception:
            deal_data["custom_fields_values"].append({
                "field_id": FIELD_MAPPING.get("reception_id", 25),
                "values": [{"value": self.id_reception}]
            })
        
        # Add patient number
        if self.patient_number:
            deal_data["custom_fields_values"].append({
                "field_id": FIELD_MAPPING.get("patient_number", 17),
                "values": [{"value": self.patient_number}]
            })
        
        # Add appointment details
        if self.appointment_date:
            deal_data["custom_fields_values"].append({
                "field_id": FIELD_MAPPING.get("appointment_date", 30),
                "values": [{"value": self.appointment_date.isoformat()}]
            })
        
        if self.staff_name:
            deal_data["custom_fields_values"].append({
                "field_id": FIELD_MAPPING.get("staff", 31),
                "values": [{"value": self.staff_name}]
            })
        
        if self.duration:
            deal_data["custom_fields_values"].append({
                "field_id": FIELD_MAPPING.get("duration", 32),
                "values": [{"value": self.duration}]
            })
        
        # Add comment
        if self.comment:
            deal_data["custom_fields_values"].append({
                "field_id": FIELD_MAPPING.get("comment", 9),
                "values": [{"value": self.comment}]
            })
        
        return deal_data


@dataclass
class SyncResult:
    """Result of synchronization operation."""
    success: bool
    patient_id: int
    reception_id: Optional[int] = None
    amocrm_contact_id: Optional[int] = None
    amocrm_deal_id: Optional[int] = None
    funnel_type: Optional[FunnelType] = None
    action: Optional[str] = None  # created, updated, found
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AmoCRMConfig:
    """AmoCRM configuration for funnels and stages."""
    # Pipeline IDs
    primary_pipeline_id: int = 1  # Первичные приёмы
    secondary_pipeline_id: int = 2  # Повторные приёмы
    
    # Excluded stage IDs (Успешно завершена, Не реализована)
    excluded_stages: List[int] = field(default_factory=lambda: [5, 6])
    
    # Default stage for new deals
    default_stage_id: int = 1
    
    # Responsible user ID
    responsible_user_id: Optional[int] = None


@dataclass
class ContactSearchResult:
    """Result of contact search in AmoCRM."""
    contact_id: int
    deal_id: Optional[int] = None
    pipeline_id: Optional[int] = None
    stage_id: Optional[int] = None
    reception_id: Optional[int] = None
    patient_number: Optional[str] = None
    phone: Optional[str] = None 