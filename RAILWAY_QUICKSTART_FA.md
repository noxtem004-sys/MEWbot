# راهنمای سریع دیپلوی روی Railway (۱۰ دقیقه)

## قبل از شروع

این موارد را آماده کنید:

- [ ] حساب [Railway.com](https://railway.com)
- [ ] حساب [GitHub](https://github.com) (اختیاری ولی توصیه می‌شود)
- [ ] ربات تلگرام از [@BotFather](https://t.me/BotFather)
- [ ] آیدی تلگرام از [@userinfobot](https://t.me/userinfobot)

---

## مرحله ۱: کلید امنیتی بسازید (۳۰ ثانیه)

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**خروجی را کپی کنید** و جایی ذخیره کنید. مثل:
```
aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdef
```

---

## مرحله ۲: کد را روی GitHub آپلود کنید (۲ دقیقه)

### روش ۱: از طریق GitHub Desktop (ساده)

1. [GitHub Desktop](https://desktop.github.com) را نصب کنید
2. باز کنید و **"Add Local Repository"**
3. پوشه `I:\python\TelegramMeowGUI` را انتخاب کنید
4. **"Publish repository"** را بزنید
5. نام: `telegram-meow-license`
6. **Private** را تیک بزنید (امنیت بیشتر)
7. Publish کنید

### روش ۲: از طریق Git (پیشرفته)

```bash
cd I:\python\TelegramMeowGUI
git init
git add .
git commit -m "Initial commit - License system"
git remote add origin https://github.com/YOUR_USERNAME/telegram-meow-license.git
git push -u origin main
```

---

## مرحله ۳: دیپلوی روی Railway (۵ دقیقه)

### ۳.۱ ایجاد پروژه

1. به [Railway.com](https://railway.com) بروید
2. **"Login"** → با GitHub وارد شوید
3. **"New Project"**
4. **"Deploy from GitHub repo"**
5. ریپازیتوری `telegram-meow-license` را انتخاب کنید

### ۳.۲ تنظیم سرویس اول (License Server)

Railway خودکار یک سرویس می‌سازد:

1. روی سرویس کلیک کنید
2. **"Variables"** را باز کنید
3. این متغیرها را اضافه کنید:

```
LICENSE_SERVER_SECRET_KEY=کلید_امنیتی_که_ساختید
LICENSE_SERVER_HOST=0.0.0.0
```

4. **"Settings"** → **"Networking"** → **"Generate Domain"**
5. دامنه را کپی کنید (مثل `https://xxx.up.railway.app`)

### ۳.۳ ساخت سرویس دوم (License Bot)

1. در پروژه، **"New"** → **"GitHub Repo"**
2. همان ریپازیتوری را انتخاب کنید
3. **"Variables"** را باز کنید
4. این متغیرها را اضافه کنید:

```
LICENSE_SERVER_SECRET_KEY=همان_کلید_امنیتی
LICENSE_BOT_TOKEN=توکن_ربات_تلگرام_شما
LICENSE_BOT_ADMIN_IDS=آیدی_تلگرام_شما
LICENSE_SERVER_URL=https://xxx.up.railway.app
```

(در `LICENSE_SERVER_URL` دامنه سرویس اول را بگذارید)

5. **"Settings"** → **"Deploy"**
6. Start Command: `python backend/license_bot.py`

---

## مرحله ۴: تست (۲ دقیقه)

### ۴.۱ تست Server

در مرورگر:
```
https://xxx.up.railway.app/health
```

باید ببینید:
```json
{"status": "healthy"}
```

### ۴.۲ تست Bot

1. تلگرام را باز کنید
2. ربات خود را پیدا کنید
3. `/start` را بفرستید
4. منو باید ظاهر شود

### ۴.۳ ساخت لایسنس

1. در ربات: **"Create License"**
2. **"1 Day"** را انتخاب کنید
3. کلید را کپی کنید

### ۴.۴ تست در برنامه

روی کامپیوتر خود:

فایل `.env` بسازید:
```
LICENSE_SERVER_URL=https://xxx.up.railway.app
LICENSE_SERVER_SECRET_KEY=همان_کلید_امنیتی
```

اجرا:
```bash
python app.py
```

کلید را وارد کنید → باید فعال شود ✅

---

## تمام! 🎉

سیستم لایسنس شما روی Railway در حال اجراست.

### چیزهایی که باید بدانید:

**✅ Server شما آنلاین است:**
- آدرس: `https://xxx.up.railway.app`
- مشتریان باید این آدرس را در فایل `.env` خود بگذارند

**✅ Bot شما در حال کار است:**
- از طریق تلگرام لایسنس بسازید
- مدیریت کامل لایسنس‌ها

**✅ دیتابیس:**
- خودکار ذخیره می‌شود
- نیاز به Volume دارد (مرحله بعد)

---

## مرحله بعدی: تنظیم دیتابیس (اختیاری)

برای اینکه دیتابیس در هر دیپلوی پاک نشود:

1. سرویس **license-server** را باز کنید
2. **"Data"** یا **"Volumes"**
3. **"New Volume"**
4. Mount Path: `/app/data`

سپس در Variables اضافه کنید:
```
LICENSE_DB_PATH=/app/data/licenses.db
```

---

## هزینه

Railway قیمت‌گذاری:
- **Trial:** $5 رایگان
- **Hobby:** $5/ماه
- **برای این پروژه:** حدود $5-10/ماه

---

## پشتیبانی

مشکل دارید؟

1. **لاگ‌ها را چک کنید:**
   - Railway Dashboard → سرویس → Deployments → View Logs

2. **مستندات کامل:**
   - `RAILWAY_DEPLOYMENT.md` (فارسی، کامل)

3. **تست سیستم:**
   ```bash
   python tests/test_license_system.py
   ```

---

## دستورات مفید

### مشاهده لاگ‌های Railway
```bash
railway logs
```

### دیپلوی جدید
```bash
git push origin main
```
(Railway خودکار دیپلوی می‌کند)

### دانلود دیتابیس
```bash
railway run cat /app/data/licenses.db > backup.db
```

---

## چک‌لیست نهایی

- [x] ✅ پروژه روی GitHub
- [x] ✅ دو سرویس در Railway
- [x] ✅ متغیرها تنظیم شده
- [x] ✅ Domain فعال
- [x] ✅ Health endpoint کار می‌کند
- [x] ✅ Bot جواب می‌دهد
- [x] ✅ لایسنس تستی فعال شد
- [ ] 🔄 Volume برای دیتابیس (اختیاری)
- [ ] 🔄 Custom domain (اختیاری)
- [ ] 🔄 Backup روزانه (اختیاری)

---

**موفق باشید!** 🚀

برای سؤالات بیشتر: `RAILWAY_DEPLOYMENT.md`
