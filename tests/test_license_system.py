"""
Comprehensive License System Test Suite

Tests cover:
- License lifecycle (create, activate, validate, extend, revoke)
- Security features (tampering, clock manipulation, rate limiting)
- Edge cases and error handling
- Database integrity
- API endpoints

Run with: python tests/test_license_system.py
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import modules to test
from backend.license_database import LicenseDatabase, LicenseStatus
from backend.license_server import LicenseServer
from core.license_client import LicenseClient
from core.security_utils import (
    security_monitor, rate_limiter,
    validate_license_key_format, sanitize_input
)


class TestResults:
    """Track test results"""
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def record_pass(self, test_name: str):
        self.total += 1
        self.passed += 1
        logger.info(f"✅ PASS: {test_name}")
    
    def record_fail(self, test_name: str, reason: str):
        self.total += 1
        self.failed += 1
        self.errors.append((test_name, reason))
        logger.error(f"❌ FAIL: {test_name} - {reason}")
    
    def summary(self):
        logger.info("\n" + "="*60)
        logger.info("TEST SUMMARY")
        logger.info("="*60)
        logger.info(f"Total Tests: {self.total}")
        logger.info(f"Passed: {self.passed}")
        logger.info(f"Failed: {self.failed}")
        
        if self.errors:
            logger.error("\nFailed Tests:")
            for test_name, reason in self.errors:
                logger.error(f"  - {test_name}: {reason}")
        
        logger.info("="*60)
        
        return self.failed == 0


results = TestResults()


def test(name: str):
    """Decorator for test functions"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                await func(*args, **kwargs)
                results.record_pass(name)
            except AssertionError as e:
                results.record_fail(name, str(e))
            except Exception as e:
                results.record_fail(name, f"Exception: {str(e)}")
        return wrapper
    return decorator


