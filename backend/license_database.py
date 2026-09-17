"""
License System Database Module

Provides async SQLite database support for the license/rental system.
Implements proper state machine, audit logging, and device binding.

Security note: License keys are stored as SHA-256 hashes. The plaintext
key is only shown once when generated and never stored permanently.
"""

import aiosqlite
import hashlib
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.config_manager import app_data_dir

LICENSE_DB_PATH: str = str(app_data_dir() / "licenses.db")

logger = logging.getLogger(__name__)


class LicenseStatus(str, Enum):
    """License state machine states"""
    PENDING = "PENDING"        # Created but not yet activated
    ACTIVE = "ACTIVE"          # Currently active and valid
    EXPIRED = "EXPIRED"        # Time limit exceeded
    REVOKED = "REVOKED"        # Permanently invalidated by admin
    BLOCKED = "BLOCKED"        # Temporarily blocked by admin


class LicenseDatabase:
    """Thread-safe async database operations for license system"""
    
    def __init__(self, db_path: str = LICENSE_DB_PATH):
        self.db_path = db_path
    
    async def init_db(self) -> None:
        """Initialize the license database and create all necessary tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Licenses table - core license information
            await db.execute("""
                CREATE TABLE IF NOT EXISTS licenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_hash TEXT NOT NULL UNIQUE,
                    plan TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    activated_at TEXT,
                    expires_at TEXT,
                    revoked_at TEXT,
                    blocked_at TEXT,
                    unblocked_at TEXT,
                    max_devices INTEGER NOT NULL DEFAULT 1,
                    metadata TEXT,
                    created_at_utc INTEGER NOT NULL,
                    activated_at_utc INTEGER,
                    expires_at_utc INTEGER,
                    CHECK (status IN ('PENDING', 'ACTIVE', 'EXPIRED', 'REVOKED', 'BLOCKED'))
                )
            """)
            
            # Device activations table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS activations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    license_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    device_info TEXT,
                    activated_at TEXT NOT NULL,
                    activated_at_utc INTEGER NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_seen_at_utc INTEGER NOT NULL,
                    revoked_at TEXT,
                    revoked_at_utc INTEGER,
                    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE,
                    UNIQUE(license_id, device_id)
                )
            """)
            
            # Audit log table - comprehensive action logging
            await db.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    timestamp_utc INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    license_id INTEGER,
                    device_id TEXT,
                    admin_id INTEGER,
                    ip_address TEXT,
                    details TEXT,
                    metadata TEXT,
                    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE SET NULL
                )
            """)
            
            # Rate limiting table - prevent brute force attacks
            await db.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identifier TEXT NOT NULL,
                    identifier_type TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 1,
                    first_attempt_at TEXT NOT NULL,
                    first_attempt_utc INTEGER NOT NULL,
                    last_attempt_at TEXT NOT NULL,
                    last_attempt_utc INTEGER NOT NULL,
                    blocked_until_utc INTEGER,
                    UNIQUE(identifier, identifier_type, action_type)
                )
            """)
            
            # Create indexes for performance
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_licenses_key_hash 
                ON licenses(key_hash)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_licenses_status 
                ON licenses(status)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_licenses_expires_at_utc 
                ON licenses(expires_at_utc)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_activations_license_id 
                ON activations(license_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_activations_device_id 
                ON activations(device_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_log_license_id 
                ON audit_log(license_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp_utc 
                ON audit_log(timestamp_utc)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_rate_limits_identifier 
                ON rate_limits(identifier, identifier_type, action_type)
            """)
            
            await db.commit()
        
        logger.info(f"License database initialized at: {self.db_path}")
    
    @staticmethod
    def hash_license_key(key: str) -> str:
        """Generate SHA-256 hash of license key for secure storage"""
        return hashlib.sha256(key.encode('utf-8')).hexdigest()
    
    @staticmethod
    def utc_now() -> datetime:
        """Get current UTC time"""
        return datetime.now(timezone.utc)
    
    @staticmethod
    def utc_timestamp() -> int:
        """Get current UTC timestamp as integer"""
        return int(datetime.now(timezone.utc).timestamp())
    
    @staticmethod
    def format_datetime(dt: datetime) -> str:
        """Format datetime for display"""
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # ==================== LICENSE OPERATIONS ====================
    
    async def create_license(
        self,
        key: str,
        plan: str,
        duration_seconds: int,
        max_devices: int = 1,
        metadata: Optional[str] = None
    ) -> int:
        """
        Create a new license in PENDING status.
        Returns the license ID.
        """
        now = self.utc_now()
        now_ts = int(now.timestamp())
        key_hash = self.hash_license_key(key)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO licenses (
                    key_hash, plan, duration_seconds, status,
                    created_at, created_at_utc, max_devices, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                key_hash, plan, duration_seconds, LicenseStatus.PENDING.value,
                self.format_datetime(now), now_ts, max_devices, metadata
            ))
            license_id = cursor.lastrowid
            await db.commit()
        
        await self.log_action(
            action="LICENSE_CREATED",
            license_id=license_id,
            details=f"Plan: {plan}, Duration: {duration_seconds}s, Max Devices: {max_devices}"
        )
        
        logger.info(f"License created: ID={license_id}, Plan={plan}")
        return license_id
    
    async def get_license_by_key(self, key: str) -> Optional[Dict[str, Any]]:
        """Get license information by key"""
        key_hash = self.hash_license_key(key)
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM licenses WHERE key_hash = ?
            """, (key_hash,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None
    
    async def get_license_by_id(self, license_id: int) -> Optional[Dict[str, Any]]:
        """Get license information by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM licenses WHERE id = ?
            """, (license_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None
    
    async def activate_license(
        self,
        key: str,
        device_id: str,
        device_info: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Activate a license for the first time.
        Returns: {"success": bool, "message": str, "expires_at": str, ...}
        
        This operation is atomic and handles race conditions.
        """
        key_hash = self.hash_license_key(key)
        now = self.utc_now()
        now_ts = int(now.timestamp())
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Start transaction
            await db.execute("BEGIN IMMEDIATE")
            
            try:
                # Get license with row lock
                async with db.execute("""
                    SELECT * FROM licenses WHERE key_hash = ?
                """, (key_hash,)) as cursor:
                    row = await cursor.fetchone()
                
                if not row:
                    await db.rollback()
                    return {"success": False, "message": "License not found"}
                
                license_data = dict(row)
                license_id = license_data["id"]
                status = license_data["status"]
                
                # Check license status
                if status == LicenseStatus.REVOKED.value:
                    await db.rollback()
                    await self.log_action(
                        action="ACTIVATION_FAILED_REVOKED",
                        license_id=license_id,
                        device_id=device_id,
                        details="License is revoked"
                    )
                    return {"success": False, "message": "License has been revoked"}
                
                if status == LicenseStatus.BLOCKED.value:
                    await db.rollback()
                    await self.log_action(
                        action="ACTIVATION_FAILED_BLOCKED",
                        license_id=license_id,
                        device_id=device_id,
                        details="License is blocked"
                    )
                    return {"success": False, "message": "License is blocked"}
                
                if status == LicenseStatus.EXPIRED.value:
                    await db.rollback()
                    await self.log_action(
                        action="ACTIVATION_FAILED_EXPIRED",
                        license_id=license_id,
                        device_id=device_id,
                        details="License has expired"
                    )
                    return {"success": False, "message": "License has expired"}
                
                # Check if already activated
                if status == LicenseStatus.ACTIVE.value:
                    # Check device limit
                    async with db.execute("""
                        SELECT COUNT(*) as count FROM activations
                        WHERE license_id = ? AND revoked_at IS NULL
                    """, (license_id,)) as cursor:
                        count_row = await cursor.fetchone()
                        active_devices = count_row["count"]
                    
                    max_devices = license_data["max_devices"]
                    
                    # Check if this device is already activated
                    async with db.execute("""
                        SELECT * FROM activations
                        WHERE license_id = ? AND device_id = ? AND revoked_at IS NULL
                    """, (license_id, device_id)) as cursor:
                        existing = await cursor.fetchone()
                    
                    if existing:
                        # Update last_seen for existing device
                        await db.execute("""
                            UPDATE activations
                            SET last_seen_at = ?, last_seen_at_utc = ?
                            WHERE license_id = ? AND device_id = ?
                        """, (self.format_datetime(now), now_ts, license_id, device_id))
                        await db.commit()
                        
                        return {
                            "success": True,
                            "message": "License already activated on this device",
                            "expires_at": license_data["expires_at"],
                            "expires_at_utc": license_data["expires_at_utc"]
                        }
                    
                    if active_devices >= max_devices:
                        await db.rollback()
                        await self.log_action(
                            action="ACTIVATION_FAILED_DEVICE_LIMIT",
                            license_id=license_id,
                            device_id=device_id,
                            details=f"Device limit reached: {active_devices}/{max_devices}"
                        )
                        return {
                            "success": False,
                            "message": f"Device limit reached ({active_devices}/{max_devices})"
                        }
                    
                    # Add new device to existing active license
                    await db.execute("""
                        INSERT INTO activations (
                            license_id, device_id, device_info,
                            activated_at, activated_at_utc,
                            last_seen_at, last_seen_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        license_id, device_id, device_info,
                        self.format_datetime(now), now_ts,
                        self.format_datetime(now), now_ts
                    ))
                    
                    await db.commit()
                    
                    await self.log_action(
                        action="DEVICE_ADDED",
                        license_id=license_id,
                        device_id=device_id,
                        details=f"Additional device activated ({active_devices + 1}/{max_devices})"
                    )
                    
                    return {
                        "success": True,
                        "message": "License activated on new device",
                        "expires_at": license_data["expires_at"],
                        "expires_at_utc": license_data["expires_at_utc"]
                    }
                
                # First activation (PENDING -> ACTIVE)
                if status != LicenseStatus.PENDING.value:
                    await db.rollback()
                    return {"success": False, "message": f"Invalid license status: {status}"}
                
                # Calculate expiration
                duration_seconds = license_data["duration_seconds"]
                expires_at = datetime.fromtimestamp(now_ts + duration_seconds, tz=timezone.utc)
                expires_at_ts = int(expires_at.timestamp())
                
                # Update license to ACTIVE
                await db.execute("""
                    UPDATE licenses
                    SET status = ?, activated_at = ?, activated_at_utc = ?,
                        expires_at = ?, expires_at_utc = ?
                    WHERE id = ?
                """, (
                    LicenseStatus.ACTIVE.value,
                    self.format_datetime(now), now_ts,
                    self.format_datetime(expires_at), expires_at_ts,
                    license_id
                ))
                
                # Create activation record
                await db.execute("""
                    INSERT INTO activations (
                        license_id, device_id, device_info,
                        activated_at, activated_at_utc,
                        last_seen_at, last_seen_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    license_id, device_id, device_info,
                    self.format_datetime(now), now_ts,
                    self.format_datetime(now), now_ts
                ))
                
                await db.commit()
                
                await self.log_action(
                    action="LICENSE_ACTIVATED",
                    license_id=license_id,
                    device_id=device_id,
                    details=f"First activation, expires: {self.format_datetime(expires_at)}"
                )
                
                logger.info(f"License activated: ID={license_id}, Device={device_id[:8]}...")
                
                return {
                    "success": True,
                    "message": "License activated successfully",
                    "expires_at": self.format_datetime(expires_at),
                    "expires_at_utc": expires_at_ts,
                    "activated_at": self.format_datetime(now),
                    "activated_at_utc": now_ts
                }
                
            except Exception as e:
                await db.rollback()
                logger.error(f"License activation error: {e}")
                return {"success": False, "message": f"Activation error: {str(e)}"}
    
    async def validate_license(
        self,
        key: str,
        device_id: str
    ) -> Dict[str, Any]:
        """
        Validate an active license.
        Returns: {"valid": bool, "message": str, "expires_at_utc": int, ...}
        """
        key_hash = self.hash_license_key(key)
        now_ts = self.utc_timestamp()
        now = self.utc_now()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Get license
            async with db.execute("""
                SELECT * FROM licenses WHERE key_hash = ?
            """, (key_hash,)) as cursor:
                row = await cursor.fetchone()
            
            if not row:
                await self.log_action(
                    action="VALIDATION_FAILED_NOT_FOUND",
                    device_id=device_id,
                    details="License not found"
                )
                return {"valid": False, "message": "License not found"}
            
            license_data = dict(row)
            license_id = license_data["id"]
            status = license_data["status"]
            expires_at_utc = license_data["expires_at_utc"]
            
            # Check status
            if status == LicenseStatus.REVOKED.value:
                await self.log_action(
                    action="VALIDATION_FAILED_REVOKED",
                    license_id=license_id,
                    device_id=device_id
                )
                return {"valid": False, "message": "License has been revoked"}
            
            if status == LicenseStatus.BLOCKED.value:
                await self.log_action(
                    action="VALIDATION_FAILED_BLOCKED",
                    license_id=license_id,
                    device_id=device_id
                )
                return {"valid": False, "message": "License is blocked"}
            
            if status == LicenseStatus.PENDING.value:
                await self.log_action(
                    action="VALIDATION_FAILED_NOT_ACTIVATED",
                    license_id=license_id,
                    device_id=device_id
                )
                return {"valid": False, "message": "License not activated"}
            
            # Check expiration
            if expires_at_utc and now_ts > expires_at_utc:
                # Auto-update status to EXPIRED
                await db.execute("""
                    UPDATE licenses SET status = ? WHERE id = ?
                """, (LicenseStatus.EXPIRED.value, license_id))
                await db.commit()
                
                await self.log_action(
                    action="VALIDATION_FAILED_EXPIRED",
                    license_id=license_id,
                    device_id=device_id,
                    details=f"Expired at: {license_data['expires_at']}"
                )
                return {"valid": False, "message": "License has expired"}
            
            # Check device authorization
            async with db.execute("""
                SELECT * FROM activations
                WHERE license_id = ? AND device_id = ? AND revoked_at IS NULL
            """, (license_id, device_id)) as cursor:
                activation = await cursor.fetchone()
            
            if not activation:
                await self.log_action(
                    action="VALIDATION_FAILED_DEVICE_NOT_AUTHORIZED",
                    license_id=license_id,
                    device_id=device_id
                )
                return {"valid": False, "message": "Device not authorized"}
            
            # Update last_seen
            await db.execute("""
                UPDATE activations
                SET last_seen_at = ?, last_seen_at_utc = ?
                WHERE license_id = ? AND device_id = ?
            """, (self.format_datetime(now), now_ts, license_id, device_id))
            await db.commit()
            
            # Successful validation
            remaining_seconds = expires_at_utc - now_ts if expires_at_utc else 0
            
            return {
                "valid": True,
                "message": "License valid",
                "license_id": license_id,
                "expires_at": license_data["expires_at"],
                "expires_at_utc": expires_at_utc,
                "remaining_seconds": remaining_seconds,
                "plan": license_data["plan"]
            }
    
    async def extend_license(
        self,
        license_id: int,
        additional_seconds: int,
        admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Extend an active license by adding additional time"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            async with db.execute("""
                SELECT * FROM licenses WHERE id = ?
            """, (license_id,)) as cursor:
                row = await cursor.fetchone()
            
            if not row:
                return {"success": False, "message": "License not found"}
            
            license_data = dict(row)
            status = license_data["status"]
            expires_at_utc = license_data["expires_at_utc"]
            
            if status not in [LicenseStatus.ACTIVE.value, LicenseStatus.EXPIRED.value]:
                return {"success": False, "message": f"Cannot extend license with status: {status}"}
            
            # Calculate new expiration
            now_ts = self.utc_timestamp()
            if expires_at_utc and expires_at_utc > now_ts:
                # License still active, extend from current expiration
                new_expires_at_utc = expires_at_utc + additional_seconds
            else:
                # License expired, extend from now
                new_expires_at_utc = now_ts + additional_seconds
            
            new_expires_at = datetime.fromtimestamp(new_expires_at_utc, tz=timezone.utc)
            
            # Update license
            new_status = LicenseStatus.ACTIVE.value
            await db.execute("""
                UPDATE licenses
                SET expires_at = ?, expires_at_utc = ?, status = ?
                WHERE id = ?
            """, (
                self.format_datetime(new_expires_at),
                new_expires_at_utc,
                new_status,
                license_id
            ))
            await db.commit()
        
        await self.log_action(
            action="LICENSE_EXTENDED",
            license_id=license_id,
            admin_id=admin_id,
            details=f"Extended by {additional_seconds}s, new expiration: {self.format_datetime(new_expires_at)}"
        )
        
        logger.info(f"License extended: ID={license_id}, +{additional_seconds}s")
        
        return {
            "success": True,
            "message": "License extended successfully",
            "new_expires_at": self.format_datetime(new_expires_at),
            "new_expires_at_utc": new_expires_at_utc
        }
    
    async def revoke_license(
        self,
        license_id: int,
        admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Permanently revoke a license"""
        now = self.utc_now()
        now_ts = int(now.timestamp())
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE licenses
                SET status = ?, revoked_at = ?
                WHERE id = ?
            """, (LicenseStatus.REVOKED.value, self.format_datetime(now), license_id))
            
            # Revoke all device activations
            await db.execute("""
                UPDATE activations
                SET revoked_at = ?, revoked_at_utc = ?
                WHERE license_id = ? AND revoked_at IS NULL
            """, (self.format_datetime(now), now_ts, license_id))
            
            await db.commit()
        
        await self.log_action(
            action="LICENSE_REVOKED",
            license_id=license_id,
            admin_id=admin_id,
            details="License permanently revoked"
        )
        
        logger.info(f"License revoked: ID={license_id}")
        
        return {"success": True, "message": "License revoked successfully"}
    
    async def block_license(
        self,
        license_id: int,
        admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Temporarily block a license"""
        now = self.utc_now()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            async with db.execute("""
                SELECT status FROM licenses WHERE id = ?
            """, (license_id,)) as cursor:
                row = await cursor.fetchone()
            
            if not row:
                return {"success": False, "message": "License not found"}
            
            if row["status"] == LicenseStatus.REVOKED.value:
                return {"success": False, "message": "Cannot block a revoked license"}
            
            await db.execute("""
                UPDATE licenses
                SET status = ?, blocked_at = ?
                WHERE id = ?
            """, (LicenseStatus.BLOCKED.value, self.format_datetime(now), license_id))
            await db.commit()
        
        await self.log_action(
            action="LICENSE_BLOCKED",
            license_id=license_id,
            admin_id=admin_id,
            details="License temporarily blocked"
        )
        
        logger.info(f"License blocked: ID={license_id}")
        
        return {"success": True, "message": "License blocked successfully"}
    
    async def unblock_license(
        self,
        license_id: int,
        admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Unblock a blocked license"""
        now = self.utc_now()
        now_ts = self.utc_timestamp()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            async with db.execute("""
                SELECT * FROM licenses WHERE id = ?
            """, (license_id,)) as cursor:
                row = await cursor.fetchone()
            
            if not row:
                return {"success": False, "message": "License not found"}
            
            license_data = dict(row)
            
            if license_data["status"] != LicenseStatus.BLOCKED.value:
                return {"success": False, "message": "License is not blocked"}
            
            # Determine new status
            if license_data["activated_at_utc"]:
                if license_data["expires_at_utc"] and now_ts > license_data["expires_at_utc"]:
                    new_status = LicenseStatus.EXPIRED.value
                else:
                    new_status = LicenseStatus.ACTIVE.value
            else:
                new_status = LicenseStatus.PENDING.value
            
            await db.execute("""
                UPDATE licenses
                SET status = ?, unblocked_at = ?
                WHERE id = ?
            """, (new_status, self.format_datetime(now), license_id))
            await db.commit()
        
        await self.log_action(
            action="LICENSE_UNBLOCKED",
            license_id=license_id,
            admin_id=admin_id,
            details=f"License unblocked, new status: {new_status}"
        )
        
        logger.info(f"License unblocked: ID={license_id}, Status={new_status}")
        
        return {"success": True, "message": f"License unblocked (status: {new_status})"}
    
    async def reset_device(
        self,
        license_id: int,
        device_id: Optional[str] = None,
        admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Reset device binding for a license"""
        now = self.utc_now()
        now_ts = int(now.timestamp())
        
        async with aiosqlite.connect(self.db_path) as db:
            if device_id:
                # Reset specific device
                await db.execute("""
                    UPDATE activations
                    SET revoked_at = ?, revoked_at_utc = ?
                    WHERE license_id = ? AND device_id = ? AND revoked_at IS NULL
                """, (self.format_datetime(now), now_ts, license_id, device_id))
                details = f"Device reset: {device_id[:8]}..."
            else:
                # Reset all devices
                await db.execute("""
                    UPDATE activations
                    SET revoked_at = ?, revoked_at_utc = ?
                    WHERE license_id = ? AND revoked_at IS NULL
                """, (self.format_datetime(now), now_ts, license_id))
                details = "All devices reset"
            
            await db.commit()
        
        await self.log_action(
            action="DEVICE_RESET",
            license_id=license_id,
            device_id=device_id,
            admin_id=admin_id,
            details=details
        )
        
        logger.info(f"Device reset: License ID={license_id}, {details}")
        
        return {"success": True, "message": "Device binding reset successfully"}
    
    # ==================== SEARCH & QUERY OPERATIONS ====================
    
    async def search_licenses(
        self,
        key: Optional[str] = None,
        license_id: Optional[int] = None,
        device_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search licenses by various criteria"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            query = "SELECT * FROM licenses WHERE 1=1"
            params = []
            
            if key:
                query += " AND key_hash = ?"
                params.append(self.hash_license_key(key))
            
            if license_id:
                query += " AND id = ?"
                params.append(license_id)
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            if device_id:
                query += """ AND id IN (
                    SELECT license_id FROM activations
                    WHERE device_id = ? AND revoked_at IS NULL
                )"""
                params.append(device_id)
            
            query += " ORDER BY created_at_utc DESC LIMIT ?"
            params.append(limit)
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_license_activations(
        self,
        license_id: int
    ) -> List[Dict[str, Any]]:
        """Get all device activations for a license"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            async with db.execute("""
                SELECT * FROM activations
                WHERE license_id = ?
                ORDER BY activated_at_utc DESC
            """, (license_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get overall license statistics"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Total licenses by status
            stats = {}
            
            async with db.execute("""
                SELECT status, COUNT(*) as count
                FROM licenses
                GROUP BY status
            """) as cursor:
                rows = await cursor.fetchall()
                stats["by_status"] = {row["status"]: row["count"] for row in rows}
            
            # Total licenses
            async with db.execute("SELECT COUNT(*) as count FROM licenses") as cursor:
                row = await cursor.fetchone()
                stats["total_licenses"] = row["count"]
            
            # Active devices
            async with db.execute("""
                SELECT COUNT(DISTINCT device_id) as count
                FROM activations
                WHERE revoked_at IS NULL
            """) as cursor:
                row = await cursor.fetchone()
                stats["active_devices"] = row["count"]
            
            # Recent activations (last 24 hours)
            day_ago_ts = self.utc_timestamp() - 86400
            async with db.execute("""
                SELECT COUNT(*) as count
                FROM activations
                WHERE activated_at_utc > ?
            """, (day_ago_ts,)) as cursor:
                row = await cursor.fetchone()
                stats["activations_24h"] = row["count"]
            
            return stats
    
    # ==================== AUDIT LOG ====================
    
    async def log_action(
        self,
        action: str,
        license_id: Optional[int] = None,
        device_id: Optional[str] = None,
        admin_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        details: Optional[str] = None,
        metadata: Optional[str] = None
    ) -> None:
        """Log an action to the audit log"""
        now = self.utc_now()
        now_ts = int(now.timestamp())
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO audit_log (
                        timestamp, timestamp_utc, action,
                        license_id, device_id, admin_id,
                        ip_address, details, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.format_datetime(now), now_ts, action,
                    license_id, device_id, admin_id,
                    ip_address, details, metadata
                ))
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
    
    async def get_audit_logs(
        self,
        license_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit logs"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            if license_id:
                query = """
                    SELECT * FROM audit_log
                    WHERE license_id = ?
                    ORDER BY timestamp_utc DESC
                    LIMIT ?
                """
                params = (license_id, limit)
            else:
                query = """
                    SELECT * FROM audit_log
                    ORDER BY timestamp_utc DESC
                    LIMIT ?
                """
                params = (limit,)
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    # ==================== RATE LIMITING ====================
    
    async def check_rate_limit(
        self,
        identifier: str,
        identifier_type: str,
        action_type: str,
        max_attempts: int,
        window_seconds: int,
        block_duration_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Check if an action is rate limited.
        Returns: {"allowed": bool, "attempts": int, "blocked_until": int}
        """
        now_ts = self.utc_timestamp()
        now = self.utc_now()
        window_start_ts = now_ts - window_seconds
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Get existing rate limit record
            async with db.execute("""
                SELECT * FROM rate_limits
                WHERE identifier = ? AND identifier_type = ? AND action_type = ?
            """, (identifier, identifier_type, action_type)) as cursor:
                row = await cursor.fetchone()
            
            if row:
                record = dict(row)
                
                # Check if blocked
                if record["blocked_until_utc"] and now_ts < record["blocked_until_utc"]:
                    return {
                        "allowed": False,
                        "attempts": record["attempt_count"],
                        "blocked_until": record["blocked_until_utc"],
                        "message": "Rate limit exceeded, temporarily blocked"
                    }
                
                # Check if within window
                if record["first_attempt_utc"] >= window_start_ts:
                    # Within window, increment count
                    new_count = record["attempt_count"] + 1
                    
                    if new_count > max_attempts:
                        # Block the identifier
                        blocked_until_utc = now_ts + block_duration_seconds
                        
                        await db.execute("""
                            UPDATE rate_limits
                            SET attempt_count = ?,
                                last_attempt_at = ?,
                                last_attempt_utc = ?,
                                blocked_until_utc = ?
                            WHERE identifier = ? AND identifier_type = ? AND action_type = ?
                        """, (
                            new_count,
                            self.format_datetime(now),
                            now_ts,
                            blocked_until_utc,
                            identifier, identifier_type, action_type
                        ))
                        await db.commit()
                        
                        return {
                            "allowed": False,
                            "attempts": new_count,
                            "blocked_until": blocked_until_utc,
                            "message": f"Rate limit exceeded ({new_count}/{max_attempts})"
                        }
                    else:
                        # Update count
                        await db.execute("""
                            UPDATE rate_limits
                            SET attempt_count = ?,
                                last_attempt_at = ?,
                                last_attempt_utc = ?
                            WHERE identifier = ? AND identifier_type = ? AND action_type = ?
                        """, (
                            new_count,
                            self.format_datetime(now),
                            now_ts,
                            identifier, identifier_type, action_type
                        ))
                        await db.commit()
                        
                        return {
                            "allowed": True,
                            "attempts": new_count,
                            "message": f"Allowed ({new_count}/{max_attempts})"
                        }
                else:
                    # Outside window, reset
                    await db.execute("""
                        UPDATE rate_limits
                        SET attempt_count = 1,
                            first_attempt_at = ?,
                            first_attempt_utc = ?,
                            last_attempt_at = ?,
                            last_attempt_utc = ?,
                            blocked_until_utc = NULL
                        WHERE identifier = ? AND identifier_type = ? AND action_type = ?
                    """, (
                        self.format_datetime(now), now_ts,
                        self.format_datetime(now), now_ts,
                        identifier, identifier_type, action_type
                    ))
                    await db.commit()
                    
                    return {
                        "allowed": True,
                        "attempts": 1,
                        "message": "Allowed (new window)"
                    }
            else:
                # Create new record
                await db.execute("""
                    INSERT INTO rate_limits (
                        identifier, identifier_type, action_type,
                        attempt_count,
                        first_attempt_at, first_attempt_utc,
                        last_attempt_at, last_attempt_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    identifier, identifier_type, action_type,
                    1,
                    self.format_datetime(now), now_ts,
                    self.format_datetime(now), now_ts
                ))
                await db.commit()
                
                return {
                    "allowed": True,
                    "attempts": 1,
                    "message": "Allowed (first attempt)"
                }
