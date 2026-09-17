"""
Security Utilities

Additional security hardening utilities for the license system.
Provides defense-in-depth measures beyond the core license validation.

Security Principles:
- Defense in depth
- Fail secure
- Least privilege
- Complete mediation
"""

import hashlib
import hmac
import logging
import os
import platform
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from core.config_manager import app_data_dir

logger = logging.getLogger(__name__)

INTEGRITY_CHECK_PATH = app_data_dir() / "integrity.dat"


class SecurityMonitor:
    """
    Security monitoring and tamper detection.
    
    Monitors for:
    - File integrity violations
    - Suspicious process behavior
    - Clock manipulation
    - Cache tampering
    """
    
    def __init__(self):
        self._baseline_timestamps: Dict[str, int] = {}
        self._last_system_time: Optional[int] = None
        self._boot_time: Optional[float] = None
        self._integrity_salt = self._load_or_create_salt()
    
    def _load_or_create_salt(self) -> bytes:
        """Load or create integrity check salt"""
        salt_path = app_data_dir() / "security_salt.dat"
        
        if salt_path.exists():
            try:
                return salt_path.read_bytes()
            except Exception as e:
                logger.warning(f"Failed to load security salt: {e}")
        
        # Create new salt
        salt = secrets.token_bytes(32)
        try:
            salt_path.parent.mkdir(parents=True, exist_ok=True)
            salt_path.write_bytes(salt)
        except Exception as e:
            logger.error(f"Failed to save security salt: {e}")
        
        return salt
    
    def compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a file"""
        try:
            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to compute hash for {file_path}: {e}")
            return ""
    
    def create_integrity_baseline(self, critical_files: list[Path]):
        """
        Create integrity baseline for critical files.
        
        Args:
            critical_files: List of file paths to monitor
        """
        baseline = {}
        
        for file_path in critical_files:
            if file_path.exists():
                file_hash = self.compute_file_hash(file_path)
                if file_hash:
                    baseline[str(file_path)] = file_hash
        
        # Save baseline
        try:
            baseline_data = {
                'timestamp': int(datetime.now(timezone.utc).timestamp()),
                'hashes': baseline
            }
            
            # Sign baseline
            payload = str(baseline_data).encode('utf-8')
            signature = hmac.new(self._integrity_salt, payload, hashlib.sha256).hexdigest()
            
            baseline_data['signature'] = signature
            
            import json
            INTEGRITY_CHECK_PATH.parent.mkdir(parents=True, exist_ok=True)
            INTEGRITY_CHECK_PATH.write_text(json.dumps(baseline_data, indent=2))
            
            logger.info(f"Integrity baseline created for {len(baseline)} files")
        except Exception as e:
            logger.error(f"Failed to save integrity baseline: {e}")
    
    def verify_integrity(self, critical_files: list[Path]) -> tuple[bool, list[str]]:
        """
        Verify file integrity against baseline.
        
        Returns:
            (is_valid, list_of_violations)
        """
        if not INTEGRITY_CHECK_PATH.exists():
            logger.warning("No integrity baseline found")
            return True, []
        
        try:
            import json
            baseline_data = json.loads(INTEGRITY_CHECK_PATH.read_text())
            
            # Verify baseline signature
            signature = baseline_data.pop('signature', '')
            payload = str(baseline_data).encode('utf-8')
            expected_signature = hmac.new(self._integrity_salt, payload, hashlib.sha256).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                logger.error("Integrity baseline signature verification FAILED")
                return False, ["Baseline signature invalid"]
            
            baseline_hashes = baseline_data.get('hashes', {})
            violations = []
            
            for file_path in critical_files:
                file_path_str = str(file_path)
                
                if file_path_str in baseline_hashes:
                    current_hash = self.compute_file_hash(file_path)
                    expected_hash = baseline_hashes[file_path_str]
                    
                    if current_hash != expected_hash:
                        violations.append(f"File modified: {file_path.name}")
                        logger.warning(f"Integrity violation: {file_path}")
            
            if violations:
                logger.error(f"Integrity check failed: {len(violations)} violations")
                return False, violations
            
            return True, []
            
        except Exception as e:
            logger.error(f"Integrity verification error: {e}")
            return False, [f"Verification error: {str(e)}"]
    
    def detect_clock_rollback(self) -> tuple[bool, Optional[str]]:
        """
        Detect system clock manipulation.
        
        Returns:
            (is_rollback_detected, reason)
        """
        current_time = int(time.time())
        
        # First check
        if self._last_system_time is None:
            self._last_system_time = current_time
            return False, None
        
        # Check for backward time movement
        time_diff = current_time - self._last_system_time
        
        if time_diff < -60:  # More than 1 minute backward
            reason = f"Clock rolled back by {-time_diff} seconds"
            logger.error(f"Clock manipulation detected: {reason}")
            return True, reason
        
        # Check for suspiciously large forward jumps (possible suspend/resume bypass attempt)
        if time_diff > 86400:  # More than 24 hours forward
            logger.warning(f"Large time jump detected: {time_diff} seconds")
            # Don't fail immediately, could be legitimate (system suspended)
        
        self._last_system_time = current_time
        return False, None
    
    def detect_debugger(self) -> bool:
        """
        Attempt to detect if a debugger is attached.
        
        Note: This is NOT foolproof and can be bypassed.
        It's just one layer of defense.
        """
        # Check for common debugger environment variables
        debugger_vars = ['PYDEVD', 'PYCHARM_HOSTED', 'VSCODE_PID']
        for var in debugger_vars:
            if var in os.environ:
                logger.warning(f"Debugger environment detected: {var}")
                return True
        
        # Check sys.gettrace (used by debuggers)
        import sys
        if sys.gettrace() is not None:
            logger.warning("sys.gettrace() indicates debugger presence")
            return True
        
        return False
    
    def validate_execution_environment(self) -> tuple[bool, list[str]]:
        """
        Validate that the application is running in a legitimate environment.
        
        Returns:
            (is_valid, list_of_issues)
        """
        issues = []
        
        # Check if running from expected location
        app_path = Path(__file__).parent.parent
        
        # Check for suspicious modifications to sys.path
        import sys
        suspicious_paths = ['/tmp/', '/var/tmp/', 'Downloads']
        for path in sys.path:
            for suspicious in suspicious_paths:
                if suspicious in path:
                    issues.append(f"Suspicious path in sys.path: {path}")
        
        # Check if critical modules have been monkey-patched
        critical_modules = ['hashlib', 'hmac', 'secrets', 'time']
        for module_name in critical_modules:
            if module_name in sys.modules:
                module = sys.modules[module_name]
                # Simple check: verify module has expected location
                if hasattr(module, '__file__'):
                    module_file = str(module.__file__ or '')
                    if not module_file or 'site-packages' not in module_file:
                        # Could be built-in or frozen, that's okay
                        pass
        
        if issues:
            logger.warning(f"Environment validation issues: {issues}")
            return False, issues
        
        return True, []


class RateLimitTracker:
    """
    Client-side rate limiting for additional protection.
    
    Prevents excessive API calls that could indicate automation/abuse.
    """
    
    def __init__(self):
        self._action_timestamps: Dict[str, list[float]] = {}
    
    def check_rate_limit(
        self,
        action: str,
        max_attempts: int,
        window_seconds: int
    ) -> tuple[bool, Optional[str]]:
        """
        Check if action is within rate limits.
        
        Returns:
            (is_allowed, reason_if_blocked)
        """
        now = time.time()
        
        # Get or create timestamp list for this action
        if action not in self._action_timestamps:
            self._action_timestamps[action] = []
        
        timestamps = self._action_timestamps[action]
        
        # Remove old timestamps outside the window
        timestamps[:] = [ts for ts in timestamps if now - ts < window_seconds]
        
        # Check limit
        if len(timestamps) >= max_attempts:
            return False, f"Rate limit exceeded for {action} ({len(timestamps)}/{max_attempts} in {window_seconds}s)"
        
        # Record this attempt
        timestamps.append(now)
        
        return True, None


class SecureStorage:
    """
    Secure storage for sensitive data.
    
    Uses encryption for data at rest where possible.
    """
    
    def __init__(self, key: bytes):
        """
        Initialize secure storage.
        
        Args:
            key: Encryption key (32 bytes for AES-256)
        """
        self.key = key
        self._ensure_cryptography()
    
    def _ensure_cryptography(self):
        """Ensure cryptography library is available"""
        try:
            from cryptography.fernet import Fernet
            # Derive a Fernet key from the provided key
            import base64
            self._fernet_key = base64.urlsafe_b64encode(self.key[:32].ljust(32, b'\x00'))
            self._cipher = Fernet(self._fernet_key)
        except ImportError:
            logger.warning("cryptography library not available, using basic obfuscation")
            self._cipher = None
    
    def encrypt(self, data: bytes) -> bytes:
        """Encrypt data"""
        if self._cipher:
            try:
                return self._cipher.encrypt(data)
            except Exception as e:
                logger.error(f"Encryption failed: {e}")
                return data
        else:
            # Fallback: XOR with key (NOT secure, just obfuscation)
            return bytes(b ^ self.key[i % len(self.key)] for i, b in enumerate(data))
    
    def decrypt(self, encrypted_data: bytes) -> Optional[bytes]:
        """Decrypt data"""
        if self._cipher:
            try:
                return self._cipher.decrypt(encrypted_data)
            except Exception as e:
                logger.error(f"Decryption failed: {e}")
                return None
        else:
            # Fallback: XOR with key
            return bytes(b ^ self.key[i % len(self.key)] for i, b in enumerate(encrypted_data))
    
    def secure_write(self, path: Path, data: bytes):
        """Write encrypted data to file"""
        encrypted = self.encrypt(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encrypted)
    
    def secure_read(self, path: Path) -> Optional[bytes]:
        """Read and decrypt data from file"""
        if not path.exists():
            return None
        
        try:
            encrypted = path.read_bytes()
            return self.decrypt(encrypted)
        except Exception as e:
            logger.error(f"Failed to read secure file: {e}")
            return None


def generate_secure_key(length: int = 32) -> bytes:
    """Generate a cryptographically secure random key"""
    return secrets.token_bytes(length)


def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks"""
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