class LicenseSystemTests:
    """Comprehensive test suite for license system"""
    
    def __init__(self):
        self.db = LicenseDatabase(db_path=":memory:")  # In-memory database for testing
        self.server = LicenseServer(secret_key="test_secret_key_12345", host="127.0.0.1", port=18765)
        self.server.db = self.db  # Use our test database
        self.client = None
        self.test_license_key = None
        self.test_license_id = None
    
    async def setup(self):
        """Setup test environment"""
        await self.db.init_db()
        await self.server.start()
        
        # Create a test client
        self.client = LicenseClient(
            server_url="http://127.0.0.1:18765",
            secret_key="test_secret_key_12345",
            validation_interval=5,
            grace_period=30
        )
        
        logger.info("Test environment setup complete")
    
    async def teardown(self):
        """Cleanup test environment"""
        if self.server:
            await self.server.stop()
        
        logger.info("Test environment cleaned up")
    
    # ==================== DATABASE TESTS ====================
    
    @test("Database Initialization")
    async def test_database_init(self):
        """Test database tables are created correctly"""
        # Database should be initialized in setup
        assert self.db.db_path == ":memory:"
        logger.info("Database initialized successfully")
    
    @test("Create License")
    async def test_create_license(self):
        """Test license creation"""
        key = self.server.generate_license_key()
        self.test_license_key = key
        
        license_id = await self.db.create_license(
            key=key,
            plan="Test Plan",
            duration_seconds=86400,  # 1 day
            max_devices=1
        )
        
        self.test_license_id = license_id
        
        assert license_id > 0, "License ID should be positive"
        
        # Verify license was created
        license_data = await self.db.get_license_by_id(license_id)
        assert license_data is not None, "License should exist"
        assert license_data['status'] == LicenseStatus.PENDING.value, "New license should be PENDING"
        assert license_data['plan'] == "Test Plan"
        assert license_data['duration_seconds'] == 86400
    
    @test("License Key Hash")
    async def test_license_key_hash(self):
        """Test license key is stored as hash"""
        license_data = await self.db.get_license_by_id(self.test_license_id)
        
        # Key should be hashed
        expected_hash = self.db.hash_license_key(self.test_license_key)
        assert license_data['key_hash'] == expected_hash, "Key should be stored as hash"
        
        # Should not be plaintext
        assert license_data['key_hash'] != self.test_license_key, "Key should not be stored as plaintext"
    
    @test("Activate License - First Time")
    async def test_activate_license_first_time(self):
        """Test first-time license activation"""
        device_id = "TEST_DEVICE_001"
        
        result = await self.db.activate_license(
            key=self.test_license_key,
            device_id=device_id,
            device_info="Test Device"
        )
        
        assert result['success'], f"Activation should succeed: {result.get('message')}"
        assert 'expires_at' in result, "Should return expiration time"
        assert 'expires_at_utc' in result, "Should return expiration timestamp"
        
        # Verify license status changed to ACTIVE
        license_data = await self.db.get_license_by_id(self.test_license_id)
        assert license_data['status'] == LicenseStatus.ACTIVE.value, "License should be ACTIVE"
        assert license_data['activated_at'] is not None, "Should have activation timestamp"
        assert license_data['expires_at'] is not None, "Should have expiration timestamp"
    
    @test("Activate License - Already Activated")
    async def test_activate_license_already_activated(self):
        """Test activating an already-activated license on same device"""
        device_id = "TEST_DEVICE_001"
        
        result = await self.db.activate_license(
            key=self.test_license_key,
            device_id=device_id,
            device_info="Test Device"
        )
        
        assert result['success'], "Should succeed for same device"
        assert "already activated" in result['message'].lower()
    
    @test("Activate License - Device Limit")
    async def test_activate_license_device_limit(self):
        """Test device limit enforcement"""
        device_id_2 = "TEST_DEVICE_002"
        
        result = await self.db.activate_license(
            key=self.test_license_key,
            device_id=device_id_2,
            device_info="Test Device 2"
        )
        
        assert not result['success'], "Should fail when device limit reached"
        assert "limit" in result['message'].lower()
    
    @test("Validate License - Valid")
    async def test_validate_license_valid(self):
        """Test validating a valid license"""
        device_id = "TEST_DEVICE_001"
        
        result = await self.db.validate_license(
            key=self.test_license_key,
            device_id=device_id
        )
        
        assert result['valid'], f"License should be valid: {result.get('message')}"
        assert result['remaining_seconds'] > 0, "Should have time remaining"
    
    @test("Extend License")
    async def test_extend_license(self):
        """Test extending license duration"""
        # Get current expiration
        license_data = await self.db.get_license_by_id(self.test_license_id)
        original_expires_at = license_data['expires_at_utc']
        
        # Extend by 1 day
        result = await self.db.extend_license(
            license_id=self.test_license_id,
            additional_seconds=86400
        )
        
        assert result['success'], "Extension should succeed"
        
        # Verify new expiration
        license_data = await self.db.get_license_by_id(self.test_license_id)
        new_expires_at = license_data['expires_at_utc']
        
        assert new_expires_at > original_expires_at, "Expiration should be extended"
        assert new_expires_at == original_expires_at + 86400, "Should extend by exactly 1 day"
    
    @test("Block License")
    async def test_block_license(self):
        """Test blocking a license"""
        result = await self.db.block_license(
            license_id=self.test_license_id
        )
        
        assert result['success'], "Block should succeed"
        
        # Verify status
        license_data = await self.db.get_license_by_id(self.test_license_id)
        assert license_data['status'] == LicenseStatus.BLOCKED.value, "License should be BLOCKED"
        
        # Validation should fail
        validate_result = await self.db.validate_license(
            key=self.test_license_key,
            device_id="TEST_DEVICE_001"
        )
        assert not validate_result['valid'], "Blocked license should not validate"
    
    @test("Unblock License")
    async def test_unblock_license(self):
        """Test unblocking a license"""
        result = await self.db.unblock_license(
            license_id=self.test_license_id
        )
        
        assert result['success'], "Unblock should succeed"
        
        # Verify status
        license_data = await self.db.get_license_by_id(self.test_license_id)
        assert license_data['status'] == LicenseStatus.ACTIVE.value, "License should be ACTIVE again"
    
    @test("Revoke License")
    async def test_revoke_license(self):
        """Test revoking a license"""
        result = await self.db.revoke_license(
            license_id=self.test_license_id
        )
        
        assert result['success'], "Revoke should succeed"
        
        # Verify status
        license_data = await self.db.get_license_by_id(self.test_license_id)
        assert license_data['status'] == LicenseStatus.REVOKED.value, "License should be REVOKED"
        
        # Validation should fail
        validate_result = await self.db.validate_license(
            key=self.test_license_key,
            device_id="TEST_DEVICE_001"
        )
        assert not validate_result['valid'], "Revoked license should not validate"
    
    @test("Reset Device")
    async def test_reset_device(self):
        """Test resetting device binding"""
        # Create a new license for this test
        new_key = self.server.generate_license_key()
        license_id = await self.db.create_license(
            key=new_key,
            plan="Device Reset Test",
            duration_seconds=86400,
            max_devices=1
        )
        
        # Activate on device
        await self.db.activate_license(
            key=new_key,
            device_id="DEVICE_RESET_TEST",
            device_info="Test"
        )
        
        # Reset device
        result = await self.db.reset_device(
            license_id=license_id,
            device_id="DEVICE_RESET_TEST"
        )
        
        assert result['success'], "Device reset should succeed"
        
        # Should be able to activate on a new device now
        activate_result = await self.db.activate_license(
            key=new_key,
            device_id="NEW_DEVICE",
            device_info="New Device"
        )
        assert activate_result['success'], "Should activate on new device after reset"
    
    # ==================== SERVER API TESTS ====================
    
    @test("Server Health Check")
    async def test_server_health(self):
        """Test server health endpoint"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:18765/health") as resp:
                assert resp.status == 200, "Health check should return 200"
                data = await resp.json()
                assert data['status'] == 'healthy', "Should report healthy status"
    
    @test("Server Time Endpoint")
    async def test_server_time(self):
        """Test server time endpoint"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:18765/api/server/time") as resp:
                assert resp.status == 200, "Should return 200"
                data = await resp.json()
                assert 'timestamp_utc' in data, "Should include timestamp"
                assert 'iso' in data, "Should include ISO format"
    
    @test("API Activation - Valid Key")
    async def test_api_activation_valid(self):
        """Test API activation with valid key"""
        # Create a new license for API testing
        api_test_key = self.server.generate_license_key()
        await self.db.create_license(
            key=api_test_key,
            plan="API Test",
            duration_seconds=3600,
            max_devices=1
        )
        
        result = await self.client.activate_license(api_test_key)
        
        assert result.get('success'), f"API activation should succeed: {result.get('message')}"
        assert 'expires_at' in result, "Should return expiration"
        assert 'signature' in result, "Should include signature"
    
    @test("API Activation - Invalid Key")
    async def test_api_activation_invalid(self):
        """Test API activation with invalid key"""
        result = await self.client.activate_license("INVALID-KEY-1234-5678")
        
        assert not result.get('success'), "Should fail with invalid key"
    
    @test("API Validation")
    async def test_api_validation(self):
        """Test API validation endpoint"""
        # Use previously activated license
        result = await self.client.validate_license()
        
        # May succeed or fail depending on state, just verify structure
        assert 'valid' in result, "Should return validation status"
        assert 'status' in result, "Should return status"
    
    # ==================== SECURITY TESTS ====================
    
    @test("License Key Format Validation")
    async def test_license_key_format(self):
        """Test license key format validation"""
        assert validate_license_key_format("ABCD-1234-EFGH-5678"), "Valid format should pass"
        assert validate_license_key_format("ABCD12

34EFGH5678"), "Format without dashes should pass"
        assert not validate_license_key_format("SHORT"), "Too short should fail"
        assert not validate_license_key_format("ABCD-1234-EFGH-567"), "15 chars should fail"
        assert not validate_license_key_format("ABCD-1234-EFGH-56789"), "17 chars should fail"
    
    @test("Input Sanitization")
    async def test_input_sanitization(self):
        """Test input sanitization"""
        # Test control character removal
        dirty = "Hello\x00World\x01Test"
        clean = sanitize_input(dirty)
        assert '\x00' not in clean, "Should remove null bytes"
        assert '\x01' not in clean, "Should remove control chars"
        
        # Test length limiting
        long_input = "A" * 2000
        clean = sanitize_input(long_input, max_length=100)
        assert len(clean) <= 100, "Should truncate to max length"
    
    @test("Rate Limiting - Client Side")
    async def test_rate_limiting_client(self):
        """Test client-side rate limiting"""
        action = "test_action"
        
        # First 5 attempts should succeed
        for i in range(5):
            allowed, _ = rate_limiter.check_rate_limit(action, max_attempts=5, window_seconds=10)
            assert allowed, f"Attempt {i+1} should be allowed"
        
        # 6th attempt should fail
        allowed, reason = rate_limiter.check_rate_limit(action, max_attempts=5, window_seconds=10)
        assert not allowed, "Should be rate limited"
        assert reason is not None, "Should provide reason"
    
    @test("HMAC Signature Verification")
    async def test_hmac_signature(self):
        """Test HMAC signature generation and verification"""
        test_data = {"test": "data", "number": 123}
        
        # Generate signature
        signature = self.server.sign_response(test_data)
        assert signature, "Should generate signature"
        assert len(signature) == 64, "SHA256 hex should be 64 chars"
        
        # Modify data
        test_data['number'] = 456
        new_signature = self.server.sign_response(test_data)
        
        assert signature != new_signature, "Signature should change with data"
    
    @test("Clock Manipulation Detection")
    async def test_clock_detection(self):
        """Test clock manipulation detection"""
        # First check establishes baseline
        detected, reason = security_monitor.detect_clock_rollback()
        assert not detected, "First check should not detect rollback"
        
        # Simulate time passing normally
        await asyncio.sleep(0.1)
        detected, reason = security_monitor.detect_clock_rollback()
        assert not detected, "Normal time progression should be fine"
    
    # ==================== EDGE CASES ====================
    
    @test("Concurrent Activation")
    async def test_concurrent_activation(self):
        """Test concurrent activation attempts (race condition)"""
        # Create a new license
        concurrent_key = self.server.generate_license_key()
        await self.db.create_license(
            key=concurrent_key,
            plan="Concurrent Test",
            duration_seconds=3600,
            max_devices=1
        )
        
        # Attempt to activate from two devices simultaneously
        async def activate_device(device_id):
            return await self.db.activate_license(
                key=concurrent_key,
                device_id=device_id,
                device_info=f"Device {device_id}"
            )
        
        results = await asyncio.gather(
            activate_device("CONCURRENT_1"),
            activate_device("CONCURRENT_2"),
            return_exceptions=True
        )
        
        # One should succeed, one should fail
        successes = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
        assert successes == 1, f"Exactly one activation should succeed (got {successes})"
    
    @test("Expired License Validation")
    async def test_expired_license(self):
        """Test validation of expired license"""
        # Create a license that's already expired
        expired_key = self.server.generate_license_key()
        license_id = await self.db.create_license(
            key=expired_key,
            plan="Expired Test",
            duration_seconds=1,  # 1 second
            max_devices=1
        )
        
        # Activate it
        await self.db.activate_license(
            key=expired_key,
            device_id="EXPIRED_TEST",
            device_info="Test"
        )
        
        # Wait for expiration
        await asyncio.sleep(2)
        
        # Validate should fail
        result = await self.db.validate_license(
            key=expired_key,
            device_id="EXPIRED_TEST"
        )
        
        assert not result['valid'], "Expired license should not validate"
    
    @test("Search Licenses")
    async def test_search_licenses(self):
        """Test license search functionality"""
        # Search all licenses
        licenses = await self.db.search_licenses(limit=100)
        assert len(licenses) > 0, "Should find licenses"
        
        # Search by status
        active_licenses = await self.db.search_licenses(status=LicenseStatus.ACTIVE.value, limit=100)
        for lic in active_licenses:
            assert lic['status'] == LicenseStatus.ACTIVE.value, "Should only return ACTIVE licenses"
        
        # Search by specific license
        specific = await self.db.search_licenses(license_id=self.test_license_id, limit=1)
        assert len(specific) == 1, "Should find specific license"
        assert specific[0]['id'] == self.test_license_id, "Should return correct license"
    
    @test("Statistics")
    async def test_statistics(self):
        """Test statistics gathering"""
        stats = await self.db.get_statistics()
        
        assert 'total_licenses' in stats, "Should include total count"
        assert 'by_status' in stats, "Should include status breakdown"
        assert 'active_devices' in stats, "Should include device count"
        assert stats['total_licenses'] > 0, "Should have licenses"
    
    @test("Audit Log")
    async def test_audit_log(self):
        """Test audit logging"""
        # Log an action
        await self.db.log_action(
            action="TEST_ACTION",
            license_id=self.test_license_id,
            device_id="TEST_DEVICE",
            details="Test audit log entry"
        )
        
        # Retrieve logs
        logs = await self.db.get_audit_logs(license_id=self.test_license_id, limit=10)
        
        assert len(logs) > 0, "Should have audit logs"
        
        # Check if our test action is there
        test_log = next((log for log in logs if log['action'] == 'TEST_ACTION'), None)
        assert test_log is not None, "Should find test action in logs"
        assert test_log['details'] == "Test audit log entry"


async def run_all_tests():
    """Run all tests"""
    logger.info("="*60)
    logger.info("LICENSE SYSTEM COMPREHENSIVE TEST SUITE")
    logger.info("="*60)
    
    tests = LicenseSystemTests()
    
    try:
        # Setup
        logger.info("\n[Setup] Initializing test environment...")
        await tests.setup()
        
        # Run all test methods
        logger.info("\n[Tests] Running test suite...\n")
        
        # Database tests
        await tests.test_database_init()
        await tests.test_create_license()
        await tests.test_license_key_hash()
        await tests.test_activate_license_first_time()
        await tests.test_activate_license_already_activated()
        await tests.test_activate_license_device_limit()
        await tests.test_validate_license_valid()
        await tests.test_extend_license()
        await tests.test_block_license()
        await tests.test_unblock_license()
        await tests.test_revoke_license()
        await tests.test_reset_device()
        
        # Server API tests
        await tests.test_server_health()
        await tests.test_server_time()
        await tests.test_api_activation_valid()
        await tests.test_api_activation_invalid()
        await tests.test_api_validation()
        
        # Security tests
        await tests.test_license_key_format()
        await tests.test_input_sanitization()
        await tests.test_rate_limiting_client()
        await tests.test_hmac_signature()
        await tests.test_clock_detection()
        
        # Edge cases
        await tests.test_concurrent_activation()
        await tests.test_expired_license()
        await tests.test_search_licenses()
        await tests.test_statistics()
        await tests.test_audit_log()
        
    finally:
        # Teardown
        logger.info("\n[Teardown] Cleaning up test environment...")
        await tests.teardown()
    
    # Print summary
    success = results.summary()
    
    return success


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
