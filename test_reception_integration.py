"""Test reception synchronization functionality."""

import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.reception_sync import ReceptionSyncManager
from src.models import Reception, Patient, Person, Gender, PatientStatus, ReceptionStatus, FunnelType
from src.database import IdentDatabase
from config import AMOCRM_CONFIG, FIELD_MAPPING


class TestReceptionSync(unittest.TestCase):
    """Test reception synchronization logic."""
    
    def setUp(self):
        """Set up test environment."""
        self.reception_sync = ReceptionSyncManager(use_mock=True)
        
        # Create test reception
        self.test_reception = Reception(
            id_reception=12345,
            id_patient=100,
            reception_datetime=datetime.now(),
            status=ReceptionStatus.SCHEDULED,
            doctor_name="Dr. Smith",
            service_name="Consultation",
            cost=1500.0
        )
        
        # Create test patient with person
        self.test_person = Person(
            id=1,
            surname="Иванов",
            name="Иван",
            patronymic="Иванович",
            sex=Gender.MALE,
            birthday=datetime(1985, 5, 15).date(),
            phone="+79161234567",
            mobile_phone="+79161234567",
            email="ivan@example.com"
        )
        
        self.test_patient = Patient(
            id_patient=100,
            id_persons=1,
            first_visit=datetime.now().date(),
            card_number="CARD001",
            patient_number="PAT001",
            status=PatientStatus.ACTIVE,
            person=self.test_person,
            completed_receptions_count=0  # Primary patient
        )
    
    def test_funnel_determination(self):
        """Test funnel type determination based on completed receptions."""
        # Primary patient (0 completed receptions)
        self.assertEqual(self.test_patient.get_funnel_type(), FunnelType.PRIMARY)
        
        # Secondary patient (1+ completed receptions)
        self.test_patient.completed_receptions_count = 1
        self.assertEqual(self.test_patient.get_funnel_type(), FunnelType.SECONDARY)
    
    def test_reception_search_keys(self):
        """Test extraction of search keys from reception."""
        search_keys = self.test_reception.get_search_keys()
        
        # Should have reception_id
        self.assertIn("reception_id", search_keys)
        self.assertEqual(search_keys["reception_id"], 12345)
    
    def test_amocrm_deal_format(self):
        """Test conversion of reception to AmoCRM deal format."""
        pipeline_id = AMOCRM_CONFIG["primary_pipeline_id"]
        stage_id = AMOCRM_CONFIG["default_stage_id"]
        
        deal_data = self.test_reception.to_amocrm_deal_format(pipeline_id, stage_id)
        
        # Check required fields
        self.assertEqual(deal_data["pipeline_id"], pipeline_id)
        self.assertEqual(deal_data["status_id"], stage_id)
        self.assertIn("name", deal_data)
        self.assertIn("custom_fields_values", deal_data)
        
        # Check custom fields
        custom_fields = {field["field_id"]: field["values"][0]["value"] 
                        for field in deal_data["custom_fields_values"]}
        
        self.assertEqual(custom_fields[FIELD_MAPPING["reception_id"]], 12345)
    
    @patch('src.reception_sync.IdentDatabase')
    def test_find_existing_deal_hierarchy(self, mock_db_class):
        """Test the search hierarchy for finding existing deals."""
        # Mock database
        mock_db = Mock()
        mock_db_class.return_value.__enter__.return_value = mock_db
        
        # Mock AmoCRM client methods
        self.reception_sync.amocrm.find_deal_by_reception_id = Mock(return_value=None)
        self.reception_sync.amocrm.find_deal_by_patient_number = Mock(return_value=None)
        self.reception_sync.amocrm.find_contact_by_phone = Mock(return_value=None)
        
        result = self.reception_sync._find_existing_deal_or_contact(self.test_reception)
        
        # Should try all search methods in order
        self.reception_sync.amocrm.find_deal_by_reception_id.assert_called_once()
        
        # Should return None if nothing found
        self.assertIsNone(result)
    
    def test_pipeline_id_selection(self):
        """Test correct pipeline ID selection based on funnel type."""
        # Primary funnel
        primary_id = self.reception_sync._get_pipeline_id(FunnelType.PRIMARY)
        self.assertEqual(primary_id, AMOCRM_CONFIG["primary_pipeline_id"])
        
        # Secondary funnel
        secondary_id = self.reception_sync._get_pipeline_id(FunnelType.SECONDARY)
        self.assertEqual(secondary_id, AMOCRM_CONFIG["secondary_pipeline_id"])
    
    @patch('src.reception_sync.IdentDatabase')
    def test_create_new_deal_flow(self, mock_db_class):
        """Test creation of new contact and deal."""
        # Mock database
        mock_db = Mock()
        mock_db_class.return_value.__enter__.return_value = mock_db
        
        # Mock successful contact and deal creation
        self.reception_sync.amocrm.create_contact = Mock(return_value=123)
        self.reception_sync.amocrm.create_deal = Mock(return_value=456)
        
        pipeline_id = AMOCRM_CONFIG["primary_pipeline_id"]
        
        result = self.reception_sync._create_new_deal(
            self.test_reception, 
            self.test_patient, 
            pipeline_id
        )
        
        # Should be successful
        self.assertTrue(result.success)
        self.assertEqual(result.amocrm_contact_id, 123)
        self.assertEqual(result.amocrm_deal_id, 456)
        self.assertEqual(result.funnel_type, FunnelType.PRIMARY)
        self.assertEqual(result.action, "created")
        
        # Verify AmoCRM calls
        self.reception_sync.amocrm.create_contact.assert_called_once()
        self.reception_sync.amocrm.create_deal.assert_called_once()
    
    def test_amocrm_integration_with_mock(self):
        """Test AmoCRM integration using mock client."""
        # The mock client should handle all operations
        contact_data = self.test_patient.to_amocrm_format()
        contact_id = self.reception_sync.amocrm.create_contact(contact_data)
        
        self.assertIsNotNone(contact_id)
        self.assertIsInstance(contact_id, int)
        
        # Test deal creation
        deal_data = self.test_reception.to_amocrm_deal_format(
            AMOCRM_CONFIG["primary_pipeline_id"],
            AMOCRM_CONFIG["default_stage_id"]
        )
        deal_id = self.reception_sync.amocrm.create_deal(deal_data, contact_id)
        
        self.assertIsNotNone(deal_id)
        self.assertIsInstance(deal_id, int)


