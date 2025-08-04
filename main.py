import telebot
from telebot import types
import sqlite3
import random
import string
import threading
import time
import re
from collections import defaultdict
from datetime import datetime, timedelta
import uuid
import math
import requests
import os

# توکن ربات
TOKEN = '7255407869:AAFPh33cnOEaCLPuoAqPk-5rwZ5ROhpinuM'
bot = telebot.TeleBot(TOKEN)

# اتصال به دیتابیس
conn = sqlite3.connect('chatbot.db', check_same_thread=False)
cursor = conn.cursor()

# عکس پروفایل پیش‌فرض
DEFAULT_PROFILE_PHOTO = 'AgACAgQAAxkBAAIB-miNPoj2J9fsD0j1BYPKCXK7RLopAAJwyDEbghBpUHUt7K43mxe5AQADAgADeAADNgQ'

# ایجاد جدول کاربران (بدون مقدار پیش‌فرض برای profile_photo)
# اضافه کردن ستون last_online به جدول users
# ایجاد جدول users
cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            gender TEXT,
            followers_count INTEGER DEFAULT 0,
            following_count INTEGER DEFAULT 0,
            province TEXT,
            city TEXT,
            age INTEGER,
            likes_count INTEGER DEFAULT 0,
            chat_id INTEGER,
            unique_id TEXT,
            status TEXT DEFAULT 'idle',
            partner_id INTEGER,
            profile_photo TEXT,
            coins INTEGER DEFAULT 10,
            private_chat_enabled INTEGER DEFAULT 0,
            latitude REAL,
            longitude REAL,
            last_online DATETIME
        )
    ''')

# ایجاد جدول block
cursor.execute('''
        CREATE TABLE IF NOT EXISTS block (
            blocker_id INTEGER,
            blocked_id INTEGER,
            PRIMARY KEY (blocker_id, blocked_id)
        )
    ''')
conn.commit()
cursor.close()

cursor = conn.cursor()
# ایجاد جدول referrals اگه وجود نداشته باشه
cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        user_id INTEGER PRIMARY KEY,
        referral_code TEXT UNIQUE,
        referral_count INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
''')
conn.commit()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS payments (
        payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        coins INTEGER,
        authority TEXT,
        status TEXT DEFAULT 'pending',
        created_at DATETIME,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
''')
conn.commit()


# تابع برای آپدیت زمان آخرین فعالیت
def update_last_online(user_id):
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_online = ? WHERE user_id = ?",
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
    conn.commit()
    cursor.close()


# تابع برای فرمت کردن زمان آخرین فعالیت
def format_last_online(last_online):
    if not last_online:
        return "هرگز آنلاین نبوده"
    last_online_time = datetime.strptime(last_online, '%Y-%m-%d %H:%M:%S')
    now = datetime.now()
    diff = now - last_online_time
    minutes = diff.total_seconds() / 60
    if minutes < 5:
        return "هم اکنون آنلاین"
    elif minutes < 60:
        return f"{int(minutes)} دقیقه پیش"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)} ساعت پیش"
    days = hours / 24
    return f"{int(days)} روز پیش"


# آپدیت کاربران موجود که profile_photo نامعتبر دارن
cursor.execute("UPDATE users SET profile_photo = ? WHERE profile_photo IS NULL OR profile_photo = ''",
               (DEFAULT_PROFILE_PHOTO,))
conn.commit()

# ایجاد جدول لایک‌ها
cursor.execute('''
CREATE TABLE IF NOT EXISTS likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    target_id INTEGER,
    UNIQUE(user_id, target_id),
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    FOREIGN KEY(target_id) REFERENCES users(user_id)
)
''')
conn.commit()
# ایجاد جدول تاریخچه‌ی چت‌ها
cursor.execute('''
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    partner_id INTEGER,
    chat_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    FOREIGN KEY(partner_id) REFERENCES users(user_id)
)
''')
conn.commit()

# لیست استان‌ها و شهرها
provinces = [
    "آذربایجا شرقی", "آذربایجا غربی", "اردبیل", "اصفهان", "البرز", "ایلام", "بوشهر", "تهران",
    "چهارمحال و بختیاری", "خراسان جنوبی", "خراسان رضوی", "خراسان شمالی", "خوزستان", "زنجان",
    "سمنان", "سیستان و بلوچستان", "فارس", "قزوین", "قم", "کردستان", "کرمان", "کرمانشاه",
    "کهگیلویه و بویراحمد", "گلستان", "گیلان", "لرستان", "مازندران", "مرکزی", "هرمزگان", "همدان", "یزد"
]

cities_by_province = {
    "آذربایجا شرقی": ["تبریز", "مراغه", "مرند", "اهر", "میانه", "بناب", "سراب", "هادیشهر", "جلفا", "کلیبر"],
    "آذربایجا غربی": ["ارومیه", "خوی", "مهاباد", "میاندوآب", "سلماس", "نقده", "پیرانشهر", "شاهین دژ", "تکاب", "ماکو"],
    "اردبیل": ["اردبیل", "پارس آباد", "مشگین شهر", "خلخال", "گرمی", "بیله سوار", "نمین", "نیر", "کوثر", "سرعین"],
    "اصفهان": ["اصفهان", "کاشان", "خمینی شهر", "نجف آباد", "شاهین شهر", "شهرضا", "فولادشهر", "بهارستان", "مبارکه",
               "آران و بیدگل"],
    "البرز": ["کرج", "فردیس", "کمال شهر", "نظرآباد", "محمدشهر", "ماهدشت", "مشکین دشت", "هشتگرد", "چهارباغ",
              "شهر جدید هشتگرد"],
    "ایلام": ["ایلام", "ایوان", "دهلران", "آبدانان", "دره شهر", "مهران", "سرابله", "ارکواز", "آسمان آباد", "چوار"],
    "بوشهر": ["بوشهر", "برازجان", "بندر گناوه", "بندر کنگان", "خورموج", "جم", "بندر دیلم", "بندر دیر", "عالی شهر",
              "آب پخش"],
    "تهران": ["تهران", "اسلامشهر", "شهریار", "قدس", "ملارد", "گلستان", "پاکدشت", "ری", "قرچک", "ورامین"],
    "چهارمحال و بختیاری": ["شهرکرد", "بروجن", "لردگان", "فرخشهر", "فارسان", "هفشجان", "جونقان", "سامان", "فرادنبه",
                           "بن"],
    "خراسان جنوبی": ["بیرجند", "قائن", "طبس", "فردوس", "نهبندان", "سرایان", "بشرویه", "سر بیشه", "خوسف", "درمیان"],
    "خراسان رضوی": ["مشهد", "نیشابور", "سبزوار", "تربت حیدریه", "کاشمر", "قوچان", "تربت جام", "تایباد", "چناران",
                    "سرخس"],
    "خراسان شمالی": ["بجنورد", "شیروان", "اسفراین", "آشخانه", "جاجرم", "فاروج", "گرمه", "راز", "پیش قلعه", "صفی آباد"],
    "خوزستان": ["اهواز", "دزفول", "آبادان", "خرمشهر", "اندیمشک", "بهبهان", "ماهشهر", "شوشتر", "ایذه", "شوش"],
    "زنجان": ["زنجان", "ابهر", "خدابنده", "طارم", "خرمدره", "سلطانیه", "هیدج", "صائین قلعه", "زرین آباد", "چورزق"],
    "سمنان": ["سمنان", "شاهرود", "دامغان", "گرمسار", "مهدی شهر", "سرخه", "ایوانکی", "آرادان", "بسطام", "بیارجمند"],
    "سیستان و بلوچستان": ["زاهدان", "زابل", "ایرانشهر", "چابهار", "سراوان", "خاش", "کنارک", "نیک شهر", "راسک",
                          "میرجاوه"],
    "فارس": ["شیراز", "مرودشت", "جهرم", "فسا", "کازرون", "صدرا", "داراب", "فیروزآباد", "لار", "آباده"],
    "قزوین": ["قزوین", "تاکستان", "الوند", "بویین زهرا", "آبیک", "محمودآباد نمونه", "محمدیه", "بیدستان", "شال",
              "دانسفهان"],
    "قم": ["قم", "قنوات", "جعفریه", "کهک", "دستجرد", "سلفچگان"],
    "کردستان": ["سنندج", "سقز", "مریوان", "بانه", "قروه", "کامیاران", "بیجار", "دیواندره", "دهگلان", "سریش آباد"],
    "کرمان": ["کرمان", "سیرجان", "رفسنجان", "جیرفت", "بم", "زرند", "کهنوج", "شهر بابک", "بافت", "بردسیر"],
    "کرمانشاه": ["کرمانشاه", "اسلام آباد غرب", "جوانرود", "کنگاور", "هرسین", "سرپل ذهاب", "سنقر", "صحنه", "گیلان غرب",
                 "پاوه"],
    "کهگیلویه و بویراحمد": ["یاسوج", "دوگنبدان", "سی سخت", "دهدشت", "لیکک", "چرام", "باشت", "مادوان", "پاتاوه",
                            "مارگون"],
    "گلستان": ["گرگان", "گنبد کاووس", "علی آباد کتول", "بندر ترکمن", "آزادشهر", "کردکوی", "کلاله", "آق قلا", "مینودشت",
               "گالیکش"],
    "گیلان": ["رشت", "بندر انزلی", "لاهیجان", "لنگرود", "هشتپر", "آستارا", "صومعه سرا", "آستانه اشرفیه", "رودسر",
              "فومن"],
    "لرستان": ["خرم آباد", "بروجرد", "دورود", "الیگودرز", "کوهدشت", "نورآباد", "ازنا", "الشتر", "پلدختر", "سپیددشت"],
    "مازندران": ["ساری", "بابل", "آمل", "قائم شهر", "بهشهر", "چالوس", "نوشهر", "تنکابن", "رامسر", "محمودآباد"],
    "مرکزی": ["اراک", "ساوه", "خمین", "محلات", "دلیجان", "زرندیه", "شازند", "آشتیان", "تفرش", "کمیجان"],
    "هرمزگان": ["بندرعباس", "میناب", "قشم", "کیش", "رودان", "بندر لنگه", "حاجی آباد", "کنگ", "پارسیان", "جاسک"],
    "همدان": ["همدان", "ملایر", "نهاوند", "اسدآباد", "تویسرکان", "بهار", "کبودراهنگ", "لالجین", "رزن", "فامنین"],
    "یزد": ["یزد", "میبد", "اردکان", "حمیدیا", "مهریز", "بافق", "تفت", "ابرکوه", "زارچ", "اشکذر"]
}

# منوی اصلی
main_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
main_markup.add("🔗به یه ناشناس وصلم کن!")
main_markup.row("🗨 جستجوی ویژه‌ 🗨", "🔍 جستجوی کاربران 🔎")
main_markup.row("👤 پروفایل من", "💰 افزایش سکه", "📄 راهنما")
main_markup.add("⚠️دعوت دوستان (سکه رایگان)")
main_markup.add("📫لینک ناشناس من")


# تابع برای تولید یا گرفتن کد ارجاع
def get_referral_code(user_id):
    cursor.execute("SELECT referral_code FROM referrals WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result:
        return result[0]
    else:
        # تولید کد ارجاع منحصربه‌فرد (فقط حروف و اعداد)
        referral_code = str(uuid.uuid4()).replace('-', '')[:12]
        cursor.execute(
            "INSERT INTO referrals (user_id, referral_code, referral_count) VALUES (?, ?, 0)",
            (user_id, referral_code)
        )
        conn.commit()
        return referral_code


# تابع برای گرفتن تعداد دعوت‌ها
def get_referral_count(user_id):
    cursor.execute("SELECT referral_count FROM referrals WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0


# تابع برای آپدیت سکه‌ها و تعداد دعوت‌ها
def add_referral(user_id, referred_user_id):
    # چک کردن اینکه کاربر جدید قبلاً دعوت نشده باشه
    cursor.execute("SELECT user_id FROM referrals WHERE user_id = ?", (referred_user_id,))
    if cursor.fetchone():
        return False  # کاربر قبلاً دعوت شده

    # اضافه کردن 20 سکه به کاربر دعوت‌کننده
    cursor.execute("UPDATE users SET coins = coins + 20 WHERE user_id = ?", (user_id,))
    # آپدیت تعداد دعوت‌ها
    cursor.execute("UPDATE referrals SET referral_count = referral_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    return True


# هندلر برای "📄 راهنما"
@bot.message_handler(func=lambda message: message.text == "📄 راهنما")
def show_help(message):
    user_id = message.from_user.id
    help_text = """
🔹راهنمای استفاده از ربات:

من اینجام که کمکت کنم! برای دریافت راهنمایی در مورد هر موضوع، کافیه دستور آبی رنگی که مقابل اون سوال هست رو لمس کنی:

⁉️ چگونه بصورت ناشناس چت کنم؟ /help_chat
⁉️ سکه یا امتیاز چیست؟ /help_seke
⁉️ چگونه افراد نزدیکمو پیدا کنم؟ /help_gps
⁉️ پروفایل چیست؟ /help_profile
⁉️ چگونه درخواست چت بفرستم؟ /help_sendchat
⁉️ پیام دایرکت چیست؟ /help_direct
⁉️ اطلاع رسانی آنلاین شدن مخاطب /help_onw
⁉️ اطلاع رسانی اتمام چت مخاطب /help_chw
⁉️ دنبال کردن چیست ؟ /help_contacts
⁉️ آموزش حذف پیام در چت /help_deleteMessage
⁉️ آموزش حذف اکانت در ربات /help_deleteAccount
⚖️ قوانین استفاده از ربات /rules
👨‍💻 ارتباط با پشتیبانی ربات:
@chatoogram100
"""
    bot.send_message(user_id, help_text, reply_markup=main_markup)


# هندلر برای /help_chat
@bot.message_handler(commands=['help_chat'])
def help_chat(message):
    user_id = message.from_user.id
    help_chat_text = """
🔹 چگونه بصورت ناشناس چت کنم؟

فقط کافیه تو منوی ربات <<🔗 به یه ناشناس وصلم کن!>> رو بزنی و یکی از گزینه هارو انتخاب کنی :

🎲 جستجوی شانسی
- بصورت تصادفی به یک نفر وصل میشی (بدون نیاز به سکه💰)

🛰 جستجوی اطراف
 - بصورت تصادفی به یک دختر یا پسر که نزدیکته وصل میشی (2 سکه 💰)

🙎‍♂️جستجوی پسر
 - بصورت تصادفی به یک پسر وصل میشی ( ۲ سکه💰 )

🙍‍♀️جستجوی دختر
 - بصورت تصادفی به یک دختر وصل میشی ( ۲ سکه💰 )

⚠️ اطلاعات شخصی شما مثل موقعیت GPS یا اسم شما در تلگرام یا عکس پروفایل و.. کاملاً مخفی هست و فقط اطلاعاتی که تو ربات ثبت میکنید مانند شهر و عکس(توی ربات) برای کاربرای ربات قابل مشاهده هست.

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, help_chat_text, reply_markup=main_markup)


# هندلر برای /help_seke
@bot.message_handler(commands=['help_seke'])
def help_seke(message):
    user_id = message.from_user.id
    help_seke_text = """
🔹 سکه یا امتیاز چیست؟

شما با داشتن سکه می‌توانید :

- پیام دایرکت بفرستید (1سکه)
- درخواست چت بفرستید(2سکه)
- اطلاع از آنلاین بودن (1 سکه)
- اطلاع از اتمام چت کاربر (1سکه )
- از جستجوی پسر یا جستجوی دختر استفاده کنید(2سکه)

📢 توجه : سکه فقط در صورتی کسر می‌شود که درخواست موفق باشد ( مثلاً درخواست چت شما توسط کاربر مقابل پذیرفته شود )

❓روش‌های بدست آوردن سکه چیست؟

1️⃣ معرفی دوستان (رایگان) :
برای افزایش سکه به صورت رایگان بنر لینک⚡️ مخصوص خودت (/link) رو برای دوستات بفرست و 10 سکه دریافت کن
- به ازای هرنفری که با لینک⚡️ شما وارد ربات میشه به محض ورود 10 تا سکه و بعد از تکمیل پروفایل 10 سکه دیگر رایگان دریافت می‌کنی 😎

2️⃣ خرید سکه بصورت آنلاین :
‌ می‌تونی 《افزایش سکه 💰》 رو لمس کنی و بصورت آنلاین سکه خرید بکنی

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, help_seke_text, reply_markup=main_markup)


# هندلر برای /help_gps
@bot.message_handler(commands=['help_gps'])
def help_gps(message):
    user_id = message.from_user.id
    help_gps_text = """
🔹چگونه افراد نزدیکمو پیدا کنم؟

برای دیدن لیست افراد نزدیکت فقط کافیه 《📍پیدا کردن افراد نزدیک با GPS》 رو لمس کنی.

- جستجوی افراد نزدیک کاملاً رایگان هست (بدون نیاز به سکه)

برای مشاهده کردن و یا چت کردن با افراد نزدیکت کافیه توی لیست روی آیدی شون بزنی تا پروفایلشونو ببینی.

📢 توجه : امکان مشاهده موقعیت کاربران وجود ندارد و فقط فاصله آنها نمایش داده می‌شود.

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, help_gps_text, reply_markup=main_markup)


# هندلر برای /help_profile
@bot.message_handler(commands=['help_profile'])
def help_profile(message):
    user_id = message.from_user.id
    help_profile_text = """
🔹پروفایل چیست؟

- برای دیدن پروفایل خودت کافیه 《👤 پروفایل》 رو لمس کنی.
- برای دیدن پروفایل کسی که باهاش چت می‌کنی کافیه 《◻️ مشاهده پروفایل این مخاطب ◻️ 》 رو لمس کنی.
- برای دیدن پروفایل هرکاربر کافیه روی آیدیش تو ربات بزنی.

📢 آیدی چیست؟ کد اختصاصی هر کاربر که با زدن آن پروفایل کاربر نمایش داده می‌شود و به صورت /user_X است.

- پروفایل هر کاربر شامل اطلاعاتی که تو ربات ثبت کرده (نام،سن،جنسیت،شهر،عکس) و تاریخ حضورش تو ربات و فاصلش با شمامیشه.

برای ارسال پیام دایرکت یا درخواست چت برای هر کاربر ابتدا باید پروفایلش رو مشاهده کنی و سپس دکمه پیام دایرکت یا درخواست چت رو بزنی.

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, help_profile_text, reply_markup=main_markup)


# هندلر برای /help_sendchat
@bot.message_handler(commands=['help_sendchat'])
def help_sendchat(message):
    user_id = message.from_user.id
    help_sendchat_text = """
🔹چگونه درخواست چت بفرستم؟

با پیام دایرکت می‌تونی بصورت آنی به کاربر پیام متنی ارسال بکنی حتی اگه درحال چت کردن باشه !

فقط کافیه وقتی پروفایل کاربر رو مشاهده می‌کنی روی گزینه 《📨 پیام دایرکت》 بزنی و متن پیامتو بفرستی.

- درصورت ارسال پیام دایرکت 1 سکه ازت کم می‌شه
- این پیام همون لحظه ارسال می‌شه و بعدا تو ربات آرشیو نمی‌شه.

📢 توجه : متن پیام حداکثر می‌تونه 200 حرف باشه و اگه متنی که ارسال می‌کنی بیشتر از 200 حرف بود فقط 200 حرف اولش ارسال می‌شه.

💥 قابلیت ویژه پیام دایرکت : درصورتی که کاربر دریافت کننده ، ربات را بلاک کرده باشد پیام دایرکت به محض آنبلاک شدن کاربر به او ارسال می‌گردد تا حتماً پیام دایرکت را مشاهده کند.

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, help_sendchat_text, reply_markup=main_markup)


# هندلر برای /help_direct
@bot.message_handler(commands=['help_direct'])
def help_direct(message):
    user_id = message.from_user.id
    help_direct_text = """
🔹پیام دایرکت چیست؟

با پیام دایرکت می‌تونی بصورت آنی به کاربر پیام متنی ارسال بکنی حتی اگه درحال چت کردن باشه !

فقط کافیه وقتی پروفایل کاربر رو مشاهده می‌کنی روی گزینه 《📨 پیام دایrekt》 بزنی و متن پیامتو بفرستی.

- درصورت ارسال پیام دایرکت 1 سکه ازت کم می‌شه
- این پیام همون لحظه ارسال می‌شه و بعدا تو ربات آرشیو نمی‌شه.

📢 توجه : متن پیام حداکثر می‌تونه 200 حرف باشه و اگه متنی که ارسال می‌کنی بیشتر از 200 حرف بود فقط 200 حرف اولش ارسال می‌شه.

💥 قابلیت ویژه پیام دایرکت : درصورتی که کاربر دریافت کننده ، ربات را بلاک کرده باشد پیام دایرکت به محض آنبلاک شدن کاربر به او ارسال می‌گردد تا حتماً پیام دایرکت را مشاهده کند.

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, help_direct_text, reply_markup=main_markup)


# هندلر برای /help_onw
@bot.message_handler(commands=['help_onw'])
def help_onw(message):
    user_id = message.from_user.id
    help_onw_text = """
🔹 اطلاع رسانی آنلاین شدن مخاطب

با این قابلیت وقتی که کاربر مورد نظرت آنلاین شد ، بهت اطلاع رسانی می‌شه.

- درصورت فعال کردن این قابلیت برای هر کاربر 1 💰سکه ازت کم می‌شه
- این قابلیت یکبار فعال می‌شه و برای اطلاع رسانی دوباره باید یکبار دیگه فعالش کنی.
- اگه بعد از 10 روز کاربر مورد نظرت آنلاین نشد این قابلیت غیر فعال می‌شه.

🔴 برای فعال کردن این قابلیت گزینه <<🔔 به محض آنلاین شدن اطلاع بده >> توی پروفایل کاربر مورد نظرت رو بزن .
(در صورتی که این گزینه وجود نداره یا کاربر آنلاینه و یا این قابلیت رو قبلاً براش فعال کردی)

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, help_onw_text, reply_markup=main_markup)


# هندلر برای /help_chw
@bot.message_handler(commands=['help_chw'])
def help_chw(message):
    user_id = message.from_user.id
    help_chw_text = """
🔹 اطلاع رسانی اتمام چت مخاطب

با این قابلیت وقتی که کاربر مورد نظرت چتش با مخاطبش تموم بشه ، بهت اطلاع رسانی می‌شه.

- درصورت فعال کردن این قابلیت برای هر کاربر 1 💰سکه ازت کم می‌شه
- این قابلیت یکبار فعال می‌شه و برای اطلاع رسانی دوباره باید یکبار دیگه فعالش کنی.
- اگه بعد از 10 روز چت کاربر مورد نظرت تموم نشد این قابلیت غیر فعال می‌شه.

🔴 برای فعال کردن این قابلیت گزینه << چت کردنش تموم شد بهم خبر بده 🔊>> توی پروفایل کاربر مورد نظرت رو بزن .
(در صورتی که این گزینه وجود نداره یا کاربر درجال چت نیست و یا این قابلیت رو قبلاً براش فعال کردی)

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, help_chw_text, reply_markup=main_markup)


# هندلر برای /help_contacts
@bot.message_handler(commands=['help_contacts'])
def help_contacts(message):
    user_id = message.from_user.id
    help_contacts_text = """
🔹 ‏ دنبال کردن چیست ؟

با قابلیت دنبال کردن می‌تونی مخاطب هاتو تو ربات داشته باشی و گمشون نکنی !

- برای دیدن لیست دنبال کننده‌ها (فالور) خودت کافیه 《👫 دوستان》 رو از منوی ربات انتخاب کنی و <<👫 اونایی که فالو کردم ♡>> رو لمس کنی.
و یا << /followers >> رو از منوی میانبر‌ها انتخاب کنی.

برای اضافه کردن کاربر به لیست فالور گزینه <<🚶‍♂️دنبال کردن >> رو تو پروفایلش بزن.

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, help_contacts_text, reply_markup=main_markup)


# هندلر برای /help_deleteMessage
@bot.message_handler(commands=['help_deleteMessage'])
def help_deleteMessage(message):
    user_id = message.from_user.id
    help_deleteMessage_text = """
🔹 آموزش حذف پیام در چت

هر پیامی که تو چت فرستادی و می‌خوای حذفش کنی کافیه ریپلایش کنی و کلمه «حذف» رو تایپ کنی تا از چت مخاطبت حذف بشه.

🔸 - ‏ راهنما : /help

کانال رسمی ما 🤖 (اخبار،آپدیت‌ها و ترفند‌ها) 🐝
"""
    bot.send_message(user_id, help_deleteMessage_text, reply_markup=main_markup)


# هندلر برای /help_deleteAccount
@bot.message_handler(commands=['help_deleteAccount'])
def help_deleteAccount(message):
    user_id = message.from_user.id
    help_deleteAccount_text = """
🔹 آموزش حذف حساب کاربری در ربات

اگه می‌خوای همه اطلاعات کاربریت داخل ربات پاک بشه، می‌تونی از این دستور استفاده کنی تا به طور کامل از سرور ما حذف بشه.

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, help_deleteAccount_text, reply_markup=main_markup)


# هندلر برای /rules
@bot.message_handler(commands=['rules'])
def rules(message):
    user_id = message.from_user.id
    rules_text = """
🚫 قوانین استفاده از چتوگرام

موارد زیر باعث مسدود شدن دائمی کاربر خواهد شد

1️⃣ تبلیغات سایت‌ها ربات‌ها و کانال‌ها
2️⃣ ارسال هرگونه محتوای غیر اخلاقی
3️⃣ ایجاد مزاحمت برای کاربران
4️⃣ پخش شماره موبایل یا اطلاعات شخصی دیگران
5️⃣ محتوای غیر اخلاقی و یا توهین آمیز در پروفایل چتوگرام
6️⃣ ثبت جنسیت اشتباه در پروفایل
7️⃣ تهدید و جا زدن خود بعنوان مدیر ربات یا پلیس فتا !

برای گزارش عدم رعایت قوانین می‌توانید با لمس 《 🚫 گزارش کاربر 》 در پروفایل، کاربر را گزارش کنید.

👈درصورت گزارش صحیح کاربر متخلف 💰 5 سکه بعنوان هدیه دریافت می‌کنید.

🔸 - ‏ راهنما : /help
"""
    bot.send_message(user_id, rules_text, reply_markup=main_markup)


# هندلر برای دکمه‌ی دعوت دوستان
@bot.message_handler(func=lambda message: message.text == "⚠️دعوت دوستان (سکه رایگان)")
def invite_friends(message):
    user_id = message.from_user.id
    update_last_online(user_id)  # فرض می‌کنیم این تابع وجود داره

    # گرفتن یا تولید کد ارجاع
    referral_code = get_referral_code(user_id)
    referral_link = f"https://t.me/testdeletebot0039_bot?start={referral_code}"
    referral_count = get_referral_count(user_id)

    # پیام اول با عکس و کپشن (با HTML)
    photo_file_id = "AgACAgQAAxkBAAIEy2iOReCzNHcp47RvZUJlLCSj2eyoAAJY0jEbjol4UEmrSb48pP90AQADAgADeQADNgQ"
    caption = (
        "<b>🔥 همین الآن کراشِتو پیدا کن 😎👫</b>\n\n"
        "با <b>چتوگرام</b> می‌تونی:\n"
        "📡 افراد <b>#نزدیک</b> خودتو پیداکنی و باهاشون آشنا بشی\n"
        "💬 به صورت <b>#ناشناس</b> با یک نفر چت کنی\n"
        "👤 عکس پروفایل طرف رو ببینی و انتخاب کنی\n\n"
        f"همین الآن روی لینک بزن 👇\n<a href='{referral_link}'>لینک دعوت</a>\n"
        "<b>✅ رایگان و واقعی 😎</b>"
    )
    try:
        bot.send_photo(user_id, photo_file_id, caption=caption, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error sending photo to user {user_id}: {e}")
        # ارسال پیام بدون عکس اگه خطا بده
        bot.send_message(user_id, caption, parse_mode="HTML", reply_markup=main_markup)

    # پیام دوم با لینک اختصاصی و تعداد دعوت‌ها (با HTML)
    second_message = (
        f"<b>🔗 لینک اختصاصی شما ایجاد شد ⚡️</b>\n"
        f"<a href='{referral_link}'>لینک دعوت</a>\n\n"
        "با دعوت هر یک نفر <b>20 سکه</b> دریافت می‌کنی 😍\n"
        f"تا حالا <b>{referral_count}</b> نفر رو دعوت کردی\n\n"
        "برای این که دوستات رو به ربات دعوت کنی می‌تونی از لینک اختصاصیت که بالا برات فرستادم استفاده کنی 😁❕"
    )
    try:
        bot.send_message(user_id, second_message, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error sending second message to user {user_id}: {e}")
        bot.send_message(user_id, second_message, reply_markup=main_markup)


# # هندلر برای پردازش لینک‌های ارجاع
# @bot.message_handler(commands=['start'])
# def handle_start(message):
#     user_id = message.from_user.id
#     update_last_online(user_id)
#
#     # چک کردن اینکه آیا لینک ارجاع داره یا نه
#
#                 bot.send_message(
#                     user_id,
#                     "به <b>چتوگرام</b> خوش اومدی! 😎 با این ربات می‌تونی دوستای جدید پیدا کنی!",
#                     parse_mode="HTML",
#                 )
#         else:
#             bot.send_message(
#                 user_id,
#                 "به <b>چتوگرام</b> خوش اومدی! 😎 با این ربات می‌تونی دوستای جدید پیدا کنی!",
#                 parse_mode="HTML"
#             )
#     else:
#         bot.send_message(
#             user_id,
#             "به <b>چتوگرام</b> خوش اومدی! 😎 با این ربات می‌تونی دوستای جدید پیدا کنی!",
#             parse_mode="HTML"
#         )



# تعریف آیدی کانال
CHANNEL_ID = "@chatooogram"


@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "کاربر"
    chat_id = message.chat.id
    unique_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    cursor = conn.cursor()

    # بررسی عضویت کاربر در کانال
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            # کاربر عضو کانال است، ادامه فرآیند
            args = message.text.split()
            if len(args) > 1:
                referral_code = args[1]
                cursor.execute("SELECT user_id FROM referrals WHERE referral_code = ?", (referral_code,))
                result = cursor.fetchone()
                if result:
                    inviter_user_id = result[0]
                    # اضافه کردن کاربر جدید به دیتابیس اگه وجود نداشته باشه
                    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                    if not cursor.fetchone():
                        cursor.execute(
                            "INSERT INTO users (user_id, status, coins, last_online) VALUES (?, 'idle', 10, ?)",
                            (user_id, datetime.now())
                        )
                        conn.commit()
                    # اضافه کردن سکه و آپدیت تعداد دعوت‌ها
                    if add_referral(inviter_user_id, user_id):
                        bot.send_message(
                            inviter_user_id,
                            "🎉 یه نفر با لینک دعوت شما وارد ربات شد! <b>20 سکه</b> به حسابت اضافه شد! 😍",
                            parse_mode="HTML"
                        )
                        bot.send_message(
                            user_id,
                            "🎉 با لینک دعوت دوستت وارد ربات شدی! حالا می‌تونی با <b>چتوگرام</b> کراشتو پیدا کنی! 😎",
                            parse_mode="HTML"
                        )
                else:
                    handle_new_user(user_id, first_name, chat_id, unique_id)
            else:
                handle_new_user(user_id, first_name, chat_id, unique_id)
        else:
            # کاربر عضو کانال نیست
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("عضویت در کانال", url=f"https://t.me/chatooogram"))
            markup.add(types.InlineKeyboardButton("بررسی عضویت", callback_data="check_membership"))
            bot.send_message(
                user_id,
                f"برای استفاده از ربات، ابتدا باید در کانال {CHANNEL_ID} عضو بشی! 😊\nبعد از عضویت، روی دکمه 'بررسی عضویت' کلیک کن.",
                reply_markup=markup
            )
    except Exception as e:
        bot.send_message(user_id, "خطایی رخ داد. لطفاً دوباره امتحان کنید.")
        print(f"Error checking membership: {e}")


# تابع برای مدیریت کاربر جدید
def handle_new_user(user_id, first_name, chat_id, unique_id):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, name, chat_id, unique_id, profile_photo, last_online) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, first_name, chat_id, unique_id, DEFAULT_PROFILE_PHOTO,
             datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        welcome_text = f"""سلام {first_name} عزیز ✋

به 《ربات چت ناشناس چَتوگِرام 📡》 خوش اومدی ، توی این ربات می تونی افراد #نزدیک ات رو پیدا کنی و باهاشون آشنا شی و یا به یه نفر بصورت #ناشناس وصل شی و باهاش #چت کنی ❗️

- استفاده از این ربات رایگانه و اطلاعات تلگرام شما مثل اسم،عکس پروفایل یا موقعیت GPS کاملا محرمانه هست😎

برای شروع بهم بگو دختری یا پسر ؟ 👇"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("من پسرم", "من دخترم")
        markup.add("لغو ❌")
        bot.send_message(user_id, welcome_text, reply_markup=markup)
    else:
        bot.send_message(user_id, "خوش برگشتی! چی کمکی می‌تونم بکنم؟", reply_markup=main_markup)


# مدیریت دکمه بررسی عضویت
@bot.callback_query_handler(func=lambda call: call.data == "check_membership")
def check_membership_callback(call):
    user_id = call.from_user.id
    first_name = call.from_user.first_name or "کاربر"
    chat_id = call.message.chat.id
    unique_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            bot.delete_message(chat_id, call.message.message_id)  # حذف پیام قبلی
            handle_new_user(user_id, first_name, chat_id, unique_id)
        else:
            bot.answer_callback_query(call.id, "شما هنوز در کانال عضو نشده‌اید! لطفاً ابتدا عضو شوید.")
    except Exception as e:
        bot.answer_callback_query(call.id, "خطایی رخ داد. لطفاً دوباره امتحان کنید.")
        print(f"Error checking membership: {e}")
# هندلر انتخاب جنسیت
@bot.message_handler(func=lambda message: message.text in ["من پسرم", "من دخترم", "لغو ❌"])
def set_gender(message):
    user_id = message.from_user.id
    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=main_markup)
        return

    if message.text == "من پسرم":
        gender = 'male'
        gender_title = "پسر"
    else:
        gender = 'female'
        gender_title = "دختر"

    cursor.execute("UPDATE users SET gender = ? WHERE user_id = ?", (gender, user_id))
    conn.commit()

    text = f"چند سالته {gender_title} ؟\nخب {gender_title} عزیز، واسه ادامه ثبت نام به اطلاعات بیشتری ازت نیاز دارم که بتونم برات افراد رو پیدا کنم تا باهاشون صحبت کنی."
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    row = []
    for age in range(13, 61):
        row.append(str(age))
        if len(row) == 7:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)
    markup.add("لغو ❌")
    bot.send_message(user_id, text, reply_markup=markup)


# --------------------------------------------------------------------------------------------------------------------------


# تنظیمات
MERCHANT_ID = "your_merchant_id_here"  # مرچنت آیدی زرین‌پال
BOT_USERNAME = "@Chatoogrambot"  # نام کاربری رباتت
ZARINPAL_API_URL = "https://www.zarinpal.com/pg/v4/payment/request.json"  # یا sandbox
ZARINPAL_VERIFY_URL = "https://www.zarinpal.com/pg/v4/payment/verify.json"  # یا sandbox
CALLBACK_URL = f"https://t.me/{BOT_USERNAME}?start=payment_"

# اتصال به دیتابیس
def get_db_connection():
    conn = sqlite3.connect('chatbot.db')  # مسیر دیتابیست
    conn.row_factory = sqlite3.Row
    return conn

# تابع برای گرفتن تعداد سکه‌های کاربر
def get_user_coins(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 10  # 10 سکه پیش‌فرض اگه کاربر جدید باشه

# تابع برای ایجاد لینک پرداخت زرین‌پال
def create_payment_link(user_id, amount, coins):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO payments (user_id, amount, coins, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (user_id, amount, coins, datetime.now())
    )
    conn.commit()
    payment_id = cursor.lastrowid

    payload = {
        "merchant_id": MERCHANT_ID,
        "amount": amount * 10,  # تبدیل تومان به ریال
        "description": f"خرید {coins} سکه برای کاربر {user_id}",
        "callback_url": f"{CALLBACK_URL}{payment_id}",
        "metadata": {"mobile": "", "email": ""}
    }
    try:
        response = requests.post(ZARINPAL_API_URL, json=payload)
        result = response.json()
        if result.get("data", {}).get("code") == 100:
            authority = result["data"]["authority"]
            cursor.execute("UPDATE payments SET authority = ? WHERE payment_id = ?", (authority, payment_id))
            conn.commit()
            conn.close()
            return f"https://www.zarinpal.com/pg/StartPay/{authority}"
            # برای sandbox: return f"https://sandbox.zarinpal.com/pg/StartPay/{authority}"
        else:
            print(f"Zarinpal error: {result.get('errors')}")
            conn.close()
            return None
    except Exception as e:
        print(f"Error creating payment link: {e}")
        conn.close()
        return None

# تابع برای تأیید پرداخت
def verify_payment(payment_id, authority):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT amount, user_id, coins FROM payments WHERE payment_id = ?", (payment_id,))
    payment = cursor.fetchone()
    if not payment:
        conn.close()
        return False, "پرداخت پیدا نشد."

    amount, user_id, coins = payment['amount'], payment['user_id'], payment['coins']

    # تأیید پرداخت از زرین‌پال
    verify_payload = {
        "merchant_id": MERCHANT_ID,
        "amount": amount * 10,  # تبدیل به ریال
        "authority": authority
    }
    try:
        response = requests.post(ZARINPAL_VERIFY_URL, json=verify_payload)
        result = response.json()
        if result.get("data", {}).get("code") == 100:
            # پرداخت موفق
            cursor.execute("UPDATE payments SET status = 'success' WHERE payment_id = ?", (payment_id,))
            cursor.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (coins, user_id))
            conn.commit()
            conn.close()
            return True, f"پرداخت موفق! {coins} سکه به حساب شما اضافه شد."
        else:
            cursor.execute("UPDATE payments SET status = 'failed' WHERE payment_id = ?", (payment_id,))
            conn.commit()
            conn.close()
            return False, "پرداخت ناموفق بود."
    except Exception as e:
        print(f"Error verifying payment: {e}")
        cursor.execute("UPDATE payments SET status = 'failed' WHERE payment_id = ?", (payment_id,))
        conn.commit()
        conn.close()
        return False, "خطا در تأیید پرداخت."

# هندلر برای callback پرداخت
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    update_last_online(user_id)  # فرض می‌کنیم این تابع وجود داره

    if message.text.startswith('/start payment_'):
        try:
            payment_id = int(message.text.split('_')[1])
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT authority, status FROM payments WHERE payment_id = ?", (payment_id,))
            payment = cursor.fetchone()
            conn.close()

            if not payment:
                bot.send_message(message.chat.id, "خطا: پرداخت پیدا نشد.", reply_markup=main_markup)
                return

            if payment['status'] == 'success':
                bot.send_message(message.chat.id, "این پرداخت قبلاً تأیید شده است.", reply_markup=main_markup)
                return

            # تأیید پرداخت
            success, response_message = verify_payment(payment_id, payment['authority'])
            bot.send_message(message.chat.id, response_message, reply_markup=main_markup)
        except Exception as e:
            print(f"Error in start handler: {e}")
            bot.send_message(message.chat.id, "خطا در پردازش پرداخت. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=main_markup)
    else:
        # هندلر عادی برای /start
        bot.send_message(message.chat.id, "خوش آمدید!", reply_markup=main_markup)

# هندلر دکمه افزایش سکه
@bot.message_handler(func=lambda message: message.text == "💰 افزایش سکه")
def show_payment_options(message):
    user_id = message.from_user.id
    update_last_online(user_id)

    coins = get_user_coins(user_id)
    text = (
        f"💰 شما <b>{coins}</b> سکه در حساب خود دارید 😃.\n"
        "ــــــــــــــــــــــــــــــــــــــــ\n"
        "راه‌های زیادی جهت دریافت سکه بیشتر وجود داره. می‌تونی از لیست زیر، یکی رو انتخاب کنی! 😇\n"
        "1️⃣ معرفی دوستان (رایگان):\n"
        "برای افزایش سکه به صورت رایگان بنر لینک⚡️ مخصوص خودت (/link) رو برای دوستات بفرست و 20 سکه دریافت کن\n"
        "2️⃣ خرید سکه بصورت آنلاین:\n"
        "برای خرید سکه یکی از تعرفه‌های زیر را انتخاب نمایید👇\n"
        "<b>🔰 آموزش مرحله به مرحله خرید سکه 💰</b>"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=create_payment_keyboard())

# ایجاد InlineKeyboard برای تعرفه‌ها
def create_payment_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        types.InlineKeyboardButton("💵 110 سکه - 44,000 تومان", callback_data="pay_44000_110"),
        types.InlineKeyboardButton("💵 250 سکه - 71,000 تومان", callback_data="pay_71000_250"),
        types.InlineKeyboardButton("💵 480 سکه - 97,000 تومان", callback_data="pay_97000_480"),
        types.InlineKeyboardButton("💵 1060 سکه - 161,000 تومان", callback_data="pay_161000_1060"),
        types.InlineKeyboardButton("💵 2024 سکه - 285,000 تومان", callback_data="pay_285000_2024"),
        types.InlineKeyboardButton("🔥 بسته ویژه 4,040 سکه - 510,000 تومان", callback_data="pay_510000_4040"),
        types.InlineKeyboardButton("🎁 هدیه به دوست", callback_data="pay_gift")
    ]
    keyboard.add(*buttons)
    return keyboard

# هندلر برای انتخاب تعرفه
@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_') and not call.data == 'pay_gift')
def handle_payment_selection(call):
    user_id = call.from_user.id
    update_last_online(user_id)

    amount, coins = map(int, call.data.split('_')[1:])
    payment_link = create_payment_link(user_id, amount, coins)
    if not payment_link:
        bot.send_message(user_id, "⚠️ خطا در ایجاد لینک پرداخت! لطفاً بعداً امتحان کنید.", reply_markup=main_markup)
        bot.answer_callback_query(call.id)
        return

    text = (
        f"لینک پرداخت آنلاین <b>{coins} سکه</b> به مبلغ <b>{amount:,} تومان</b> برای شما ساخته شد 👇\n"
        f"<a href='{payment_link}'>پرداخت آنلاین</a>\n\n"
        "یک روش پرداخت را انتخاب کنید:\n"
        "▪️ پرداخت آنلاین (پرداخت از طریق درگاه بانکی شتابی بصورت کاملا امن انجام می‌گیرد.)\n"
        "▫️ پرداخت آفلاین (پرداخت از طریق کارت به کارت 💳)\n"
        "⚠️ توجه: هنگام پرداخت آنلاین حتما باید فیلترشکن خود را خاموش کنید ❗️"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("▪️ پرداخت آنلاین", url=payment_link),
        types.InlineKeyboardButton("▫️ پرداخت آفلاین", callback_data=f"offline_payment_{amount}_{coins}"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_payment_options")
    )

    try:
        bot.edit_message_text(
            text,
            chat_id=user_id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=markup
        )
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error editing message for user {user_id}: {e}")
        bot.send_message(user_id, text, parse_mode="HTML", reply_markup=markup)
    bot.answer_callback_query(call.id, f"لینک پرداخت برای {coins} سکه ساخته شد!")

# هندلر برای پرداخت آفلاین
@bot.callback_query_handler(func=lambda call: call.data.startswith('offline_payment_'))
def handle_offline_payment(call):
    user_id = call.from_user.id
    update_last_online(user_id)
    amount, coins = map(int, call.data.split('_')[2:])

    text = (
        f"برای پرداخت آفلاین <b>{coins} سکه</b> به مبلغ <b>{amount:,} تومان</b>:\n"
        "لطفاً مبلغ را به شماره کارت زیر واریز کنید و رسید را برای پشتیبانی ارسال کنید:\n\n"
        "🏧 شماره کارت: <YOUR_CARD_NUMBER>\n"
        "🏦 بانک: <YOUR_BANK_NAME>\n"
        "👤 به نام: <YOUR_NAME>\n\n"
        "📞 پشتیبانی: @chatoogram100\n"
        "⚠️ توجه: پس از ارسال رسید، سکه‌ها به حسابتون اضافه می‌شه."
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_payment_options"))

    try:
        bot.edit_message_text(
            text,
            chat_id=user_id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=markup
        )
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error editing message for user {user_id}: {e}")
        bot.send_message(user_id, text, parse_mode="HTML", reply_markup=markup)
    bot.answer_callback_query(call.id, "اطلاعات پرداخت آفلاین نمایش داده شد!")

# هندلر برای بازگشت به منوی تعرفه‌ها
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_payment_options')
def back_to_payment_options(call):
    user_id = call.from_user.id
    update_last_online(user_id)
    coins = get_user_coins(user_id)
    text = (
        f"💰 شما <b>{coins}</b> سکه در حساب خود دارید 😃.\n"
        "ــــــــــــــــــــــــــــــــــــــــ\n"
        "راه‌های زیادی جهت دریافت سکه بیشتر وجود داره. می‌تونی از لیست زیر، یکی رو انتخاب کنی! 😇\n"
        "1️⃣ معرفی دوستان (رایگان):\n"
        "برای افزایش سکه به صورت رایگان بنر لینک⚡️ مخصوص خودت (/link) رو برای دوستات بفرست و 20 سکه دریافت کن\n"
        "2️⃣ خرید سکه بصورت آنلاین:\n"
        "برای خرید سکه یکی از تعرفه‌های زیر را انتخاب نمایید👇\n"
        "<b>🔰 آموزش مرحله به مرحله خرید سکه 💰</b>"
    )
    try:
        bot.edit_message_text(
            text,
            chat_id=user_id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=create_payment_keyboard()
        )
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error editing message for user {user_id}: {e}")
        bot.send_message(user_id, text, parse_mode="HTML", reply_markup=create_payment_keyboard())
    bot.answer_callback_query(call.id, "بازگشت به منوی افزایش سکه")
# هندلر برای هدیه به دوست (فعلاً placeholder)
@bot.callback_query_handler(func=lambda call: call.data == 'pay_gift')
def handle_gift_payment(call):
    user_id = call.from_user.id
    update_last_online(user_id)
    bot.send_message(user_id, "🎁 این قابلیت هنوز پیاده‌سازی نشده! به‌زودی اضافه می‌شه 😊", reply_markup=main_markup)
    bot.answer_callback_query(call.id)


# دیکشنری برای ذخیره نتایج جستجو و صفحه‌بندی
search_results = defaultdict(list)
current_page = defaultdict(int)


# تابع برای محاسبه فاصله جغرافیایی با فرمول Haversine
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # شعاع زمین (کیلومتر)
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


# تابع برای نمایش کاربران در یک صفحه خاص
def display_users_page(user_id, search_type, page=1):
    users = search_results[user_id]
    if not users:
        bot.send_message(user_id, "هیچ کاربری پیدا نشد!", reply_markup=main_markup)
        return

    users_per_page = 10
    start_idx = (page - 1) * users_per_page
    end_idx = start_idx + users_per_page
    page_users = users[start_idx:end_idx]

    if not page_users:
        bot.send_message(user_id, "صفحه‌ای برای نمایش وجود ندارد!", reply_markup=main_markup)
        return

    message_text = "🎌 لیست افراد جستجو شده:\n\n"
    for user in page_users:
        name, age, province, unique_id, last_online = user[:5]
        gender_display = "👨‍🦰" if user[5] == 'male' else "👩"
        province_display = province if province else "نامشخص"
        age_display = age if age else "نامشخص"
        message_text += f"{gender_display} نام‌: {name} (سن: {age_display})\n"
        message_text += f"استان:‌ {province_display}\n"
        message_text += f"{format_last_online(last_online)}\n"
        message_text += f"🆔 : /user_{unique_id}\n"
        message_text += "〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"

    markup = types.InlineKeyboardMarkup(row_width=2)
    if end_idx < len(users):
        markup.add(
            types.InlineKeyboardButton("صفحه بعدی", callback_data=f'next_page_{search_type}_{page + 1}')
        )
    markup.add(
        types.InlineKeyboardButton("بازگشت به منوی جستجو", callback_data='back_to_search_menu')
    )

    try:
        bot.send_message(user_id, message_text, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error sending message to user {user_id}: {e}")
        bot.send_message(user_id, message_text, reply_markup=main_markup)


# هندلر برای دکمه‌ی جستجوی کاربران
@bot.message_handler(func=lambda message: message.text == "🔍 جستجوی کاربران 🔎")
def user_search(message):
    user_id = message.from_user.id
    update_last_online(user_id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("هم استانی‌ها 🎌", callback_data='search_same_province'),
        types.InlineKeyboardButton("هم سن‌ها 👥", callback_data='search_same_age')
    )
    markup.add(
        types.InlineKeyboardButton("🔍 جستجوی پیشرفته 🔎", callback_data='search_advanced'),
        types.InlineKeyboardButton("بدون چت‌ها 🚶‍♀️‍➡️", callback_data='search_no_chat')
    )
    markup.add(
        types.InlineKeyboardButton("کاربران جدید 🙋‍♀️", callback_data='search_new_users'),
        types.InlineKeyboardButton("افراد نزدیک 📍", callback_data='search_nearby')
    )
    bot.send_message(
        user_id,
        "کیو پیدا کنم برات؟ انتخاب کن👇",
        reply_markup=markup
    )


search_results = defaultdict(list)
current_page = defaultdict(int)


# هندلر برای دکمه‌ی جستجوی پیشرفته
@bot.callback_query_handler(func=lambda call: call.data == "search_advanced")
def special_search(message):
    user_id = message.from_user.id
    update_last_online(user_id)  # آپدیت زمان آنلاین
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("فقط پسر باشه 👱‍♂️", callback_data='special_search_male'),
        types.InlineKeyboardButton("فقط دختر باشه 👱‍♀️", callback_data='special_search_female')
    )
    markup.add(
        types.InlineKeyboardButton("همه رو نشون بده 🧑‍🤝‍🧑", callback_data='special_search_all')
    )
    bot.send_message(
        user_id,
        """چه کسایی رو از لیست 🗨 جستجوی ویژه‌ 🗨 نشونت بدم؟
انتخاب کن👇""",
        reply_markup=markup
    )


# تابع برای نمایش کاربران در یک صفحه خاص
def display_users_page(user_id, search_type, page=1):
    # گرفتن نتایج جستجو از دیکشنری
    users = search_results[user_id]
    if not users:
        bot.send_message(user_id, "هیچ کاربر آنلاینی پیدا نشد!", reply_markup=main_markup)
        return

    # تنظیم محدوده کاربران برای صفحه فعلی
    users_per_page = 10
    start_idx = (page - 1) * users_per_page
    end_idx = start_idx + users_per_page
    page_users = users[start_idx:end_idx]

    if not page_users:
        bot.send_message(user_id, "صفحه‌ای برای نمایش وجود ندارد!", reply_markup=main_markup)
        return

    # ساخت متن خروجی
    message_text = "🎌 لیست افراد جست و جو شده شما که در ۳ روز اخیر آنلاین بوده اند.\n\n"
    for user in page_users:
        name, gender, age, province, city, unique_id, last_online = user
        gender_display = "👨‍🦰" if gender == 'male' else "👩"
        province_display = province if province else "نامشخص"
        city_display = city if city else "نامشخص"
        age_display = age if age else "نامشخص"
        message_text += f"{gender_display} نام‌: {name} (سن: {age_display})\n"
        message_text += f"استان:‌ {province_display} ({city_display})\n"
        message_text += f"{format_last_online(last_online)}\n"
        message_text += f"🆔 : /user_{unique_id}\n"
        message_text += "〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"

    # ساخت کیبورد اینلاین
    markup = types.InlineKeyboardMarkup(row_width=2)
    if end_idx < len(users):
        markup.add(
            types.InlineKeyboardButton("صفحه بعدی", callback_data=f'next_page_{search_type}_{page + 1}')
        )
    markup.add(
        types.InlineKeyboardButton("نمایش کشویی", callback_data=f'slider_view_{search_type}')
    )

    # ارسال یا ویرایش پیام
    try:
        bot.send_message(user_id, message_text, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error sending message to user {user_id}: {e}")
        bot.send_message(user_id, message_text, reply_markup=main_markup)


# هندلرهای جستجوی ویژه
@bot.callback_query_handler(
    func=lambda call: call.data in ['special_search_male', 'special_search_female',
                                    'special_search_all'] or call.data.startswith('next_page_'))
def handle_special_search(call):
    user_id = call.from_user.id
    update_last_online(user_id)  # آپدیت زمان آنلاین
    search_type = call.data.split('_')[2] if call.data.startswith('next_page_') else call.data
    page = int(call.data.split('_')[3]) if call.data.startswith('next_page_') else 1

    # اگر جستجوی جدیده، نتایج رو از دیتابیس بگیریم
    if not call.data.startswith('next_page_'):
        now = datetime.now()
        three_days_ago = now - timedelta(days=3)

        cursor = conn.cursor()
        if search_type == 'special_search_male':
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online 
                FROM users 
                WHERE gender = 'male' AND last_online >= ? AND user_id != ?
                """,
                (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )
        elif search_type == 'special_search_female':
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online 
                FROM users 
                WHERE gender = 'female' AND last_online >= ? AND user_id != ?
                """,
                (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )
        else:  # special_search_all
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online 
                FROM users 
                WHERE last_online >= ? AND user_id != ?
                """,
                (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )

        # ذخیره نتایج در دیکشنری
        search_results[user_id] = cursor.fetchall()
        cursor.close()
        current_page[user_id] = 1
    else:
        current_page[user_id] = page

    # نمایش کاربران صفحه فعلی
    display_users_page(user_id, search_type, current_page[user_id])
    bot.answer_callback_query(call.id, f"صفحه {current_page[user_id]} نمایش داده شد!")


# -----------------------------------------------------------------------------------------
# هندلر برای callback queryهای جستجو
@bot.callback_query_handler(
    func=lambda call: call.data in [
        'search_same_province', 'search_same_age', 'search_advanced',
        'search_no_chat', 'search_new_users', 'search_nearby',
        'back_to_search_menu'
    ] or call.data.startswith('next_page_'))
def handle_user_search(call):
    user_id = call.from_user.id
    update_last_online(user_id)

    if call.data == 'back_to_search_menu':
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("هم استانی‌ها 🎌", callback_data='search_same_province'),
            types.InlineKeyboardButton("هم سن‌ها 👥", callback_data='search_same_age')
        )
        markup.add(
            types.InlineKeyboardButton("🔍 جستجوی پیشرفته 🔎", callback_data='search_advanced'),
            types.InlineKeyboardButton("بدون چت‌ها 🚶‍♀️‍➡️", callback_data='search_no_chat')
        )
        markup.add(

            types.InlineKeyboardButton("افراد نزدیک 📍", callback_data='search_nearby')
        )
        bot.edit_message_text(
            "کیو پیدا کنم برات؟ انتخاب کن👇",
            chat_id=user_id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
        return

    search_type = call.data.split('_')[2] if call.data.startswith('next_page_') else call.data
    page = int(call.data.split('_')[3]) if call.data.startswith('next_page_') else 1

    if not call.data.startswith('next_page_'):
        now = datetime.now()
        three_days_ago = now - timedelta(days=3)
        cursor = conn.cursor()

        # گرفتن اطلاعات کاربر فعلی برای مقایسه
        cursor.execute("SELECT province, age, latitude, longitude FROM users WHERE user_id = ?", (user_id,))
        user_data = cursor.fetchone()
        if not user_data:
            bot.send_message(user_id, "اطلاعات شما یافت نشد!", reply_markup=main_markup)
            cursor.close()
            return
        user_province, user_age, user_lat, user_lon = user_data

        # تعریف کوئری‌ها برای هر نوع جستجو
        if search_type == 'search_same_province':
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online 
                FROM users 
                WHERE province = ? AND last_online >= ? AND user_id != ?
                """,
                (user_province, three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )
        elif search_type == 'search_same_age':
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online 
                FROM users 
                WHERE age = ? AND last_online >= ? AND user_id != ?
                """,
                (user_age, three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )
        elif search_type == 'search_no_chat':
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online 
                FROM users 
                WHERE status = 'idle' AND last_online >= ? AND user_id != ?
                """,
                (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )
        elif search_type == 'search_new_users':
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online 
                FROM users 
                WHERE last_online >= ? AND user_id != ?
                ORDER BY created_at DESC
                """,
                (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )
        elif search_type == 'search_nearby':
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online, latitude, longitude 
                FROM users 
                WHERE last_online >= ? AND user_id != ? AND latitude IS NOT NULL AND longitude IS NOT NULL
                """,
                (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )
            users = cursor.fetchall()
            if user_lat is None or user_lon is None:
                bot.send_message(user_id, "موقعیت شما ثبت نشده است!", reply_markup=main_markup)
                cursor.close()
                return
            # محاسبه فاصله و مرتب‌سازی
            users_with_distance = [
                (name, gender, age, province, city, unique_id, last_online,
                 haversine_distance(user_lat, user_lon, lat, lon))
                for name, gender, age, province, city, unique_id, last_online, lat, lon in users
            ]
            users_with_distance.sort(key=lambda x: x[7])  # مرتب‌سازی بر اساس فاصله
            search_results[user_id] = [(name, gender, age, province, city, unique_id, last_online) for
                                       name, gender, age, province, city, unique_id, last_online, _ in
                                       users_with_distance]
        elif search_type == 'search_advanced':
            bot.send_message(user_id, "جستجوی پیشرفته هنوز پیاده‌سازی نشده است!", reply_markup=main_markup)
            cursor.close()
            bot.answer_callback_query(call.id, "این قابلیت بعداً اضافه خواهد شد!")
            return

        if search_type != 'search_nearby':
            search_results[user_id] = cursor.fetchall()
        cursor.close()
        current_page[user_id] = 1

    display_users_page(user_id, search_type, current_page[user_id])
    bot.answer_callback_query(call.id, f"صفحه {current_page[user_id]} نمایش داده شد!")


# کیبورد چت
chat_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
chat_markup.add("مشاهده پروفایل مخاطب 👀")
chat_markup.add("فعال سازی چت خصوصی 🔐‌")
chat_markup.add("پایان چت ❌")

try:
    cursor.execute("ALTER TABLE users ADD COLUMN private_chat_enabled INTEGER DEFAULT 0")
    conn.commit()
except sqlite3.OperationalError:
    # اگه ستون قبلاً وجود داشته باشه، خطا رو نادیده بگیر
    pass

BOT_USERNAME = "@testdeletebot0039_bot"
# دیکشنری برای ذخیره نتایج جستجو و صفحه‌بندی
search_results = defaultdict(list)
current_page = defaultdict(int)


# هندلر برای دکمه‌ی جستجوی ویژه
@bot.message_handler(func=lambda message: message.text == "🗨 جستجوی ویژه‌ 🗨")
def special_search(message):
    user_id = message.from_user.id
    update_last_online(user_id)  # آپدیت زمان آنلاین
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("فقط پسر باشه 👱‍♂️", callback_data='special_search_male'),
        types.InlineKeyboardButton("فقط دختر باشه 👱‍♀️", callback_data='special_search_female')
    )
    markup.add(
        types.InlineKeyboardButton("همه رو نشون بده 🧑‍🤝‍🧑", callback_data='special_search_all')
    )
    bot.send_message(
        user_id,
        """چه کسایی رو از لیست 🗨 جستجوی ویژه‌ 🗨 نشونت بدم؟
انتخاب کن👇""",
        reply_markup=markup
    )


# تابع برای نمایش کاربران در یک صفحه خاص
def display_users_page(user_id, search_type, page=1):
    # گرفتن نتایج جستجو از دیکشنری
    users = search_results[user_id]
    if not users:
        bot.send_message(user_id, "هیچ کاربر آنلاینی پیدا نشد!", reply_markup=main_markup)
        return

    # تنظیم محدوده کاربران برای صفحه فعلی
    users_per_page = 10
    start_idx = (page - 1) * users_per_page
    end_idx = start_idx + users_per_page
    page_users = users[start_idx:end_idx]

    if not page_users:
        bot.send_message(user_id, "صفحه‌ای برای نمایش وجود ندارد!", reply_markup=main_markup)
        return

    # ساخت متن خروجی
    message_text = "🎌 لیست افراد جست و جو شده شما که در ۳ روز اخیر آنلاین بوده اند.\n\n"
    for user in page_users:
        name, gender, age, province, city, unique_id, last_online = user
        gender_display = "👨‍🦰" if gender == 'male' else "👩"
        province_display = province if province else "نامشخص"
        city_display = city if city else "نامشخص"
        age_display = age if age else "نامشخص"
        message_text += f"{gender_display} نام‌: {name} (سن: {age_display})\n"
        message_text += f"استان:‌ {province_display} ({city_display})\n"
        message_text += f"{format_last_online(last_online)}\n"
        message_text += f"🆔 : /user_{unique_id}\n"
        message_text += "〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"

    # ساخت کیبورد اینلاین
    markup = types.InlineKeyboardMarkup(row_width=2)
    if end_idx < len(users):
        markup.add(
            types.InlineKeyboardButton("صفحه بعدی", callback_data=f'next_page_{search_type}_{page + 1}')
        )
    markup.add(
        types.InlineKeyboardButton("نمایش کشویی", callback_data=f'slider_view_{search_type}')
    )

    # ارسال یا ویرایش پیام
    try:
        bot.send_message(user_id, message_text, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error sending message to user {user_id}: {e}")
        bot.send_message(user_id, message_text, reply_markup=main_markup)


# هندلرهای جستجوی ویژه
@bot.callback_query_handler(
    func=lambda call: call.data in ['special_search_male', 'special_search_female',
                                    'special_search_all'] or call.data.startswith('next_page_'))
def handle_special_search(call):
    user_id = call.from_user.id
    update_last_online(user_id)  # آپدیت زمان آنلاین
    search_type = call.data.split('_')[2] if call.data.startswith('next_page_') else call.data
    page = int(call.data.split('_')[3]) if call.data.startswith('next_page_') else 1

    # اگر جستجوی جدیده، نتایج رو از دیتابیس بگیریم
    if not call.data.startswith('next_page_'):
        now = datetime.now()
        three_days_ago = now - timedelta(days=3)

        cursor = conn.cursor()
        if search_type == 'special_search_male':
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online 
                FROM users 
                WHERE gender = 'male' AND last_online >= ? AND user_id != ?
                """,
                (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )
        elif search_type == 'special_search_female':
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online 
                FROM users 
                WHERE gender = 'female' AND last_online >= ? AND user_id != ?
                """,
                (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )
        else:  # special_search_all
            cursor.execute(
                """
                SELECT name, gender, age, province, city, unique_id, last_online 
                FROM users 
                WHERE last_online >= ? AND user_id != ?
                """,
                (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'), user_id)
            )

        # ذخیره نتایج در دیکشنری
        search_results[user_id] = cursor.fetchall()
        cursor.close()
        current_page[user_id] = 1
    else:
        current_page[user_id] = page

    # نمایش کاربران صفحه فعلی
    display_users_page(user_id, search_type, current_page[user_id])
    bot.answer_callback_query(call.id, f"صفحه {current_page[user_id]} نمایش داده شد!")


# کشویی رو از اینجا برداشتم


# تابع برای ساخت اینلاین کیبورد پروفایل
def get_profile_inline_keyboard(user_id):
    cursor.execute("SELECT private_chat_enabled FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    private_chat_enabled = result[0] if result else 0

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✏️ ویرایش پروفایل", callback_data='edit_profile'),
        types.InlineKeyboardButton("🖊️ تغییر یوزرنیم", callback_data='change_username')
    )
    markup.add(
        types.InlineKeyboardButton("✅ لایک (فعال)", callback_data='like_profile'),
        types.InlineKeyboardButton("❤️ مشاهده لایک کننده ها", callback_data='view_likers')
    )
    markup.add(
        types.InlineKeyboardButton("🧑‍🤝‍🧑 گفت و گو های اخیر", callback_data='recent_chats'),
        types.InlineKeyboardButton("🚫 بلاک لیست ❗", callback_data='block_list')
    )
    markup.add(
        types.InlineKeyboardButton("📍 موقعیت مکانی", callback_data='location'),
        types.InlineKeyboardButton("🧍‍♂️🧍‍♀️ دوستان", callback_data='friends')
    )

    private_chat_text = "🔒 چت خصوصی (فعال ✅)" if private_chat_enabled else "🔒 چت خصوصی (غیرفعال ❌)"
    markup.row(types.InlineKeyboardButton(private_chat_text, callback_data='private_chat_toggle'))
    markup.add(
        types.InlineKeyboardButton("❌ دیلیت اکانت", callback_data='delete_account')
    )
    return markup


def register_block_partner_handler(bot, conn):
    @bot.callback_query_handler(func=lambda call: call.data.startswith('block_partner_'))
    def block_partner(call):
        user_id = call.from_user.id
        partner_id = int(call.data.split('_')[-1])
        bot.answer_callback_query(call.id, "کاربر بلاک شد!")

        cursor = conn.cursor()
        # بررسی اینکه آیا کاربر قبلاً بلاک شده
        cursor.execute('''
            SELECT 1 FROM block WHERE blocker_id = ? AND blocked_id = ?
        ''', (user_id, partner_id))
        already_blocked = cursor.fetchone()

        if already_blocked:
            bot.send_message(call.message.chat.id, "این کاربر قبلاً بلاک شده است!")
            cursor.close()
            return

        # اضافه کردن به جدول block
        cursor.execute('''
            INSERT INTO block (blocker_id, blocked_id) VALUES (?, ?)
        ''', (user_id, partner_id))
        # حذف رابطه فالو/فالوئر اگه وجود داره
        cursor.execute('''
            DELETE FROM follow WHERE (follower_id = ? AND followed_id = ?) OR (follower_id = ? AND followed_id = ?)
        ''', (user_id, partner_id, partner_id, user_id))
        # به‌روزرسانی تعداد فالوئرها و فالووینگ‌ها
        cursor.execute('''
            UPDATE users SET following_count = following_count - 1 WHERE user_id = ? AND following_count > 0
        ''', (user_id,))
        cursor.execute('''
            UPDATE users SET followers_count = followers_count - 1 WHERE user_id = ? AND followers_count > 0
        ''', (user_id,))
        cursor.execute('''
            UPDATE users SET following_count = following_count - 1 WHERE user_id = ? AND following_count > 0
        ''', (partner_id,))
        cursor.execute('''
            UPDATE users SET followers_count = followers_count - 1 WHERE user_id = ? AND followers_count > 0
        ''', (partner_id,))
        conn.commit()
        cursor.close()


def register_block_list_handler(bot, conn):
    @bot.callback_query_handler(func=lambda call: call.data == 'block_list')
    def handle_block_list_query(call):
        user_id = call.from_user.id
        bot.answer_callback_query(call.id)

        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.unique_id
            FROM users u
            JOIN block b ON u.user_id = b.blocked_id
            WHERE b.blocker_id = ?
        ''', (user_id,))

        blocked_users = cursor.fetchall()
        cursor.close()

        if not blocked_users:
            bot.send_message(call.message.chat.id, "شما هنوز کسی رو بلاک نکردید!", )
            return

        message = "لیست کاربران بلاک‌شده:\n"
        for user in blocked_users:
            message += f"آیدی: /user_{user[1]}\n\n"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("آنبلاک", callback_data=f'unblock_partner_{user[0]}'))
            bot.send_message(call.message.chat.id, message, reply_markup=keyboard)
            message = ""  # ریست پیام برای کاربر بعدی


