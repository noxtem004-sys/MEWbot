"""
License Client

Client-side license validation and management.

Security features:
- Secure local cache with HMAC validation
- Device ID generation
- Periodic server validation with grace period
- Clock-skew protection
- Anti-tampering measures
- Replay attack prevention with nonces
"""

import asyncio
import hashlib
import hmac
import json
import logging
import platform
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Callable

import aiohttp

from core.config_manager import app_data_dir
from core.security_utils import (
    security_monitor, rate_limiter, anti_fuzzing,
    perform_security_checks, log_security_event
)

logger = logging.getLogger(__name__)

LICENSE_CACHE_PATH = app_data_dir() / "license_cache.dat"
DEVICE_ID_PATH = app_data_dir() / "device_id.dat"


class LicenseStatus:
    """License validation status"""
    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    BLOCKED = "blocked"
    NOT_ACTIVATED = "not_activated"
    DEVICE_NOT_AUTHORIZED = "device_not_authorized"
    SERVER_UNREACHABLE = "server_unreachable"
    GRACE_PERIOD = "grace_period"


class LicenseClient:
    """
    Client-side license manager.
    
    Handles:
    - License activation
    - Periodic validation
    - Grace period during network outages
    - Secure local caching
    - Device binding
    """
    
    def __init__(
        self,
        server_url: str,
        secret_key: str,
        validation_interval: int = 300,  # 5 minutes
        grace_period: int = 1800  # 30 minutes
    ):
        """
        Initialize license client.
        
        Args:
            server_url: License server base URL (e.g., "http://localhost:8765")
            secret_key: Shared secret for HMAC verification
            validation_interval: Seconds between validation checks
            grace_period: Seconds to allow offline operation
        """
        self.server_url = server_url.rstrip('/')
        self.secret_key = secret_key.encode('utf-8')
        self.validation_interval = validation_interval
        self.grace_period = grace_period
        
        self._device_id: Optional[str] = None
        self._license_key: Optional[str] = None
        self._cache: Dict[str, Any] = {}
        self._last_successful_validation: Optional[int] = None
        self._validation_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Callbacks
        self.on_license_invalid: Optional[Callable[[str, str], None]] = None
        self.on_license_expiring: Optional[Callable[[int], None]] = None
        self.on_grace_period_start: Optional[Callable[], None]] = None
        self.on_grace_period_end: Optional[Callable[], None]] = None
    
    # ==================== DEVICE ID ====================
    
    def _generate_device_id(self) -> str:
        """
        Generate a stable device identifier.
        
        Uses a combination of:
        - Platform info
        - UUID based on hardware
        - Random component for privacy
        
        The ID is saved to disk and reused on subsequent runs.
        """
        # Try to get a hardware-based UUID
        try:
            # This attempts to get a UUID based on hardware address
            hardware_uuid = uuid.getnode()
        except Exception:
            hardware_uuid = 0
        
        # Combine platform info
        platform_info = f"{platform.system()}_{platform.machine()}_{platform.node()}"
        
        # Add a stable random component
        stable_random = hashlib.sha256(
            f"{platform_info}_{hardware_uuid}".encode('utf-8')
        ).hexdigest()[:16]
        
        # Generate device ID
        device_id = f"{platform.system()[:3].upper()}-{stable_random}"
        
        return device_id
    
    def get_device_id(self) -> str:
        """Get or create device ID"""
        if self._device_id:
            return self._device_id
        
        # Try to load from disk
        if DEVICE_ID_PATH.exists():
            try:
                self._device_id = DEVICE_ID_PATH.read_text(encoding='utf-8').strip()
                logger.info(f"Loaded device ID: {self._device_id[:12]}...")
                return self._device_id
            except Exception as e:
                logger.warning(f"Failed to load device ID: {e}")
        
        # Generate new device ID
        self._device_id = self._generate_device_id()
        
        # Save to disk
        try:
            DEVICE_ID_PATH.parent.mkdir(parents=True, exist_ok=True)
            DEVICE_ID_PATH.write_text(self._device_id, encoding='utf-8')
            logger.info(f"Generated new device ID: {self._device_id[:12]}...")
        except Exception as e:
            logger.error(f"Failed to save device ID: {e}")
        
        return self._device_id
    
    # ==================== SECURE CACHE ====================
    
    def _sign_cache(self, data: Dict[str, Any]) -> str:
        """Generate HMAC signature for cache data"""
        payload = json.dumps(data, sort_keys=True)
        signature = hmac.new(
            self.secret_key,
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _verify_cache_signature(self, data: Dict[str, Any], signature: str) -> bool:
        """Verify cache signature"""
        expected_signature = self._sign_cache(data)
        return hmac.compare_digest(expected_signature, signature)
    
    def _load_cache(self) -> bool:
        """Load and verify cached license state"""
        if not LICENSE_CACHE_PATH.exists():
            return False
        
        try:
            cache_data = json.loads(LICENSE_CACHE_PATH.read_text(encoding='utf-8'))
            
            # Verify signature
            signature = cache_data.get('signature', '')
            data = cache_data.get('data', {})
            
            if not self._verify_cache_signature(data, signature):
                logger.warning("Cache signature verification failed - cache may be tampered")
                return False
            
            # Check if cache is stale (older than grace period)
            cached_ts = data.get('cached_at_utc', 0)
            now_ts = int(datetime.now(timezone.utc).timestamp())
            
            if now_ts - cached_ts > self.grace_period:
                logger.warning("Cache is stale (older than grace period)")
                return False
            
            self._cache = data
            self._last_successful_validation = cached_ts
            
            logger.info("Loaded valid license cache")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            return False
    
    def _save_cache(self, license_data: Dict[str, Any]):
        """Save license state to secure cache"""
        try:
            cache_data = {
                'license_key': self._license_key,
                'device_id': self._device_id,
                'status': license_data.get('status', 'valid'),
                'expires_at_utc': license_data.get('expires_at_utc'),
                'plan': license_data.get('plan'),
                'cached_at_utc': int(datetime.now(timezone.utc).timestamp()),
                'server_timestamp_utc': license_data.get('server_timestamp_utc'),
            }
            
            signature = self._sign_cache(cache_data)
            
            cache_file_data = {
                'data': cache_data,
                'signature': signature
            }
            
            LICENSE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            LICENSE_CACHE_PATH.write_text(
                json.dumps(cache_file_data, indent=2),
                encoding='utf-8'
            )
            
            self._cache = cache_data
            
            logger.debug("License cache saved")
            
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def _clear_cache(self):
        """Clear cached license data"""
        self._cache = {}
        self._last_successful_validation = None
        
        try:
            if LICENSE_CACHE_PATH.exists():
                LICENSE_CACHE_PATH.unlink()
                logger.info("License cache cleared")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
    
    # ==================== NONCE GENERATION ====================
    
    def _generate_nonce(self) -> str:
        """Generate a unique nonce for replay attack prevention"""
        timestamp = int(datetime.now(timezone.utc).timestamp())
        random_part = secrets.token_urlsafe(16)
        return f"{timestamp}_{random_part}"
    
    # ==================== API COMMUNICATION ====================
    
    async def _api_request(
        self,
        endpoint: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make an API request to the license server.
        
        Returns:
            Response data dict, or error dict on failure
        """
        url = f"{self.server_url}{endpoint}"
        
        # Add nonce to prevent replay attacks
        data['nonce'] = self._generate_nonce()
        
        # Add client timestamp for clock skew detection
        data['client_timestamp_utc'] = int(datetime.now(timezone.utc).timestamp())
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_data = await response.json()
                    
                    # Log rate limiting
                    if response.status == 429:
                        logger.warning(f"Rate limited: {response_data.get('message')}")
                    
                    return response_data
                    
        except asyncio.TimeoutError:
            logger.error(f"Request timeout: {endpoint}")
            return {
                'success': False,
                'valid': False,
                'error': 'timeout',
                'message': 'Server request timeout'
            }
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            return {
                'success': False,
                'valid': False,
                'error': 'network_error',
                'message': f'Network error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error during API request: {e}")
            return {
                'success': False,
                'valid': False,
                'error': 'unknown_error',
                'message': f'Unexpected error: {str(e)}'
            }
    
    def _verify_response_signature(self, response: Dict[str, Any]) -> bool:
        """
        Verify server response signature.
        
        Prevents client-side response manipulation.
        """
        signature = response.pop('signature', None)
        if not signature:
            logger.warning("Server response missing signature")
            return False
        
        expected_signature = self._sign_cache(response)
        
        # Restore signature for further use
        response['signature'] = signature
        
        if not hmac.compare_digest(expected_signature, signature):
            logger.error("Server response signature verification FAILED")
            return False
        
        return True
    
    # ==================== LICENSE OPERATIONS ====================
    
    async def activate_license(self, license_key: str) -> Dict[str, Any]:
        """
        Activate a license for the first time.
        
        Returns:
            {
                'success': True/False,
                'message': '...',
                'expires_at': '...',
                'expires_at_utc': ...,
                ...
            }
        """
        # Perform security checks
        security_ok, security_issues = perform_security_checks()
        if not security_ok:
            log_security_event(
                "ACTIVATION_BLOCKED",
                f"Security checks failed: {security_issues}",
                "WARNING"
            )
            # Log but don't necessarily block (some checks may be false positives)
        
        # Check client-side rate limiting (prevent brute force)
        allowed, reason = rate_limiter.check_rate_limit(
            action="license_activation",
            max_attempts=5,
            window_seconds=300  # 5 attempts per 5 minutes
        )
        
        if not allowed:
            log_security_event(
                "RATE_LIMIT_ACTIVATION",
                reason or "Rate limit exceeded",
                "WARNING"
            )
            return {
                'success': False,
                'message': 'Too many activation attempts. Please wait before trying again.'
            }
        
        device_id = self.get_device_id()
        device_info = f"{platform.system()} {platform.release()}"
        
        logger.info(f"Activating license for device: {device_id[:12]}...")
        log_security_event("ACTIVATION_ATTEMPT", f"Device: {device_id[:12]}...", "INFO")
        
        response = await self._api_request(
            '/api/license/activate',
            {
                'license_key': license_key,
                'device_id': device_id,
                'device_info': device_info
            }
        )
        
        if response.get('success'):
            # Verify signature
            if not self._verify_response_signature(response):
                log_security_event(
                    "SIGNATURE_VERIFICATION_FAILED",
                    "Activation response signature invalid",
                    "ERROR"
                )
                anti_fuzzing.record_failure("signature_verification")
                return {
                    'success': False,
                    'message': 'Server response signature verification failed'
                }
            
            # Store license key
            self._license_key = license_key
            
            # Save to cache
            self._save_cache(response)
            self._last_successful_validation = int(datetime.now(timezone.utc).timestamp())
            
            logger.info("License activated successfully")
            log_security_event("ACTIVATION_SUCCESS", f"License activated", "INFO")
        else:
            logger.error(f"License activation failed: {response.get('message')}")
            log_security_event(
                "ACTIVATION_FAILED",
                response.get('message', 'Unknown error'),
                "WARNING"
            )
            anti_fuzzing.record_failure("activation")
        
        return response
    
    async def validate_license(self) -> Dict[str, Any]:
        """
        Validate the current license with the server.
        
        Returns:
            {
                'valid': True/False,
                'status': 'valid'|'expired'|'revoked'|etc,
                'message': '...',
                'expires_at_utc': ...,
                'remaining_seconds': ...,
                ...
            }
        """
        if not self._license_key:
            return {
                'valid': False,
                'status': LicenseStatus.NOT_ACTIVATED,
                'message': 'License not activated'
            }
        
        # Check for clock manipulation
        clock_rollback, clock_reason = security_monitor.detect_clock_rollback()
        if clock_rollback:
            log_security_event(
                "CLOCK_MANIPULATION",
                clock_reason or "Clock rollback detected",
                "ERROR"
            )
            # Don't immediately fail, but log the event
        
        device_id = self.get_device_id()
        
        response = await self._api_request(
            '/api/license/validate',
            {
                'license_key': self._license_key,
                'device_id': device_id
            }
        )
        
        # Check if server is reachable
        if response.get('error') in ['timeout', 'network_error']:
            # Server unreachable - check grace period
            return self._handle_offline_validation()
        
        if response.get('valid'):
            # Verify signature
            if not self._verify_response_signature(response):
                logger.error("Validation response signature verification failed")
                log_security_event(
                    "SIGNATURE_VERIFICATION_FAILED",
                    "Validation response signature invalid",
                    "ERROR"
                )
                # Don't trust this response, fall back to cache
                return self._handle_offline_validation()
            
            # Update cache
            response['status'] = 'valid'
            self._save_cache(response)
            self._last_successful_validation = int(datetime.now(timezone.utc).timestamp())
            
            # Check if expiring soon (within 24 hours)
            remaining = response.get('remaining_seconds', 0)
            if remaining > 0 and remaining < 86400:
                if self.on_license_expiring:
                    self.on_license_expiring(remaining)
        else:
            # Invalid license
            self._clear_cache()
            
            # Determine status from message
            message = response.get('message', '').lower()
            if 'expired' in message:
                response['status'] = LicenseStatus.EXPIRED
            elif 'revoked' in message:
                response['status'] = LicenseStatus.REVOKED
            elif 'blocked' in message:
                response['status'] = LicenseStatus.BLOCKED
            elif 'not authorized' in message or 'device' in message:
                response['status'] = LicenseStatus.DEVICE_NOT_AUTHORIZED
            else:
                response['status'] = LicenseStatus.INVALID
            
            log_security_event(
                "VALIDATION_FAILED",
                f"Status: {response['status']}, Message: {response.get('message')}",
                "WARNING"
            )
        
        return response
    
    def _handle_offline_validation(self) -> Dict[str, Any]:
        """
        Handle validation when server is unreachable.
        
        Uses cached license state with grace period.
        """
        now_ts = int(datetime.now(timezone.utc).timestamp())
        
        # Check if we have a valid cache
        if not self._cache or not self._last_successful_validation:
            return {
                'valid': False,
                'status': LicenseStatus.SERVER_UNREACHABLE,
                'message': 'License server unreachable and no valid cache available'
            }
        
        # Check grace period
        time_since_last_validation = now_ts - self._last_successful_validation
        
        if time_since_last_validation > self.grace_period:
            # Grace period expired
            if self.on_grace_period_end:
                self.on_grace_period_end()
            
            return {
                'valid': False,
                'status': LicenseStatus.SERVER_UNREACHABLE,
                'message': f'License server unreachable for {time_since_last_validation}s (grace period: {self.grace_period}s)'
            }
        
        # Within grace period - use cached license
        if self.on_grace_period_start:
            self.on_grace_period_start()
        
        logger.warning(
            f"Using cached license (server unreachable, "
            f"grace period: {self.grace_period - time_since_last_validation}s remaining)"
        )
        
        # Check if cached license is expired
        expires_at_utc = self._cache.get('expires_at_utc', 0)
        if expires_at_utc and now_ts > expires_at_utc:
            return {
                'valid': False,
                'status': LicenseStatus.EXPIRED,
                'message': 'License expired (cached)'
            }
        
        return {
            'valid': True,
            'status': LicenseStatus.GRACE_PERIOD,
            'message': 'License valid (cached, server unreachable)',
            'expires_at_utc': expires_at_utc,
            'remaining_seconds': max(0, expires_at_utc - now_ts) if expires_at_utc else 0,
            'grace_period_remaining': self.grace_period - time_since_last_validation
        }
    
    async def deactivate_license(self) -> Dict[str, Any]:
        """
        Deactivate the license on this device.
        
        Returns:
            {'success': True/False, 'message': '...'}
        """
        if not self._license_key:
            return {
                'success': False,
                'message': 'No active license to deactivate'
            }
        
        device_id = self.get_device_id()
        
        response = await self._api_request(
            '/api/license/deactivate',
            {
                'license_key': self._license_key,
                'device_id': device_id
            }
        )
        
        if response.get('success'):
            self._clear_cache()
            self._license_key = None
            logger.info("License deactivated successfully")
        
        return response
    
    async def heartbeat(self) -> bool:
        """
        Send a lightweight heartbeat to update last_seen.
        
        Returns True if successful, False otherwise.
        """
        if not self._license_key:
            return False
        
        device_id = self.get_device_id()
        
        response = await self._api_request(
            '/api/license/heartbeat',
            {
                'license_key': self._license_key,
                'device_id': device_id
            }
        )
        
        return response.get('success', False)
    
    # ==================== PERIODIC VALIDATION ====================
    
    async def start_periodic_validation(self):
        """Start periodic license validation loop"""
        if self._running:
            logger.warning("Periodic validation already running")
            return
        
        self._running = True
        self._validation_task = asyncio.create_task(self._validation_loop())
        logger.info(f"Started periodic validation (interval: {self.validation_interval}s)")
    
    async def stop_periodic_validation(self):
        """Stop periodic license validation"""
        if not self._running:
            return
        
        self._running = False
        
        if self._validation_task:
            self._validation_task.cancel()
            try:
                await self._validation_task
            except asyncio.CancelledError:
                pass
            self._validation_task = None
        
        logger.info("Stopped periodic validation")
    
    async def _validation_loop(self):
        """Background task for periodic validation"""
        try:
            while self._running:
                try:
                    result = await self.validate_license()
                    
                    if not result.get('valid'):
                        # License is invalid
                        status = result.get('status', LicenseStatus.INVALID)
                        message = result.get('message', 'License validation failed')
                        
                        logger.error(f"License validation failed: {status} - {message}")
                        
                        if self.on_license_invalid and status != LicenseStatus.SERVER_UNREACHABLE:
                            self.on_license_invalid(status, message)
                    
                except Exception as e:
                    logger.error(f"Error during periodic validation: {e}")
                
                # Wait for next validation
                await asyncio.sleep(self.validation_interval)
                
        except asyncio.CancelledError:
            logger.debug("Validation loop cancelled")
            raise
    
    # ==================== CONVENIENCE METHODS ====================
    
    async def check_license_status(self) -> str:
        """
        Quick check of current license status without full validation.
        
        Returns status string: 'valid', 'expired', 'invalid', etc.
        """
        if not self._license_key:
            return LicenseStatus.NOT_ACTIVATED
        
        # Try to use cache first
        if self._cache:
            expires_at_utc = self._cache.get('expires_at_utc', 0)
            now_ts = int(datetime.now(timezone.utc).timestamp())
            
            if expires_at_utc and now_ts > expires_at_utc:
                return LicenseStatus.EXPIRED
            
            return LicenseStatus.VALID
        
        # No cache, perform validation
        result = await self.validate_license()
        return result.get('status', LicenseStatus.INVALID)
    
    def get_cached_license_info(self) -> Optional[Dict[str, Any]]:
        """Get cached license information"""
        return self._cache.copy() if self._cache else None
    
    def is_license_active(self) -> bool:
        """Check if license is currently active (based on cache)"""
        if not self._cache:
            return False
        
        expires_at_utc = self._cache.get('expires_at_utc', 0)
        if not expires_at_utc:
            return False
        
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return now_ts < expires_at_utc
    
    def get_time_remaining(self) -> int:
        """Get remaining time in seconds (based on cache), or 0 if expired"""
        if not self._cache:
            return 0
        
        expires_at_utc = self._cache.get('expires_at_utc', 0)
        if not expires_at_utc:
            return 0
        
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return max(0, expires_at_utc - now_ts)
    
    # ==================== INITIALIZATION ====================
    
    async def initialize(self) -> bool:
        """
        Initialize the license client.
        
        Loads cached license and performs initial validation if available.
        
        Returns True if a valid license is available, False otherwise.
        """
        # Load device ID
        self.get_device_id()
        
        # Try to load cached license
        if self._load_cache():
            cached_key = self._cache.get('license_key')
            if cached_key:
                self._license_key = cached_key
                logger.info("Loaded license from cache")
                
                # Perform initial validation
                result = await self.validate_license()
                return result.get('valid', False)
        
        logger.info("No valid cached license found")
        return False


# ==================== TESTING UTILITY ====================

async def test_license_client():
    """Test the license client"""
    import os
    
    logging.basicConfig(level=logging.INFO)
    
    server_url = os.environ.get('LICENSE_SERVER_URL', 'http://localhost:8765')
    secret_key = os.environ.get('LICENSE_SERVER_SECRET_KEY', 'test_secret_key')
    
    client = LicenseClient(
        server_url=server_url,
        secret_key=secret_key,
        validation_interval=10,  # 10 seconds for testing
        grace_period=60  # 1 minute for testing
    )
    
    # Set up callbacks
    def on_invalid(status, message):
        logger.error(f"LICENSE INVALID: {status} - {message}")
    
    def on_expiring(remaining):
        logger.warning(f"LICENSE EXPIRING: {remaining}s remaining")
    
    client.on_license_invalid = on_invalid
    client.on_license_expiring = on_expiring
    
    # Initialize
    await client.initialize()
    
    # Get device ID
    logger.info(f"Device ID: {client.get_device_id()}")
    
    # Try to activate (you'll need a valid license key)
    license_key = input("Enter license key (or press Enter to skip): ").strip()
    
    if license_key:
        result = await client.activate_license(license_key)
        logger.info(f"Activation result: {result}")
    
    # Check status
    status = await client.check_license_status()
    logger.info(f"License status: {status}")
    
    if client.is_license_active():
        remaining = client.get_time_remaining()
        logger.info(f"Time remaining: {remaining}s")
        
        # Start periodic validation
        await client.start_periodic_validation()
        
        # Wait a bit
        await asyncio.sleep(30)
        
        # Stop
        await client.stop_periodic_validation()


if __name__ == '__main__':
    asyncio.run(test_license_client())
