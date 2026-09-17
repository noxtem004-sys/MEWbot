# راهنمای دیپلوی روی Railway

این راهنما مراحل کامل آپلود و راه‌اندازی سیستم لایسنس روی Railway.com را توضیح می‌دهد.

## پیش‌نیازها

1. حساب کاربری در [Railway.com](https://railway.com)
2. ربات تلگرام (از @BotFather)
3. آیدی تلگرام شما (از @userinfobot)
4. Git نصب شده روی کامپیوتر

---

## مرحله ۱: آماده‌سازی پروژه

### ۱.۱ ساخت کلید امنیتی

دستور زیر را اجرا کنید و خروجی را کپی کنید:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

خروجی مثل این است: `aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdef`

**این کلید را جایی ذخیره کنید** (بعداً لازم است).

### ۱.۲ ساخت ریپازیتوری Git (اختیاری)

اگر پروژه را روی GitHub یا GitLab دارید، از آن استفاده کنید.

اگر نه، یک ریپازیتوری جدید بسازید:

```bash
cd I:\python\TelegramMeowGUI
git init
git add .
git commit -m "Initial commit - License system"
```

---

## مرحله ۲: ساخت پروژه در Railway

### ۲.۱ ورود به Railway

1. به [Railway.com](https://railway.com) بروید
2. "Login" یا "Start a New Project" را بزنید
3. با GitHub یا Email وارد شوید

### ۲.۲ ایجاد پروژه جدید

1. روی **"New Project"** کلیک کنید
2. گزینه **"Deploy from GitHub repo"** را انتخاب کنید (یا "Empty Project")

**اگر GitHub ندارید:**
- "Empty Project" را بزنید
- بعداً با Railway CLI آپلود می‌کنیم

**اگر GitHub دارید:**
- ریپازیتوری خود را انتخاب کنید
- Railway خودکار پروژه را شناسایی می‌کند

---

## مرحله ۳: تنظیم متغیرهای محیطی (Environment Variables)

### ۳.۱ سرویس License Server

1. در Dashboard روی پروژه خود کلیک کنید
2. اگر سرویسی ایجاد نشده، "New" → "Empty Service" بزنید
3. روی سرویس کلیک کنید
4. تب **"Variables"** را باز کنید
5. این متغیرها را اضافه کنید:

```
LICENSE_SERVER_SECRET_KEY=کلید_امنیتی_که_ساختید
LICENSE_SERVER_HOST=0.0.0.0
RAILWAY_ENVIRONMENT=production
```

**نکته:** `PORT` خودکار توسط Railway تنظیم می‌شود.

### ۳.۲ سرویس License Bot (جداگانه)

1. روی **"New"** کلیک کنید
2. **"Empty Service"** را انتخاب کنید  
3. نام سرویس را `license-bot` بگذارید
4. تب **"Variables"** را باز کنید
5. این متغیرها را اضافه کنید:

```
LICENSE_SERVER_SECRET_KEY=همان_کلید_امنیتی
LICENSE_BOT_TOKEN=توکن_ربات_تلگرام_شما
LICENSE_BOT_ADMIN_IDS=آیدی_تلگرام_شما
LICENSE_SERVER_URL=آدرس_سرویس_اول
```

**مهم:** برای `LICENSE_SERVER_URL`:
- اگر هر دو سرویس در یک پروژه هستند، می‌توانید از آدرس داخلی استفاده کنید
- یا از domain عمومی که Railway می‌دهد

---

## مرحله ۴: تنظیم دیپلوی

### ۴.۱ برای سرویس Server:

1. تب **"Settings"** را باز کنید
2. در قسمت **"Deploy"**:
   - **Start Command:** `python backend/license_server.py`
3. در قسمت **"Networking"**:
   - **Generate Domain** را بزنید (یک آدرس عمومی می‌سازد)
   - آدرس مثل: `https://your-project.up.railway.app`

### ۴.۲ برای سرویس Bot:

1. تب **"Settings"** را باز کنید
2. در قسمت **"Deploy"**:
   - **Start Command:** `python backend/license_bot.py`
3. **نیازی به Generate Domain ندارد** (ربات Webhook ندارد)

---

## مرحله ۵: آپلود کد

### روش ۱: از طریق GitHub (توصیه می‌شود)

اگر پروژه را به GitHub متصل کردید:
1. هر تغییری در کد بدهید
2. `git push` کنید
3. Railway خودکار دیپلوی می‌کند

### روش ۲: با Railway CLI

1. نصب Railway CLI:

**Windows:**
```bash
npm i -g @railway/cli
```

**یا:**
```bash
scoop install railway
```

2. لاگین:
```bash
railway login
```

3. لینک کردن پروژه:
```bash
cd I:\python\TelegramMeowGUI
railway link
```

4. دیپلوی:
```bash
railway up
```

---

## مرحله ۶: بررسی لاگ‌ها

### ۶.۱ چک کردن Server

1. سرویس `license-server` را باز کنید
2. تب **"Deployments"** → آخرین دیپلوی
3. لاگ‌ها را ببینید
4. باید ببینید:
```
License Server started on http://0.0.0.0:XXXX
```

### ۶.۲ چک کردن Bot

1. سرویس `license-bot` را باز کنید
2. لاگ‌ها را چک کنید
3. باید ببینید:
```
Authorized admin IDs: [123456789]
```

---

## مرحله ۷: تست سیستم

### ۷.۱ تست Server

در مرورگر یا با `curl`:

```bash
curl https://your-project.up.railway.app/health
```

باید پاسخ بدهد:
```json
{
  "status": "healthy",
  "server": "license_server",
  "timestamp": "..."
}
```

### ۷.۲ تست Bot

1. تلگرام را باز کنید
2. ربات خود را پیدا کنید
3. `/start` را بفرستید
4. منوی مدیریت لایسنس باید ظاهر شود

### ۷.۳ ساخت لایسنس آزمایشی

1. در ربات: **"Create License"** → **"1 Day"**
2. کلید لایسنس را کپی کنید
3. برنامه کلاینت را روی سیستم خود اجرا کنید:

فایل `.env` کلاینت:
```
LICENSE_SERVER_URL=https://your-project.up.railway.app
LICENSE_SERVER_SECRET_KEY=همان_کلید_امنیتی
```

4. `python app.py` را اجرا کنید
5. کلید را وارد کنید
6. باید فعال شود ✅

---

## مرحله ۸: تنظیم دیتابیس (مهم!)

### ۸.۱ نصب Railway Volume

Railway به صورت پیش‌فرض فایل‌ها را در هر دیپلوی پاک می‌کند.

برای ذخیره دیتابیس:

1. سرویس `license-server` را باز کنید
2. تب **"Data"** یا **"Volumes"** را بزنید
3. **"New Volume"** را بزنید
4. Mount Path: `/app/data`
5. ذخیره کنید

### ۸.۲ تغییر مسیر دیتابیس

فایل `backend/license_database.py` را ویرایش کنید:

```python
# قبل:
LICENSE_DB_PATH: str = str(app_data_dir() / "licenses.db")

# بعد:
import os
LICENSE_DB_PATH: str = os.environ.get(
    'LICENSE_DB_PATH',
    str(app_data_dir() / "licenses.db")
)
```

سپس در Railway، متغیر اضافه کنید:
```
LICENSE_DB_PATH=/app/data/licenses.db
```

**یا ساده‌تر:** از Railway Postgres استفاده کنید:

1. **"New"** → **"Database"** → **"PostgreSQL"**
2. کد را برای استفاده از PostgreSQL تغییر دهید (نیاز به تغییرات)

---

## مرحله ۹: پشتیبان‌گیری خودکار

### ۹.۱ دانلود دیتابیس

با Railway CLI:

```bash
railway run python -c "
import shutil
from backend.license_database import LICENSE_DB_PATH
shutil.copy(LICENSE_DB_PATH, 'backup_licenses.db')
"
```

سپس دانلود کنید:
```bash
railway run cat backup_licenses.db > local_backup.db
```

### ۹.۲ تنظیم Cron Job (پیشرفته)

می‌توانید یک سرویس جداگانه برای backup بسازید که روزانه اجرا شود.

---

## تنظیمات پیشرفته

### Custom Domain

1. یک دامنه بخرید (مثل `license.yourdomain.com`)
2. در Railway: **"Settings"** → **"Networking"** → **"Custom Domain"**
3. دامنه را اضافه کنید
4. DNS را تنظیم کنید (CNAME به Railway)
5. SSL خودکار فعال می‌شود

### Environment ها

می‌توانید چند Environment بسازید:
- **Production**: سرور اصلی
- **Staging**: تست
- **Development**: توسعه

هر کدام متغیرهای جداگانه دارند.

### مانیتورینگ

Railway لاگ‌ها را نگه می‌دارد، اما برای مانیتورینگ بهتر:
- [Sentry](https://sentry.io) برای error tracking
- [Better Stack](https://betterstack.com) برای لاگ‌ها
- [UptimeRobot](https://uptimerobot.com) برای uptime monitoring

---

## هزینه‌ها

Railway قیمت‌گذاری Pay-as-you-go دارد:

- **Trial:** $5 credit رایگان
- **Hobby Plan:** $5/ماه
- **Pro Plan:** $20/ماه

برای این پروژه:
- **2 سرویس** (Server + Bot)
- **1 دیتابیس** (SQLite Volume یا Postgres)
- تخمین: **$5-10/ماه**

---

## رفع مشکلات

### خطا: "Module not found"

**راه حل:**
- فایل `requirements.txt` را چک کنید
- مطمئن شوید همه پکیج‌ها لیست شده‌اند

### خطا: "DATABASE_URL not set"

**راه حل:**
- مطمئن شوید Volume درست mount شده
- یا متغیر `LICENSE_DB_PATH` را set کنید

### خطا: "Port already in use"

**راه حل:**
- Railway خودکار `PORT` را set می‌کند
- در کد باید از `os.environ.get('PORT')` استفاده کنید

### Bot جواب نمی‌دهد

**راه حل:**
1. لاگ‌های bot را چک کنید
2. مطمئن شوید `LICENSE_BOT_TOKEN` درست است
3. مطمئن شوید `LICENSE_SERVER_URL` به server اشاره می‌کند

### Server در دسترس نیست

**راه حل:**
1. Domain را Generate کرده‌اید؟
2. لاگ‌ها چه می‌گویند؟
3. Health endpoint را تست کنید

---

## چک‌لیست دیپلوی

- [ ] حساب Railway ساخته شده
- [ ] پروژه در Railway ایجاد شده
- [ ] متغیرهای محیطی تنظیم شده
- [ ] کد آپلود شده
- [ ] Server سرویس اجرا می‌شود
- [ ] Bot سرویس اجرا می‌شود
- [ ] Domain فعال شده
- [ ] Health endpoint پاسخ می‌دهد
- [ ] Bot در تلگرام جواب می‌دهد
- [ ] لایسنس تستی ساخته و فعال شد
- [ ] Volume برای دیتابیس تنظیم شده
- [ ] پشتیبان‌گیری راه‌اندازی شده

---

## ساختار نهایی Railway

```
Railway Project: TelegramMeowGUI-License
├── Service: license-server
│   ├── Environment Variables
│   │   ├── LICENSE_SERVER_SECRET_KEY
│   │   ├── LICENSE_SERVER_HOST=0.0.0.0
│   │   └── LICENSE_DB_PATH=/app/data/licenses.db
│   ├── Volume: /app/data
│   └── Domain: https://your-project.up.railway.app
│
└── Service: license-bot
    └── Environment Variables
        ├── LICENSE_SERVER_SECRET_KEY
        ├── LICENSE_BOT_TOKEN
        ├── LICENSE_BOT_ADMIN_IDS
        └── LICENSE_SERVER_URL=https://your-project.up.railway.app
```

---

## بعد از دیپلوی

### برای مشتریان

فایل `.env` کلاینت آن‌ها:

```bash
LICENSE_SERVER_URL=https://your-project.up.railway.app
LICENSE_SERVER_SECRET_KEY=همان_کلید_امنیتی_شما
LICENSE_VALIDATION_INTERVAL=300
LICENSE_GRACE_PERIOD=1800
```

### پشتیبانی

1. **لاگ‌ها را مانیتور کنید** (Railway Dashboard)
2. **آمار را چک کنید** (ربات تلگرام → Statistics)
3. **پشتیبان‌گیری منظم** (هر روز)
4. **بروزرسانی امنیتی** (هر ماه dependencies را آپدیت کنید)

---

## لینک‌های مفید

- [Railway Documentation](https://docs.railway.app)
- [Railway CLI](https://docs.railway.app/develop/cli)
- [Railway Discord](https://discord.gg/railway) - برای کمک

---

**تبریک! سیستم لایسنس شما روی Railway در حال اجراست** 🚀

برای سؤالات بیشتر، به مستندات `LICENSE_SYSTEM_README.md` مراجعه کنید.