def register_unblock_partner_handler(bot, conn):
    @bot.callback_query_handler(func=lambda call: call.data.startswith('unblock_partner_'))
    def unblock_partner(call):
        user_id = call.from_user.id
        partner_id = int(call.data.split('_')[-1])
        bot.answer_callback_query(call.id)

        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1 FROM block WHERE blocker_id = ? AND blocked_id = ?
        ''', (user_id, partner_id))
        is_blocked = cursor.fetchone()

        if not is_blocked:
            bot.send_message(call.message.chat.id, "این کاربر بلاک نشده است!")
            cursor.close()
            return

        cursor.execute('''
            DELETE FROM block WHERE blocker_id = ? AND blocked_id = ?
        ''', (user_id, partner_id))
        conn.commit()
        cursor.close()

        bot.send_message(call.message.chat.id, "کاربر با موفقیت آنبلاک شد! ✅")


# ایجاد جدول follow
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS follow (
    follower_id INTEGER,
    followed_id INTEGER,
    PRIMARY KEY (follower_id, followed_id)
)""")
conn.commit()
cursor.close()

# بررسی و اضافه کردن ستون latitude به جدول users (برای سازگاری با کد قبلی)
cursor = conn.cursor()
try:
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'latitude' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN latitude REAL")
        conn.commit()
    else:
        pass
except sqlite3.OperationalError as e:
    pass
finally:
    cursor.close()


# تعریف handlerها
def register_callback_handlers(bot):
    @bot.callback_query_handler(func=lambda call: call.data == 'friends')
    def handle_friends_query(call):
        user_id = call.from_user.id
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "به بخش 👫 دوستان خوش آمدید ❕",
            reply_markup=create_friends_menu()
        )


def create_friends_menu():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("کسایی که فالو کردم", callback_data='following'),
        types.InlineKeyboardButton("کسایی که منو فالو کردن", callback_data='followers')
    )
    return keyboard


def register_following_handler(bot, conn):
    @bot.callback_query_handler(func=lambda call: call.data == 'following')
    def handle_following_query(call):
        user_id = call.from_user.id
        bot.answer_callback_query(call.id)

        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.name, u.age, u.city, u.unique_id
            FROM users u
            JOIN follow f ON u.user_id = f.followed_id
            WHERE f.follower_id = ?
        ''', (user_id,))

        following = cursor.fetchall()
        cursor.close()

        if not following:
            bot.send_message(call.message.chat.id, "شما هنوز کسی رو فالو نکردید!", reply_markup=create_friends_menu())
            return

        message = "کسایی که فالو کردید:\n"
        for user in following:
            message += f"نام: {user[1]}\nسن: {user[2]}\nشهر: {user[3]}\n/آیدی: @/user_{user[4]}\n\n"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🛑 آنفالو", callback_data=f'unfollow_partner_{user[0]}'))
            bot.send_message(call.message.chat.id, message, reply_markup=keyboard)
            message = ""  # ریست پیام برای کاربر بعدی

        bot.send_message(call.message.chat.id, "بازگشت به منوی دوستان:", reply_markup=create_friends_menu())


