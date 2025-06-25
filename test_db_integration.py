#!/usr/bin/env python3
"""Test database integration with SQL Server in Docker."""

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

def test_database_connection():
    """Test connection to SQL Server in Docker."""
    logger.info("🧪 Testing Database Connection")
    
    try:
        # Try to install pyodbc if available
        try:
            import pyodbc
            logger.info("✅ pyodbc is available")
        except ImportError:
            logger.warning("⚠️  pyodbc not available, trying pymssql")
            try:
                import pymssql
                logger.info("✅ pymssql is available")
            except ImportError:
                logger.error("❌ No SQL Server drivers available")
                return False
        
        # Test connection parameters
        connection_params = {
            'server': 'localhost,1433',
            'database': 'PZ',
            'user': 'sa',
            'password': 'TestPassword123!',
            'driver': '{ODBC Driver 18 for SQL Server}',
            'trust_server_certificate': 'yes'
        }
        
        logger.info(f"Connecting to database: {connection_params['server']}")
        
        # Try pyodbc first
        try:
            import pyodbc
            conn_str = (
                f"DRIVER={connection_params['driver']};"
                f"SERVER={connection_params['server']};"
                f"DATABASE={connection_params['database']};"
                f"UID={connection_params['user']};"
                f"PWD={connection_params['password']};"
                f"TrustServerCertificate=yes;"
            )
            
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            logger.info("✅ Connected using pyodbc")
            
        except Exception as e:
            logger.warning(f"pyodbc failed: {e}")
            
            # Try pymssql
            try:
                import pymssql
                conn = pymssql.connect(
                    server=connection_params['server'],
                    user=connection_params['user'],
                    password=connection_params['password'],
                    database=connection_params['database']
                )
                cursor = conn.cursor()
                logger.info("✅ Connected using pymssql")
            except Exception as e2:
                logger.error(f"❌ Both connection methods failed: {e2}")
                return False
        
        # Test basic queries
        logger.info("Testing basic queries...")
        
        # Count patients
        cursor.execute("SELECT COUNT(*) FROM Patients")
        patient_count = cursor.fetchone()[0]
        logger.info(f"✅ Found {patient_count} patients")
        
        # Get sample patient data
        cursor.execute("""
            SELECT TOP 3
                p.ID_Patients,
                per.Surname,
                per.Name,
                per.MobilePhone
            FROM Patients p
            LEFT JOIN Persons per ON p.ID_Persons = per.ID
        """)
        
        rows = cursor.fetchall()
        logger.info("✅ Sample patients:")
        for row in rows:
            logger.info(f"   - ID: {row[0]}, Name: {row[1]} {row[2]}, Phone: {row[3]}")
        
        # Test patient data retrieval for AmoCRM format
        cursor.execute("""
            SELECT 
                p.ID_Patients,
                p.ID_Persons,
                p.FirstVisit,
                p.CardNumber,
                p.Comment,
                p.PatientNumber,
                p.Status,
                per.Surname,
                per.Name,
                per.Patronymic,
                per.Sex,
                per.Birthday,
                per.MobilePhone,
                per.Email,
                per.City,
                per.INN,
                per.SNILS,
                per.Age
            FROM Patients p
            LEFT JOIN Persons per ON p.ID_Persons = per.ID
            WHERE p.ID_Patients = 1
        """)
        
        row = cursor.fetchone()
        if row:
            logger.info("✅ Retrieved detailed patient data for ID 1:")
            logger.info(f"   - Name: {row[7]} {row[8]} {row[9]}")
            logger.info(f"   - Phone: {row[12]}")
            logger.info(f"   - Email: {row[13]}")
            logger.info(f"   - Age: {row[17]}")
            logger.info(f"   - Card: {row[3]}")
        else:
            logger.warning("⚠️  No patient found with ID 1")
        
        conn.close()
        logger.info("🎉 Database connection test passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database test failed: {e}")
        return False


