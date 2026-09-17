# License System Documentation

## Overview

This application includes a comprehensive server-side license/rental system that allows you to:
- Rent the software to customers for specific periods
- Manage licenses via Telegram bot
- Track device activations
- Remotely revoke or extend licenses
- Monitor usage statistics

## Architecture

### Components

1. **License Server** (`backend/license_server.py`)
   - REST API for license validation
   - Cryptographic key generation
   - Rate limiting and anti-abuse
   - HMAC-signed responses

2. **License Database** (`backend/license_database.py`)
   - SQLite database with proper state machine
   - Atomic operations with race condition protection
   - Audit logging
   - Device binding

3. **License Bot** (`backend/license_bot.py`)
   - Telegram bot for license management
   - Admin-only access (User ID authorization)
   - 11 administrative functions
   - Interactive menus

4. **License Client** (`core/license_client.py`)
   - Client-side validation
   - Secure local caching
   - Periodic validation
   - Grace period for offline operation

5. **License GUI** (`gui/pages/license_activation_page.py`)
   - Professional activation screen
   - Real-time validation feedback
   - Error handling

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example environment file:

```bash
copy .env.example .env
```

Edit `.env` and set:

```bash
# Generate a secure secret key
LICENSE_SERVER_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Set your Telegram bot token (from @BotFather)
LICENSE_BOT_TOKEN=your_bot_token_here

# Set your Telegram User ID (from @userinfobot)
LICENSE_BOT_ADMIN_IDS=123456789

# Configure server URL (use public IP or domain for production)
LICENSE_SERVER_URL=http://your-server-ip:8765
```

### 3. Start the License Server

The license server must be running for clients to activate and validate licenses.

```bash
python backend/license_server.py
```

The server will:
- Initialize the license database
- Start listening on the configured host:port
- Log all license operations

**Production Deployment:**
- Use a production-grade WSGI server (e.g., gunicorn, uvicorn)
- Enable HTTPS with valid SSL certificates
- Configure firewall rules
- Set up monitoring and logging
- Use environment variables for secrets (never commit them to git)

### 4. Start the License Management Bot

The Telegram bot allows you to create and manage licenses.

```bash
python backend/license_bot.py
```

Open Telegram and start a conversation with your bot. You'll see the management menu.

### 5. Run the Client Application

```bash
python app.py
```

The application will:
- Check for a valid license on startup
- Show activation dialog if no valid license exists
- Start periodic validation after successful activation
- Lock the application if license becomes invalid

## License Management (via Telegram Bot)

### Creating a License

1. Open your Telegram bot
2. Select **Create License**
3. Choose a predefined plan:
   - 1 Day
   - 3 Days
   - 7 Days
   - 30 Days
   - 90 Days
   - 180 Days
   - 365 Days
   - Custom Duration

4. The bot will generate a license key in format: `XXXX-XXXX-XXXX-XXXX`
5. Share this key with your customer

**Important:** The license timer does NOT start when created. It starts when the customer first activates it.

### License States

- **PENDING**: Created but not yet activated
- **ACTIVE**: Currently active and valid
- **EXPIRED**: Time limit exceeded
- **REVOKED**: Permanently invalidated by admin
- **BLOCKED**: Temporarily blocked by admin

### Managing Licenses

**View All Licenses:**
- Select **License List** from the main menu
- Filter by status (All, Active, Pending, etc.)
- Tap any license to view details

**Search for a License:**
- Select **Search License**
- Enter license ID or key
- View full license information

**Extend a License:**
- View license information
- Select **Extend License**
- Choose additional duration
- Confirm extension

**Revoke a License:**
- View license information
- Select **Revoke License**
- License becomes permanently invalid
- Customer's application will stop working

**Block/Unblock a License:**
- View license information
- Select **Block License** (temporary suspension)
- Select **Unblock License** (restore access)

**Reset Device Binding:**
- View license information
- Select **Reset Device**
- Customer can activate on a new device

**View Statistics:**
- Select **Statistics** from main menu
- See total licenses by status
- Active devices count
- Recent activations