def register_followers_handler(bot, conn):
    @bot.callback_query_handler(func=lambda call: call.data == 'followers')
    def handle_followers_query(call):
        user_id = call.from_user.id
        bot.answer_callback_query(call.id)

        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.name, u.age, u.city, u.unique_id
            FROM users u
            JOIN follow f ON u.user_id = f.follower_id
            WHERE f.followed_id = ?
        ''', (user_id,))

        followers = cursor.fetchall()
        cursor.close()

        if not followers:
            bot.send_message(call.message.chat.id, "هنوز کسی شما رو فالو نکرده!", reply_markup=create_friends_menu())
            return

        message = "کسایی که شما رو فالو کردن:\n"
        for user in followers:
            cursor2 = conn.cursor()
            cursor2.execute('''
                SELECT 1 FROM follow WHERE follower_id = ? AND followed_id = ?
            ''', (user_id, user[0]))
            is_following = cursor2.fetchone()
            cursor2.close()

            follow_button_text = "🛑 آنفالو" if is_following else "🕺 دنبال کردن"
            follow_button_data = f'unfollow_partner_{user[0]}' if is_following else f'follow_partner_{user[0]}'

            message += f"نام: {user[1]}\nسن: {user[2]}\nشهر: {user[3]}\nآیدی: @{user[4]}\n\n"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton(follow_button_text, callback_data=follow_button_data))
            bot.send_message(call.message.chat.id, message, reply_markup=keyboard)
            message = ""  # ریست پیام برای کاربر بعدی

        bot.send_message(call.message.chat.id, "بازگشت به منوی دوستان:", reply_markup=create_friends_menu())


def register_follow_partner_handler(bot, conn):
    @bot.callback_query_handler(func=lambda call: call.data.startswith('follow_partner_'))
    def handle_follow_partner(call):
        user_id = call.from_user.id
        partner_id = int(call.data.split('_')[-1])
        bot.answer_callback_query(call.id)

        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1 FROM follow WHERE follower_id = ? AND followed_id = ?
        ''', (user_id, partner_id))
        already_following = cursor.fetchone()

        if already_following:
            bot.send_message(call.message.chat.id, "شما این کاربر را قبلاً فالو کرده‌اید!")
            cursor.close()
            return

        cursor.execute('''
            INSERT INTO follow (follower_id, followed_id) VALUES (?, ?)
        ''', (user_id, partner_id))
        cursor.execute('''
            UPDATE users SET following_count = following_count + 1 WHERE user_id = ?
        ''', (user_id,))
        cursor.execute('''
            UPDATE users SET followers_count = followers_count + 1 WHERE user_id = ?
        ''', (partner_id,))
        conn.commit()
        cursor.close()

        bot.send_message(call.message.chat.id, "کاربر با موفقیت فالو شد! ✅", reply_markup=create_friends_menu())


