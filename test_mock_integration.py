#!/usr/bin/env python3
"""Simple test script to verify mock AmoCRM integration."""

import sys
import os
from datetime import datetime
from loguru import logger

# Add src to path
sys.path.append('src')

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    level="DEBUG",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

def test_mock_amocrm():
    """Test the mock AmoCRM client."""
    logger.info("🧪 Testing Mock AmoCRM Client")
    
    try:
        from test_amocrm import MockAmoCRMClient
        
        # Initialize mock client
        client = MockAmoCRMClient()
        logger.info("✅ Mock AmoCRM client initialized")
        
        # Test creating a contact
        test_contact_data = {
            'name': 'Иванов Иван Иванович',
            'custom_fields_values': [
                {
                    'field_id': 2,  # Phone field
                    'values': [{'value': '+7 (925) 123-45-67'}]
                },
                {
                    'field_id': 25,  # Patient ID field
                    'values': [{'value': '1'}]
                },
                {
                    'field_id': 3,  # Age field
                    'values': [{'value': 39}]
                },
                {
                    'field_id': 4,  # Gender field
                    'values': [{'value': 'Мужской'}]
                }
            ]
        }
        
        # Create contact
        contact_id = client.create_contact(test_contact_data)
        logger.info(f"✅ Created contact with ID: {contact_id}")
        
        # Test finding contact by phone
        found_contact = client.get_contact_by_phone('+7 (925) 123-45-67')
        if found_contact:
            logger.info(f"✅ Found contact by phone: {found_contact['id']}")
        else:
            logger.error("❌ Failed to find contact by phone")
            return False
        
        # Test finding contact by patient ID
        found_contact_by_id = client.get_contact_by_custom_field(25, '1')
        if found_contact_by_id:
            logger.info(f"✅ Found contact by patient ID: {found_contact_by_id['id']}")
        else:
            logger.error("❌ Failed to find contact by patient ID")
            return False
        
        # Test updating contact
        update_data = {
            'name': 'Иванов Иван Иванович (Обновлено)',
            'custom_fields_values': [
                {
                    'field_id': 3,  # Age field
                    'values': [{'value': 40}]
                }
            ]
        }
        
        success = client.update_contact(contact_id, update_data)
        if success:
            logger.info("✅ Successfully updated contact")
        else:
            logger.error("❌ Failed to update contact")
            return False
        
        # Test batch operations
        batch_data = [
            {
                'name': 'Петрова Мария Сергеевна',
                'custom_fields_values': [
                    {'field_id': 2, 'values': [{'value': '+7 (916) 987-65-43'}]},
                    {'field_id': 25, 'values': [{'value': '2'}]}
                ]
            },
            {
                'name': 'Сидоров Петр Александрович',
                'custom_fields_values': [
                    {'field_id': 2, 'values': [{'value': '+7 (903) 555-44-33'}]},
                    {'field_id': 25, 'values': [{'value': '3'}]}
                ]
            }
        ]
        
        batch_results = client.batch_create_or_update_contacts(batch_data)
        logger.info(f"✅ Batch operation results: {len(batch_results['created'])} created, {len(batch_results['failed'])} failed")
        
        # Show statistics
        stats = client.get_stats()
        logger.info("📊 Mock AmoCRM Statistics:")
        logger.info(f"   - Total contacts: {stats['total_contacts']}")
        logger.info(f"   - API calls made: {stats['api_calls']}")
        logger.info(f"   - Created contacts:")
        
        for contact in stats['contacts']:
            logger.info(f"     * {contact['name']} (ID: {contact['id']})")
        
        logger.info("🎉 All mock tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Mock test failed: {e}")
        return False


def test_patient_model():
    """Test patient model and AmoCRM format conversion."""
    logger.info("🧪 Testing Patient Model")
    
    try:
        from models import Patient, Person, Gender, PatientStatus
        
        # Create test person
        person = Person(
            id=1,
            surname="Иванов",
            name="Иван",
            patronymic="Иванович",
            sex=Gender.MALE,
            birthday=datetime(1985, 5, 15),
            phone=None,
            mobile_phone="+7 (925) 123-45-67",
            email="ivanov@email.com",
            city="Москва",
            inn="1234567890",
            snils="12345678901",
            passport="1234 567890",
            age=39,
            date_time_changed=datetime.now()
        )
        
        # Create test patient
        patient = Patient(
            id_patient=1,
            id_persons=1,
            first_visit=datetime(2023, 1, 15),
            card_number="CARD001",
            comment="Регулярный пациент, профилактические осмотры",
            patient_number="PAT001",
            status=PatientStatus.ACTIVE,
            archive_reason=None,
            branch="Главный филиал",
            person=person,
            last_updated=datetime.now(),
            discount=5.0,
            total_visits=2,
            advance=0.0,
            debt=0.0
        )
        
        logger.info(f"✅ Created patient: {patient._format_name()}")
        
        # Test AmoCRM format conversion
        amocrm_data = patient.to_amocrm_format()
        logger.info("✅ Converted to AmoCRM format:")
        logger.info(f"   - Name: {amocrm_data['name']}")
        logger.info(f"   - Custom fields: {len(amocrm_data['custom_fields_values'])}")
        
        # Show some custom fields
        for field in amocrm_data['custom_fields_values'][:5]:
            field_name = {
                2: "Телефон",
                25: "ID пациента IDENT",
                3: "Возраст",
                4: "Пол",
                5: "Email"
            }.get(field['field_id'], f"Field {field['field_id']}")
            
            value = field['values'][0]['value'] if field['values'] else 'N/A'
            logger.info(f"     * {field_name}: {value}")
        
        logger.info("🎉 Patient model test passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Patient model test failed: {e}")
        return False


def main():
    """Run all tests."""
    logger.info("🚀 Starting Mock Integration Tests")
    
    tests = [
        ("Mock AmoCRM Client", test_mock_amocrm),
        ("Patient Model", test_patient_model),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*50}")
        
        if test_func():
            passed += 1
            logger.info(f"✅ {test_name}: PASSED")
        else:
            logger.error(f"❌ {test_name}: FAILED")
    
    logger.info(f"\n{'='*50}")
    logger.info(f"Test Results: {passed}/{total} tests passed")
    logger.info(f"{'='*50}")
    
    if passed == total:
        logger.info("🎉 All tests passed! Integration is working correctly.")
        return True
    else:
        logger.error("❌ Some tests failed. Please check the logs above.")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1) 