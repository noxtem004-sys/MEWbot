# License System Testing Checklist

This document provides a comprehensive manual testing checklist for the license system.
Use this to verify all functionality works correctly in a real environment.

## Prerequisites

- [ ] License server is running
- [ ] Telegram bot is running
- [ ] Environment variables are configured (.env file)
- [ ] All dependencies are installed

## Automated Tests

### Run the test suite:

```bash
python tests/test_license_system.py
```

**Expected Result:** All tests should pass (green checkmarks)

## Manual Testing

### 1. License Server Tests

#### 1.1 Start License Server
```bash
python backend/license_server.py
```

**Expected:**
- [ ] Server starts without errors
- [ ] Logs show "License Server started on http://..."
- [ ] Database is initialized
- [ ] API endpoints are listed

#### 1.2 Health Check
```bash
curl http://localhost:8765/health
```

**Expected:**
- [ ] Returns JSON with status: "healthy"
- [ ] HTTP status code 200

#### 1.3 Server Time
```bash
curl http://localhost:8765/api/server/time
```

**Expected:**
- [ ] Returns current UTC timestamp
- [ ] Returns ISO format time
- [ ] HTTP status code 200

### 2. Telegram Bot Tests

#### 2.1 Start License Bot
```bash
python backend/license_bot.py
```

**Expected:**
- [ ] Bot starts without errors
- [ ] Logs show authorized admin IDs
- [ ] No connection errors

#### 2.2 Bot Authorization
- [ ] Open Telegram and find your bot
- [ ] Send `/start` command
- [ ] **Expected:** Welcome message with menu buttons

**Unauthorized User Test:**
- [ ] Ask someone else to message the bot
- [ ] **Expected:** "Unauthorized" message (no access to functions)

#### 2.3 Create License - Predefined Plan
- [ ] Click "➕ Create License"
- [ ] Select "30 Days"
- [ ] **Expected:** 
  - License created successfully
  - License key displayed (XXXX-XXXX-XXXX-XXXX format)
  - Status shows PENDING
  - Copy button available

#### 2.4 Create License - Custom Duration
- [ ] Click "➕ Create License"
- [ ] Click "✏️ Custom Duration"
- [ ] Enter "45 days"
- [ ] **Expected:**
  - License created with custom duration
  - Plan shows "Custom (45d)"

#### 2.5 View License List
- [ ] Click "📋 License List"
- [ ] **Expected:**
  - List of recent licenses displayed
  - Each shows status emoji, ID, and plan
  - Filter buttons work (All, Active, Pending)

#### 2.6 Search License
- [ ] Click "🔍 Search License"
- [ ] Enter a license ID
- [ ] **Expected:**
  - License details displayed
  - All information accurate

#### 2.7 View Statistics
- [ ] Click "📊 Statistics"
- [ ] **Expected:**
  - Total licenses count
  - Breakdown by status
  - Active devices count
  - Recent activations (24h)

### 3. Client Application Tests

#### 3.1 First Launch (No License)
- [ ] Delete license cache: `%APPDATA%\TelegramMeowGUI\license_cache.dat`
- [ ] Run `python app.py`
- [ ] **Expected:**
  - License activation dialog appears
  - Main application is NOT accessible
  - Cannot close dialog to bypass

#### 3.2 License Activation - Valid Key
- [ ] Enter a valid license key from bot
- [ ] Click "Activate License"
- [ ] **Expected:**
  - "Connecting to license server..." shown
  - Progress indicator displays
  - Success message: "License activated successfully"
  - Shows expiration date
  - Main application loads after 1 second

#### 3.3 License Activation - Invalid Key
- [ ] Delete license cache
- [ ] Run application
- [ ] Enter "INVALID-1234-5678-9999"
- [ ] Click "Activate"
- [ ] **Expected:**
  - Error message displayed (red box)
  - Input field shows error state (red border)
  - Application does NOT proceed
  - Can try again

#### 3.4 License Activation - Malformed Key
- [ ] Enter "SHORT"
- [ ] Click "Activate"
- [ ] **Expected:**
  - Error: "Invalid license key format"
  - Does not contact server

