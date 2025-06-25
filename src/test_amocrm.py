"""Mock AmoCRM client for testing without real API keys."""

import json
import time
from typing import Dict, Any, Optional, List
from loguru import logger


class MockAmoCRMClient:
    """Mock AmoCRM client that simulates API responses without making real calls."""
    
    def __init__(self):
        """Initialize mock client."""
        self.subdomain = "test_subdomain"
        self.client_id = "test_client_id"
        self.client_secret = "test_client_secret"
        self.access_token = "mock_access_token"
        self.refresh_token = "mock_refresh_token"
        
        # Mock database of contacts
        self.mock_contacts = {}
        self.next_contact_id = 1000
        
        # Track API calls for testing
        self.api_calls = []
        
        logger.info("Initialized Mock AmoCRM Client")
    
    def _log_api_call(self, method: str, endpoint: str, data: Any = None):
        """Log API call for testing purposes."""
        call = {
            'timestamp': time.time(),
            'method': method,
            'endpoint': endpoint,
            'data': data
        }
        self.api_calls.append(call)
        logger.debug(f"Mock API Call: {method} {endpoint}")
    
    def get_contact_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Mock: Find contact by phone number."""
        self._log_api_call('GET', 'contacts', {'query': phone})
        
        normalized_phone = self._normalize_phone(phone)
        
        for contact in self.mock_contacts.values():
            custom_fields = contact.get('custom_fields_values', [])
            for field in custom_fields:
                if field.get('field_id') == 2:  # Phone field
                    for value in field.get('values', []):
                        if self._normalize_phone(value.get('value', '')) == normalized_phone:
                            logger.info(f"Mock: Found contact by phone {phone}")
                            return contact
        
        logger.info(f"Mock: No contact found for phone {phone}")
        return None
    
    def get_contact_by_custom_field(self, field_id: int, value: str) -> Optional[Dict[str, Any]]:
        """Mock: Find contact by custom field value."""
        self._log_api_call('GET', 'contacts', {'query': value})
        
        for contact in self.mock_contacts.values():
            custom_fields = contact.get('custom_fields_values', [])
            for field in custom_fields:
                if field.get('field_id') == field_id:
                    for field_value in field.get('values', []):
                        if str(field_value.get('value', '')) == str(value):
                            logger.info(f"Mock: Found contact by field {field_id} = {value}")
                            return contact
        
        logger.info(f"Mock: No contact found for field {field_id} = {value}")
        return None
    
    def create_contact(self, contact_data: Dict[str, Any]) -> Optional[int]:
        """Mock: Create new contact."""
        self._log_api_call('POST', 'contacts', contact_data)
        
        contact_id = self.next_contact_id
        self.next_contact_id += 1
        
        # Store the contact with ID
        mock_contact = {
            'id': contact_id,
            'name': contact_data.get('name', 'Unknown'),
            'custom_fields_values': contact_data.get('custom_fields_values', []),
            'created_at': int(time.time()),
            'updated_at': int(time.time())
        }
        
        self.mock_contacts[contact_id] = mock_contact
        
        logger.info(f"Mock: Created contact with ID {contact_id}")
        return contact_id
    
    def update_contact(self, contact_id: int, contact_data: Dict[str, Any]) -> bool:
        """Mock: Update existing contact."""
        self._log_api_call('PATCH', f'contacts/{contact_id}', contact_data)
        
        if contact_id not in self.mock_contacts:
            logger.error(f"Mock: Contact {contact_id} not found for update")
            return False
        
        # Update the contact
        contact = self.mock_contacts[contact_id]
        contact['name'] = contact_data.get('name', contact['name'])
        contact['custom_fields_values'] = contact_data.get('custom_fields_values', contact['custom_fields_values'])
        contact['updated_at'] = int(time.time())
        
        logger.info(f"Mock: Updated contact {contact_id}")
        return True
    
    def create_or_update_contact(self, patient_data: Dict[str, Any]) -> Optional[int]:
        """Mock: Create or update contact based on patient data."""
        # Extract patient ID and phone from data
        patient_id = None
        phone = None
        
        for field in patient_data.get('custom_fields_values', []):
            if field['field_id'] == 25:  # Patient ID field
                patient_id = field['values'][0]['value']
            elif field['field_id'] == 2:  # Phone field
                phone = field['values'][0]['value']
        
        if not patient_id:
            logger.error("Mock: Patient ID not found in data")
            return None
        
        # First, try to find by patient ID (primary key)
        existing_contact = self.get_contact_by_custom_field(25, patient_id)
        
        # If not found and phone exists, try to find by phone (secondary key)
        if not existing_contact and phone:
            existing_contact = self.get_contact_by_phone(phone)
        
        if existing_contact:
            # Update existing contact
            contact_id = existing_contact['id']
            if self.update_contact(contact_id, patient_data):
                return contact_id
        else:
            # Create new contact
            return self.create_contact(patient_data)
        
        return None
    
    def batch_create_or_update_contacts(self, contacts_data: List[Dict[str, Any]], 
                                      batch_size: int = 50) -> Dict[str, List[int]]:
        """Mock: Batch create or update contacts."""
        results = {
            'created': [],
            'updated': [],
            'failed': []
        }
        
        logger.info(f"Mock: Processing batch of {len(contacts_data)} contacts")
        
        for contact_data in contacts_data:
            try:
                contact_id = self.create_or_update_contact(contact_data)
                if contact_id:
                    # Check if it was created or updated (simplified)
                    results['created'].append(contact_id)
                else:
                    results['failed'].append(contact_data)
            except Exception as e:
                logger.error(f"Mock: Failed to process contact: {e}")
                results['failed'].append(contact_data)
        
        logger.info(f"Mock: Batch results - Created: {len(results['created'])}, "
                   f"Updated: {len(results['updated'])}, Failed: {len(results['failed'])}")
        
        return results
    
    def get_custom_fields(self) -> List[Dict[str, Any]]:
        """Mock: Get list of custom fields."""
        self._log_api_call('GET', 'contacts/custom_fields')
        
        # Return mock custom fields
        mock_fields = [
            {'id': 2, 'name': 'Телефон', 'type': 'phone'},
            {'id': 3, 'name': 'Возраст', 'type': 'numeric'},
            {'id': 4, 'name': 'Пол', 'type': 'select'},
            {'id': 25, 'name': 'ID пациента IDENT', 'type': 'text'},
        ]
        
        logger.info(f"Mock: Returned {len(mock_fields)} custom fields")
        return mock_fields
    
    def authenticate_with_code(self, code: str) -> bool:
        """Mock: Authenticate using authorization code."""
        self._log_api_call('POST', 'oauth2/access_token', {'code': code})
        
        if code == "test_auth_code":
            logger.info("Mock: Authentication successful")
            return True
        else:
            logger.error("Mock: Authentication failed")
            return False
    
    def refresh_access_token(self) -> bool:
        """Mock: Refresh access token."""
        self._log_api_call('POST', 'oauth2/access_token', {'grant_type': 'refresh_token'})
        
        logger.info("Mock: Token refreshed successfully")
        return True
    
    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number for comparison."""
        return ''.join(filter(str.isdigit, phone))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get mock client statistics for testing."""
        return {
            'total_contacts': len(self.mock_contacts),
            'api_calls': len(self.api_calls),
            'contacts': list(self.mock_contacts.values())
        } 