def test_full_integration():
    """Test full integration with database and mock AmoCRM."""
    logger.info("🧪 Testing Full Integration")
    
    try:
        from test_amocrm import MockAmoCRMClient
        
        # Initialize mock AmoCRM client
        amocrm = MockAmoCRMClient()
        logger.info("✅ Mock AmoCRM client initialized")
        
        # Test database connection and data retrieval
        try:
            import pyodbc
            conn_str = (
                "DRIVER={ODBC Driver 18 for SQL Server};"
                "SERVER=localhost,1433;"
                "DATABASE=PZ;"
                "UID=sa;"
                "PWD=TestPassword123!;"
                "TrustServerCertificate=yes;"
            )
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            
        except Exception:
            import pymssql
            conn = pymssql.connect(
                server='localhost,1433',
                user='sa',
                password='TestPassword123!',
                database='PZ'
            )
            cursor = conn.cursor()
        
        logger.info("✅ Database connected")
        
        # Get patient data
        cursor.execute("""
            SELECT 
                p.ID_Patients,
                per.Surname,
                per.Name,
                per.Patronymic,
                per.MobilePhone,
                per.Email,
                per.Age,
                per.Sex,
                p.CardNumber,
                p.Comment
            FROM Patients p
            LEFT JOIN Persons per ON p.ID_Persons = per.ID
            ORDER BY p.ID_Patients
        """)
        
        patients = cursor.fetchall()
        logger.info(f"✅ Retrieved {len(patients)} patients from database")
        
        # Convert and sync first few patients
        synced_count = 0
        for patient_row in patients[:3]:  # Test with first 3 patients
            try:
                # Create AmoCRM contact data
                full_name = f"{patient_row[1] or ''} {patient_row[2] or ''} {patient_row[3] or ''}".strip()
                
                contact_data = {
                    'name': full_name,
                    'custom_fields_values': [
                        {
                            'field_id': 2,  # Phone
                            'values': [{'value': patient_row[4] or ''}]
                        },
                        {
                            'field_id': 25,  # Patient ID
                            'values': [{'value': str(patient_row[0])}]
                        },
                        {
                            'field_id': 3,  # Age
                            'values': [{'value': patient_row[6] or 0}]
                        },
                        {
                            'field_id': 4,  # Gender
                            'values': [{'value': 'Мужской' if patient_row[7] == 1 else 'Женский' if patient_row[7] == 2 else 'Не указан'}]
                        },
                        {
                            'field_id': 5,  # Email
                            'values': [{'value': patient_row[5] or ''}]
                        }
                    ]
                }
                
                # Sync to AmoCRM
                contact_id = amocrm.create_or_update_contact(contact_data)
                if contact_id:
                    synced_count += 1
                    logger.info(f"✅ Synced patient {patient_row[0]}: {full_name}")
                else:
                    logger.warning(f"⚠️  Failed to sync patient {patient_row[0]}")
                    
            except Exception as e:
                logger.error(f"❌ Error syncing patient {patient_row[0]}: {e}")
        
        conn.close()
        
        # Show sync results
        stats = amocrm.get_stats()
        logger.info("📊 Integration Test Results:")
        logger.info(f"   - Patients processed: {len(patients[:3])}")
        logger.info(f"   - Successfully synced: {synced_count}")
        logger.info(f"   - Total contacts in AmoCRM: {stats['total_contacts']}")
        logger.info(f"   - API calls made: {stats['api_calls']}")
        
        logger.info("✅ Created contacts:")
        for contact in stats['contacts']:
            logger.info(f"     * {contact['name']} (ID: {contact['id']})")
        
        logger.info("🎉 Full integration test passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Full integration test failed: {e}")
        return False


def main():
    """Run database integration tests."""
    logger.info("🚀 Starting Database Integration Tests")
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Full Integration", test_full_integration),
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
        logger.info("🎉 All database tests passed! Integration is working correctly.")
        return True
    else:
        logger.error("❌ Some tests failed. Please check the logs above.")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1) 