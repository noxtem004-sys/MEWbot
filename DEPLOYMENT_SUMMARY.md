# خلاصه آماده‌سازی برای Railway

## ✅ فایل‌های ایجاد شده برای Railway

### فایل‌های اصلی:
- ✅ `Procfile` - تعریف process ها
- ✅ `runtime.txt` - نسخه پایتون
- ✅ `railway.toml` - تنظیمات Railway
- ✅ `.gitignore` - فایل‌های نادیده گرفته شده
- ✅ `requirements.txt` - وابستگی‌های پایتون (قبلاً موجود بود)

### اسکریپت‌های کمکی:
- ✅ `start_services.py` - اجرای همزمان سرور و بات
- ✅ `check_deployment_ready.py` - چک آمادگی دیپلوی

### مستندات:
- ✅ `RAILWAY_DEPLOYMENT.md` - راهنمای کامل فارسی
- ✅ `RAILWAY_QUICKSTART_FA.md` - راهنمای سریع ۱۰ دقیقه‌ای
- ✅ `README_RAILWAY.md` - خلاصه Railway
- ✅ `railway-template.json` - Template برای دیپلوی یک‌کلیکه

---

## 📋 چک‌لیست آمادگی

### ✅ همه چیز آماده است!

```
✅ requirements.txt (required)
✅ Procfile (required)
✅ runtime.txt (optional)
✅ railway.toml (optional)
✅ backend/license_server.py (required)
✅ backend/license_bot.py (required)
✅ backend/license_database.py (required)
✅ core/license_client.py (required)
✅ .gitignore (optional)
✅ .env.example (optional)
✅ RAILWAY_DEPLOYMENT.md (optional)

✅ aiogram found in requirements.txt
✅ aiohttp found in requirements.txt
✅ aiosqlite found in requirements.txt
✅ cryptography found in requirements.txt

✅ LICENSE_SERVER_SECRET_KEY documented
✅ LICENSE_BOT_TOKEN documented
✅ LICENSE_BOT_ADMIN_IDS documented

✅ .env is in .gitignore
✅ *.db is in .gitignore
```

---

## 🚀 مراحل دیپلوی (خلاصه)

### مرحله ۱: آماده‌سازی (۱ دقیقه)

```bash
# ساخت کلید امنیتی
python -c "import secrets; print(secrets.token_urlsafe(32))"

# چک آمادگی
python check_deployment_ready.py
```

### مرحله ۲: GitHub (۲ دقیقه)

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/repo.git
git push -u origin main
```

### مرحله ۳: Railway (۵ دقیقه)

1. New Project → Deploy from GitHub
2. تنظیم Variables برای Server
3. ساخت سرویس دوم برای Bot
4. تنظیم Variables برای Bot
5. Generate Domain برای Server

### مرحله ۴: تست (۲ دقیقه)

```bash
curl https://your-domain.up.railway.app/health
```

---

## 🔧 متغیرهای محیطی

### سرویس License Server:
```env
LICENSE_SERVER_SECRET_KEY=your_secret_key_here
LICENSE_SERVER_HOST=0.0.0.0
```

### سرویس License Bot:
```env
LICENSE_SERVER_SECRET_KEY=همان_کلید
LICENSE_BOT_TOKEN=bot_token_from_botfather
LICENSE_BOT_ADMIN_IDS=123456789
LICENSE_SERVER_URL=https://your-domain.up.railway.app
```

---

## 📁 ساختار پروژه Railway

```
Railway Project
├── Service 1: license-server
│   ├── Start Command: python backend/license_server.py
│   ├── Environment Variables (3)
│   ├── Domain: https://xxx.up.railway.app
│   └── Volume: /app/data (اختیاری)
│
└── Service 2: license-bot
    ├── Start Command: python backend/license_bot.py
    ├── Environment Variables (4)
    └── No domain needed
```

---

## 📖 راهنماهای موجود

| فایل | توضیح | زمان مطالعه |
|------|-------|-------------|
| `RAILWAY_QUICKSTART_FA.md` | راهنمای سریع ۱۰ دقیقه‌ای | ۵ دقیقه |
| `RAILWAY_DEPLOYMENT.md` | راهنمای کامل با جزئیات | ۲۰ دقیقه |
| `README_RAILWAY.md` | خلاصه Railway | ۲ دقیقه |
| `.env.example` | نمونه تنظیمات | ۱ دقیقه |

---

## 🎯 توصیه‌ها

### برای شروع سریع:
👉 **ابتدا بخوانید:** `RAILWAY_QUICKSTART_FA.md`

### برای یادگیری کامل:
👉 **بخوانید:** `RAILWAY_DEPLOYMENT.md`

### برای رفع مشکل:
👉 **چک کنید:** لاگ‌های Railway Dashboard

---

## 🔒 نکات امنیتی

### ✅ انجام شده:
- `.env` در `.gitignore`
- `*.db` در `.gitignore`
- کلید امنیتی در environment variable
- سرور روی `0.0.0.0` bind می‌شود

### ⚠️ قبل از production:
- [ ] کلید امنیتی قوی بسازید
- [ ] Volume برای دیتابیس تنظیم کنید
- [ ] پشتیبان‌گیری روزانه راه‌اندازی کنید
- [ ] Custom domain (اختیاری)
- [ ] HTTPS فعال است (Railway خودکار فعال می‌کند)

---

## 💰 هزینه‌ها

**Railway Pricing:**
- Trial: $5 رایگان
- Hobby: $5/ماه
- **این پروژه:** ~$5-10/ماه

**شامل:**
- 2 سرویس (Server + Bot)
- 1 Volume (برای دیتابیس)
- SSL رایگان
- Domain رایگان

---

## 🆘 پشتیبانی

### مشکل دارید؟

1. **لاگ‌های Railway:**
   ```
   Dashboard → Service → Deployments → View Logs
   ```

2. **تست محلی:**
   ```bash
   python tests/test_license_system.py
   ```

3. **چک آمادگی:**
   ```bash
   python check_deployment_ready.py
   ```

4. **مستندات:**
   - `RAILWAY_DEPLOYMENT.md`
   - `LICENSE_SYSTEM_README.md`

---

## ✨ آماده دیپلوی!

پروژه شما **۱۰۰٪ آماده** برای دیپلوی روی Railway است.

### دستورات نهایی:

```bash
# چک آمادگی
python check_deployment_ready.py

# ساخت کلید امنیتی
python -c "import secrets; print(secrets.token_urlsafe(32))"

# آپلود روی GitHub
git init
git add .
git commit -m "Ready for Railway deployment"
git push

# سپس در Railway:
# New Project → Deploy from GitHub → انتخاب repo
```

---

## 📞 لینک‌های مفید

- [Railway Dashboard](https://railway.app/dashboard)
- [Railway Docs](https://docs.railway.app)
- [Railway Discord](https://discord.gg/railway)
- [Railway CLI](https://docs.railway.app/develop/cli)

---

**موفق باشید! 🚀**

برای شروع سریع، فایل `RAILWAY_QUICKSTART_FA.md` را باز کنید.
