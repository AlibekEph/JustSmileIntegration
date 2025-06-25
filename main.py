"""Main entry point for IDENT to AmoCRM synchronization."""

import sys
import os
import argparse
from loguru import logger
from flask import Flask, request, jsonify
import threading

from config import app_config
from src.sync import SyncManager
from src.amocrm import AmoCRMClient


# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    level=app_config.log_level,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)
logger.add(
    app_config.log_file,
    level=app_config.log_level,
    rotation="10 MB",
    retention="30 days"
)


def run_sync_service():
    """Run the synchronization service."""
    # Check if we should use mock client
    use_mock = os.getenv('USE_MOCK_AMOCRM', 'false').lower() == 'true'
    sync_manager = SyncManager(use_mock=use_mock)
    sync_manager.run()


def run_auth_server():
    """Run OAuth callback server."""
    app = Flask(__name__)
    
    @app.route('/callback')
    def oauth_callback():
        """Handle OAuth callback from AmoCRM."""
        code = request.args.get('code')
        if not code:
            return jsonify({'error': 'No authorization code provided'}), 400
        
        # Authenticate with the code
        client = AmoCRMClient()
        if client.authenticate_with_code(code):
            return jsonify({'status': 'success', 'message': 'Authentication successful'}), 200
        else:
            return jsonify({'error': 'Authentication failed'}), 500
    
    @app.route('/health')
    def health_check():
        """Health check endpoint."""
        return jsonify({'status': 'healthy'}), 200
    
    logger.info("Starting OAuth callback server on port 8080")
    app.run(host='0.0.0.0', port=8080)


def test_database_connection():
    """Test database connection."""
    logger.info("Testing database connection...")
    
    try:
        from src.database import IdentDatabase
        
        with IdentDatabase() as db:
            # Test basic query
            db._cursor.execute("SELECT COUNT(*) as patient_count FROM Patients")
            row = db._cursor.fetchone()
            patient_count = row.patient_count if row else 0
            
            logger.info(f"Database connection successful! Found {patient_count} patients.")
            
            # Test getting a few patients
            patients = db.get_all_patients(limit=3)
            logger.info(f"Sample patients:")
            for patient in patients:
                logger.info(f"  - {patient._format_name()} (ID: {patient.id_patient})")
            
            return True
            
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def test_integration():
    """Test the full integration flow."""
    logger.info("Starting integration test...")
    
    # Test database connection first
    if not test_database_connection():
        logger.error("Database test failed, stopping integration test")
        return False
    
    # Test sync with mock AmoCRM
    logger.info("Testing sync with Mock AmoCRM...")
    
    try:
        # Force use of mock client
        os.environ['USE_MOCK_AMOCRM'] = 'true'
        
        sync_manager = SyncManager(use_mock=True)
        
        # Test syncing first patient
        success = sync_manager.sync_single_patient(1)
        
        if success:
            logger.info("✅ Integration test passed!")
            
            # Show mock statistics
            if hasattr(sync_manager.amocrm, 'get_stats'):
                stats = sync_manager.amocrm.get_stats()
                logger.info(f"Mock AmoCRM Statistics:")
                logger.info(f"  - Total contacts: {stats['total_contacts']}")
                logger.info(f"  - API calls made: {stats['api_calls']}")
                logger.info(f"  - Created contacts: {len(stats['contacts'])}")
                
                for contact in stats['contacts']:
                    logger.info(f"    * {contact['name']} (ID: {contact['id']})")
            
            return True
        else:
            logger.error("❌ Integration test failed!")
            return False
            
    except Exception as e:
        logger.error(f"Integration test error: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='IDENT to AmoCRM Synchronization')
    parser.add_argument(
        'command',
        choices=['sync', 'auth', 'test', 'test-db', 'test-integration'],
        help='Command to run'
    )
    parser.add_argument(
        '--patient-id',
        type=int,
        help='Patient ID for test sync'
    )
    parser.add_argument(
        '--use-mock',
        action='store_true',
        help='Use mock AmoCRM client for testing'
    )
    
    args = parser.parse_args()
    
    # Set mock mode if requested
    if args.use_mock:
        os.environ['USE_MOCK_AMOCRM'] = 'true'
    
    if args.command == 'sync':
        logger.info("Starting synchronization service")
        run_sync_service()
        
    elif args.command == 'auth':
        logger.info("Starting authentication server")
        logger.info("Please visit the following URL to authenticate:")
        
        client = AmoCRMClient()
        auth_url = (
            f"https://{client.subdomain}.amocrm.ru/oauth"
            f"?mode=request"
            f"&client_id={client.client_id}"
            f"&redirect_uri={client.redirect_uri}"
            f"&response_type=code"
        )
        logger.info(auth_url)
        
        run_auth_server()
        
    elif args.command == 'test':
        if not args.patient_id:
            logger.error("Patient ID is required for test sync")
            sys.exit(1)
        
        logger.info(f"Running test sync for patient {args.patient_id}")
        
        # Force mock mode for individual tests
        os.environ['USE_MOCK_AMOCRM'] = 'true'
        sync_manager = SyncManager(use_mock=True)
        success = sync_manager.sync_single_patient(args.patient_id)
        
        if success:
            logger.info("Test sync completed successfully")
        else:
            logger.error("Test sync failed")
            sys.exit(1)
    
    elif args.command == 'test-db':
        logger.info("Testing database connection only")
        success = test_database_connection()
        
        if not success:
            sys.exit(1)
    
    elif args.command == 'test-integration':
        logger.info("Running full integration test")
        success = test_integration()
        
        if not success:
            sys.exit(1)


if __name__ == '__main__':
    main() 