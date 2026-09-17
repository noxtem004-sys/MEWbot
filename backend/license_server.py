"""
License Server Backend

Provides REST API endpoints for license validation, activation, and management.
This is the central authority for all license operations.

Security features:
- HMAC-signed responses to prevent tampering
- Nonce-based replay attack prevention
- Rate limiting per device/IP
- Server-side time authority
- Secure random license key generation
"""

import asyncio
import hmac
import hashlib
import logging
import secrets
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

from aiohttp import web
from aiohttp.web import Request, Response, middleware

from license_database import LicenseDatabase, LicenseStatus

logger = logging.getLogger(__name__)


class LicenseServer:
    """License validation and management server"""
    
    def __init__(self, secret_key: str, host: str = "0.0.0.0", port: int = 8765):
        self.secret_key = secret_key.encode('utf-8')
        self.host = host
        self.port = port
        self.db = LicenseDatabase()
        self.app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        
        # Nonce cache for replay attack prevention (simple in-memory cache)
        # In production, use Redis or similar distributed cache
        self._nonce_cache: Dict[str, int] = {}  # nonce -> expiry_timestamp
        self._nonce_cache_size = 10000
        self._nonce_ttl = 300  # 5 minutes
    
    def generate_license_key(self) -> str:
        """
        Generate cryptographically secure license key.
        Format: XXXX-XXXX-XXXX-XXXX (16 characters in groups of 4)
        
        Uses secrets.token_urlsafe for high entropy.
        """
        # Generate 12 bytes (96 bits) of secure random data
        # Base64-url-safe encoding gives us ~16 characters
        raw = secrets.token_urlsafe(12)
        # Remove any dashes/underscores and take uppercase alphanumeric
        clean = ''.join(c for c in raw if c.isalnum()).upper()[:16]
        
        # If we don't have enough characters, generate more
        while len(clean) < 16:
            raw = secrets.token_urlsafe(12)
            clean += ''.join(c for c in raw if c.isalnum()).upper()
        
        clean = clean[:16]
        
        # Format as XXXX-XXXX-XXXX-XXXX
        return f"{clean[0:4]}-{clean[4:8]}-{clean[8:12]}-{clean[12:16]}"
    
    def sign_response(self, data: Dict[str, Any]) -> str:
        """
        Generate HMAC signature for response data.
        Client can verify this signature to ensure response authenticity.
        """
        # Sort keys for consistent signature
        payload = json.dumps(data, sort_keys=True)
        signature = hmac.new(
            self.secret_key,
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def verify_nonce(self, nonce: str) -> bool:
        """
        Verify that a nonce hasn't been used before (replay attack prevention).
        Returns True if nonce is valid (not seen before and not expired).
        """
        if not nonce or len(nonce) < 16:
            return False
        
        # Clean expired nonces periodically
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if len(self._nonce_cache) > self._nonce_cache_size:
            self._nonce_cache = {
                k: v for k, v in self._nonce_cache.items()
                if v > now_ts
            }
        
        # Check if nonce was already used
        if nonce in self._nonce_cache:
            logger.warning(f"Replay attack detected: nonce reused: {nonce[:8]}...")
            return False
        
        # Store nonce with expiration
        self._nonce_cache[nonce] = now_ts + self._nonce_ttl
        return True
    
    def get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request"""
        # Check for proxy headers
        forwarded = request.headers.get('X-Forwarded-For')
        if forwarded:
            return forwarded.split(',')[0].strip()
        
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip
        
        # Fallback to peer name
        peername = request.transport.get_extra_info('peername')
        if peername:
            return peername[0]
        
        return "unknown"
    
    async def check_rate_limit(
        self,
        request: Request,
        identifier: str,
        action_type: str,
        max_attempts: int = 10,
        window_seconds: int = 60
    ) -> Optional[Response]:
        """
        Check rate limit and return error response if exceeded.
        Returns None if allowed, Response if blocked.
        """
        result = await self.db.check_rate_limit(
            identifier=identifier,
            identifier_type="device" if action_type in ["activate", "validate"] else "ip",
            action_type=action_type,
            max_attempts=max_attempts,
            window_seconds=window_seconds,
            block_duration_seconds=300  # 5 minute block
        )
        
        if not result["allowed"]:
            blocked_until = result.get("blocked_until", 0)
            remaining = max(0, blocked_until - int(datetime.now(timezone.utc).timestamp()))
            
            await self.db.log_action(
                action=f"RATE_LIMIT_EXCEEDED_{action_type.upper()}",
                device_id=identifier if "device" in result else None,
                ip_address=self.get_client_ip(request),
                details=f"Blocked for {remaining}s"
            )
            
            return web.json_response({
                "success": False,
                "error": "rate_limit_exceeded",
                "message": result.get("message", "Too many requests"),
                "blocked_until": blocked_until,
                "retry_after": remaining
            }, status=429)
        
        return None
    
    # ==================== API ENDPOINTS ====================
    
    async def handle_health(self, request: Request) -> Response:
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "server": "license_server",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    async def handle_activate(self, request: Request) -> Response:
        """
        POST /api/license/activate
        
        Activate a license for the first time.
        
        Request body:
        {
            "license_key": "XXXX-XXXX-XXXX-XXXX",
            "device_id": "unique_device_identifier",
            "device_info": "optional device description",
            "nonce": "unique_request_nonce"
        }
        
        Response:
        {
            "success": true/false,
            "message": "...",
            "expires_at": "2026-10-18 15:30:00 UTC",
            "expires_at_utc": 1729264200,
            "signature": "hmac_signature"
        }
        """
        try:
            data = await request.json()
        except Exception as e:
            return web.json_response({
                "success": False,
                "error": "invalid_request",
                "message": "Invalid JSON"
            }, status=400)
        
        # Validate required fields
        license_key = data.get("license_key", "").strip()
        device_id = data.get("device_id", "").strip()
        device_info = data.get("device_info", "").strip()
        nonce = data.get("nonce", "").strip()
        
        if not license_key or not device_id:
            return web.json_response({
                "success": False,
                "error": "missing_fields",
                "message": "license_key and device_id are required"
            }, status=400)
        
        # Verify nonce (replay attack prevention)
        if not self.verify_nonce(nonce):
            return web.json_response({
                "success": False,
                "error": "invalid_nonce",
                "message": "Invalid or reused nonce"
            }, status=400)
        
        # Rate limiting: 5 activation attempts per device per minute
        rate_limit_response = await self.check_rate_limit(
            request, device_id, "activate",
            max_attempts=5, window_seconds=60
        )
        if rate_limit_response:
            return rate_limit_response
        
        # Perform activation
        result = await self.db.activate_license(
            key=license_key,
            device_id=device_id,
            device_info=device_info or None
        )
        
        # Log the attempt
        ip_address = self.get_client_ip(request)
        if result["success"]:
            await self.db.log_action(
                action="ACTIVATION_SUCCESS",
                device_id=device_id,
                ip_address=ip_address,
                details=f"Device activated successfully"
            )
        else:
            await self.db.log_action(
                action="ACTIVATION_FAILED",
                device_id=device_id,
                ip_address=ip_address,
                details=result.get("message", "Unknown error")
            )
        
        # Add signature to response
        if result["success"]:
            # Add server timestamp for clock skew protection
            result["server_timestamp_utc"] = int(datetime.now(timezone.utc).timestamp())
            result["signature"] = self.sign_response(result)
        
        status_code = 200 if result["success"] else 400
        return web.json_response(result, status=status_code)
    
    async def handle_validate(self, request: Request) -> Response:
        """
        POST /api/license/validate
        
        Validate an active license (periodic check).
        
        Request body:
        {
            "license_key": "XXXX-XXXX-XXXX-XXXX",
            "device_id": "unique_device_identifier",
            "nonce": "unique_request_nonce",
            "client_timestamp_utc": 1234567890
        }
        
        Response:
        {
            "valid": true/false,
            "message": "...",
            "expires_at_utc": 1729264200,
            "remaining_seconds": 86400,
            "server_timestamp_utc": 1729177800,
            "signature": "hmac_signature"
        }
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response({
                "valid": False,
                "error": "invalid_request",
                "message": "Invalid JSON"
            }, status=400)
        
        # Validate required fields
        license_key = data.get("license_key", "").strip()
        device_id = data.get("device_id", "").strip()
        nonce = data.get("nonce", "").strip()
        client_timestamp = data.get("client_timestamp_utc", 0)
        
        if not license_key or not device_id:
            return web.json_response({
                "valid": False,
                "error": "missing_fields",
                "message": "license_key and device_id are required"
            }, status=400)
        
        # Verify nonce
        if not self.verify_nonce(nonce):
            return web.json_response({
                "valid": False,
                "error": "invalid_nonce",
                "message": "Invalid or reused nonce"
            }, status=400)
        
        # Rate limiting: 20 validations per device per minute (more lenient than activation)
        rate_limit_response = await self.check_rate_limit(
            request, device_id, "validate",
            max_attempts=20, window_seconds=60
        )
        if rate_limit_response:
            return rate_limit_response
        
        # Check for clock skew (detect time manipulation)
        server_ts = int(datetime.now(timezone.utc).timestamp())
        if client_timestamp:
            skew = abs(server_ts - client_timestamp)
            if skew > 300:  # 5 minutes tolerance
                logger.warning(
                    f"Large clock skew detected: {skew}s for device {device_id[:8]}..."
                )
                # Don't reject, but log for monitoring
        
        # Perform validation
        result = await self.db.validate_license(
            key=license_key,
            device_id=device_id
        )
        
        # Add server timestamp
        result["server_timestamp_utc"] = server_ts
        
        # Add signature
        result["signature"] = self.sign_response(result)
        
        status_code = 200 if result.get("valid") else 400
        return web.json_response(result, status=status_code)
    
    async def handle_heartbeat(self, request: Request) -> Response:
        """
        POST /api/license/heartbeat
        
        Lightweight heartbeat to update last_seen without full validation.
        Used for periodic "I'm still here" checks.
        
        Request body:
        {
            "license_key": "XXXX-XXXX-XXXX-XXXX",
            "device_id": "unique_device_identifier",
            "nonce": "unique_request_nonce"
        }
        
        Response:
        {
            "success": true/false,
            "server_timestamp_utc": 1729177800
        }
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response({
                "success": False,
                "error": "invalid_request"
            }, status=400)
        
        license_key = data.get("license_key", "").strip()
        device_id = data.get("device_id", "").strip()
        nonce = data.get("nonce", "").strip()
        
        if not license_key or not device_id:
            return web.json_response({
                "success": False,
                "error": "missing_fields"
            }, status=400)
        
        # Verify nonce
        if not self.verify_nonce(nonce):
            return web.json_response({
                "success": False,
                "error": "invalid_nonce"
            }, status=400)
        
        # Rate limiting: 60 heartbeats per device per minute
        rate_limit_response = await self.check_rate_limit(
            request, device_id, "heartbeat",
            max_attempts=60, window_seconds=60
        )
        if rate_limit_response:
            return rate_limit_response
        
        # Perform lightweight validation
        result = await self.db.validate_license(
            key=license_key,
            device_id=device_id
        )
        
        response = {
            "success": result.get("valid", False),
            "server_timestamp_utc": int(datetime.now(timezone.utc).timestamp())
        }
        
        if not response["success"]:
            response["message"] = result.get("message", "Invalid license")
        
        return web.json_response(response)
    
    async def handle_deactivate(self, request: Request) -> Response:
        """
        POST /api/license/deactivate
        
        Deactivate a license on a specific device.
        
        Request body:
        {
            "license_key": "XXXX-XXXX-XXXX-XXXX",
            "device_id": "unique_device_identifier",
            "nonce": "unique_request_nonce"
        }
        
        Response:
        {
            "success": true/false,
            "message": "..."
        }
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response({
                "success": False,
                "error": "invalid_request"
            }, status=400)
        
        license_key = data.get("license_key", "").strip()
        device_id = data.get("device_id", "").strip()
        nonce = data.get("nonce", "").strip()
        
        if not license_key or not device_id:
            return web.json_response({
                "success": False,
                "error": "missing_fields"
            }, status=400)
        
        # Verify nonce
        if not self.verify_nonce(nonce):
            return web.json_response({
                "success": False,
                "error": "invalid_nonce"
            }, status=400)
        
        # Get license ID
        license_data = await self.db.get_license_by_key(license_key)
        if not license_data:
            return web.json_response({
                "success": False,
                "message": "License not found"
            }, status=404)
        
        # Reset this specific device
        result = await self.db.reset_device(
            license_id=license_data["id"],
            device_id=device_id
        )
        
        ip_address = self.get_client_ip(request)
        await self.db.log_action(
            action="DEACTIVATION",
            license_id=license_data["id"],
            device_id=device_id,
            ip_address=ip_address,
            details="Device deactivated by client request"
        )
        
        return web.json_response(result)
    
    async def handle_server_time(self, request: Request) -> Response:
        """
        GET /api/server/time
        
        Get current server time (UTC timestamp).
        Used by clients to detect clock skew.
        
        Response:
        {
            "timestamp_utc": 1729177800,
            "iso": "2026-09-17T12:30:00Z"
        }
        """
        now = datetime.now(timezone.utc)
        return web.json_response({
            "timestamp_utc": int(now.timestamp()),
            "iso": now.isoformat()
        })
    
    # ==================== MIDDLEWARE ====================
    
    @middleware
    async def error_middleware(self, request: Request, handler):
        """Global error handling middleware"""
        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unhandled error in {request.path}: {e}", exc_info=True)
            return web.json_response({
                "success": False,
                "error": "internal_server_error",
                "message": "An internal error occurred"
            }, status=500)
    
    @middleware
    async def logging_middleware(self, request: Request, handler):
        """Request logging middleware"""
        start_time = datetime.now()
        
        try:
            response = await handler(request)
            duration = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                f"{request.method} {request.path} "
                f"-> {response.status} ({duration:.3f}s)"
            )
            
            return response
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(
                f"{request.method} {request.path} "
                f"-> ERROR ({duration:.3f}s): {e}"
            )
            raise
    
    # ==================== SERVER LIFECYCLE ====================
    
    def setup_routes(self):
        """Setup all API routes"""
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_get('/api/server/time', self.handle_server_time)
        
        self.app.router.add_post('/api/license/activate', self.handle_activate)
        self.app.router.add_post('/api/license/validate', self.handle_validate)
        self.app.router.add_post('/api/license/heartbeat', self.handle_heartbeat)
        self.app.router.add_post('/api/license/deactivate', self.handle_deactivate)
    
    async def start(self):
        """Start the license server"""
        # Initialize database
        await self.db.init_db()
        
        # Create aiohttp application
        self.app = web.Application(
            middlewares=[
                self.error_middleware,
                self.logging_middleware
            ]
        )
        
        # Setup routes
        self.setup_routes()
        
        # Start server
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        
        logger.info(f"License Server started on http://{self.host}:{self.port}")
        logger.info("API Endpoints:")
        logger.info("  POST /api/license/activate")
        logger.info("  POST /api/license/validate")
        logger.info("  POST /api/license/heartbeat")
        logger.info("  POST /api/license/deactivate")
        logger.info("  GET  /api/server/time")
        logger.info("  GET  /health")
    
    async def stop(self):
        """Stop the license server"""
        if self._site:
            await self._site.stop()
        
        if self._runner:
            await self._runner.cleanup()
        
        logger.info("License Server stopped")
    
    async def run_forever(self):
        """Run the server until interrupted"""
        await self.start()
        
        try:
            # Keep running forever
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            await self.stop()


# ==================== STANDALONE SERVER SCRIPT ====================

async def main():
    """Standalone server entry point"""
    import sys
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get secret key from environment or generate one
    import os
    secret_key = os.environ.get('LICENSE_SERVER_SECRET_KEY')
    
    if not secret_key:
        logger.error("LICENSE_SERVER_SECRET_KEY not set!")
        logger.error("Please set this environment variable for production use.")
        sys.exit(1)
    
    # Get host and port from environment or use defaults
    # Railway provides PORT environment variable
    host = os.environ.get('LICENSE_SERVER_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', os.environ.get('LICENSE_SERVER_PORT', '8765')))
    
    logger.info(f"Starting license server on {host}:{port}")
    
    # Create and run server
    server = LicenseServer(secret_key=secret_key, host=host, port=port)
    
    try:
        await server.run_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await server.stop()


if __name__ == '__main__':
    asyncio.run(main())