## Security Features

### Server-Side

1. **Cryptographic Key Generation**
   - Uses `secrets.token_urlsafe()` for high entropy
   - Keys are unpredictable and unique

2. **HMAC-Signed Responses**
   - All server responses are HMAC-signed
   - Prevents client-side response tampering

3. **Nonce-Based Replay Prevention**
   - Each request requires a unique nonce
   - Prevents replay attacks

4. **Rate Limiting**
   - Activation: 5 attempts per device per minute
   - Validation: 20 attempts per device per minute
   - Heartbeat: 60 attempts per device per minute

5. **Clock-Skew Detection**
   - Server tracks client timestamps
   - Detects large time discrepancies

### Client-Side

1. **Secure Local Cache**
   - License state cached with HMAC signature
   - Detects cache tampering

2. **Device Binding**
   - Stable device ID generation
   - License tied to specific device

3. **Periodic Validation**
   - Regular server checks (default: 5 minutes)
   - Detects revoked/blocked licenses

4. **Grace Period**
   - Continues operation during temporary network outage
   - Default: 30 minutes offline tolerance

5. **Response Signature Verification**
   - Verifies all server responses
   - Prevents fake responses

6. **Clock Manipulation Detection**
   - Monitors system time
   - Detects rollback attempts

### Database

1. **SHA-256 Key Hashing**
   - License keys stored as hashes
   - Never stored in plaintext

2. **Atomic Operations**
   - Prevents race conditions
   - Two simultaneous activations handled correctly

3. **Audit Logging**
   - All operations logged
   - Tracks who did what when

4. **Foreign Key Constraints**
   - Database integrity enforced
   - Cascading deletes handled properly

## API Endpoints

### POST /api/license/activate
Activate a license for the first time.

**Request:**
```json
{
  "license_key": "XXXX-XXXX-XXXX-XXXX",
  "device_id": "unique_device_id",
  "device_info": "Windows 10",
  "nonce": "unique_nonce"
}
```

**Response:**
```json
{
  "success": true,
  "message": "License activated successfully",
  "expires_at": "2026-10-18 15:30:00 UTC",
  "expires_at_utc": 1729264200,
  "server_timestamp_utc": 1729177800,
  "signature": "hmac_signature"
}
```

### POST /api/license/validate
Validate an active license.

**Request:**
```json
{
  "license_key": "XXXX-XXXX-XXXX-XXXX",
  "device_id": "unique_device_id",
  "nonce": "unique_nonce",
  "client_timestamp_utc": 1729177800
}
```

**Response:**
```json
{
  "valid": true,
  "message": "License valid",
  "expires_at_utc": 1729264200,
  "remaining_seconds": 86400,
  "server_timestamp_utc": 1729177800,
  "signature": "hmac_signature"
}
```

### POST /api/license/heartbeat
Lightweight heartbeat to update last_seen.

### POST /api/license/deactivate
Deactivate license on a specific device.

### GET /api/server/time
Get current server time (UTC).

### GET /health
Health check endpoint.

## Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LICENSE_SERVER_URL` | License server URL | `http://localhost:8765` |
| `LICENSE_SERVER_SECRET_KEY` | Shared secret for HMAC | Required |
| `LICENSE_VALIDATION_INTERVAL` | Validation interval (seconds) | `300` |
| `LICENSE_GRACE_PERIOD` | Offline grace period (seconds) | `1800` |
| `LICENSE_BOT_TOKEN` | Telegram bot token | Required for bot |
| `LICENSE_BOT_ADMIN_IDS` | Admin Telegram IDs (comma-separated) | Required for bot |
| `LICENSE_SERVER_HOST` | Server bind address | `0.0.0.0` |
| `LICENSE_SERVER_PORT` | Server listen port | `8765` |

## Troubleshooting

### Client Can't Connect to Server

1. Check that the license server is running
2. Verify `LICENSE_SERVER_URL` is correct
3. Check firewall rules
4. Test server health: `curl http://your-server:8765/health`

### License Activation Fails

