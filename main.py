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

# --- মেইন মেনু ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.collection('users').document(str(user_id)).set({'id': user_id}, merge=True)
    keyboard = [["🎭 নাম্বার নিন", "💸 ব্যালেন্স"], ["💰 টাকা উত্তোলন", "🎁 My Referrals"], ["🧐 সাপোর্ট"]]
    if user_id == ADMIN_ID: keyboard.append(["👑 অ্যাডমিন প্যানেল"])
    await update.message.reply_text("👋 স্বাগতম! নিচে ক্লিক করুন:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# --- অ্যাডমিন প্যানেল ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    keyboard = [
        [InlineKeyboardButton("👥 USER MANAGEMENT", callback_data="adm_user_mgmt")],
        [InlineKeyboardButton("⚙️ SYSTEM CONFIGURATION", callback_data="adm_sys_conf")],
        [InlineKeyboardButton("🔗 REQUIRED CHANNELS", callback_data="adm_req_chan")],
        [InlineKeyboardButton("⚡ FAKE OTP", callback_data="adm_fake_otp")],
        [InlineKeyboardButton("🔙 BACK TO MAIN", callback_data="back_main")]
    ]
    if update.callback_query:
        await update.callback_query.edit_message_text("👑 প্রধান অ্যাডমিন মেনু:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("👑 প্রধান অ্যাডমিন মেনু:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- অ্যাডমিন কলব্যাক হ্যান্ডলার ---
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_main":
        await query.edit_message_text("🔙 প্রধান মেনুতে ফিরে এসেছেন।")
    elif data == "admin_main":
        await admin_panel(update, context)
    
    # ইউজার ম্যানেজমেন্ট
    elif data == "adm_user_mgmt":
        keyboard = [
            [InlineKeyboardButton("📢 SEND MSG TO ALL", callback_data="bc_all")],
            [InlineKeyboardButton("🆔 ALL ID", callback_data="all_ids"), InlineKeyboardButton("📜 BAN LIST", callback_data="ban_list")],
            [InlineKeyboardButton("💰 ALL BAL", callback_data="all_bal"), InlineKeyboardButton("👥 ALL USERS", callback_data="all_users")],
            [InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_main")]
        ]
        await query.edit_message_text("👥 ইউজার ম্যানেজমেন্ট:", reply_markup=InlineKeyboardMarkup(keyboard))

    # সিস্টেম কনফিগারেশন
    elif data == "adm_sys_conf":
        keyboard = [
            [InlineKeyboardButton("📈 STATUS", callback_data="t_stat"), InlineKeyboardButton("👤 CHECK", callback_data="u_stat")],
            [InlineKeyboardButton("⛔ BAN", callback_data="ban_u"), InlineKeyboardButton("🔓 UNBAN", callback_data="unban_u")],
            [InlineKeyboardButton("➖ REMOVE", callback_data="rem_bal"), InlineKeyboardButton("➕ ADD", callback_data="add_bal")],
            [InlineKeyboardButton("💲 OTP PRICE", callback_data="otp_p"), InlineKeyboardButton("📋 VIEW RATE", callback_data="v_otp_r")],
            [InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_main")]
        ]
        await query.edit_message_text("⚙️ সিস্টেম কনফিগারেশন:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- বাটন ফাংশনাল হ্যান্ডলার ---
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ref = db.collection('users').document(str(user_id)).get()
    balance = user_ref.to_dict().get('balance', 0.0) if user_ref.exists else 0.0
    text = (f"💵 আপনার ব্যালেন্স\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 ব্যালেন্স: {balance:.2f} BDT\n"
            f"💸 পেন্ডিং (উইথড্র): 0.00 BDT\n"
            f"💰 Total Income: 0.00 BDT\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📞 মোট ওটিপি রিসিভ: 0 টি")
    await update.message.reply_text(text)

async def show_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = (await context.bot.get_me()).username
    refer_link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
    text = (f"🎁 My Referrals\n\n"
            f"🔗 আপনার রেফার লিংক:\n{refer_link}\n\n"
            f"ℹ️ প্রতি রেফারে পাবেন ০.১০ পয়সা বোনাস।")
    await update.message.reply_text(text)

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👤 অ্যাডমিন সাপোর্ট", url="https://t.me/helptg10")],
        [InlineKeyboardButton("📢 অফিসিয়াল চ্যানেল", url="https://t.me/helptg100")]
    ]
    await update.message.reply_text("📞 গ্রাহক সেবা কেন্দ্র:\nসম্মানিত মেম্বার, আপনার যেকোনো সমস্যার জন্য সাপোর্ট টিমের সাথে যোগাযোগ করুন।", reply_markup=InlineKeyboardMarkup(keyboard))

# --- ওটিপি ফাংশন ---
async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = f"{BASE_URL}/getnum"
    headers = {"mauthapi": API_KEY}
    response = requests.post(url, headers=headers, json={"rid": "26134"}).json()
    
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
                await context.bot.send_message(chat_id=user_id, text=f"🔔 নতুন ওটিপি এসেছে!\n📱 নাম্বার: {number}\n✉️ কোড: {latest_otp['message']}")
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
    
    if app.job_queue:
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
