"""AmoCRM API client implementation."""

import time
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import requests
from loguru import logger
import redis

from config import amocrm_config, redis_config, app_config, AMOCRM_CONFIG, FIELD_MAPPING
from src.models import ContactSearchResult, FunnelType


class AmoCRMClient:
    """AmoCRM API client with OAuth 2.0 support."""
    
    def __init__(self):
        """Initialize AmoCRM client."""
        self.subdomain = amocrm_config.subdomain
        self.client_id = amocrm_config.client_id
        self.client_secret = amocrm_config.client_secret
        self.redirect_uri = amocrm_config.redirect_uri
        self.base_url = amocrm_config.base_url
        self.oauth_url = amocrm_config.oauth_url
        
        # Initialize Redis for token storage
        self.redis_client = redis.Redis(
            host=redis_config.host,
            port=redis_config.port,
            db=redis_config.db,
            decode_responses=True
        )
        
        # Rate limiting
        self.rate_limit_requests = app_config.rate_limit_requests
        self.rate_limit_period = app_config.rate_limit_period
        self.request_times = []
        
        # Load tokens from Redis or config
        self._load_tokens()
    
    def _load_tokens(self):
        """Load tokens from Redis or configuration."""
        self.access_token = self.redis_client.get('amocrm:access_token') or amocrm_config.access_token
        self.refresh_token = self.redis_client.get('amocrm:refresh_token') or amocrm_config.refresh_token
        
        if not self.access_token or not self.refresh_token:
            logger.warning("No tokens found. Please authenticate first.")
    
    def _save_tokens(self, access_token: str, refresh_token: str, expires_in: int):
        """Save tokens to Redis."""
        self.access_token = access_token
        self.refresh_token = refresh_token
        
        # Save to Redis with expiration
        self.redis_client.setex('amocrm:access_token', expires_in - 300, access_token)  # Expire 5 min before actual
        self.redis_client.set('amocrm:refresh_token', refresh_token)  # No expiration for refresh token
        
        logger.info("Tokens saved to Redis")
    
    def _rate_limit(self):
        """Implement rate limiting."""
        now = time.time()
        # Remove requests older than rate limit period
        self.request_times = [t for t in self.request_times if now - t < self.rate_limit_period]
        
        if len(self.request_times) >= self.rate_limit_requests:
            # Need to wait
            sleep_time = self.rate_limit_period - (now - self.request_times[0]) + 0.1
            logger.debug(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
            # Retry
            self._rate_limit()
        
        self.request_times.append(now)
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                     params: Optional[Dict] = None, retry_count: int = 0) -> Dict[str, Any]:
        """Make API request with automatic token refresh."""
        self._rate_limit()
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=30
            )
            
            if response.status_code == 401 and retry_count == 0:
                # Token expired, try to refresh
                logger.info("Access token expired, refreshing...")
                if self.refresh_access_token():
                    return self._make_request(method, endpoint, data, params, retry_count + 1)
                else:
                    raise Exception("Failed to refresh access token")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
    
    def refresh_access_token(self) -> bool:
        """Refresh access token using refresh token."""
        if not self.refresh_token:
            logger.error("No refresh token available")
            return False
        
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'redirect_uri': self.redirect_uri
        }
        
        try:
            response = requests.post(self.oauth_url, json=data, timeout=30)
            response.raise_for_status()
            
            token_data = response.json()
            self._save_tokens(
                token_data['access_token'],
                token_data['refresh_token'],
                token_data['expires_in']
            )
            
            logger.info("Access token refreshed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            return False
    
    def find_deal_by_reception_id(self, reception_id: int) -> Optional[ContactSearchResult]:
        """Find deal by reception ID (primary search key)."""
        logger.debug(f"Searching for deal with reception ID: {reception_id}")
        
        # Search in both primary and secondary pipelines
        pipelines = [AMOCRM_CONFIG["primary_pipeline_id"], AMOCRM_CONFIG["secondary_pipeline_id"]]
        
        for pipeline_id in pipelines:
            result = self._search_deals_by_custom_field(
                field_id=FIELD_MAPPING["reception_id"],
                value=str(reception_id),
                pipeline_id=pipeline_id
            )
            if result:
                result.reception_id = reception_id
                return result
        
        logger.debug(f"No deal found with reception ID: {reception_id}")
        return None
    
    def find_deal_by_patient_number(self, patient_number: str) -> Optional[ContactSearchResult]:
        """Find deal by patient number (secondary search key)."""
        logger.debug(f"Searching for deal with patient number: {patient_number}")
        
        # Search in both pipelines for deals with empty reception_id
        pipelines = [AMOCRM_CONFIG["primary_pipeline_id"], AMOCRM_CONFIG["secondary_pipeline_id"]]
        
        for pipeline_id in pipelines:
            result = self._search_deals_by_patient_number_empty_reception(
                patient_number=patient_number,
                pipeline_id=pipeline_id
            )
            if result:
                result.patient_number = patient_number
                return result
        
        logger.debug(f"No deal found with patient number: {patient_number}")
        return None
    
    def find_contact_by_phone(self, phone: str) -> Optional[ContactSearchResult]:
        """Find contact by phone number (tertiary search key)."""
        logger.debug(f"Searching for contact with phone: {phone}")
        
        contact = self.get_contact_by_phone(phone)
        if contact:
            # Check if contact has deals in target pipelines
            deals = self._get_contact_deals(contact['id'])
            target_deals = self._filter_deals_by_pipelines_and_stages(deals)
            
            if target_deals:
                deal = target_deals[0]  # Take first active deal
                return ContactSearchResult(
                    contact_id=contact['id'],
                    deal_id=deal['id'],
                    pipeline_id=deal['pipeline_id'],
                    stage_id=deal['status_id'],
                    phone=phone
                )
            else:
                # Contact exists but no active deals
                return ContactSearchResult(
                    contact_id=contact['id'],
                    phone=phone
                )
        
        logger.debug(f"No contact found with phone: {phone}")
        return None
    
    def _search_deals_by_custom_field(self, field_id: int, value: str, pipeline_id: int) -> Optional[ContactSearchResult]:
        """Search deals by custom field value in specific pipeline."""
        params = {
            'filter[pipeline_id]': pipeline_id,
            'filter[custom_fields_values]': f"{field_id}={value}",
            'with': 'contacts'
        }
        
        try:
            response = self._make_request('GET', 'leads', params=params)
            deals = response.get('_embedded', {}).get('leads', [])
            
            # Filter deals not in excluded stages
            active_deals = [deal for deal in deals if deal['status_id'] not in AMOCRM_CONFIG["excluded_stages"]]
            
            if active_deals:
                deal = active_deals[0]
                contacts = deal.get('_embedded', {}).get('contacts', [])
                contact_id = contacts[0]['id'] if contacts else None
                
                return ContactSearchResult(
                    contact_id=contact_id,
                    deal_id=deal['id'],
                    pipeline_id=deal['pipeline_id'],
                    stage_id=deal['status_id']
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to search deals by custom field: {e}")
            return None
    
    def _search_deals_by_patient_number_empty_reception(self, patient_number: str, pipeline_id: int) -> Optional[ContactSearchResult]:
        """Search deals by patient number where reception_id is empty."""
        params = {
            'filter[pipeline_id]': pipeline_id,
            'with': 'contacts'
        }
        
        try:
            response = self._make_request('GET', 'leads', params=params)
            deals = response.get('_embedded', {}).get('leads', [])
            
            # Filter deals manually for empty reception_id and matching patient_number
            for deal in deals:
                if deal['status_id'] in AMOCRM_CONFIG["excluded_stages"]:
                    continue
                
                custom_fields = deal.get('custom_fields_values', [])
                has_reception_id = False
                has_patient_number = False
                
                for field in custom_fields:
                    if field['field_id'] == FIELD_MAPPING["reception_id"]:
                        # Check if reception_id is empty or None
                        values = field.get('values', [])
                        if values and values[0].get('value'):
                            has_reception_id = True
                            break
                    elif field['field_id'] == FIELD_MAPPING["patient_number"]:
                        values = field.get('values', [])
                        if values and str(values[0].get('value', '')) == str(patient_number):
                            has_patient_number = True
                
                # Deal should have patient_number but no reception_id
                if has_patient_number and not has_reception_id:
                    contacts = deal.get('_embedded', {}).get('contacts', [])
                    contact_id = contacts[0]['id'] if contacts else None
                    
                    return ContactSearchResult(
                        contact_id=contact_id,
                        deal_id=deal['id'],
                        pipeline_id=deal['pipeline_id'],
                        stage_id=deal['status_id']
                    )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to search deals by patient number: {e}")
            return None
    
    def _get_contact_deals(self, contact_id: int) -> List[Dict[str, Any]]:
        """Get all deals for a contact."""
        params = {
            'filter[contacts]': contact_id
        }
        
        try:
            response = self._make_request('GET', 'leads', params=params)
            return response.get('_embedded', {}).get('leads', [])
        except Exception as e:
            logger.error(f"Failed to get contact deals: {e}")
            return []
    
    def _filter_deals_by_pipelines_and_stages(self, deals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter deals by target pipelines and active stages."""
        target_pipelines = [AMOCRM_CONFIG["primary_pipeline_id"], AMOCRM_CONFIG["secondary_pipeline_id"]]
        excluded_stages = AMOCRM_CONFIG["excluded_stages"]
        
        return [
            deal for deal in deals
            if deal['pipeline_id'] in target_pipelines
            and deal['status_id'] not in excluded_stages
        ]
    
    def create_deal(self, deal_data: Dict[str, Any], contact_id: Optional[int] = None) -> Optional[int]:
        """Create new deal in AmoCRM."""
        try:
            if contact_id:
                deal_data['_embedded'] = {
                    'contacts': [{'id': contact_id}]
                }
            
            # Set responsible user if configured
            if AMOCRM_CONFIG.get("responsible_user_id"):
                deal_data['responsible_user_id'] = AMOCRM_CONFIG["responsible_user_id"]
            
            response = self._make_request('POST', 'leads', data=[deal_data])
            deals = response.get('_embedded', {}).get('leads', [])
            
            if deals:
                deal_id = deals[0].get('id')
                logger.info(f"Created deal with ID: {deal_id}")
                return deal_id
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to create deal: {e}")
            return None
    
    def update_deal(self, deal_id: int, deal_data: Dict[str, Any]) -> bool:
        """Update existing deal in AmoCRM."""
        try:
            deal_data['id'] = deal_id
            self._make_request('PATCH', f'leads/{deal_id}', data=deal_data)
            logger.info(f"Updated deal with ID: {deal_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update deal {deal_id}: {e}")
            return False
    
    def get_contact_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Find contact by phone number."""
        params = {
            'query': phone,
            'with': 'contacts'
        }
        
        try:
            response = self._make_request('GET', 'contacts', params=params)
            contacts = response.get('_embedded', {}).get('contacts', [])
            
            # Filter contacts that have the exact phone number
            for contact in contacts:
                custom_fields = contact.get('custom_fields_values', [])
                for field in custom_fields:
                    if field.get('field_id') == FIELD_MAPPING["phone"]:
                        for value in field.get('values', []):
                            if self._normalize_phone(value.get('value', '')) == self._normalize_phone(phone):
                                return contact
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to search contact by phone: {e}")
            return None
    
    def get_contact_by_custom_field(self, field_id: int, value: str) -> Optional[Dict[str, Any]]:
        """Find contact by custom field value."""
        params = {
            'query': value
        }
        
        try:
            response = self._make_request('GET', 'contacts', params=params)
            contacts = response.get('_embedded', {}).get('contacts', [])
            
            # Filter contacts that have the exact custom field value
            for contact in contacts:
                custom_fields = contact.get('custom_fields_values', [])
                for field in custom_fields:
                    if field.get('field_id') == field_id:
                        for field_value in field.get('values', []):
                            if str(field_value.get('value', '')) == str(value):
                                return contact
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to search contact by custom field: {e}")
            return None
    
    def create_contact(self, contact_data: Dict[str, Any]) -> Optional[int]:
        """Create new contact in AmoCRM."""
        try:
            response = self._make_request('POST', 'contacts', data=[contact_data])
            contacts = response.get('_embedded', {}).get('contacts', [])
            
            if contacts:
                contact_id = contacts[0].get('id')
                logger.info(f"Created contact with ID: {contact_id}")
                return contact_id
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to create contact: {e}")
            return None
    
    def update_contact(self, contact_id: int, contact_data: Dict[str, Any]) -> bool:
        """Update existing contact in AmoCRM."""
        try:
            contact_data['id'] = contact_id
            self._make_request('PATCH', f'contacts/{contact_id}', data=contact_data)
            logger.info(f"Updated contact with ID: {contact_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update contact {contact_id}: {e}")
            return False
    
    def create_or_update_contact(self, patient_data: Dict[str, Any]) -> Optional[int]:
        """Create or update contact based on patient data."""
        # Extract patient ID and phone from data
        patient_id = None
        phone = None
        
        for field in patient_data.get('custom_fields_values', []):
            if field['field_id'] == FIELD_MAPPING["patient_id"]:
                patient_id = field['values'][0]['value']
            elif field['field_id'] == FIELD_MAPPING["phone"]:
                phone = field['values'][0]['value']
        
        if not patient_id:
            logger.error("Patient ID not found in data")
            return None
        
        # First, try to find by patient ID (primary key)
        existing_contact = self.get_contact_by_custom_field(FIELD_MAPPING["patient_id"], patient_id)
        
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
    
    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number for comparison."""
        # Remove all non-digit characters
        return ''.join(filter(str.isdigit, phone))
    
    def batch_create_or_update_contacts(self, contacts_data: List[Dict[str, Any]], 
                                      batch_size: int = 50) -> Dict[str, List[int]]:
        """Batch create or update contacts."""
        results = {
            'created': [],
            'updated': [],
            'failed': []
        }
        
        # Process in batches to avoid API limits
        for i in range(0, len(contacts_data), batch_size):
            batch = contacts_data[i:i + batch_size]
            
            for contact_data in batch:
                try:
                    contact_id = self.create_or_update_contact(contact_data)
                    if contact_id:
                        # Determine if created or updated (simplified)
                        results['created'].append(contact_id)
                    else:
                        results['failed'].append(contact_data)
                except Exception as e:
                    logger.error(f"Failed to process contact: {e}")
                    results['failed'].append(contact_data)
        
        return results
    
    def get_custom_fields(self) -> List[Dict[str, Any]]:
        """Get list of custom fields for contacts."""
        try:
            response = self._make_request('GET', 'contacts/custom_fields')
            return response.get('_embedded', {}).get('custom_fields', [])
        except Exception as e:
            logger.error(f"Failed to get custom fields: {e}")
            return []
    
    def authenticate_with_code(self, code: str) -> bool:
        """Authenticate using authorization code."""
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        
        try:
            response = requests.post(self.oauth_url, json=data, timeout=30)
            response.raise_for_status()
            
            token_data = response.json()
            self._save_tokens(
                token_data['access_token'],
                token_data['refresh_token'],
                token_data['expires_in']
            )
            
            logger.info("Authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"Failed to authenticate: {e}")
            return False 