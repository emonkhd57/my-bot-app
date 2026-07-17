import logging
import os
import json
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import firebase_admin
from firebase_admin import credentials, firestore
import requests

# --- কনফিগারেশন ---
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
API_KEY = os.getenv('API_KEY')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
OTP_GROUP_ID = os.getenv('OTP_GROUP_ID') # ওটিপি ফরওয়ার্ড করার গ্রুপ আইডি
BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnemn/@public/api"

firebase_json = json.loads(os.getenv('FIREBASE_JSON'))
cred = credentials.Certificate(firebase_json)
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- মেইন মেনু কিবোর্ড ---
def get_main_menu(user_id):
    keyboard = [
        ["🎭 নাম্বার নিন", "💸 ব্যালেন্স"],
        ["💰 টাকা উত্তোলন", "🎁 My Referrals"],
        ["🧐 সাপোর্ট", "🆕 আমি নতুন"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 অ্যাডমিন প্যানেল"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.collection('users').document(str(user_id)).set({'id': user_id, 'balance': 0.0}, merge=True)
    text = ("👋 হ্যালো! নাম্বার ওটিপি বোটে আপনাকে স্বাগতম।\n\n"
            "সরাসরি ইনস্টাগ্রাম নাম্বার পেতে নিচের 🎭 Number বাটনে প্রেস করুন।")
    await update.message.reply_text(text, reply_markup=get_main_menu(user_id))

# --- অ্যাডমিন প্যানেল ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    keyboard = [
        [InlineKeyboardButton("👥 USER MANAGEMENT", callback_data="adm_user_mgmt")],
        [InlineKeyboardButton("⚙️ SYSTEM CONFIGURATION", callback_data="adm_sys_conf")],
        [InlineKeyboardButton("💲 ওটিপি রেট পরিবর্তন", callback_data="change_otp_rate")],
        [InlineKeyboardButton("🔙 BACK TO MAIN", callback_data="back_main")]
    ]
    await update.message.reply_text("👑 প্রধান অ্যাডমিন মেনু:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_main":
        await query.edit_message_text("🔙 প্রধান মেনুতে ফিরে এসেছেন।")
    elif data == "adm_user_mgmt":
        keyboard = [
            [InlineKeyboardButton("📢 SEND MSG TO ALL", callback_data="bc_all")],
            [InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_main")]
        ]
        await query.edit_message_text("👥 ইউজার ম্যানেজমেন্ট:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "change_otp_rate":
        await query.edit_message_text("💰 নতুন ওটিপি রেট লিখুন (যেমন: ২০):")
        context.user_data['waiting_for_rate'] = True
    elif data == "admin_main":
        keyboard = [
            [InlineKeyboardButton("👥 USER MANAGEMENT", callback_data="adm_user_mgmt")],
            [InlineKeyboardButton("⚙️ SYSTEM CONFIGURATION", callback_data="adm_sys_conf")],
            [InlineKeyboardButton("💲 ওটিপি রেট পরিবর্তন", callback_data="change_otp_rate")]
        ]
        await query.edit_message_text("👑 প্রধান অ্যাডমিন মেনু:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- ইউজার ফাংশন ---
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ref = db.collection('users').document(str(user_id)).get()
    balance = user_ref.to_dict().get('balance', 0.0) if user_ref.exists else 0.0
    text = (f"💲 আপনার ব্যালেন্স\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 ব্যালেন্স: {balance:.2f} BDT\n"
            f"💰 পেন্ডিং (উইথড্র): 0.00 BDT\n"
            f"💵 Total Income: 0.00 BDT\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ মোট ওটিপি রিসিভ: 0 টি")
    await update.message.reply_text(text)

async def withdraw_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💳 USDT (BEP-20) -> সর্বনিম্ন: 0.20(-0.05)", callback_data="wd_usdt")],
        [InlineKeyboardButton(" বিকাশ -> সর্বনিম্ন: ১১০ট(-৫)", callback_data="wd_bkash")],
        [InlineKeyboardButton(" নগদ -> সর্বনিম্ন: ১১০ট(-৫)", callback_data="wd_nagad")],
        [InlineKeyboardButton("🔙 ফিরে যান", callback_data="back_main")]
    ]
    await update.message.reply_text("📥 টাকা তোলার মাধ্যম সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- ওটিপি ফাংশন ও ফরওয়ার্ডিং ---
async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # API কল
    response = requests.post(f"{BASE_URL}/getnum", headers={"mauthapi": API_KEY}, json={"rid": "26134"}).json()
    if response.get('meta', {}).get('code') == 200:
        number = response['data']['full_number']
        db.collection('orders').document(str(number)).set({'user_id': user_id, 'status': 'active'})
        await update.message.reply_text(f"✅ নাম্বার পাওয়া গেছে: {number}\nওটিপির জন্য অপেক্ষা করুন...")
    else:
        await update.message.reply_text("❌ দুঃখিত, বর্তমানে কোনো নাম্বার নেই।")

async def check_otp_and_forward(context: ContextTypes.DEFAULT_TYPE):
    url = f"{BASE_URL}/success-otp"
    try:
        data = requests.get(url, headers={"mauthapi": API_KEY}).json()
        if data.get('meta', {}).get('code') == 200 and data['data']['otps']:
            latest_otp = data['data']['otps'][0]
            number = latest_otp['number']
            order_ref = db.collection('orders').document(str(number))
            order = order_ref.get()
            if order.exists:
                user_id = order.to_dict()['user_id']
                # ইউজারকে পাঠানো
                await context.bot.send_message(chat_id=user_id, text=f"🔔 নতুন ওটিপি এসেছে!\n📱 নাম্বার: {number}\n✉️ কোড: {latest_otp['message']}")
                # ওটিপি গ্রুপে ফরওয়ার্ডিং
                await context.bot.send_message(chat_id=OTP_GROUP_ID, text=f"🔔 নতুন ওটিপি!\n📱 নাম্বার: {number}\n✉️ কোড: {latest_otp['message']}")
                order_ref.update({'status': 'completed'})
    except Exception as e:
        print(f"Error: {e}")
        
# --- রানার ---
def run_dummy_server():
    try:
        server_address = ('', 8080)
        httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
        httpd.serve_forever()
    except: pass

if __name__ == '__main__':
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Text(["🎭 নাম্বার নিন"]), lambda u, c: u.message.reply_text("নাম্বার রিকোয়েস্ট প্রসেস হচ্ছে...")))
    app.add_handler(MessageHandler(filters.Text(["💸 ব্যালেন্স"]), show_balance))
    app.add_handler(MessageHandler(filters.Text(["💰 টাকা উত্তোলন"]), withdraw_money))
    app.add_handler(MessageHandler(filters.Text(["👑 অ্যাডমিন প্যানেল"]), admin_panel))
    
    app.add_handler(CallbackQueryHandler(admin_callback))
    
    print("Bot is running...")
    app.run_polling()