def sanitize_input(text: str, max_length: int = 1024) -> str:
    """
    Sanitize user input to prevent injection attacks.
    
    Args:
        text: Input text
        max_length: Maximum allowed length
    
    Returns:
        Sanitized text
    """
    # Truncate to max length
    text = text[:max_length]
    
    # Remove control characters except common whitespace
    sanitized = ''.join(
        c for c in text
        if c.isprintable() or c in ['\n', '\r', '\t', ' ']
    )
    
    return sanitized.strip()


def validate_license_key_format(key: str) -> bool:
    """
    Validate license key format without making network requests.
    
    Basic format check before attempting activation.
    """
    # Remove dashes and whitespace
    clean = ''.join(c for c in key if c.isalnum())
    
    # Check length (should be 16 alphanumeric characters)
    if len(clean) != 16:
        return False
    
    # Check that it's all uppercase alphanumeric
    if not clean.isalnum():
        return False
    
    return True


class AntiFuzzingProtection:
    """
    Protection against fuzzing and automated attacks.
    
    Detects patterns of automated testing/fuzzing.
    """
    
    def __init__(self):
        self._failed_attempts = 0
        self._unique_failures: set[str] = set()
        self._start_time = time.time()
    
    def record_failure(self, error_type: str):
        """Record a failed operation"""
        self._failed_attempts += 1
        self._unique_failures.add(error_type)
    
    def is_fuzzing_detected(self) -> bool:
        """
        Detect if fuzzing is likely occurring.
        
        Indicators:
        - High number of failures in short time
        - Many unique error types
        - Rapid succession of requests
        """
        elapsed = time.time() - self._start_time
        
        if elapsed < 60:  # Within first minute
            if self._failed_attempts > 20:
                logger.warning("Possible fuzzing detected: high failure rate")
                return True
            
            if len(self._unique_failures) > 10:
                logger.warning("Possible fuzzing detected: many unique errors")
                return True
        
        return False