1. Check server logs for detailed error
2. Verify license key format (16 alphanumeric characters)
3. Ensure license is not already activated on max devices
4. Check for rate limiting

### Bot Doesn't Respond

1. Verify bot token is correct
2. Check that your Telegram User ID is in `LICENSE_BOT_ADMIN_IDS`
3. Ensure bot is running: `python backend/license_bot.py`
4. Check bot logs for errors

### Application Says License Expired

1. Check license expiration: use bot to view license info
2. Extend license if needed: bot → License Info → Extend
3. Verify system clock is correct (don't manually change it)
4. Check server logs for validation failures

### Grace Period Expired

The application requires server validation after the grace period (default 30 minutes offline).

1. Ensure internet connection is working
2. Check that license server is accessible
3. Verify `LICENSE_SERVER_URL` is correct

## Security Best Practices

### For Production Deployment

1. **Use HTTPS**
   - Never use HTTP in production
   - Get valid SSL certificates (Let's Encrypt)
   - Configure HTTPS in your reverse proxy (nginx/Apache)

2. **Secure the Secret Key**
   - Generate strong random key: `secrets.token_urlsafe(32)`
   - Store in environment variable, not in code
   - Never commit to version control
   - Use different keys for dev/staging/production

3. **Network Security**
   - Use firewall to restrict server access
   - Consider VPN for server-to-server communication
   - Enable fail2ban or similar for DDoS protection

4. **Database Security**
   - Regular backups
   - Secure file permissions
   - Consider encryption at rest

5. **Monitor and Log**
   - Enable comprehensive logging
   - Monitor for suspicious patterns
   - Set up alerts for unusual activity

6. **Keep Updated**
   - Regularly update dependencies
   - Monitor security advisories
   - Test updates in staging first

### Known Limitations

This is **client-side software running on customer machines**. It can never be 100% unbreakable.

The goal is to make unauthorized use:
- **Significantly harder** (not trivial to bypass)
- **Detectable** (audit logs show violations)
- **Not worth the effort** for most users

A determined attacker with:
- Reverse engineering skills
- Debugger/disassembler
- Time and motivation

Can potentially bypass client-side checks.

**Mitigations:**
- Server-side authority (client can't forge valid responses)
- Frequent validation (offline operation limited to grace period)
- Device binding (can't share license easily)
- Audit logging (detect suspicious activity)
- Rate limiting (prevent brute force)

## Database Schema

### licenses
- `id`: Primary key
- `key_hash`: SHA-256 hash of license key
- `plan`: Plan name (e.g., "30 Days")
- `duration_seconds`: Duration in seconds
- `status`: PENDING|ACTIVE|EXPIRED|REVOKED|BLOCKED
- `created_at`: Creation timestamp
- `activated_at`: First activation timestamp
- `expires_at`: Expiration timestamp
- `revoked_at`: Revocation timestamp
- `blocked_at`: Block timestamp
- `max_devices`: Maximum device count
- `metadata`: Additional data (JSON)

### activations
- `id`: Primary key
- `license_id`: Foreign key to licenses
- `device_id`: Device identifier
- `device_info`: Device description
- `activated_at`: Activation timestamp
- `last_seen_at`: Last heartbeat timestamp
- `revoked_at`: Revocation timestamp

### audit_log
- `id`: Primary key
- `timestamp`: Event timestamp
- `action`: Action type
- `license_id`: Related license
- `device_id`: Related device
- `admin_id`: Telegram admin ID
- `ip_address`: Client IP
- `details`: Event details
- `metadata`: Additional data

### rate_limits
- `id`: Primary key
- `identifier`: Device ID or IP
- `identifier_type`: "device" or "ip"
- `action_type`: Action being rate limited
- `attempt_count`: Number of attempts
- `first_attempt_at`: Window start
- `last_attempt_at`: Last attempt
- `blocked_until_utc`: Block expiration

## Support

For issues, questions, or feature requests:

1. Check this documentation first
2. Review server and client logs
3. Check the audit log in the database
4. Verify environment configuration

## License

This license system is part of the TelegramMeowGUI application.
