# -*- coding: utf-8 -*-
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
BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnemn/@public/api"

firebase_json = json.loads(os.getenv('FIREBASE_JSON'))
cred = credentials.Certificate(firebase_json)
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- মেইন মেনু হ্যান্ডলার ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.collection('users').document(str(user_id)).set({'id': user_id}, merge=True)
    
    keyboard = [
        ["🎭 নাম্বার নিন", "💸 ব্যালেন্স"],
        ["💰 টাকা উত্তোলন", "🎁 My Referrals"],
        ["🧐 সাপোর্ট"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 অ্যাডমিন প্যানেল"])
        
    await update.message.reply_text("👋 স্বাগতম! নিচে ক্লিক করুন:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# --- অ্যাডমিন প্যানেল (মেইন) ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    keyboard = [
        [InlineKeyboardButton("👥 USER MANAGEMENT", callback_data="admin_user_mgmt")],
        [InlineKeyboardButton("⚙️ SYSTEM CONFIGURATION", callback_data="admin_sys_conf")],
        [InlineKeyboardButton("🔗 REQUIRED CHANNELS", callback_data="admin_req_chan")],
        [InlineKeyboardButton("⚡ FAKE OTP", callback_data="admin_fake_otp")],
        [InlineKeyboardButton("🔙 BACK TO MAIN", callback_data="back_main")]
    ]
    await update.message.reply_text("👑 প্রধান অ্যাডমিন মেনু:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- অ্যাডমিন বাটন হ্যান্ডলার ---
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "back_main":
        await query.edit_message_text("🔙 আপনি মেইন মেনুতে ফিরে গেছেন।")
    
    elif data == "admin_user_mgmt":
        keyboard = [
            [InlineKeyboardButton("📢 SEND MESSAGE TO ALL USERS", callback_data="bc_all")],
            [InlineKeyboardButton("🆔 ALL USER ID", callback_data="all_ids"), InlineKeyboardButton("📜 BAN USER LIST", callback_data="ban_list")],
            [InlineKeyboardButton("💰 ALL USER BALANCE", callback_data="all_bal"), InlineKeyboardButton("👥 USER LIST (ALL)", callback_data="all_users")],
            [InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_home")]
        ]
        await query.edit_message_text("👥 ইউজার ম্যানেজমেন্ট:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_sys_conf":
        keyboard = [
            [InlineKeyboardButton("📈 TODAY ALL STATUS", callback_data="t_stat"), InlineKeyboardButton("👤 USER STATUS CHECK", callback_data="u_stat")],
            [InlineKeyboardButton("⛔ BAN USER", callback_data="ban_u"), InlineKeyboardButton("🔓 UNBAN USER", callback_data="unban_u")],
            [InlineKeyboardButton("📜 BAN USER LIST", callback_data="ban_list")],
            [InlineKeyboardButton("➖ REMOVE BALANCE", callback_data="rem_bal"), InlineKeyboardButton("➕ ADD BALANCE", callback_data="add_bal")],
            [InlineKeyboardButton("⚙️ CHANGE MIN WITHDRAW", callback_data="c_min_wit"), InlineKeyboardButton("💳 TOGGLE PAYMENT METHODS", callback_data="pay_m")],
            [InlineKeyboardButton("💲 CHANGE OTP PRICE", callback_data="otp_p"), InlineKeyboardButton("🔧 SET USER OTP RATE", callback_data="s_otp_r")],
            [InlineKeyboardButton("📋 VIEW USER OTP RATE", callback_data="v_otp_r")],
            [InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_home")]
        ]
        await query.edit_message_text("⚙️ সিস্টেম কনফিগারেশন:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_req_chan":
        keyboard = [
            [InlineKeyboardButton("➕ ADD CHANNEL", callback_data="add_ch"), InlineKeyboardButton("❌ REMOVE CHANNEL", callback_data="rem_ch")],
            [InlineKeyboardButton("📋 LIST CHANNELS", callback_data="list_ch")],
            [InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_home")]
        ]
        await query.edit_message_text("🔗 রিকোয়ার্ড চ্যানেল:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_fake_otp":
        keyboard = [
            [InlineKeyboardButton("📊 STATUS (চালু/বন্ধ)", callback_data="f_stat"), InlineKeyboardButton("▶️ START", callback_data="f_start"), InlineKeyboardButton("⏹ STOP", callback_data="f_stop")],
            [InlineKeyboardButton("⚙️ SETTINGS", callback_data="f_set")],
            [InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_home")]
        ]
        await query.edit_message_text("⚡ ফেক ওটিপি:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_home":
        await admin_panel(update, context)
# --- বাটন ফাংশনাল হ্যান্ডলার ---
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("💵 আপনার ব্যালেন্স\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💵 ব্যালেন্স: 0.00 BDT\n"
            "💸 পেন্ডিং (উইথড্র): 0.00 BDT\n"
            "💰 Total Income: 0.00 BDT\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📞 মোট ওটিপি রিসিভ: 0 টি")
    await update.message.reply_text(text)

async def show_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = (await context.bot.get_me()).username
    refer_link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
    text = (f"🎁 My Referrals\n\n"
            f"👤 Total Refer: 1\n"
            f"😃 Total Refer Income: 0.00 BDT\n"
            f"🔗 আপনার রেফার লিংক:\n{refer_link}\n\n"
            f"ℹ️ প্রতি রেফারে পাবেন ০.১০ পয়সা বোনাস। আপনার রেফার করা ইউজার যদি দিনে ১০০ otp নেয় তাহলে ১০ টাকা।")
    await update.message.reply_text(text)

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👤 অ্যাডমিন সাপোর্ট", url="https://t.me/helptg10")],
        [InlineKeyboardButton("📢 অফিসিয়াল চ্যানেল", url="https://t.me/helptg100")]
    ]
    await update.message.reply_text("📞 গ্রাহক সেবা কেন্দ্র:\nসম্মানিত মেম্বার, আপনার যেকোনো সমস্যার জন্য সাপোর্ট টিমের সাথে যোগাযোগ করুন।", reply_markup=InlineKeyboardMarkup(keyboard))

# --- এডমিন প্যানেল সিস্টেম ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("💰 বোনাস আপডেট", callback_data="set_bonus"),
             InlineKeyboardButton("📢 ব্রডকাস্ট", callback_data="broadcast")],
            [InlineKeyboardButton("👥 ইউজার লিস্ট", callback_data="user_list")]
        ]
        await update.message.reply_text("👑 অ্যাডমিন প্যানেল টুলস:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "set_bonus":
        await query.edit_message_text("✅ বোনাস সেট করতে লিখুন: /setbonus <amount>")
    elif query.data == "broadcast":
        await query.edit_message_text("✅ ব্রডকাস্ট করতে লিখুন: /broadcast <message>")
    elif query.data == "user_list":
        users = db.collection('users').stream()
        count = sum(1 for _ in users)
        await query.edit_message_text(f"📊 মোট ব্যবহারকারী: {count}")

# --- ওটিপি ফাংশন ---
async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = f"{BASE_URL}/getnum"
    payload = {"rid": "26134"}
    headers = {"mauthapi": API_KEY}
    response = requests.post(url, headers=headers, json=payload).json()
    
    if response.get('meta', {}).get('code') == 200:
        number = response['data']['full_number']
        db.collection('orders').document(str(number)).set({'user_id': user_id, 'status': 'active'})
        await update.message.reply_text(f"✅ নাম্বার পাওয়া গেছে: {number}\nওটিপির জন্য অপেক্ষা করুন...")
    else:
        await update.message.reply_text("❌ দুঃখিত, বর্তমানে কোনো নাম্বার নেই।")

async def check_otp_and_forward(context: ContextTypes.DEFAULT_TYPE):
    url = f"{BASE_URL}/success-otp"
    headers = {"mauthapi": API_KEY}
    try:
        data = requests.get(url, headers=headers).json()
        if data.get('meta', {}).get('code') == 200 and data['data']['otps']:
            latest_otp = data['data']['otps'][0]
            number = latest_otp['number']
            order_ref = db.collection('orders').document(str(number))
            order = order_ref.get()
            if order.exists:
                user_id = order.to_dict()['user_id']
                bonus = db.collection('bot_state').document('1').get().to_dict().get('bonus_per_otp', 0.50)
                await context.bot.send_message(chat_id=user_id, text=f"🔔 নতুন ওটিপি এসেছে!\n📱 নাম্বার: {number}\n✉️ কোড: {latest_otp['message']}\n💰 বোনাস: {bonus} BDT")
                order_ref.update({'status': 'completed'})
    except Exception as e:
        print(f"Error: {e}")

# --- মেইন রানার ---
def run_dummy_server():
    try:
        server_address = ('', 8080)
        httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
        httpd.serve_forever()
    except: pass

if __name__ == '__main__':
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.job_queue.run_repeating(check_otp_and_forward, interval=10, first=5)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(admin_callback))
    app.add_handler(MessageHandler(filters.Text(["🎭 নাম্বার নিন"]), get_number))
    app.add_handler(MessageHandler(filters.Text(["💸 ব্যালেন্স"]), show_balance))
    app.add_handler(MessageHandler(filters.Text(["💰 টাকা উত্তোলন"]), lambda u, c: u.message.reply_text("⚠️ বর্তমানে উইথড্র সিস্টেম আপডেট হচ্ছে।")))
    app.add_handler(MessageHandler(filters.Text(["🎁 My Referrals"]), show_referrals))
    app.add_handler(MessageHandler(filters.Text(["🧐 সাপোর্ট"]), show_support))
    app.add_handler(MessageHandler(filters.Text(["👑 অ্যাডমিন প্যানেল"]), admin_panel))
    
    app.run_polling()
