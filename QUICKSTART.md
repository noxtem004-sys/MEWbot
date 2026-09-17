# License System Quick Start Guide

This guide will get you up and running with the license system in under 10 minutes.

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Configure Environment

Create a `.env` file in the project root:

```bash
copy .env.example .env
```

Edit `.env` and set these **required** values:

```bash
# Generate a secure secret key
LICENSE_SERVER_SECRET_KEY=your_secure_secret_key_here

# Get from @BotFather on Telegram
LICENSE_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Get from @userinfobot on Telegram
LICENSE_BOT_ADMIN_IDS=123456789

# Server URL (use your public IP for production)
LICENSE_SERVER_URL=http://localhost:8765
```

### Generate Secure Secret Key

Run this to generate a secure key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output and paste it as `LICENSE_SERVER_SECRET_KEY`.

## Step 3: Start the License Server

Open a terminal and run:

```bash
python backend/license_server.py
```

You should see:
```
License Server started on http://0.0.0.0:8765
```

**Keep this terminal open.**

## Step 4: Start the Telegram Bot

Open a **new** terminal and run:

```bash
python backend/license_bot.py
```

You should see:
```
Authorized admin IDs: [123456789]
```

**Keep this terminal open.**

## Step 5: Create Your First License

1. Open Telegram
2. Find your bot (search for the bot username you created with @BotFather)
3. Send `/start`
4. Click **➕ Create License**
5. Click **30 Days** (or any plan)
6. Copy the license key shown (format: XXXX-XXXX-XXXX-XXXX)

## Step 6: Test the Client Application

Open a **third** terminal and run:

```bash
python app.py
```

You should see:
1. License activation dialog
2. Paste your license key
3. Click "Activate License"
4. Main application loads

**Success!** The license system is working.

## Common Issues

### Issue: "LICENSE_SERVER_SECRET_KEY not set"

**Solution:** Create the `.env` file and set the secret key.

### Issue: "License server unreachable"

**Solution:** 
- Make sure the license server is running (Step 3)
- Check that `LICENSE_SERVER_URL` in `.env` matches the server address

### Issue: "Unauthorized" in Telegram bot

**Solution:**
- Make sure your Telegram User ID is in `LICENSE_BOT_ADMIN_IDS`
- Get your ID from @userinfobot on Telegram
- Restart the bot after changing `.env`

### Issue: Can't connect from another computer

**Solution:**
- Change `LICENSE_SERVER_HOST` to `0.0.0.0` (default)
- Use your server's public IP in `LICENSE_SERVER_URL`
- Check firewall rules (port 8765 must be open)

## Next Steps

- Read [LICENSE_SYSTEM_README.md](LICENSE_SYSTEM_README.md) for complete documentation
- Run tests: `python tests/test_license_system.py`
- Review [TESTING_CHECKLIST.md](TESTING_CHECKLIST.md) for manual testing

## Production Deployment

For production use:

1. **Use HTTPS** - Never use HTTP in production
2. **Strong secret key** - Generate with `secrets.token_urlsafe(32)`
3. **Secure the server** - Firewall, rate limiting, monitoring
4. **Backup database** - Regular backups of `licenses.db`
5. **Environment variables** - Don't commit secrets to git

See [LICENSE_SYSTEM_README.md](LICENSE_SYSTEM_README.md) section "Security Best Practices" for details.

## Architecture Overview

```
┌─────────────────┐
│  Telegram Bot   │  ← You create/manage licenses here
│  (Admin Only)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ License Server  │  ← Central authority for validation
│   (aiohttp)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Database     │  ← Stores licenses, activations, audit logs
│    (SQLite)     │
└─────────────────┘
         ▲
         │
┌────────┴────────┐
│ Client App      │  ← Customer runs this
│  (PySide6)      │
└─────────────────┘
```

## File Structure

```
TelegramMeowGUI/
├── backend/
│   ├── license_server.py      # REST API server
│   ├── license_bot.py          # Telegram bot
│   └── license_database.py     # Database operations
├── core/
│   ├── license_client.py       # Client-side validation
│   └── security_utils.py       # Security hardening
├── gui/
│   └── pages/
│       └── license_activation_page.py  # Activation UI
├── tests/
│   └── test_license_system.py  # Test suite
├── .env.example                # Configuration template
├── LICENSE_SYSTEM_README.md    # Full documentation
├── QUICKSTART.md               # This file
└── TESTING_CHECKLIST.md        # Manual testing guide
```

## Support

If you encounter issues:

1. Check the logs (server, bot, client)
2. Review [LICENSE_SYSTEM_README.md](LICENSE_SYSTEM_README.md) troubleshooting section
3. Run automated tests: `python tests/test_license_system.py`
4. Check database: `sqlite3 %APPDATA%\TelegramMeowGUI\licenses.db`

## License System Features

✅ Server-side validation (security authority on server)  
✅ Telegram bot management (11 admin functions)  
✅ Device binding (limit activations per license)  
✅ Periodic validation (detects revoked licenses)  
✅ Grace period (30 min offline tolerance)  
✅ HMAC-signed responses (prevents tampering)  
✅ Rate limiting (prevents brute force)  
✅ Audit logging (tracks all operations)  
✅ Clock manipulation detection  
✅ Professional GUI (auto-formatting input)  
✅ Comprehensive testing (29 automated tests)  

---

**You're all set!** The license system is ready to protect your application.
