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

# ==================== FIRESTORE SYSTEM CONFIG ====================
async def load_system_config():
    doc = db.collection("system").document("config").get()
    if not doc.exists:
        default_config = {
            "min_withdraw": 110.0,
            "max_withdraw": 5000.0,
            "payment_methods": {"BKASH": True, "NAGAD": True, "ROCKET": True, "BINANCE": True},
            "otp_rate": 20.0
        }
        db.collection("system").document("config").set(default_config)
        return default_config
    return doc.to_dict()

async def update_min_withdraw(new_min):
    db.collection("system").document("config").update({"min_withdraw": float(new_min)})

async def update_otp_rate(new_rate):
    db.collection("system").document("config").update({"otp_rate": float(new_rate)})

async def get_otp_rate():
    config = await load_system_config()
    return config.get("otp_rate", 20.0)

async def toggle_payment_method(method_name):
    config = await load_system_config()
    methods = config.get("payment_methods", {})
    if method_name in methods:
        methods[method_name] = not methods[method_name]
        db.collection("system").document("config").update({"payment_methods": methods})
        return methods[method_name]
    return None

async def get_enabled_payment_methods():
    config = await load_system_config()
    return [name for name, enabled in config.get("payment_methods", {}).items() if enabled]

# ==================== PER-USER OTP RATE ====================
async def get_user_otp_rate(user_id):
    doc = db.collection("user_rates").document(str(user_id)).get()
    if doc.exists:
        return doc.to_dict().get("rate", await get_otp_rate())
    return await get_otp_rate()

async def set_user_otp_rate(user_id, rate):
    if float(rate) > 0:
        db.collection("user_rates").document(str(user_id)).set({"rate": float(rate)}, merge=True)
    else:
        db.collection("user_rates").document(str(user_id)).delete()

# ==================== FAKE OTP CONFIG ====================
async def load_fake_otp_config():
    doc = db.collection("system").document("fake_otp").get()
    if not doc.exists:
        default = {"enabled": False, "service": "facebook", "range": "", "interval": 10, "running": False, "otp_digits": 6}
        db.collection("system").document("fake_otp").set(default)
        return default
    return doc.to_dict()

async def update_fake_otp_config(**kwargs):
    db.collection("system").document("fake_otp").update(kwargs)

# ==================== REQUIRED CHANNELS ====================
async def get_all_required_channels():
    doc = db.collection("system").document("channels").get()
    return doc.to_dict().get("list", []) if doc.exists else []

async def add_required_channel(link, label=None, chat_id=None):
    channels = await get_all_required_channels()
    if any(ch['link'] == link for ch in channels): return False, "এই লিংক ইতিমধ্যে আছে।"
    entry = {"link": link, "label": label or link, "chat_id": chat_id}
    channels.append(entry)
    db.collection("system").document("channels").set({"list": channels})
    return True, "সফলভাবে যোগ করা হয়েছে।"

async def remove_required_channel(link_or_label):
    channels = await get_all_required_channels()
    new_channels = [ch for ch in channels if ch.get("link") != link_or_label and ch.get("label") != link_or_label]
    if len(new_channels) < len(channels):
        db.collection("system").document("channels").set({"list": new_channels})
        return True, "সরানো হয়েছে।"
    return False, "কোনো ম্যাচ পাওয়া যায়নি।"

# ==================== BANNED USERS ====================
async def is_user_banned(uid):
    return db.collection("banned").document(str(uid)).get().exists

async def ban_user(uid):
    db.collection("banned").document(str(uid)).set({"banned": True})

async def unban_user(uid):
    db.collection("banned").document(str(uid)).delete()

# ==================== REFERRAL DATA ====================
async def get_referral_count(uid):
    doc = db.collection("referrals").document(str(uid)).get()
    return doc.to_dict().get("referral_count", 0) if doc.exists else 0

async def update_referral_count(uid, count):
    db.collection("referrals").document(str(uid)).set({"referral_count": count}, merge=True)



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