#### 3.5 Relaunch with Valid License
- [ ] Close application
- [ ] Run `python app.py` again
- [ ] **Expected:**
  - Checks existing license
  - Shows "License valid..." message briefly
  - Main application loads without activation dialog

#### 3.6 License Status Bar
- [ ] Observe top bar of main window
- [ ] **Expected:**
  - Shows "✅ License: Active (X days)"
  - Color is green if > 7 days remaining
  - Color is yellow if < 1 day remaining
  - Updates periodically

### 4. License Lifecycle Tests

#### 4.1 Activate → Validate → Still Works
- [ ] Create license via bot (30 days)
- [ ] Activate in application
- [ ] Wait 1 minute
- [ ] **Expected:**
  - Application continues running
  - Status bar shows time remaining
  - Periodic validations succeed (check logs)

#### 4.2 Extend License
- [ ] View license in bot
- [ ] Click "⏱ Extend License"
- [ ] Select "+ 30 Days"
- [ ] **Expected:**
  - Success confirmation
  - License info shows new expiration
  - Client application updates (may take up to validation interval)

#### 4.3 Block License
- [ ] View license in bot
- [ ] Click "🚫 Block License"
- [ ] **Expected:**
  - License status changes to BLOCKED
  - Client application detects block within validation interval
  - Error dialog: "Your license is no longer valid"
  - Application exits

#### 4.4 Unblock License
- [ ] In bot, unblock the license
- [ ] Restart client application
- [ ] **Expected:**
  - License validates successfully
  - Application runs normally

#### 4.5 Revoke License
- [ ] View license in bot
- [ ] Click "❌ Revoke License"
- [ ] **Expected:**
  - License status changes to REVOKED
  - Client detects revocation
  - Application exits
  - **Cannot be unblocked** (permanent)

#### 4.6 Expired License
- [ ] Create a 1-minute license via bot (custom duration: "1 minute")
- [ ] Activate in client
- [ ] Wait 2 minutes
- [ ] **Expected:**
  - License expires
  - Client detects expiration
  - Application shows error and exits

### 5. Device Binding Tests

#### 5.1 Single Device Activation
- [ ] Create license (max_devices = 1, default)
- [ ] Activate on first device
- [ ] **Expected:** Activation succeeds

#### 5.2 Device Limit Enforcement
- [ ] Try to activate same license on second device
- [ ] **Expected:**
  - Error: "Device limit reached"
  - Second device cannot activate

#### 5.3 Reset Device
- [ ] In bot, view license
- [ ] Click "🔄 Reset Device"
- [ ] Try activation on second device again
- [ ] **Expected:**
  - First device binding removed
  - Second device can now activate

### 6. Security Tests

#### 6.1 Rate Limiting - Activation
- [ ] Try to activate invalid key 6 times rapidly
- [ ] **Expected:**
  - First 5 attempts: "License not found" or similar
  - 6th attempt: "Too many activation attempts. Please wait..."

#### 6.2 Rate Limiting - Server Side
- [ ] Make many rapid activation requests
- [ ] **Expected:**
  - HTTP 429 (Too Many Requests) after threshold
  - Response includes retry_after

#### 6.3 Cache Tampering Detection
- [ ] Activate a license successfully
- [ ] Close application
- [ ] Edit `%APPDATA%\TelegramMeowGUI\license_cache.dat`
- [ ] Change "expires_at_utc" to future date
- [ ] Run application
- [ ] **Expected:**
  - Cache signature verification fails
  - Application re-validates with server
  - Uses server response (not tampered cache)

#### 6.4 Offline Mode (Grace Period)
- [ ] Activate license successfully
- [ ] Stop license server
- [ ] Run application
- [ ] **Expected:**
  - Application loads using cached license
  - Status shows "⚠️ License valid (offline mode)"
  - Works for grace period duration (default 30 min)

#### 6.5 Grace Period Expiration
- [ ] Keep server stopped for > 30 minutes
- [ ] Try to run application
- [ ] **Expected:**
  - Error: "License server unreachable and grace period expired"
  - Application does not start

#### 6.6 Clock Manipulation Detection
- [ ] Activate license
- [ ] Manually change system clock backward by 1 hour
- [ ] Wait for next validation cycle
- [ ] Check logs
- [ ] **Expected:**
  - Log entry: "Clock manipulation detected"
  - Event logged but application may continue (logged for monitoring)

