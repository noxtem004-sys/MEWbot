# دیپلوی سریع روی Railway

## گام ۱: کلید امنیتی بسازید

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

کلید را کپی کنید.

## گام ۲: روی Railway دیپلوی کنید

### با یک کلیک (Deploy Button):

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

### یا دستی:

1. در Railway: **New Project** → **Deploy from GitHub repo**
2. ریپازیتوری را انتخاب کنید

## گام ۳: متغیرها را تنظیم کنید

### سرویس Server:

```
LICENSE_SERVER_SECRET_KEY=کلید_شما
LICENSE_SERVER_HOST=0.0.0.0
```

### سرویس Bot (سرویس جداگانه):

```
LICENSE_SERVER_SECRET_KEY=همان_کلید
LICENSE_BOT_TOKEN=توکن_ربات_تلگرام
LICENSE_BOT_ADMIN_IDS=آیدی_تلگرام_شما
LICENSE_SERVER_URL=https://your-server.up.railway.app
```

## گام ۴: Generate Domain

در سرویس Server:
- Settings → Networking → Generate Domain

## گام ۵: تست کنید

```bash
curl https://your-domain.up.railway.app/health
```

## مستندات کامل

برای راهنمای کامل، فایل `RAILWAY_DEPLOYMENT.md` را ببینید.

---

## ساختار فایل‌ها برای Railway

```
.
├── Procfile                    # Railway process definitions
├── runtime.txt                 # Python version
├── requirements.txt            # Python dependencies
├── railway.toml               # Railway configuration
├── backend/
│   ├── license_server.py      # Main server
│   ├── license_bot.py         # Telegram bot
│   └── license_database.py    # Database
└── RAILWAY_DEPLOYMENT.md      # Full guide (Persian)
```

## نیازمندی‌ها

- Python 3.11+
- حساب Railway
- ربات تلگرام
- کلید امنیتی

## پشتیبانی

برای سؤالات و مشکلات، به فایل `RAILWAY_DEPLOYMENT.md` مراجعه کنید.