class TestReceptionSyncIntegration(unittest.TestCase):
    """Integration tests for reception synchronization."""
    
    def setUp(self):
        """Set up test environment."""
        self.reception_sync = ReceptionSyncManager(use_mock=True)
    
    def test_database_connection(self):
        """Test database connectivity for reception sync."""
        try:
            with IdentDatabase() as db:
                # Test getting receptions
                receptions = db.get_receptions()
                self.assertIsInstance(receptions, list)
                
                print(f"Found {len(receptions)} receptions in database")
                
                # Test getting patients
                if receptions:
                    sample_reception = receptions[0]
                    print(f"Sample reception: ID {sample_reception.id_reception}, Patient {sample_reception.id_patient}")
                    
        except Exception as e:
            self.fail(f"Database connection failed: {e}")
    
    def test_full_reception_sync(self):
        """Test full reception synchronization process."""
        try:
            # Run sync with limited data
            results = self.reception_sync.sync_receptions()
            
            self.assertIsInstance(results, list)
            
            print(f"Sync results: {len(results)} receptions processed")
            
            # Count successful vs failed
            successful = sum(1 for r in results if r.success)
            failed = len(results) - successful
            
            print(f"Successful: {successful}, Failed: {failed}")
            
            # Count funnel distribution
            if results:
                primary_count = sum(1 for r in results if r.success and r.funnel_type == FunnelType.PRIMARY)
                secondary_count = sum(1 for r in results if r.success and r.funnel_type == FunnelType.SECONDARY)
                
                print(f"Funnel distribution: {primary_count} primary, {secondary_count} secondary")
            
        except Exception as e:
            self.fail(f"Reception sync failed: {e}")
    
    def test_single_reception_sync(self):
        """Test syncing a single reception."""
        try:
            # Get a reception ID from database
            with IdentDatabase() as db:
                receptions = db.get_receptions()
                
            if not receptions:
                self.skipTest("No receptions found in database")
            
            test_reception_id = receptions[0].id_reception
            
            # Sync single reception
            result = self.reception_sync.sync_single_reception_by_id(test_reception_id)
            
            self.assertIsNotNone(result)
            
            print(f"Single reception sync result: {result.success}")
            if result.success:
                print(f"Contact ID: {result.amocrm_contact_id}, Deal ID: {result.amocrm_deal_id}")
                print(f"Funnel type: {result.funnel_type}")
            else:
                print(f"Error: {result.error}")
                
        except Exception as e:
            self.fail(f"Single reception sync failed: {e}")


if __name__ == '__main__':
    # Set up test environment
    os.environ['USE_MOCK_AMOCRM'] = 'true'
    
    # Run specific test suites
    loader = unittest.TestLoader()
    
    # Unit tests
    print("=== Running Reception Sync Unit Tests ===")
    unit_suite = loader.loadTestsFromTestCase(TestReceptionSync)
    unittest.TextTestRunner(verbosity=2).run(unit_suite)
    
    print("\n=== Running Reception Sync Integration Tests ===")
    integration_suite = loader.loadTestsFromTestCase(TestReceptionSyncIntegration)
    unittest.TextTestRunner(verbosity=2).run(integration_suite) 