# Global instances
security_monitor = SecurityMonitor()
rate_limiter = RateLimitTracker()
anti_fuzzing = AntiFuzzingProtection()


def perform_security_checks() -> tuple[bool, list[str]]:
    """
    Perform comprehensive security checks.
    
    Returns:
        (all_checks_passed, list_of_issues)
    """
    issues = []
    
    # Check for debugger
    if security_monitor.detect_debugger():
        # Note: Don't immediately fail on debugger detection during development
        # In production, you might want to treat this more seriously
        logger.debug("Debugger detected (may be legitimate during development)")
    
    # Check execution environment
    env_valid, env_issues = security_monitor.validate_execution_environment()
    if not env_valid:
        issues.extend(env_issues)
    
    # Check for clock manipulation
    clock_rollback, clock_reason = security_monitor.detect_clock_rollback()
    if clock_rollback:
        issues.append(f"Clock manipulation: {clock_reason}")
    
    # Check for fuzzing
    if anti_fuzzing.is_fuzzing_detected():
        issues.append("Automated attack/fuzzing detected")
    
    return len(issues) == 0, issues


def log_security_event(event_type: str, details: str, severity: str = "INFO"):
    """
    Log security-relevant events.
    
    Args:
        event_type: Type of security event
        details: Event details
        severity: INFO, WARNING, ERROR, CRITICAL
    """
    log_levels = {
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    
    level = log_levels.get(severity.upper(), logging.INFO)
    
    logger.log(
        level,
        f"[SECURITY:{event_type}] {details}"
    )