### 7. Edge Cases

#### 7.1 Network Timeout
- [ ] Configure server URL to unreachable address
- [ ] Try to activate
- [ ] **Expected:**
  - After ~30 seconds: "Server request timeout"
  - Graceful error handling

#### 7.2 Server Restart During Operation
- [ ] Activate license and run application
- [ ] Restart license server
- [ ] Wait for validation interval
- [ ] **Expected:**
  - Temporary validation failure (grace period)
  - Once server is back, validation succeeds
  - Application continues running

#### 7.3 Multiple Activations Same Device
- [ ] Activate license
- [ ] Without closing app, try to activate same license again
- [ ] **Expected:**
  - Returns success
  - Message: "License already activated on this device"

#### 7.4 Very Long License Key
- [ ] Enter 100-character string
- [ ] **Expected:**
  - Input truncated to max length
  - Validation fails gracefully

### 8. Telegram Bot Security Tests

#### 8.1 Unauthorized Callback Manipulation
**Manual test (requires Telegram API knowledge):**
- [ ] Attempt to send callback_data directly to bot
- [ ] **Expected:** Server-side User ID check rejects unauthorized access

#### 8.2 Admin ID Verification
- [ ] Remove your ID from LICENSE_BOT_ADMIN_IDS
- [ ] Restart bot
- [ ] Send /start
- [ ] **Expected:** "Unauthorized" message

### 9. Concurrent Operations

#### 9.1 Multiple Clients Same License
- [ ] Activate license on Device A
- [ ] Simultaneously try to activate on Device B
- [ ] **Expected:**
  - One succeeds
  - Other fails with "device limit" error
  - No race condition

### 10. Data Integrity

#### 10.1 Database Audit Log
- [ ] Perform various operations (create, activate, extend, revoke)
- [ ] Check database: `sqlite3 %APPDATA%\TelegramMeowGUI\licenses.db`
- [ ] Query: `SELECT * FROM audit_log ORDER BY timestamp_utc DESC LIMIT 20;`
- [ ] **Expected:**
  - All operations logged
  - Timestamps accurate
  - Details captured

#### 10.2 Foreign Key Constraints
- [ ] Check database schema
- [ ] Verify foreign keys exist
- [ ] **Expected:**
  - activations.license_id → licenses.id
  - Cascading deletes configured

## Test Data Cleanup

After all tests are complete:

### 1. Clean Database
```sql
DELETE FROM audit_log WHERE action LIKE 'TEST%';
DELETE FROM activations WHERE device_id LIKE 'TEST%';
DELETE FROM licenses WHERE plan LIKE '%Test%';
DELETE FROM rate_limits;
```

### 2. Clean Client Cache
```bash
del %APPDATA%\TelegramMeowGUI\license_cache.dat
del %APPDATA%\TelegramMeowGUI\device_id.dat
```

### 3. Verify Clean State
- [ ] No test licenses remain in bot
- [ ] No test devices in database
- [ ] Client starts fresh (no cached license)

## Known Issues / Limitations

Document any issues found during testing:

1. **Issue:** ___________________
   **Severity:** Low / Medium / High
   **Workaround:** ___________________

2. **Issue:** ___________________
   **Severity:** Low / Medium / High
   **Workaround:** ___________________

## Test Sign-Off

- **Tester Name:** ___________________
- **Date:** ___________________
- **Environment:** Dev / Staging / Production
- **Result:** ☐ All tests passed  ☐ Some tests failed (see issues above)
- **Notes:** ___________________

## Appendix: Quick Commands

### Check Server Status
```bash
curl http://localhost:8765/health
```

### View Database
```bash
sqlite3 %APPDATA%\TelegramMeowGUI\licenses.db
.tables
SELECT * FROM licenses;
SELECT * FROM activations;
SELECT * FROM audit_log ORDER BY timestamp_utc DESC LIMIT 10;
.quit
```

### Generate Test License Key
```python
python -c "from backend.license_server import LicenseServer; s=LicenseServer('test','',0); print(s.generate_license_key())"
```

### Check Logs
```bash
# Server logs (console output)
# Bot logs (console output)
# Client logs (console output or log file if configured)
```