def register_unfollow_partner_handler(bot, conn):
    @bot.callback_query_handler(func=lambda call: call.data.startswith('unfollow_partner_'))
    def handle_unfollow_partner(call):
        user_id = call.from_user.id
        partner_id = int(call.data.split('_')[-1])
        bot.answer_callback_query(call.id)

        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1 FROM follow WHERE follower_id = ? AND followed_id = ?
        ''', (user_id, partner_id))
        is_following = cursor.fetchone()

        if not is_following:
            bot.send_message(call.message.chat.id, "شما این کاربر را فالو نکرده‌اید!")
            cursor.close()
            return

        cursor.execute('''
            DELETE FROM follow WHERE follower_id = ? AND followed_id = ?
        ''', (user_id, partner_id))
        cursor.execute('''
            UPDATE users SET following_count = following_count - 1 WHERE user_id = ?
        ''', (user_id,))
        cursor.execute('''
            UPDATE users SET followers_count = followers_count - 1 WHERE user_id = ?
        ''', (partner_id,))
        conn.commit()
        cursor.close()

        bot.send_message(call.message.chat.id, "کاربر با موفقیت آنفالو شد! 🛑", reply_markup=create_friends_menu())


# فرض می‌کنیم bot قبلاً تعریف شده


# ثبت handlerها
register_following_handler(bot, conn)
register_followers_handler(bot, conn)
register_follow_partner_handler(bot, conn)
register_unfollow_partner_handler(bot, conn)
register_callback_handlers(bot)
register_block_partner_handler(bot, conn)
register_block_list_handler(bot, conn)
register_unblock_partner_handler(bot, conn)


@bot.callback_query_handler(func=lambda call: call.data == 'private_chat_toggle')
def private_chat_toggle(call):
    user_id = call.from_user.id
    cursor.execute(
        "SELECT private_chat_enabled, name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo FROM users WHERE user_id = ?",
        (user_id,))
    user = cursor.fetchone()

    if not user:
        bot.answer_callback_query(call.id, "حساب شما پیدا نشد!")
        return

    private_chat_enabled, name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo = user

    # تغییر وضعیت چت خصوصی
    new_status = 1 if private_chat_enabled == 0 else 0
    cursor.execute("UPDATE users SET private_chat_enabled = ? WHERE user_id = ?", (new_status, user_id))
    conn.commit()

    # آپدیت متن پروفایل
    gender_display = "پسر 👨‍🦰" if gender == 'male' else "دختر 👩"
    profile_text = f"""•نام: {name} 
•جنسیت: {gender_display}
دنبال کننده ها: {followers_count}
دنبال میکند: {following_count}
•استان: {province or 'نامشخص'}
•شهر: {city or 'نامشخص'}
•سن: {age or 'نامشخص'}
🆔 : /user_{unique_id}
تعداد لایک ها : {likes_count}"""

    # آپدیت کیبورد با وضعیت جدید
    markup = get_profile_inline_keyboard(user_id)

    # آپدیت پیام پروفایل
    try:
        if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
            bot.edit_message_media(
                media=types.InputMediaPhoto(profile_photo, caption=profile_text),
                chat_id=user_id,
                message_id=call.message.message_id,
                reply_markup=markup
            )
        else:
            bot.edit_message_text(
                text=profile_text,
                chat_id=user_id,
                message_id=call.message.message_id,
                reply_markup=markup
            )
        bot.answer_callback_query(call.id, "وضعیت چت خصوصی تغییر کرد!")
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error updating profile message: {e}")
        bot.send_message(user_id, profile_text, reply_markup=markup)
        bot.answer_callback_query(call.id, "وضعیت چت خصوصی تغییر کرد، اما پیام پروفایل آپدیت نشد!")


cursor = conn.cursor()
# اضافه کردن ستون‌های latitude و longitude به جدول users
try:
    cursor.execute("ALTER TABLE users ADD COLUMN latitude REAL")
    cursor.execute("ALTER TABLE users ADD COLUMN longitude REAL")
    conn.commit()
except sqlite3.OperationalError:
    # اگه ستون‌ها قبلاً وجود داشته باشن، خطا رو نادیده بگیر
    pass

# تعریف کیبورد برای ارسال موقعیت مکانی و لغو
location_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
location_button = types.KeyboardButton("ارسال موقعیت مکانی 📍", request_location=True)
cancel_button = types.KeyboardButton("لغو ❌")
location_markup.add(location_button, cancel_button)


# هندلر برای دکمه‌ی موقعیت مکانی
@bot.callback_query_handler(func=lambda call: call.data == 'location')
def request_location(call):
    user_id = call.from_user.id
    text = """❓موقعیت GPS خود را ارسال کنید👇

⚠️ هنگام ارسال موقعیت مکانی مطمعن شوید GPS موبایل شما روشن است.

✅ کسی قادر به دیدن موقعیت مکانی شما در ربات نخواهد بود و فقط برای تخمین فاصله و یافتن افراد نزدیک کاربرد خواهد داشت"""

    try:
        bot.delete_message(user_id, call.message.message_id)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error deleting message: {e}")

    bot.send_message(user_id, text, reply_markup=location_markup)
    bot.register_next_step_handler(call.message, process_location)


# هندلر برای پردازش موقعیت مکانی یا لغو
def process_location(message):
    user_id = message.from_user.id

    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=main_markup)
        return

    if message.location:
        latitude = message.location.latitude
        longitude = message.location.longitude

        # ذخیره‌ی مختصات در دیتابیس
        cursor.execute("UPDATE users SET latitude = ?, longitude = ? WHERE user_id = ?", (latitude, longitude, user_id))
        conn.commit()

        bot.send_message(user_id, "موقعیت مکانی شما با موفقیت ذخیره شد! ✅", reply_markup=main_markup)
    else:
        bot.send_message(user_id, "لطفاً موقعیت مکانی خود را ارسال کنید یا لغو کنید.", reply_markup=location_markup)
        bot.register_next_step_handler(message, process_location)


# هندلر برای نمایش گفت‌وگوهای اخیر
@bot.callback_query_handler(func=lambda call: call.data == 'recent_chats')
def recent_chats(call):
    user_id = call.from_user.id
    cursor.execute('''
        SELECT u.name, u.gender, u.age, u.province, u.city, u.unique_id
        FROM chat_history ch
        JOIN users u ON ch.partner_id = u.user_id
        WHERE ch.user_id = ?
        ORDER BY ch.chat_time DESC
        LIMIT 10
    ''', (user_id,))
    recent_partners = cursor.fetchall()

    if not recent_partners:
        bot.answer_callback_query(call.id, "شما هنوز با کسی چت نکرده‌اید!")
        bot.send_message(user_id, "📋 هنوز با کسی چت نکرده‌اید!", reply_markup=main_markup)
        return

    message_text = "📋 لیست کسانی که اخیرا باهاشون چت کردی ❕\n\n"
    for name, gender, age, province, city, unique_id in recent_partners:
        gender_display = "👨‍🦰" if gender == 'male' else "👩"
        province_display = province if province else "نامشخص"
        city_display = city if city else "نامشخص"
        age_display = age if age else "نامشخص"
        message_text += f"{gender_display} نام‌: {name} (سن: {age_display})\n"
        message_text += f"استان:‌ {province_display} ({city_display})\n\n"
        message_text += f"🆔 : /user_{unique_id}\n"
        message_text += "〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"

    try:
        bot.delete_message(user_id, call.message.message_id)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error deleting message: {e}")

    bot.send_message(user_id, message_text, reply_markup=main_markup)
    bot.answer_callback_query(call.id, "لیست گفت‌وگوهای اخیر نمایش داده شد!")


@bot.callback_query_handler(func=lambda call: call.data == 'delete_account')
def delete_account(call):
    user_id = call.from_user.id
    cursor.execute("SELECT status, partner_id, name, unique_id FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        bot.answer_callback_query(call.id, "حساب شما پیدا نشد!")
        return

    status, partner_id, name, unique_id = user

    # اگه کاربر در حال چت باشه، به پارتنر اطلاع بده و چت رو پایان بده
    if status == 'chatting' and partner_id:
        cursor.execute("UPDATE users SET status = 'idle', partner_id = NULL WHERE user_id = ?", (partner_id,))
        conn.commit()
        bot.send_message(partner_id, f"چت با ({name}) /user_{unique_id} به دلیل حذف حساب کاربر پایان یافت.",
                         reply_markup=main_markup)

    # حذف تمام لایک‌های مرتبط با کاربر (چه به عنوان لايک‌کننده و چه لايک‌شده)
    cursor.execute("DELETE FROM likes WHERE user_id = ? OR target_id = ?", (user_id, user_id))

    # آپدیت تعداد لایک‌های کاربرانی که توسط این کاربر لایک شده بودن
    cursor.execute(
        "UPDATE users SET likes_count = likes_count - 1 WHERE user_id IN (SELECT target_id FROM likes WHERE user_id = ?)",
        (user_id,))

    # حذف حساب کاربر از جدول users
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()

    # حذف پیام پروفایل
    try:
        bot.delete_message(user_id, call.message.message_id)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error deleting message: {e}")

    # اطلاع به کاربر
    bot.answer_callback_query(call.id, "حساب شما با موفقیت حذف شد!")
    bot.send_message(user_id, "حساب شما حذف شد. برای ثبت‌نام دوباره، /start رو بزن.",
                     reply_markup=types.ReplyKeyboardRemove())


# تابع اصلاح‌شده برای ساخت اینلاین کیبورد پروفایل مخاطب در چت
def get_partner_profile_inline_keyboard(user_id, partner_id):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM likes WHERE user_id = ? AND target_id = ?", (user_id, partner_id))
    has_liked = cursor.fetchone()[0] > 0
    cursor.close()
    like_button_text = "Unlike 🤍" if has_liked else "Like 🤍"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(like_button_text, callback_data=f'like_partner_{partner_id}'),
        types.InlineKeyboardButton("🕺 دنبال کردن", callback_data=f'follow_partner_{partner_id}')
    )
    markup.add(
        types.InlineKeyboardButton("💬 درخواست چت", callback_data=f'request_chat_{partner_id}'),
        types.InlineKeyboardButton("✉️ پیام دایرکت", callback_data=f'direct_message_{partner_id}')
    )
    markup.add(
        types.InlineKeyboardButton("🚫 بلاک", callback_data=f'block_partner_{partner_id}'),
        types.InlineKeyboardButton("⛔ گزارش کردن", callback_data=f'report_partner_{partner_id}')
    )
    markup.add(
        types.InlineKeyboardButton("🎁 هدیه به کاربر", callback_data=f'gift_partner_{partner_id}'),
        types.InlineKeyboardButton("🎙️ چت کردنش تموم شد بهم خبر بده", callback_data=f'notify_chat_end_{partner_id}')
    )
    return markup


# دیکشنری موقت برای ذخیره درخواست‌های اعلان پایان چت
pending_chat_end_notifications = defaultdict(list)


# هندلر برای دکمه‌ی اعلان پایان چت
@bot.callback_query_handler(func=lambda call: call.data.startswith('notify_chat_end_'))
def notify_chat_end(call):
    user_id = call.from_user.id
    update_last_online(user_id)
    try:
        target_id = int(call.data.split('_')[-1])  # فرمت: notify_chat_end_<target_id>
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, "خطا: درخواست نامعتبر است!")
        return

    # چک کردن اینکه target_id با user_id یکسان نباشه
    if target_id == user_id:
        bot.answer_callback_query(call.id, "نمی‌تونید برای خودتون اعلان تنظیم کنید!")
        return

    # چک کردن وجود کاربر و هدف
    cursor = conn.cursor()
    cursor.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    requester = cursor.fetchone()
    cursor.execute("SELECT unique_id FROM users WHERE user_id = ?", (target_id,))
    target = cursor.fetchone()
    cursor.close()

    if not requester or not target:
        bot.answer_callback_query(call.id, "کاربر یا مخاطب پیدا نشد!")
        return

    requester_coins = requester[0]
    target_unique_id = target[0]

    # چک کردن تعداد سکه‌ها
    if requester_coins < 1:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("خرید سکه", callback_data='buy_coins'))
        bot.send_message(
            user_id,
            """⚠️ توجه: شما سکه کافی ندارید! (۱ سکه مورد نیاز)
💡 برای بدست آوردن سکه می‌تونی رباتو به دوستات معرفی کنی و به ازای معرفی هر نفر ۲۰ سکه هدیه بگیری.
❗️ اگه دوستی نداری که دعوت کنی می‌تونی از پنل خرید سکه 💰 استفاده کنی و سکه‌هاتو افزایش بدی.""",
            reply_markup=markup
        )
        bot.answer_callback_query(call.id, "سکه کافی ندارید!")
        return

    # چک کردن درخواست تکراری
    if user_id in pending_chat_end_notifications[target_id]:
        bot.answer_callback_query(call.id, "شما قبلاً برای این کاربر اعلان تنظیم کرده‌اید!")
        return

    # کسر ۱ سکه
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET coins = coins - 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    cursor.close()

    # ذخیره درخواست اعلان
    pending_chat_end_notifications[target_id].append(user_id)

    # ارسال پیام تأیید
    bot.send_message(
        user_id,
        f"""✅ یه سکه ازت کسر شد.

🔔 به محض اتمام چت کاربر /user_{target_unique_id} به شما اطلاع داده خواهد شد.

(راهنما: /help_chw)""",
        reply_markup=main_markup
    )
    bot.answer_callback_query(call.id, "اعلان پایان چت با موفقیت تنظیم شد!")


# هندلر برای دکمه‌ی بلاک
@bot.callback_query_handler(func=lambda call: call.data.startswith('block_partner_'))
def block_partner(call):
    bot.answer_callback_query(call.id, "کاربر بلاک شد!")


# هندلر برای دکمه‌ی گزارش کردن
@bot.callback_query_handler(func=lambda call: call.data.startswith('report_partner_'))
def report_partner(call):
    bot.answer_callback_query(call.id, "کاربر گزارش شد!")


# دیکشنری موقت برای ذخیره حالت انتظار پیام دایرکت
pending_direct_messages = defaultdict(dict)


# هندلر برای دکمه‌ی پیام دایرکت
@bot.callback_query_handler(func=lambda call: call.data.startswith('direct_message_'))
def direct_message_start(call):
    user_id = call.from_user.id
    update_last_online(user_id)
    try:
        target_id = int(call.data.split('_')[-1])  # فرمت: direct_message_<target_id>
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, "خطا: درخواست نامعتبر است!")
        return

    # چک کردن اینکه target_id با user_id یکسان نباشه
    if target_id == user_id:
        bot.answer_callback_query(call.id, "نمی‌تونید به خودتون پیام دایرکت بفرستید!")
        return

    # چک کردن وجود کاربر و هدف
    cursor = conn.cursor()
    cursor.execute("SELECT name, unique_id FROM users WHERE user_id = ?", (target_id,))
    target = cursor.fetchone()
    cursor.close()

    if not target:
        bot.answer_callback_query(call.id, "کاربر هدف پیدا نشد!")
        return

    target_name, target_unique_id = target

    # ذخیره حالت انتظار برای دریافت پیام
    pending_direct_messages[user_id] = {'target_id': target_id, 'timestamp': time.time()}

    # ایجاد کیبورد Reply برای لغو
    cancel_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    cancel_markup.add(types.KeyboardButton("لغو ❌"))

    # ارسال پیام درخواست متن و ثبت تابع بعدی
    sent_message = bot.send_message(
        user_id,
        f"""متن پیام دایرکت خود را ارسال کنید (حداکثر ۲۰۰ حرف)

- برای لغو ارسال پیام دایرکت به ({target_name}) /user_{target_unique_id} 《لغو》 را لمس کنید""",
        reply_markup=cancel_markup
    )
    bot.register_next_step_handler(sent_message, handle_direct_message_text)
    bot.answer_callback_query(call.id, "لطفاً متن پیام دایرکت را وارد کنید.")


# تابع برای دریافت متن پیام دایرکت یا لغو
def handle_direct_message_text(message):
    user_id = message.from_user.id
    text = message.text

    # چک کردن آیا کاربر در حالت انتظار پیام دایرکت هست
    if user_id not in pending_direct_messages:
        bot.send_message(user_id, "خطا: درخواست نامعتبر است!", reply_markup=main_markup)
        return

    target_id = pending_direct_messages[user_id]['target_id']
    cursor = conn.cursor()
    cursor.execute("SELECT name, unique_id, coins FROM users WHERE user_id = ?", (user_id,))
    requester = cursor.fetchone()
    cursor.execute("SELECT name, unique_id FROM users WHERE user_id = ?", (target_id,))
    target = cursor.fetchone()
    cursor.close()

    if not requester or not target:
        bot.send_message(user_id, "کاربر یا مخاطب پیدا نشد!", reply_markup=main_markup)
        del pending_direct_messages[user_id]
        return

    requester_name, requester_unique_id, requester_coins = requester
    target_name, target_unique_id = target

    # چک کردن لغو
    if text == "لغو ❌":
        bot.send_message(user_id, "ارسال پیام دایرکت لغو شد.", reply_markup=main_markup)
        del pending_direct_messages[user_id]
        return

    # چک کردن طول پیام
    if len(text) > 200:
        cancel_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        cancel_markup.add(types.KeyboardButton("لغو ❌"))
        sent_message = bot.send_message(
            user_id,
            "پیام شما بیشتر از ۲۰۰ حرف است! لطفاً پیام کوتاه‌تری بنویسید.",
            reply_markup=cancel_markup
        )
        bot.register_next_step_handler(sent_message, handle_direct_message_text)
        return

    # چک کردن تعداد سکه‌ها
    if requester_coins < 1:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("خرید سکه", callback_data='buy_coins'))
        bot.send_message(
            user_id,
            """⚠️ توجه: شما سکه کافی ندارید! (۱ سکه مورد نیاز)
💡 برای بدست آوردن سکه می‌تونی رباتو به دوستات معرفی کنی و به ازای معرفی هر نفر ۲۰ سکه هدیه بگیری.
❗️ اگه دوستی نداری که دعوت کنی می‌تونی از پنل خرید سکه 💰 استفاده کنی و سکه‌هاتو افزایش بدی.""",
            reply_markup=markup
        )
        del pending_direct_messages[user_id]
        return

    # کسر ۱ سکه
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET coins = coins - 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    cursor.close()

    # ارسال پیام دایرکت به کاربر هدف
    message_text = f"""پیام دایرکت از ({requester_name}) /user_{requester_unique_id}:
{text}

💡 می‌تونی با /user_{requester_unique_id} پروفایلش رو ببینی یا جواب بدی!"""
    try:
        bot.send_message(target_id, message_text)
        bot.send_message(user_id, f"پیام دایرکت به ({target_name}) /user_{target_unique_id} ارسال شد!",
                         reply_markup=main_markup)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error sending direct message to {target_id}: {e}")
        # در صورت خطا، سکه رو برگردون
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET coins = coins + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        cursor.close()
        bot.send_message(user_id, "خطا در ارسال پیام دایرکت! لطفاً دوباره امتحان کنید.", reply_markup=main_markup)

    # پاک کردن حالت انتظار
    del pending_direct_messages[user_id]


# هندلر برای دکمه‌ی خرید سکه (placeholder)
@bot.callback_query_handler(func=lambda call: call.data == 'buy_coins')
def buy_coins(call):
    bot.answer_callback_query(call.id, "اینجا باید به پنل خرید سکه هدایت بشید! (در حال حاضر پیاده‌سازی نشده)")
    bot.send_message(call.from_user.id, "برای خرید سکه، لطفاً به پنل خرید مراجعه کنید یا دوستان خود را دعوت کنید!",
                     reply_markup=main_markup)


pending_requests = defaultdict(dict)


# هندلر اصلاح‌شده برای دکمه‌ی درخواست چت
@bot.callback_query_handler(func=lambda call: call.data.startswith('request_chat'))
def request_chat(call):
    user_id = call.from_user.id
    # گرفتن target_id از callback_data
    try:
        target_id = int(call.data.split('_')[-1])  # فرمت: request_chat_<target_id>
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, "خطا: درخواست نامعتبر است!")
        return

    # چک کردن اینکه target_id با user_id یکسان نباشه
    if target_id == user_id:
        bot.answer_callback_query(call.id, "نمی‌تونید به خودتون درخواست چت بفرستید!")
        return

    # چک کردن وجود کاربر و هدف
    cursor = conn.cursor()
    cursor.execute("SELECT coins, name, unique_id FROM users WHERE user_id = ?", (user_id,))
    requester = cursor.fetchone()
    cursor.execute("SELECT name, unique_id, status, private_chat_enabled FROM users WHERE user_id = ?", (target_id,))
    target = cursor.fetchone()
    cursor.close()

    if not requester or not target:
        bot.answer_callback_query(call.id, "کاربر یا مخاطب پیدا نشد!")
        return

    requester_coins, requester_name, requester_unique_id = requester
    target_name, target_unique_id, target_status, private_chat_enabled = target

    # چک کردن حالت سکوت
    if private_chat_enabled:
        bot.answer_callback_query(call.id, "این کاربر حالت سکوت را فعال کرده و نمی‌توان به او درخواست چت فرستاد!")
        return

    # چک کردن تعداد سکه‌ها
    if requester_coins < 2:
        bot.answer_callback_query(call.id, "شما سکه‌ی کافی ندارید! حداقل ۲ سکه نیاز است.")
        return

    # چک کردن وضعیت هدف (نباید در چت باشه)
    if target_status == 'chatting':
        bot.answer_callback_query(call.id, "این کاربر در حال حاضر در چت است!")
        return

    # کسر ۲ سکه
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET coins = coins - 2 WHERE user_id = ?", (user_id,))
    conn.commit()
    cursor.close()

    # ثبت درخواست در دیکشنری موقت
    pending_requests[target_id][user_id] = time.time()

    # ارسال پیام درخواست به کاربر هدف
    request_text = f"""({requester_name}) /user_{requester_unique_id}
بهت یه درخواست چت فرستاده, میتونی قبول کنی یا ردش کنی 😉

یادت باشه این درخواست تا ۴ دقیقه معتبره !

💡با فعال کردن حالت سکوت، کسی امکان درخواست چت به شما را نخواهد داشت 👈 /silent"""
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("قبول درخواست ✅", callback_data=f'accept_chat_{user_id}'),
        types.InlineKeyboardButton("رد درخواست ❌", callback_data=f'reject_chat_{user_id}')
    )
    try:
        bot.send_message(target_id, request_text, reply_markup=markup)
        bot.answer_callback_query(call.id, "درخواست چت به کاربر هدف ارسال شد!")
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error sending chat request to user {target_id}: {e}")
        bot.answer_callback_query(call.id, "خطا در ارسال درخواست چت!")


# هندلر برای قبول درخواست چت
@bot.callback_query_handler(func=lambda call: call.data.startswith('accept_chat_'))
def accept_chat(call):
    user_id = call.from_user.id  # کاربر هدف (کسی که درخواست رو قبول می‌کنه)
    update_last_online(user_id)
    try:
        requester_id = int(call.data.split('_')[-1])  # فرمت: accept_chat_<requester_id>
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, "خطا: درخواست نامعتبر است!")
        return

    # چک کردن وجود درخواست
    if requester_id not in pending_requests.get(user_id, {}):
        bot.answer_callback_query(call.id, "این درخواست دیگر معتبر نیست یا وجود ندارد!")
        return

    # چک کردن وجود و وضعیت کاربران
    cursor = conn.cursor()
    cursor.execute("SELECT status, name, unique_id FROM users WHERE user_id = ?", (user_id,))
    target = cursor.fetchone()
    cursor.execute("SELECT status, name, unique_id FROM users WHERE user_id = ?", (requester_id,))
    requester = cursor.fetchone()
    cursor.close()

    if not target or not requester:
        bot.answer_callback_query(call.id, "کاربر یا درخواست‌کننده پیدا نشد!")
        if requester_id in pending_requests[user_id]:
            del pending_requests[user_id][requester_id]
            if not pending_requests[user_id]:
                del pending_requests[user_id]
        return

    target_status, target_name, target_unique_id = target
    requester_status, requester_name, requester_unique_id = requester

    # چک کردن وضعیت (نباید در چت باشن)
    if target_status == 'chatting' or requester_status == 'chatting':
        bot.answer_callback_query(call.id, "شما یا درخواست‌کننده در حال حاضر در چت هستید!")
        if requester_id in pending_requests[user_id]:
            del pending_requests[user_id][requester_id]
            if not pending_requests[user_id]:
                del pending_requests[user_id]
        return

    # حذف درخواست از دیکشنری
    del pending_requests[user_id][requester_id]
    if not pending_requests[user_id]:
        del pending_requests[user_id]

    # به‌روزرسانی وضعیت کاربران
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = 'chatting', partner_id = ? WHERE user_id = ?", (requester_id, user_id))
    cursor.execute("UPDATE users SET status = 'chatting', partner_id = ? WHERE user_id = ?", (user_id, requester_id))
    cursor.execute("INSERT INTO chat_history (user_id, partner_id) VALUES (?, ?)", (user_id, requester_id))
    cursor.execute("INSERT INTO chat_history (user_id, partner_id) VALUES (?, ?)", (requester_id, user_id))
    conn.commit()
    cursor.close()

    # ارسال پیام شروع چت
    start_text_target = f"چت با ({requester_name}) /user_{requester_unique_id} شروع شد! بهش سلام کن :)\n🤖 پیام سیستم 👇🏻\n⚠️ اخطار: به هیچ کاربری در ربات اعتماد نکنید و اطلاعات شخصیتان را در اختیار کسی قرار ندهید!"
    start_text_requester = f"چت با ({target_name}) /user_{target_unique_id} شروع شد! بهش سلام کن :)\n🤖 پیام سیستم 👇🏻\n⚠️ اخطار: به هیچ کاربری در ربات اعتماد نکنید و اطلاعات شخصیتان را در اختیار کسی قرار ندهید!"

    # تلاش برای ارسال پیام به هر دو کاربر
    target_message_sent = False
    requester_message_sent = False

    # ارسال پیام به کاربر هدف (اول سعی می‌کنه ویرایش کنه، اگه نشد پیام جدید می‌فرسته)
    try:
        bot.edit_message_text(start_text_target, user_id, call.message.message_id, reply_markup=chat_markup)
        target_message_sent = True
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error editing message for target {user_id}: {e}")
        try:
            bot.send_message(user_id, start_text_target, reply_markup=chat_markup)
            target_message_sent = True
        except telebot.apihelper.ApiTelegramException as e:
            print(f"Error sending new message to target {user_id}: {e}")

    # ارسال پیام به درخواست‌کننده
    try:
        bot.send_message(requester_id, start_text_requester, reply_markup=chat_markup)
        requester_message_sent = True
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error sending message to requester {requester_id}: {e}")

    # بررسی موفقیت ارسال پیام‌ها
    if target_message_sent and requester_message_sent:
        bot.answer_callback_query(call.id, "چت با موفقیت شروع شد!")
    else:
        bot.answer_callback_query(call.id, "خطا در شروع چت!")
        # در صورت خطا، وضعیت رو برگردون
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'idle', partner_id = NULL WHERE user_id IN (?, ?)",
                       (user_id, requester_id))
        conn.commit()
        cursor.close()
        if not target_message_sent:
            bot.send_message(user_id, "خطا در شروع چت! لطفاً دوباره امتحان کنید.", reply_markup=main_markup)
        if not requester_message_sent:
            try:
                bot.send_message(requester_id, "خطا در شروع چت! لطفاً دوباره امتحان کنید.", reply_markup=main_markup)
            except telebot.apihelper.ApiTelegramException as e:
                print(f"Error sending error message to requester {requester_id}: {e}")


# هندلر برای رد درخواست چت
@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_chat_'))
def reject_chat(call):
    user_id = call.from_user.id  # کاربر هدف (کسی که درخواست رو رد می‌کنه)
    try:
        requester_id = int(call.data.split('_')[-1])  # فرمت: reject_chat_<requester_id>
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, "خطا: درخواست نامعتبر است!")
        return

    # چک کردن وجود درخواست
    if requester_id not in pending_requests.get(user_id, {}):
        bot.answer_callback_query(call.id, "این درخواست دیگر معتبر نیست یا وجود ندارد!")
        return

    # حذف درخواست از دیکشنری
    del pending_requests[user_id][requester_id]
    if not pending_requests[user_id]:
        del pending_requests[user_id]

    # اطلاع به کاربران
    try:
        bot.edit_message_text("درخواست چت رد شد.", user_id, call.message.message_id, reply_markup=None)
        bot.send_message(requester_id, "درخواست چت شما رد شد.", reply_markup=main_markup)
        bot.answer_callback_query(call.id, "درخواست چت رد شد!")
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error rejecting chat for users {user_id} and {requester_id}: {e}")
        bot.answer_callback_query(call.id, "خطا در رد درخواست!")


# تابع اصلاح‌شده برای نمایش پروفایل با /user_<unique_id>
@bot.message_handler(regexp=r'^/user_([A-Za-z0-9]{8})$')
def show_user_profile_by_unique_id(message):
    user_id = message.from_user.id
    update_last_online(user_id)  # آپدیت زمان آنلاین
    unique_id = re.match(r'^/user_([A-Za-z0-9]{8})$', message.text).group(1)

    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online FROM users WHERE unique_id = ?",
        (unique_id,))
    user = cursor.fetchone()
    cursor.close()

    if user:
        target_id, name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online = user
        if target_id == user_id:
            bot.send_message(user_id,
                             "نمی‌تونید پروفایل خودتون رو با این دستور ببینید! از '👤 پروفایل من' استفاده کنید.",
                             reply_markup=main_markup)
            return
        gender_display = "پسر 👨‍🦰" if gender == 'male' else "دختر 👩"
        profile_text = f"""•نام: {name} 
        •جنسیت: {gender_display}
        دنبال کننده ها: {followers_count}
        دنبال میکند: {following_count}
        •استان: {province or 'نامشخص'}
        •شهر: {city or 'نامشخص'}
        •سن: {age or 'نامشخص'}
        🆔 : /user_{unique_id}
        تعداد لایک ها : {likes_count}
        سکه‌ها: {coins}
        •وضعیت: {format_last_online(last_online)}"""

        markup = get_partner_profile_inline_keyboard(user_id, target_id)
        if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
            try:
                bot.send_photo(user_id, profile_photo, caption=profile_text, reply_markup=markup)
            except telebot.apihelper.ApiTelegramException as e:
                print(f"Error sending profile photo for unique_id {unique_id}: {e} (file_id: {profile_photo})")
                bot.send_message(user_id, profile_text + "\n⚠️ خطا در نمایش عکس پروفایل!", reply_markup=markup)
        else:
            bot.send_message(user_id, profile_text, reply_markup=markup)
    else:
        bot.send_message(user_id, f"کاربری با آیدی /user_{unique_id} پیدا نشد!", reply_markup=main_markup)


# هندلر اصلاح‌شده برای لایک کردن پروفایل مخاطب
@bot.callback_query_handler(func=lambda call: call.data.startswith('like_partner_'))
def like_partner(call):
    user_id = call.from_user.id
    update_last_online(user_id)
    try:
        partner_id = int(call.data.split('_')[-1])  # فرمت: like_partner_<partner_id>
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, "خطا: درخواست نامعتبر است!")
        return

    if partner_id == user_id:
        bot.answer_callback_query(call.id, "نمی‌تونید خودتون رو لایک کنید!")
        return

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM likes WHERE user_id = ? AND target_id = ?", (user_id, partner_id))
    has_liked = cursor.fetchone()[0] > 0

    if has_liked:
        # Unlike
        cursor.execute("DELETE FROM likes WHERE user_id = ? AND target_id = ?", (user_id, partner_id))
        cursor.execute("UPDATE users SET likes_count = likes_count - 1 WHERE user_id = ?", (partner_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "لایک شما برداشته شد!")
    else:
        # Like
        try:
            cursor.execute("INSERT INTO likes (user_id, target_id) VALUES (?, ?)", (user_id, partner_id))
            cursor.execute("UPDATE users SET likes_count = likes_count + 1 WHERE user_id = ?", (partner_id,))
            conn.commit()
            bot.answer_callback_query(call.id, "پروفایل لایک شد!")
        except sqlite3.IntegrityError:
            bot.answer_callback_query(call.id, "شما قبلاً این پروفایل را لایک کرده‌اید!")

    # به‌روزرسانی پروفایل مخاطب
    cursor.execute(
        "SELECT name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, last_online FROM users WHERE user_id = ?",
        (partner_id,))
    user = cursor.fetchone()
    cursor.close()
    if user:
        p_name, p_gender, p_followers, p_following, p_province, p_city, p_age, p_likes, p_unique, profile_photo, last_online = user
        p_gender_display = "پسر 👨‍🦰" if p_gender == 'male' else "دختر 👩"
        profile_text = f"""•نام: {p_name} 
    •جنسیت: {p_gender_display}
    دنبال کننده ها: {p_followers}
    دنبال میکند: {p_following}
    •استان: {p_province or 'نامشخص'}
    •شهر: {p_city or 'نامشخص'}
    •سن: {p_age or 'نامشخص'}
    🆔 : /user_{p_unique}
    تعداد لایک ها : {p_likes}
    •وضعیت: {format_last_online(last_online)}"""
        markup = get_partner_profile_inline_keyboard(user_id, partner_id)
        try:
            if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
                bot.edit_message_media(
                    media=types.InputMediaPhoto(profile_photo, caption=profile_text),
                    chat_id=user_id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
            else:
                bot.edit_message_text(
                    text=profile_text,
                    chat_id=user_id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
        except telebot.apihelper.ApiTelegramException as e:
            print(f"Error updating partner profile for user {user_id}: {e}")
            bot.send_message(user_id, profile_text, reply_markup=markup)
            bot.answer_callback_query(call.id, "خطا در به‌روزرسانی پروفایل!")


# هندلر شروع


# هندلر انتخاب سن
@bot.message_handler(
    func=lambda message: message.text.isdigit() and 13 <= int(message.text) <= 60 or message.text == "لغو ❌")
def set_age(message):
    user_id = message.from_user.id
    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=main_markup)
        return

    age = int(message.text)
    cursor.execute("UPDATE users SET age = ? WHERE user_id = ?", (age, user_id))
    conn.commit()

    text = "از کدوم استان ؟\nخب حالا که سنت ثبت شد, فقط میمونه استان و شهرت که بهم بگی تا کارمون تموم بشه !"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    row = []
    for i, prov in enumerate(provinces):
        row.append(prov)
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)
    markup.add("لغو ❌")
    bot.send_message(user_id, text, reply_markup=markup)


# هندلر انتخاب استان
@bot.message_handler(func=lambda message: message.text in provinces or message.text == "لغو ❌")
def set_province(message):
    user_id = message.from_user.id
    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=main_markup)
        return

    province = message.text
    cursor.execute("UPDATE users SET province = ? WHERE user_id = ?", (province, user_id))
    conn.commit()

    text = "خب حالا که استانت ثبت شد, فقط میمونه شهرت که بهم بگی تا کارمون تموم بشه !"
    cities = cities_by_province.get(province, [])
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    row = []
    for city in cities:
        row.append(city)
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)
    markup.add("لغو ❌")
    bot.send_message(user_id, text, reply_markup=markup)


# هندلر انتخاب شهر
@bot.message_handler(func=lambda message: any(
    message.text in cities for cities in cities_by_province.values()) or message.text == "لغو ❌")
def set_city(message):
    user_id = message.from_user.id
    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=main_markup)
        return

    city = message.text
    cursor.execute("UPDATE users SET city = ? WHERE user_id = ?", (city, user_id))
    conn.commit()

    text = "🌟 خب حالا فقط کافیه یه اسم مستعار برای نمایش در ربات انتخاب کنی تا وارد ربات شیم!\n• اسم مستعارتو بفرست"
    bot.send_message(user_id, text, reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(message, get_name)


def get_name(message):
    user_id = message.from_user.id
    name = message.text
    cursor.execute("SELECT city FROM users WHERE user_id=?", (user_id,))
    if cursor.fetchone()[0]:
        cursor.execute("UPDATE users SET name = ? WHERE user_id = ?", (name, user_id))
        conn.commit()
        welcome = "خوش اومدی عزیز 🐳\nثبت نامت تکمیل شد✅"
        bot.send_message(user_id, welcome, reply_markup=main_markup)
    else:
        pass


# تابع show_profile (برای اطمینان از سازگاری)
# تابع show_profile
@bot.message_handler(func=lambda message: message.text == "👤 پروفایل من")
def show_profile(message):
    user_id = message.from_user.id
    update_last_online(user_id)  # آپدیت زمان آنلاین
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online FROM users WHERE user_id=?",
        (user_id,)
    )

    user = cursor.fetchone()
    cursor.close()

    if user:
        name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online = user
        gender_display = "پسر 👨‍🦰" if gender == 'male' else "دختر 👩"
        profile_text = f"""•نام: {name} 
•جنسیت: {gender_display}
دنبال کننده ها: {followers_count}
دنبال میکند: {following_count}
•استان: {province or 'نامشخص'}
•شهر: {city or 'نامشخص'}
•سن: {age or 'نامشخص'}
🆔 : /user_{unique_id}
تعداد لایک ها : {likes_count}
سکه‌ها: {coins}
•وضعیت: {format_last_online(last_online)}"""

        markup = get_profile_inline_keyboard(user_id)
        if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
            try:
                bot.send_photo(user_id, profile_photo, caption=profile_text, reply_markup=markup)
            except telebot.apihelper.ApiTelegramException as e:
                print(f"Error sending profile photo for user {user_id}: {e} (file_id: {profile_photo})")
                bot.send_message(user_id, profile_text + "\n⚠️ خطا در نمایش عکس پروفایل!", reply_markup=markup)
        else:
            bot.send_message(user_id, profile_text, reply_markup=markup)
    else:
        bot.send_message(user_id, "حساب شما پیدا نشد! لطفاً دوباره با /start ثبت‌نام کنید.", reply_markup=main_markup)


# کال‌بک برای ویرایش پروفایل
@bot.callback_query_handler(func=lambda call: call.data == 'edit_profile')
def edit_profile(call):
    user_id = call.from_user.id
    update_last_online(user_id)
    text = "یکی رو برای ویرایش انتخاب کن."
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("تغیر نام 📝", callback_data='edit_username'),
        types.InlineKeyboardButton("تغیر عکس پروفایل 🖼", callback_data='edit_photo')
    )
    markup.add(
        types.InlineKeyboardButton("تغیر استان 🗺", callback_data='edit_province'),
        types.InlineKeyboardButton("تغیر سن 🎂", callback_data='edit_age')
    )
    markup.add(
        types.InlineKeyboardButton("تغیر جنسیت ⚥", callback_data='edit_gender')
    )

    try:
        bot.delete_message(user_id, call.message.message_id)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error deleting message: {e}")

    bot.send_message(user_id, text, reply_markup=markup)


# کال‌بک برای تغییر نام
@bot.callback_query_handler(func=lambda call: call.data == 'edit_username')
def request_username(call):
    user_id = call.from_user.id
    text = "لطفاً نام جدید خود را وارد کنید."
    reply_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    reply_markup.add("لغو ❌")
    bot.send_message(user_id, text, reply_markup=reply_markup)
    bot.register_next_step_handler(call.message, process_username_step, call.message.message_id)


def process_username_step(message, edit_message_id):
    user_id = message.from_user.id
    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=types.ReplyKeyboardRemove())
        edit_markup = types.InlineKeyboardMarkup(row_width=2)
        edit_markup.add(
            types.InlineKeyboardButton("تغیر نام 📝", callback_data='edit_username'),
            types.InlineKeyboardButton("تغیر عکس پروفایل 🖼", callback_data='edit_photo')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر استان 🗺", callback_data='edit_province'),
            types.InlineKeyboardButton("تغیر سن 🎂", callback_data='edit_age')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر جنسیت ⚥", callback_data='edit_gender')
        )
        bot.edit_message_reply_markup(user_id, edit_message_id, reply_markup=edit_markup)
        return

    if message.text:
        new_username = message.text
        cursor.execute("UPDATE users SET name = ? WHERE user_id = ?", (new_username, user_id))
        conn.commit()
        bot.send_message(user_id, "نام شما تغییر کرد.", reply_markup=types.ReplyKeyboardRemove())
        cursor.execute(
            "SELECT name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online FROM users WHERE user_id=?",
            (user_id,)
        )
        user = cursor.fetchone()
        if user:
            name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online = user
            gender_display = "پسر 👨‍🦰" if gender == 'male' else "دختر 👩"
            profile_text = f"""•نام: {name} 
•جنسیت: {gender_display}
دنبال کننده ها: {followers_count}
دنبال میکند: {following_count}
•استان: {province or 'نامشخص'}
•شهر: {city or 'نامشخص'}
•سن: {age or 'نامشخص'}
🆔 : /user_{unique_id}
تعداد لایک ها : {likes_count}
سکه‌ها: {coins}
•وضعیت: {format_last_online(last_online)}"""
            markup = get_profile_inline_keyboard(user_id)
            if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
                try:
                    bot.send_photo(user_id, profile_photo, caption=profile_text, reply_markup=markup)
                except telebot.apihelper.ApiTelegramException as e:
                    print(f"Error sending profile photo for user {user_id}: {e} (file_id: {profile_photo})")
                    bot.send_message(user_id, profile_text + "\n⚠️ خطا در نمایش عکس پروفایل!", reply_markup=markup)
            else:
                bot.send_message(user_id, profile_text, reply_markup=markup)
        else:
            bot.send_message(user_id, "حساب شما پیدا نشد!", reply_markup=main_markup)
    else:
        bot.send_message(user_id, "لطفاً یک نام معتبر وارد کنید یا لغو کنید.")
        bot.register_next_step_handler(message, process_username_step, edit_message_id)


# کال‌بک برای تغییر جنسیت
@bot.callback_query_handler(func=lambda call: call.data == 'edit_gender')
def request_gender(call):
    user_id = call.from_user.id
    text = "جنسیت خود را انتخاب کنید:"
    reply_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    reply_markup.add("پسر 👨‍🦰", "دختر 👩")
    reply_markup.add("لغو ❌")
    bot.send_message(user_id, text, reply_markup=reply_markup)
    bot.register_next_step_handler(call.message, process_gender_step, call.message.message_id)


def process_gender_step(message, edit_message_id):
    user_id = message.from_user.id

    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=types.ReplyKeyboardRemove())
        edit_markup = types.InlineKeyboardMarkup(row_width=2)
        edit_markup.add(
            types.InlineKeyboardButton("تغیر نام 📝", callback_data='edit_username'),
            types.InlineKeyboardButton("تغیر عکس پروفایل 🖼", callback_data='edit_photo')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر استان 🗺", callback_data='edit_province'),
            types.InlineKeyboardButton("تغیر سن 🎂", callback_data='edit_age')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر جنسیت ⚥", callback_data='edit_gender')
        )
        bot.edit_message_reply_markup(user_id, edit_message_id, reply_markup=edit_markup)
        return

    if message.text in ["پسر 👨‍🦰", "دختر 👩"]:
        new_gender = 'male' if message.text == "پسر 👨‍🦰" else 'female'
        cursor.execute("UPDATE users SET gender = ? WHERE user_id = ?", (new_gender, user_id))
        conn.commit()
        bot.send_message(user_id, "جنسیت شما تغییر کرد.", reply_markup=types.ReplyKeyboardRemove())
        cursor.execute(
            "SELECT name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online FROM users WHERE user_id=?",
            (user_id,)
        )
        user = cursor.fetchone()
        if user:
            name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online = user
            gender_display = "پسر 👨‍🦰" if gender == 'male' else "دختر 👩"
            profile_text = f"""•نام: {name} 
•جنسیت: {gender_display}
دنبال کننده ها: {followers_count}
دنبال میکند: {following_count}
•استان: {province or 'نامشخص'}
•شهر: {city or 'نامشخص'}
•سن: {age or 'نامشخص'}
🆔 : /user_{unique_id}
تعداد لایک ها : {likes_count}
سکه‌ها: {coins}
•وضعیت: {format_last_online(last_online)}"""
            markup = get_profile_inline_keyboard(user_id)
            if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
                try:
                    bot.send_photo(user_id, profile_photo, caption=profile_text, reply_markup=markup)
                except telebot.apihelper.ApiTelegramException as e:
                    print(f"Error sending profile photo for user {user_id}: {e} (file_id: {profile_photo})")
                    bot.send_message(user_id, profile_text + "\n⚠️ خطا در نمایش عکس پروفایل!", reply_markup=markup)
            else:
                bot.send_message(user_id, profile_text, reply_markup=markup)
    else:
        bot.send_message(user_id, "لطفاً یکی از گزینه‌های جنسیت را انتخاب کنید یا لغو کنید.")
        bot.register_next_step_handler(message, process_gender_step, edit_message_id)


# کال‌بک برای تغییر عکس پروفایل
@bot.callback_query_handler(func=lambda call: call.data == 'edit_photo')
def request_profile_photo(call):
    user_id = call.from_user.id
    text = "🏞 عکس پروفایل خود را ارسال کنید."
    reply_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    reply_markup.add("لغو ❌")
    bot.send_message(user_id, text, reply_markup=reply_markup)
    bot.register_next_step_handler(call.message, process_photo_step, call.message.message_id)


def process_photo_step(message, edit_message_id):
    user_id = message.from_user.id
    update_last_online(user_id)  # آپدیت زمان آنلاین
    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=types.ReplyKeyboardRemove())
        edit_markup = types.InlineKeyboardMarkup(row_width=2)
        edit_markup.add(
            types.InlineKeyboardButton("تغیر نام 📝", callback_data='edit_username'),
            types.InlineKeyboardButton("تغیر عکس پروفایل 🖼", callback_data='edit_photo')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر استان 🗺", callback_data='edit_province'),
            types.InlineKeyboardButton("تغیر سن 🎂", callback_data='edit_age')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر جنسیت ⚥", callback_data='edit_gender')
        )
        bot.edit_message_reply_markup(user_id, edit_message_id, reply_markup=edit_markup)
        return

    if message.photo:
        photo_id = message.photo[-1].file_id
        print(f"Storing photo_id for user {user_id}: {photo_id}")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET profile_photo = ? WHERE user_id = ?", (photo_id, user_id))
        conn.commit()
        cursor.execute(
            "SELECT name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online FROM users WHERE user_id=?",
            (user_id,)
        )
        user = cursor.fetchone()
        cursor.close()

        if user:
            name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online = user
            gender_display = "پسر 👨‍🦰" if gender == 'male' else "دختر 👩"
            profile_text = f"""•نام: {name} 
•جنسیت: {gender_display}
دنبال کننده ها: {followers_count}
دنبال میکند: {following_count}
•استان: {province or 'نامشخص'}
•شهر: {city or 'نامشخص'}
•سن: {age or 'نامشخص'}
🆔 : /user_{unique_id}
تعداد لایک ها : {likes_count}
سکه‌ها: {coins}
•وضعیت: {format_last_online(last_online)}"""
            markup = get_profile_inline_keyboard(user_id)  # اصلاح فراخوانی تابع با آرگومان user_id
            bot.send_message(user_id, "تصویر شما تغییر کرد", reply_markup=types.ReplyKeyboardRemove())
            if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
                try:
                    bot.send_photo(user_id, profile_photo, caption=profile_text, reply_markup=markup)
                except telebot.apihelper.ApiTelegramException as e:
                    print(f"Error sending profile photo for user {user_id}: {e} (file_id: {profile_photo})")
                    bot.send_message(user_id, profile_text + "\n⚠️ خطا در نمایش عکس پروفایل!", reply_markup=markup)
            else:
                bot.send_message(user_id, profile_text, reply_markup=markup)
        else:
            bot.send_message(user_id, "حساب شما پیدا نشد! لطفاً دوباره با /start ثبت‌نام کنید.",
                             reply_markup=main_markup)
    else:
        bot.send_message(user_id, "لطفاً یک عکس ارسال کنید یا لغو کنید.")
        bot.register_next_step_handler(message, process_photo_step, edit_message_id)


# کال‌بک برای تغییر استان
@bot.callback_query_handler(func=lambda call: call.data == 'edit_province')
def request_province(call):
    user_id = call.from_user.id
    text = "از کدوم استان؟"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    row = []
    for i, prov in enumerate(provinces):
        row.append(prov)
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)
    markup.add("لغو ❌")
    bot.send_message(user_id, text, reply_markup=markup)
    bot.register_next_step_handler(call.message, process_province_step, call.message.message_id)


def process_province_step(message, edit_message_id):
    user_id = message.from_user.id
    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=types.ReplyKeyboardRemove())
        edit_markup = types.InlineKeyboardMarkup(row_width=2)
        edit_markup.add(
            types.InlineKeyboardButton("تغیر نام 📝", callback_data='edit_username'),
            types.InlineKeyboardButton("تغیر عکس پروفایل 🖼", callback_data='edit_photo')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر استان 🗺", callback_data='edit_province'),
            types.InlineKeyboardButton("تغیر سن 🎂", callback_data='edit_age')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر جنسیت ⚥", callback_data='edit_gender')
        )
        bot.edit_message_reply_markup(user_id, edit_message_id, reply_markup=edit_markup)
        return

    if message.text in provinces:
        province = message.text
        cursor.execute("UPDATE users SET province = ? WHERE user_id = ?", (province, user_id))
        conn.commit()
        text = "خب حالا شهر جدیدت رو انتخاب کن:"
        cities = cities_by_province.get(province, [])
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        row = []
        for city in cities:
            row.append(city)
            if len(row) == 3:
                markup.row(*row)
                row = []
        if row:
            markup.row(*row)
        markup.add("لغو ❌")
        bot.send_message(user_id, text, reply_markup=markup)
        bot.register_next_step_handler(message, process_city_step, edit_message_id)
    else:
        bot.send_message(user_id, "لطفاً یکی از استان‌ها رو انتخاب کن یا لغو کن.")
        bot.register_next_step_handler(message, process_province_step, edit_message_id)


def process_city_step(message, edit_message_id):
    user_id = message.from_user.id
    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=types.ReplyKeyboardRemove())
        edit_markup = types.InlineKeyboardMarkup(row_width=2)
        edit_markup.add(
            types.InlineKeyboardButton("تغیر نام 📝", callback_data='edit_username'),
            types.InlineKeyboardButton("تغیر عکس پروفایل 🖼", callback_data='edit_photo')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر استان 🗺", callback_data='edit_province'),
            types.InlineKeyboardButton("تغیر سن 🎂", callback_data='edit_age')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر جنسیت ⚥", callback_data='edit_gender')
        )
        bot.edit_message_reply_markup(user_id, edit_message_id, reply_markup=edit_markup)
        return

    if any(message.text in cities for cities in cities_by_province.values()):
        city = message.text
        cursor.execute("UPDATE users SET city = ? WHERE user_id = ?", (city, user_id))
        conn.commit()
        bot.send_message(user_id, "استان و شهر شما تغییر کرد.", reply_markup=types.ReplyKeyboardRemove())
        cursor.execute(
            "SELECT name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online FROM users WHERE user_id=?",
            (user_id,)
        )
        user = cursor.fetchone()
        if user:
            name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online = user
            gender_display = "پسر 👨‍🦰" if gender == 'male' else "دختر 👩"
            profile_text = f"""•نام: {name} 
•جنسیت: {gender_display}
دنبال کننده ها: {followers_count}
دنبال میکند: {following_count}
•استان: {province or 'نامشخص'}
•شهر: {city or 'نامشخص'}
•سن: {age or 'نامشخص'}
🆔 : /user_{unique_id}
تعداد لایک ها : {likes_count}
سکه‌ها: {coins}
•وضعیت: {format_last_online(last_online)}"""
            markup = get_profile_inline_keyboard(user_id)
            if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
                try:
                    bot.send_photo(user_id, profile_photo, caption=profile_text, reply_markup=markup)
                except telebot.apihelper.ApiTelegramException as e:
                    print(f"Error sending profile photo for user {user_id}: {e} (file_id: {profile_photo})")
                    bot.send_message(user_id, profile_text + "\n⚠️ خطا در نمایش عکس پروفایل!", reply_markup=markup)
            else:
                bot.send_message(user_id, profile_text, reply_markup=markup)
    else:
        bot.send_message(user_id, "لطفاً یکی از شهرها رو انتخاب کن یا لغو کن.")
        bot.register_next_step_handler(message, process_city_step, edit_message_id)


# کال‌بک برای تغییر سن
@bot.callback_query_handler(func=lambda call: call.data == 'edit_age')
def request_age(call):
    user_id = call.from_user.id
    text = "سن جدید خود را انتخاب کنید:"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    row = []
    for age in range(13, 61):
        row.append(str(age))
        if len(row) == 7:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)
    markup.add("لغو ❌")
    bot.send_message(user_id, text, reply_markup=markup)
    bot.register_next_step_handler(call.message, process_age_step, call.message.message_id)


def process_age_step(message, edit_message_id):
    user_id = message.from_user.id
    if message.text == "لغو ❌":
        bot.send_message(user_id, "عملیات لغو شد.", reply_markup=types.ReplyKeyboardRemove())
        edit_markup = types.InlineKeyboardMarkup(row_width=2)
        edit_markup.add(
            types.InlineKeyboardButton("تغیر نام 📝", callback_data='edit_username'),
            types.InlineKeyboardButton("تغیر عکس پروفایل 🖼", callback_data='edit_photo')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر استان 🗺", callback_data='edit_province'),
            types.InlineKeyboardButton("تغیر سن 🎂", callback_data='edit_age')
        )
        edit_markup.add(
            types.InlineKeyboardButton("تغیر جنسیت ⚥", callback_data='edit_gender')
        )
        bot.edit_message_reply_markup(user_id, edit_message_id, reply_markup=edit_markup)
        return

    if message.text.isdigit() and 13 <= int(message.text) <= 60:
        new_age = int(message.text)
        cursor.execute("UPDATE users SET age = ? WHERE user_id = ?", (new_age, user_id))
        conn.commit()
        bot.send_message(user_id, "سن شما تغییر کرد.", reply_markup=types.ReplyKeyboardRemove())
        cursor.execute(
            "SELECT name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online FROM users WHERE user_id=?",
            (user_id,)
        )
        user = cursor.fetchone()
        if user:
            name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo, coins, last_online = user
            gender_display = "پسر 👨‍🦰" if gender == 'male' else "دختر 👩"
            profile_text = f"""•نام: {name} 
•جنسیت: {gender_display}
دنبال کننده ها: {followers_count}
دنبال میکند: {following_count}
•استان: {province or 'نامشخص'}
•شهر: {city or 'نامشخص'}
•سن: {age or 'نامشخص'}
🆔 : /user_{unique_id}
تعداد لایک ها : {likes_count}
سکه‌ها: {coins}
•وضعیت: {format_last_online(last_online)}"""
            markup = get_profile_inline_keyboard(user_id)
            if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
                try:
                    bot.send_photo(user_id, profile_photo, caption=profile_text, reply_markup=markup)
                except telebot.apihelper.ApiTelegramException as e:
                    print(f"Error sending profile photo for user {user_id}: {e} (file_id: {profile_photo})")
                    bot.send_message(user_id, profile_text + "\n⚠️ خطا در نمایش عکس پروفایل!", reply_markup=markup)
            else:
                bot.send_message(user_id, profile_text, reply_markup=markup)
    else:
        bot.send_message(user_id, "لطفاً یک سن معتبر (بین 13 تا 60) انتخاب کنید یا لغو کنید.")
        bot.register_next_step_handler(message, process_age_step, edit_message_id)


# هندلر برای "🔗به یه ناشناس وصلم کن!"
@bot.message_handler(func=lambda message: message.text == "🔗به یه ناشناس وصلم کن!")
def connect_anonymous(message):
    user_id = message.from_user.id
    text = "کیو پیدا کنم برات؟🤨 انتخاب کن👇"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("جستجوی شانسی 🎲", callback_data='random_search'))
    markup.add(types.InlineKeyboardButton("جستجوی دختر 👩", callback_data='girl'),
               types.InlineKeyboardButton("جستجوی پسر 🧑", callback_data='boy'))
    markup.add(types.InlineKeyboardButton("جستجوی هم سن: ❌ غیر فعال ", callback_data="same_age"))
    bot.send_message(user_id, text, reply_markup=markup)


same_age_status = defaultdict(lambda: False)  # پیش‌فرض غیرفعال


# تابع برای ساخت کیبورد با دکمه‌ی جستجوی هم سن
def create_same_age_keyboard(user_id):
    status = same_age_status[user_id]
    button_text = "جستجوی هم سن: ✅ فعال" if status else "جستجوی هم سن: ❌ غیر فعال"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("جستجوی شانسی 🎲", callback_data='random_search'))
    markup.add(types.InlineKeyboardButton("جستجوی دختر 👩", callback_data='girl'),
               types.InlineKeyboardButton("جستجوی پسر 🧑", callback_data='boy'))
    markup.add(types.InlineKeyboardButton(button_text, callback_data="same_age"))

    return markup


# هندلر فرضی برای نمایش منوی تنظیمات (یا هر پیام که دکمه رو نشون می‌ده)
@bot.message_handler(func=lambda message: message.text == "تنظیمات")  # فرضاً دکمه‌ی تنظیمات
def show_settings(message):
    user_id = message.from_user.id
    update_last_online(user_id)  # فرض می‌کنیم این تابع وجود داره

    text = "⚙️ تنظیمات جستجو\nوضعیت جستجوی هم سن رو از اینجا می‌تونی تغییر بدی:"
    bot.send_message(user_id, text, reply_markup=create_same_age_keyboard(user_id))


# هندلر برای تغییر وضعیت جستجوی هم سن
@bot.callback_query_handler(func=lambda call: call.data == "same_age")
def toggle_same_age(call):
    user_id = call.from_user.id
    update_last_online(user_id)

    # تغییر وضعیت (toggle)
    same_age_status[user_id] = not same_age_status[user_id]
    status_text = "فعال" if same_age_status[user_id] else "غیر فعال"

    # ویرایش پیام با کیبورد جدید
    text = "کیو پیدا کنم برات؟🤨 انتخاب کن👇"

    try:
        bot.edit_message_text(
            text,
            chat_id=user_id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=create_same_age_keyboard(user_id)
        )
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error editing message for user {user_id}: {e}")
        bot.send_message(user_id, text, parse_mode="HTML", reply_markup=create_same_age_keyboard(user_id))

    bot.answer_callback_query(call.id, f"جستجوی هم سن {status_text} شد!")


import logging

# تنظیم لاگ‌گیری
logging.basicConfig(level=logging.DEBUG, filename='chatbot.log', format='%(asctime)s - %(levelname)s - %(message)s')

# مسیر مطلق برای فایل پایگاه داده
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'chatbot.db'))

# قفل سراسری برای جلوگیری از Race Condition
search_lock = threading.Lock()


@bot.callback_query_handler(func=lambda call: call.data == 'random_search')
def start_random_search(call):
    user_id = call.from_user.id

    # استفاده از اتصال اختصاصی برای به‌روزرسانی وضعیت
    local_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    local_conn.execute('PRAGMA journal_mode=WAL;')
    local_cursor = local_conn.cursor()

    try:
        with search_lock:
            local_cursor.execute("BEGIN IMMEDIATE")
            # بررسی وضعیت فعلی کاربر
            local_cursor.execute("SELECT status, partner_id FROM users WHERE user_id = ?", (user_id,))
            user_status = local_cursor.fetchone()
            if user_status and (user_status[0] == 'chatting' or user_status[1] is not None):
                local_conn.rollback()
                bot.send_message(user_id, "شما در حال چت هستید! لطفاً چت فعلی را پایان دهید.", reply_markup=main_markup)
                logging.debug(f"User {user_id} tried to start search while in chatting state")
                return

            # به‌روزرسانی وضعیت به searching
            local_cursor.execute("UPDATE users SET status = 'searching', partner_id = NULL WHERE user_id = ?",
                                 (user_id,))
            local_conn.commit()
    except Exception as e:
        logging.error(f"Error in start_random_search for user {user_id}: {e}")
        local_conn.rollback()
        bot.send_message(user_id, "خطایی رخ داد. لطفاً دوباره تلاش کنید.", reply_markup=main_markup)
        return
    finally:
        local_cursor.close()
        local_conn.close()

    text = "🔎 درحال جستجوی مخاطب ناشناس شما\n🎲 جستجوی شانسی\n⏳ حداکثر تا 2 دقیقه صبر کنید."
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("لغو جستجو", callback_data='cancel_search'))
    try:
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)
    except Exception as e:
        logging.error(f"Error editing message for user {user_id}: {e}")
        bot.send_message(user_id, text, reply_markup=markup)

    threading.Thread(target=search_partner_random, args=(user_id, bot)).start()


def search_partner_random(user_id, bot):
    start_time = time.time()
    max_search_time = 120  # حداکثر 2 دقیقه

    # ایجاد اتصال اختصاصی برای این نخ
    local_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    local_conn.execute('PRAGMA journal_mode=WAL;')
    local_cursor = local_conn.cursor()

    try:
        logging.debug(f"Starting random search for user {user_id}")
        while time.time() - start_time < max_search_time:
            with search_lock:
                local_cursor.execute("BEGIN IMMEDIATE")

                # بررسی وضعیت کاربر فعلی
                local_cursor.execute("SELECT status, partner_id FROM users WHERE user_id = ?", (user_id,))
                user_status = local_cursor.fetchone()
                if not user_status or user_status[0] != 'searching' or user_status[1] is not None:
                    local_conn.rollback()
                    bot.send_message(user_id, "به کاربر سلام کن", reply_markup=chat_markup)
                    logging.debug(
                        f"Search cancelled for user {user_id}: status={user_status[0] if user_status else None}, partner_id={user_status[1] if user_status else None}")
                    return

                # انتخاب کاربر مناسب
                local_cursor.execute("""
                    SELECT user_id 
                    FROM users 
                    WHERE status = 'searching' 
                    AND user_id != ? 
                    AND partner_id IS NULL 
                    AND user_id NOT IN (SELECT blocked_id FROM block WHERE blocker_id = ?)
                    LIMIT 1
                """, (user_id, user_id))
                partner = local_cursor.fetchone()

                if partner:
                    partner_id = partner[0]
                    logging.debug(f"Found potential partner {partner_id} for user {user_id}")

                    # بررسی دوباره وضعیت پارتنر با قفل
                    local_cursor.execute("SELECT status, partner_id FROM users WHERE user_id = ?", (partner_id,))
                    partner_status = local_cursor.fetchone()
                    if not partner_status or partner_status[0] != 'searching' or partner_status[1] is not None:
                        local_conn.rollback()
                        logging.debug(
                            f"Partner {partner_id} invalid: status={partner_status[0] if partner_status else None}, partner_id={partner_status[1] if partner_status else None}")
                        time.sleep(0.1)
                        continue

                    # به‌روزرسانی اتمیک برای هر دو کاربر
                    local_cursor.execute("UPDATE users SET status = 'chatting', partner_id = ? WHERE user_id = ?",
                                         (partner_id, user_id))
                    local_cursor.execute("UPDATE users SET status = 'chatting', partner_id = ? WHERE user_id = ?",
                                         (user_id, partner_id))
                    local_cursor.execute("INSERT INTO chat_history (user_id, partner_id) VALUES (?, ?)",
                                         (user_id, partner_id))
                    local_cursor.execute("INSERT INTO chat_history (user_id, partner_id) VALUES (?, ?)",
                                         (partner_id, user_id))
                    local_cursor.execute("UPDATE users SET last_online = ? WHERE user_id = ?",
                                         (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
                    local_cursor.execute("UPDATE users SET last_online = ? WHERE user_id = ?",
                                         (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), partner_id))
                    local_conn.commit()
                    logging.info(f"Chat started between {user_id} and {partner_id}")

                    # ارسال پیام به هر دو کاربر
                    local_cursor.execute("SELECT name, unique_id FROM users WHERE user_id = ?", (partner_id,))
                    partner_name, partner_unique = local_cursor.fetchone()
                    start_text_user = (f"چت با ({partner_name}) /user_{partner_unique} شروع شد! "
                                       "بهش سلام کن :)\n🤖 پیام سیستم 👇🏻\n"
                                       "⚠️ اخطار: به هیچ کاربری در ربات اعتماد نکنید و اطلاعات شخصیتان را در اختیار کسی قرار ندهید!")
                    bot.send_message(user_id, start_text_user, reply_markup=chat_markup)

                    local_cursor.execute("SELECT name, unique_id FROM users WHERE user_id = ?", (user_id,))
                    user_name, user_unique = local_cursor.fetchone()
                    start_text_partner = (f"چت با ({user_name}) /user_{user_unique} شروع شد! "
                                          "بهش سلام کن :)\n🤖 پیام سیستم 👇🏻\n"
                                          "⚠️ اخطار: به هیچ کاربری در ربات اعتماد نکنید و اطلاعات شخصیتان را در اختیار کسی قرار ندهید!")
                    bot.send_message(partner_id, start_text_partner, reply_markup=chat_markup)

                    return

                local_conn.rollback()
            time.sleep(0.1)  # کاهش فاصله برای واکنش سریع‌تر

        # اگر هیچ کاربری پیدا نشد
        with search_lock:
            local_cursor.execute("UPDATE users SET status = 'idle', partner_id = NULL WHERE user_id = ?", (user_id,))
            local_conn.commit()
        bot.send_message(user_id, "متاسفانه کسی پیدا نشد 😔 دوباره تلاش کن!", reply_markup=main_markup)
        logging.debug(f"No partner found for user {user_id}")

    except Exception as e:
        logging.error(f"Error in search_partner_random for user {user_id}: {e}")
        local_conn.rollback()
        bot.send_message(user_id, "خطایی رخ داد. لطفاً دوباره تلاش کنید.", reply_markup=main_markup)

    finally:
        local_cursor.close()
        local_conn.close()
        logging.debug(f"Connection closed for user {user_id}")
# تابع برای گرفتن تعداد سکه‌های کاربر
def get_user_coins(user_id):
    cursor.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 10  # 10 سکه پیش‌فرض


# تابع برای کسر سکه
def deduct_coins(user_id, amount=1):
    cursor.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()


# تابع برای جستجوی پارتنر با جنسیت خاص
def search_partner(user_id, gender):
    start_time = time.time()
    local_cursor = conn.cursor()
    while time.time() - start_time < 120:  # حداکثر 2 دقیقه صبر
        local_cursor.execute(
            """
            SELECT user_id FROM users 
            WHERE status = 'searching' AND user_id != ? AND gender = ?
            LIMIT 1
            """,
            (user_id, gender)
        )
        partner = local_cursor.fetchone()
        if partner:
            partner_id = partner[0]
            # آپدیت وضعیت و پارتنر برای هر دو کاربر
            local_cursor.execute("UPDATE users SET status = 'chatting', partner_id = ? WHERE user_id = ?",
                                 (partner_id, user_id))
            local_cursor.execute("UPDATE users SET status = 'chatting', partner_id = ? WHERE user_id = ?",
                                 (user_id, partner_id))
            # ثبت چت در تاریخچه
            local_cursor.execute("INSERT INTO chat_history (user_id, partner_id) VALUES (?, ?)", (user_id, partner_id))
            local_cursor.execute("INSERT INTO chat_history (user_id, partner_id) VALUES (?, ?)", (partner_id, user_id))
            # آپدیت last_online
            local_cursor.execute("UPDATE users SET last_online = ? WHERE user_id = ?",
                                 (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
            local_cursor.execute("UPDATE users SET last_online = ? WHERE user_id = ?",
                                 (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), partner_id))
            conn.commit()
            # ارسال پیام به کاربر
            local_cursor.execute("SELECT name, unique_id FROM users WHERE user_id = ?", (partner_id,))
            partner_name, partner_unique = local_cursor.fetchone()
            start_text_user = (
                f"چت با <b>{partner_name}</b> (/user_{partner_unique}) شروع شد! بهش سلام کن :)\n"
                "🤖 پیام سیستم 👇🏻\n"
                "⚠️ اخطار: به هیچ کاربری در ربات اعتماد نکنید و اطلاعات شخصیتان را در اختیار کسی قرار ندهید!"
            )
            bot.send_message(user_id, start_text_user, parse_mode="HTML", reply_markup=chat_markup)
            # ارسال پیام به پارتنر
            local_cursor.execute("SELECT name, unique_id FROM users WHERE user_id = ?", (user_id,))
            user_name, user_unique = local_cursor.fetchone()
            start_text_partner = (
                f"چت با <b>{user_name}</b> (/user_{user_unique}) شروع شد! بهش سلام کن :)\n"
                "🤖 پیام سیستم 👇🏻\n"
                "⚠️ اخطار: به هیچ کاربری در ربات اعتماد نکنید و اطلاعات شخصیتان را در اختیار کسی قرار ندهید!"
            )
            bot.send_message(partner_id, start_text_partner, parse_mode="HTML", reply_markup=chat_markup)
            return
        time.sleep(5)


# کال‌بک برای جستجوی دختر
@bot.callback_query_handler(func=lambda call: call.data == 'girl')
def start_girl_search(call):
    user_id = call.from_user.id
    update_last_online(user_id)

    # چک کردن تعداد سکه‌ها
    coins = get_user_coins(user_id)
    if coins < 1:
        text = (
            "⚠️ <b>توجه: شما سکه کافی ندارید!</b> (1 سکه مورد نیاز)\n"
            "💡 برای بدست آوردن سکه می‌تونی رباتو به دوستات معرفی کنی و به ازای معرفی هر نفر <b>20 سکه</b> هدیه بگیری.\n"
            "❗️ اگه دوستی نداری که دعوت کنی می‌تونی از پنل خرید سکه 💰 استفاده کنی و سکه‌هاتو افزایش بدی."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💰 افزایش سکه", callback_data="show_payment_options"))
        try:
            bot.edit_message_text(
                text,
                chat_id=user_id,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=markup
            )
        except telebot.apihelper.ApiTelegramException as e:
            print(f"Error editing message for user {user_id}: {e}")
            bot.send_message(user_id, text, parse_mode="HTML", reply_markup=markup)
        bot.answer_callback_query(call.id, "سکه کافی نداری!")
        return

    # کسر یک سکه
    deduct_coins(user_id)

    # شروع جستجو
    cursor.execute("UPDATE users SET status = 'searching', partner_id = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    text = "🔎 درحال جستجوی یه دختر ناشناس\n🎲 جستجوی شانسی\n⏳ حداکثر تا 2 دقیقه صبر کنید."
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("لغو جستجو", callback_data="cancel_search"))
    try:
        bot.edit_message_text(
            text,
            chat_id=user_id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error editing message for user {user_id}: {e}")
        bot.send_message(user_id, text, reply_markup=markup)
    bot.answer_callback_query(call.id, "جستجوی دختر شروع شد!")
    threading.Thread(target=search_partner, args=(user_id, 'female')).start()


# کال‌بک برای جستجوی پسر
@bot.callback_query_handler(func=lambda call: call.data == 'boy')
def start_boy_search(call):
    user_id = call.from_user.id
    update_last_online(user_id)

    # چک کردن تعداد سکه‌ها
    coins = get_user_coins(user_id)
    if coins < 1:
        text = (
            "⚠️ <b>توجه: شما سکه کافی ندارید!</b> (1 سکه مورد نیاز)\n"
            "💡 برای بدست آوردن سکه می‌تونی رباتو به دوستات معرفی کنی و به ازای معرفی هر نفر <b>20 سکه</b> هدیه بگیری.\n"
            "❗️ اگه دوستی نداری که دعوت کنی می‌تونی از پنل خرید سکه 💰 استفاده کنی و سکه‌هاتو افزایش بدی."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💰 افزایش سکه", callback_data="show_payment_options"))
        try:
            bot.edit_message_text(
                text,
                chat_id=user_id,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=markup
            )
        except telebot.apihelper.ApiTelegramException as e:
            print(f"Error editing message for user {user_id}: {e}")
            bot.send_message(user_id, text, parse_mode="HTML", reply_markup=markup)
        bot.answer_callback_query(call.id, "سکه کافی نداری!")
        return

    # کسر یک سکه
    deduct_coins(user_id)

    # شروع جستجو
    cursor.execute("UPDATE users SET status = 'searching', partner_id = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    text = "🔎 درحال جستجوی یه پسر ناشناس\n🎲 جستجوی شانسی\n⏳ حداکثر تا 2 دقیقه صبر کنید."
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("لغو جستجو", callback_data="cancel_search"))
    try:
        bot.edit_message_text(
            text,
            chat_id=user_id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error editing message for user {user_id}: {e}")
        bot.send_message(user_id, text, reply_markup=markup)
    bot.answer_callback_query(call.id, "جستجوی پسر شروع شد!")
    threading.Thread(target=search_partner, args=(user_id, 'male')).start()


# هندلر برای لغو جستجو
@bot.callback_query_handler(func=lambda call: call.data == 'cancel_search')
def cancel_search(call):
    user_id = call.from_user.id
    update_last_online(user_id)
    cursor.execute("UPDATE users SET status = 'idle', partner_id = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    text = "جستجو لغو شد! 😊 چی کار دیگه‌ای می‌تونی بکنم؟"
    try:
        bot.edit_message_text(
            text,
            chat_id=user_id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=main_markup
        )
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error editing message for user {user_id}: {e}")
        bot.send_message(user_id, text, parse_mode="HTML", reply_markup=main_markup)
    bot.answer_callback_query(call.id, "جستجو لغو شد!")


# کال‌بک برای لغو جستجو
@bot.callback_query_handler(func=lambda call: call.data == 'cancel_search')
def cancel_search(call):
    user_id = call.from_user.id
    cursor.execute("UPDATE users SET status = 'idle' WHERE user_id = ?", (user_id,))
    conn.commit()
    bot.edit_message_text("جستجو لغو شد.", user_id, call.message.message_id)
    bot.send_message(user_id, "خوش برگشتی!", reply_markup=main_markup)


# لیست دکمه‌های چت
chat_commands = ["مشاهده پروفایل مخاطب 👀", "فعال سازی چت خصوصی 🔐‌", "پایان چت ❌"]


# هندلر برای مشاهده پروفایل مخاطب
@bot.message_handler(func=lambda message: message.text == "مشاهده پروفایل مخاطب 👀")
def view_partner_profile(message):
    user_id = message.from_user.id
    cursor.execute("SELECT status, partner_id FROM users WHERE user_id = ?", (user_id,))
    status, partner_id = cursor.fetchone()
    if status == 'chatting' and partner_id:
        cursor.execute(
            "SELECT name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo FROM users WHERE user_id = ?",
            (partner_id,))
        p_name, p_gender, p_followers, p_following, p_province, p_city, p_age, p_likes, p_unique, profile_photo = cursor.fetchone()
        p_gender_display = "پسر 👨‍🦰" if p_gender == 'male' else "دختر 👩"
        profile_text = f"""•نام: {p_name} 
•جنسیت: {p_gender_display}
دنبال کننده ها: {p_followers}
دنبال میکند: {p_following}
•استان: {p_province or 'نامشخص'}
•شهر: {p_city or 'نامشخص'}
•سن: {p_age or 'نامشخص'}
🆔 : /user_{p_unique}
تعداد لایک ها : {p_likes}"""
        markup = get_partner_profile_inline_keyboard(user_id, partner_id)
        if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
            try:
                bot.send_photo(user_id, profile_photo, caption=profile_text, reply_markup=markup)
            except telebot.apihelper.ApiTelegramException as e:
                print(f"Error sending partner profile photo for user {user_id}: {e} (file_id: {profile_photo})")
                bot.send_message(user_id, profile_text + "\n⚠️ خطا در نمایش عکس پروفایل!", reply_markup=markup)
        else:
            bot.send_message(user_id, profile_text, reply_markup=markup)
        bot.send_message(partner_id,
                         "🤖 پیام سیستم 👇\n🗣 مخاطبت «پروفایل ِ چتوگرامِ » تو رو نگاه کرد.\n⚠️ توجه: پروفایل چتوگرام اطلاعاتی است که در بخش پروفایل ربات ثبت کرده اید!")
    else:
        bot.send_message(user_id, "شما در چت نیستید.")


# هندلر برای پایان چت
@bot.message_handler(func=lambda message: message.text == "پایان چت ❌")
def confirm_end_chat(message):
    user_id = message.from_user.id
    cursor.execute("SELECT status, partner_id FROM users WHERE user_id = ?", (user_id,))
    status, partner_id = cursor.fetchone()
    if status == 'chatting' and partner_id:
        cursor.execute("SELECT name, unique_id FROM users WHERE user_id = ?", (partner_id,))
        p_name, p_unique = cursor.fetchone()
        text = f"مطمئنی که میخوای گفتگو رو با ({p_name}) /user_{p_unique} تموم کنی ⁉️"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("دستم خورد🤦‍♂️", callback_data='cancel_end'),
            types.InlineKeyboardButton("اره تمومش کن❌", callback_data='confirm_end')
        )
        bot.send_message(user_id, text, reply_markup=markup)
    else:
        bot.send_message(user_id, "شما در چت نیستید.")


# کال‌بک برای لایک کردن پروفایل مخاطب
@bot.callback_query_handler(func=lambda call: call.data == 'like_partner')
def like_partner(call):
    user_id = call.from_user.id
    cursor.execute("SELECT partner_id FROM users WHERE user_id = ?", (user_id,))
    partner_id = cursor.fetchone()[0]
    if not partner_id:
        bot.answer_callback_query(call.id, "شما در چت نیستید!")
        return

    cursor.execute("SELECT COUNT(*) FROM likes WHERE user_id = ? AND target_id = ?", (user_id, partner_id))
    has_liked = cursor.fetchone()[0] > 0

    if has_liked:
        # Unlike
        cursor.execute("DELETE FROM likes WHERE user_id = ? AND target_id = ?", (user_id, partner_id))
        cursor.execute("UPDATE users SET likes_count = likes_count - 1 WHERE user_id = ?", (partner_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "لایک شما برداشته شد!")
    else:
        # Like
        try:
            cursor.execute("INSERT INTO likes (user_id, target_id) VALUES (?, ?)", (user_id, partner_id))
            cursor.execute("UPDATE users SET likes_count = likes_count + 1 WHERE user_id = ?", (partner_id,))
            conn.commit()
            bot.answer_callback_query(call.id, "پروفایل لایک شد!")
        except sqlite3.IntegrityError:
            bot.answer_callback_query(call.id, "شما قبلاً این پروفایل را لایک کرده‌اید!")

    # به‌روزرسانی پروفایل مخاطب
    cursor.execute(
        "SELECT name, gender, followers_count, following_count, province, city, age, likes_count, unique_id, profile_photo FROM users WHERE user_id = ?",
        (partner_id,))
    p_name, p_gender, p_followers, p_following, p_province, p_city, p_age, p_likes, p_unique, profile_photo = cursor.fetchone()
    p_gender_display = "پسر 👨‍🦰" if p_gender == 'male' else "دختر 👩"
    profile_text = f"""•نام: {p_name} 
•جنسیت: {p_gender_display}
دنبال کننده ها: {p_followers}
دنبال میکند: {p_following}
•استان: {p_province or 'نامشخص'}
•شهر: {p_city or 'نامشخص'}
•سن: {p_age or 'نامشخص'}
🆔 : /user_{p_unique}
تعداد لایک ها : {p_likes}"""
    markup = get_partner_profile_inline_keyboard(user_id, partner_id)
    try:
        if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 0:
            bot.edit_message_media(
                media=types.InputMediaPhoto(profile_photo, caption=profile_text),
                chat_id=user_id,
                message_id=call.message.message_id,
                reply_markup=markup
            )
        else:
            bot.edit_message_text(
                text=profile_text,
                chat_id=user_id,
                message_id=call.message.message_id,
                reply_markup=markup
            )
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error updating partner profile for user {user_id}: {e}")
        bot.answer_callback_query(call.id, "خطا در به‌روزرسانی پروفایل!")


# کال‌بک برای مشاهده لایک‌کنندگان
@bot.callback_query_handler(func=lambda call: call.data == 'view_likers')
def view_likers(call):
    user_id = call.from_user.id
    cursor.execute(
        "SELECT u.name, u.unique_id FROM likes l JOIN users u ON l.user_id = u.user_id WHERE l.target_id = ?",
        (user_id,))
    likers = cursor.fetchall()

    if likers:
        likers_text = "👥 کسانی که پروفایل شما را لایک کرده‌اند:\n"
        for name, unique_id in likers:
            likers_text += f"• {name} (/user_{unique_id})\n"
    else:
        likers_text = "😕 هنوز کسی پروفایل شما را لایک نکرده است!"

    bot.send_message(user_id, likers_text)


# کال‌بک برای تایید پایان
@bot.callback_query_handler(func=lambda call: call.data in ['cancel_end', 'confirm_end'])
def handle_end_confirmation(call):
    user_id = call.from_user.id
    if call.data == 'cancel_end':
        bot.edit_message_text("چت ادامه داره!", user_id, call.message.message_id)
        bot.send_message(user_id, "برگشت به چت.", reply_markup=chat_markup)
    elif call.data == 'confirm_end':
        cursor.execute("SELECT partner_id FROM users WHERE user_id = ?", (user_id,))
        partner_id = cursor.fetchone()[0]
        if partner_id:
            cursor.execute("SELECT name, unique_id FROM users WHERE user_id = ?", (partner_id,))
            p_name, p_unique = cursor.fetchone()
            cursor.execute("UPDATE users SET status = 'idle', partner_id = NULL WHERE user_id IN (?, ?)",
                           (user_id, partner_id))
            conn.commit()
            end_text_user = f"چت با ({p_name}) /user_{p_unique} از طرف خودت بسته شد.\nبرای گزارش عدم رعایت قوانین (/rules) می‌توانید با لمس 《 🚫 گزارش کاربر 》 در پروفایل، کاربر را گزارش کنید."
            bot.send_message(user_id, end_text_user, reply_markup=main_markup)
            end_text_partner = f"چت با طرف مقابل از طرف کاربر بسته شد.\nبرای گزارش عدم رعایت قوانین (/rules) می‌توانید با لمس 《 🚫 گزارش کاربر 》 در پروفایل، کاربر را گزارش کنید."
            bot.send_message(partner_id, end_text_partner, reply_markup=main_markup)


# هندلر برای "فعال سازی چت خصوصی 🔐‌"
@bot.message_handler(func=lambda message: message.text == "فعال سازی چت خصوصی 🔐‌")
def activate_private_chat(message):
    user_id = message.from_user.id
    bot.send_message(user_id, "چت خصوصی فعال شد! (این فقط برای شما نمایش داده می‌شه)")


# هندلر پیام‌ها در چت
@bot.message_handler(content_types=['text', 'photo', 'voice', 'video', 'document'])
def handle_chat_message(message):
    user_id = message.from_user.id
    update_last_online(user_id)  # اضافه کردن آپدیت زمان آنلاین
    cursor.execute("SELECT status, partner_id FROM users WHERE user_id = ?", (user_id,))
    status, partner_id = cursor.fetchone()
    if status == 'chatting' and partner_id:
        if message.text and message.text in chat_commands:
            return
        if message.text:
            bot.send_message(partner_id, message.text)
        elif message.photo:
            bot.send_photo(partner_id, message.photo[-1].file_id, caption=message.caption)
        elif message.voice:
            bot.send_voice(partner_id, message.voice.file_id)
        elif message.video:
            bot.send_video(partner_id, message.video.file_id, caption=message.caption)
        elif message.document:
            bot.send_document(partner_id, message.document.file_id, caption=message.caption)
    else:
        pass


# اجرای ربات
if __name__ == '__main__':
    bot.polling()