"""Main entry point for IDENT to AmoCRM integration."""

import argparse
import sys
import os
from datetime import datetime, timedelta
from loguru import logger

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.sync import SyncManager
from src.reception_sync import ReceptionSyncManager
from config import app_config


def setup_logging():
    """Setup logging configuration."""
    logger.remove()  # Remove default handler
    
    # Add console handler
    logger.add(
        sys.stdout,
        level=app_config.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True
    )
    
    # Add file handler
    os.makedirs(os.path.dirname(app_config.log_file), exist_ok=True)
    logger.add(
        app_config.log_file,
        level=app_config.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="1 day",
        retention="30 days"
    )


def run_sync_service():
    """Run the continuous synchronization service."""
    logger.info("Starting IDENT to AmoCRM synchronization service")
    
    try:
        sync_manager = SyncManager()
        sync_manager.run()
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service failed: {e}")
        sys.exit(1)


def run_full_sync():
    """Run a one-time full synchronization."""
    logger.info("Running one-time full synchronization")
    
    try:
        sync_manager = SyncManager()
        sync_manager.full_sync()
        logger.info("Full synchronization completed successfully")
    except Exception as e:
        logger.error(f"Full sync failed: {e}")
        sys.exit(1)


def run_incremental_sync():
    """Run a one-time incremental synchronization."""
    logger.info("Running one-time incremental synchronization")
    
    try:
        sync_manager = SyncManager()
        sync_manager.incremental_sync()
        logger.info("Incremental synchronization completed successfully")
    except Exception as e:
        logger.error(f"Incremental sync failed: {e}")
        sys.exit(1)


def test_patient_sync(patient_id: int):
    """Test synchronization of a single patient."""
    logger.info(f"Testing patient synchronization for patient ID: {patient_id}")
    
    try:
        sync_manager = SyncManager(use_mock=True)
        success = sync_manager.sync_single_patient(patient_id)
        
        if success:
            logger.info(f"Patient {patient_id} synchronized successfully")
        else:
            logger.error(f"Failed to synchronize patient {patient_id}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Test patient sync failed: {e}")
        sys.exit(1)


def test_reception_sync(reception_id: int):
    """Test synchronization of a single reception."""
    logger.info(f"Testing reception synchronization for reception ID: {reception_id}")
    
    try:
        sync_manager = SyncManager(use_mock=True)
        success = sync_manager.sync_single_reception(reception_id)
        
        if success:
            logger.info(f"Reception {reception_id} synchronized successfully")
        else:
            logger.error(f"Failed to synchronize reception {reception_id}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Test reception sync failed: {e}")
        sys.exit(1)


def run_reception_sync():
    """Run reception synchronization."""
    logger.info("Running reception synchronization")
    
    try:
        reception_sync = ReceptionSyncManager(use_mock=True)
        results = reception_sync.sync_receptions()
        
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        
        logger.info(f"Reception sync completed: {successful} successful, {failed} failed")
        
        # Log funnel distribution
        primary_count = sum(1 for r in results if r.success and r.funnel_type and r.funnel_type.name == 'PRIMARY')
        secondary_count = sum(1 for r in results if r.success and r.funnel_type and r.funnel_type.name == 'SECONDARY')
        logger.info(f"Funnel distribution: {primary_count} primary, {secondary_count} secondary")
        
        if failed > 0:
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Reception sync failed: {e}")
        sys.exit(1)


def show_statistics():
    """Show synchronization statistics."""
    logger.info("Retrieving synchronization statistics")
    
    try:
        sync_manager = SyncManager()
        stats = sync_manager.get_sync_statistics()
        
        logger.info("=== Synchronization Statistics ===")
        for key, value in stats.items():
            if isinstance(value, datetime):
                value = value.strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"{key}: {value}")
            
    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        sys.exit(1)


def test_database_connection():
    """Test database connection."""
    logger.info("Testing database connection")
    
    try:
        from src.database import IdentDatabase
        
        with IdentDatabase() as db:
            # Test patient query
            patients = db.get_all_patients(limit=1)
            logger.info(f"Successfully connected to database. Found {len(patients)} test patients.")
            
            # Test reception query
            receptions = db.get_receptions()
            logger.info(f"Found {len(receptions)} receptions in database.")
            
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        sys.exit(1)


def test_amocrm_connection():
    """Test AmoCRM connection."""
    logger.info("Testing AmoCRM connection")
    
    try:
        from src.amocrm import AmoCRMClient
        
        client = AmoCRMClient()
        fields = client.get_custom_fields()
        logger.info(f"Successfully connected to AmoCRM. Found {len(fields)} custom fields.")
        
    except Exception as e:
        logger.error(f"AmoCRM connection test failed: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="IDENT to AmoCRM Integration")
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Service command
    subparsers.add_parser('service', help='Run continuous synchronization service')
    
    # Sync commands
    subparsers.add_parser('full-sync', help='Run one-time full synchronization')
    subparsers.add_parser('incremental-sync', help='Run one-time incremental synchronization')
    subparsers.add_parser('reception-sync', help='Run reception synchronization')
    
    # Test commands
    test_patient_parser = subparsers.add_parser('test-patient', help='Test single patient synchronization')
    test_patient_parser.add_argument('patient_id', type=int, help='Patient ID to test')
    
    test_reception_parser = subparsers.add_parser('test-reception', help='Test single reception synchronization')
    test_reception_parser.add_argument('reception_id', type=int, help='Reception ID to test')
    
    # Info commands
    subparsers.add_parser('stats', help='Show synchronization statistics')
    subparsers.add_parser('test-db', help='Test database connection')
    subparsers.add_parser('test-amocrm', help='Test AmoCRM connection')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    # Execute command
    if args.command == 'service':
        run_sync_service()
    elif args.command == 'full-sync':
        run_full_sync()
    elif args.command == 'incremental-sync':
        run_incremental_sync()
    elif args.command == 'reception-sync':
        run_reception_sync()
    elif args.command == 'test-patient':
        test_patient_sync(args.patient_id)
    elif args.command == 'test-reception':
        test_reception_sync(args.reception_id)
    elif args.command == 'stats':
        show_statistics()
    elif args.command == 'test-db':
        test_database_connection()
    elif args.command == 'test-amocrm':
        test_amocrm_connection()
    else:
        parser.print_help()


if __name__ == '__main__':
    main() 