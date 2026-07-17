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

# ডেটাবেসে গ্লোবাল সেটিংস (যেমন ওটিপি রেট) ইনিশিয়াল করার ফাংশন
def get_bot_settings():
    settings_ref = db.collection('settings').document('config').get()
    if settings_ref.exists:
        return settings_ref.to_dict()
    else:
        # ডিফল্ট ওটিপি রেট ২.৫০ টাকা সেট করা হলো
        default_config = {'otp_rate': 2.50}
        db.collection('settings').document('config').set(default_config)
        return default_config

# --- মেইন মেনু কিবোর্ড ---
def get_main_menu(user_id):
    keyboard = [
        ["🎭 নাম্বার নিন", "💸 ব্যালেন্স"],
        ["💰 টাকা উত্তোলন", "🎁 My Referrals"],
        ["🧐 সাপোর্ট"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 অ্যাডমিন প্যানেল"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.collection('users').document(str(user_id)).set({
        'id': user_id, 
        'balance': 0.0,
        'total_otp': 0
    }, merge=True)
    
    text = ("👋 হ্যালো! নাম্বার ওটিপি বোটে আপনাকে স্বাগতম।\n\n"
            "সরাসরি ইনস্টাগ্রাম নাম্বার পেতে নিচের 🎭 নাম্বার নিন বাটনে প্রেস করুন।")
    await update.message.reply_text(text, reply_markup=get_main_menu(user_id))

# --- ইউজার ফাংশন ---
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ref = db.collection('users').document(str(user_id)).get()
    
    balance = 0.0
    total_otp = 0
    if user_ref.exists:
        user_data = user_ref.to_dict()
        balance = user_data.get('balance', 0.0)
        total_otp = user_data.get('total_otp', 0)
        
    text = (f"💲 আপনার ব্যালেন্স\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 ব্যালেন্স: {balance:.2f} BDT\n"
            f"💰 পেন্ডিং (উইথড্র): 0.00 BDT\n"
            f"💵 Total Income: {balance:.2f} BDT\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ মোট ওটিপি রিসিভ: {total_otp} টি")
    await update.message.reply_text(text)

async def withdraw_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💳 USDT (BEP-20) -> সর্বনিম্ন: 0.20(-0.05)", callback_data="wd_usdt")],
        [InlineKeyboardButton(" বিকাশ -> সর্বনিম্ন: ১১কোটি(-৫)", callback_data="wd_bkash")],
        [InlineKeyboardButton(" নগদ -> সর্বনিম্ন: ১১০ট(-৫)", callback_data="wd_nagad")],
        [InlineKeyboardButton("🔙 ফিরে যান", callback_data="back_main")]
    ]
    await update.message.reply_text("📥 টাকা তোলার মাধ্যম সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- ওটিপি ফাংশন ও ফরওয়ার্ডিং ---
async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("⏳ নাম্বার রিকোয়েস্ট প্রসেস হচ্ছে...")
    
    try:
        response = requests.post(f"{BASE_URL}/getnum", headers={"mauthapi": API_KEY}, json={"rid": "26134"}).json()
        if response.get('meta', {}).get('code') == 200:
            number = response['data']['full_number']
            db.collection('orders').document(str(number)).set({'user_id': user_id, 'status': 'active'})
            await update.message.reply_text(f"✅ নাম্বার পাওয়া গেছে: `{number}`\nওটিপির জন্য অপেক্ষা করুন...", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ দুঃখিত, বর্তমানে কোনো নাম্বার নেই।")
    except Exception as e:
        await update.message.reply_text("❌ এপিআই কানেকশনে সমস্যা হয়েছে।")

# অটোমেটিক ওটিপি চেকার এবং ব্যালেন্স এডার (JobQueue দ্বারা রান হবে)
async def check_otp_and_forward(context: ContextTypes.DEFAULT_TYPE):
    url = f"{BASE_URL}/success-otp"
    try:
        data = requests.get(url, headers={"mauthapi": API_KEY}).json()
        if data.get('meta', {}).get('code') == 200 and data['data']['otps']:
            config = get_bot_settings()
            otp_rate = config.get('otp_rate', 2.50) # অ্যাডমিনের সেট করা প্রতি ওটিপির রেট
            
            for latest_otp in data['data']['otps']:
                number = latest_otp['number']
                order_ref = db.collection('orders').document(str(number))
                order = order_ref.get()
                
                # অর্ডারটি যদি একটিভ থাকে তবেই প্রসেস হবে
                if order.exists and order.to_dict().get('status') == 'active':
                    user_id = order.to_dict()['user_id']
                    otp_code = latest_otp['message']
                    
                    # ১. ইউজারকে ওটিপি পাঠানো
                    await context.bot.send_message(
                        chat_id=user_id, 
                        text=f"🔔 **নতুন ওটিপি এসেছে!**\n📱 নাম্বার: `{number}`\n✉️ কোড: `{otp_code}`\n💰 এই ওটিপি বাবদ আপনার ব্যালেন্সে **+{otp_rate:.2f} BDT** যোগ করা হয়েছে।",
                        parse_mode="Markdown"
                    )
                    
                    # ২. অ্যাডমিন গ্রুপে ওটিপি ফরওয়ার্ডিং
                    await context.bot.send_message(
                        chat_id=OTP_GROUP_ID, 
                        text=f"🔔 **গ্রুপ ওটিপি ফরওয়ার্ড!**\n📱 নাম্বার: `{number}`\n✉️ কোড: `{otp_code}`\n👤 ইউজার আইডি: `{user_id}`",
                        parse_mode="Markdown"
                    )
                    
                    # ৩. ডেটাবেসে ইউজারের ব্যালেন্স এবং ওটিপি কাউন্ট বাড়িয়ে দেওয়া
                    user_ref = db.collection('users').document(str(user_id))
                    user_doc = user_ref.get()
                    if user_doc.exists:
                        current_bal = user_doc.to_dict().get('balance', 0.0)
                        current_otp_count = user_doc.to_dict().get('total_otp', 0)
                        user_ref.update({
                            'balance': current_bal + otp_rate,
                            'total_otp': current_otp_count + 1
                        })
                    
                    # ৪. অর্ডার স্ট্যাটাস কমপ্লিট করা
                    order_ref.update({'status': 'completed', 'otp_code': otp_code})
                    
    except Exception as e:
        print(f"OTP Loop Error: {e}")

# --- 👑 অ্যাডমিন প্যানেল ফাংশনস ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ আপনি এই কমান্ডটি ব্যবহারের যোগ্য নন।")
        return

    # ডেটাবেস স্ট্যাটাস চেক
    users_ref = db.collection('users').stream()
    total_users = sum(1 for _ in users_ref)
    
    orders_ref = db.collection('orders').where('status', '==', 'completed').stream()
    total_success_otp = sum(1 for _ in orders_ref)

    config = get_bot_settings()
    current_rate = config.get('otp_rate', 2.50)

    text = (f"👑 ━━ **অ্যাডমিন কন্ট্রোল প্যানেল** ━━\n\n"
            f"📊 মোট বোট ইউজার: `{total_users}` জন\n"
            f"✅ মোট সফল ওটিপি: `{total_success_otp}` টি\n"
            f"💵 বর্তমান ওটিপি রেট: `{current_rate:.2f} BDT` (প্রতি ওটিপি)\n\n"
            f"⚙️ নিচে থেকে কাঙ্ক্ষিত কন্ট্রোল সিলেক্ট করুন:")

    keyboard = [
        [InlineKeyboardButton("💸 ওটিপি রেট পরিবর্তন", callback_data="adm_set_rate")],
        [InlineKeyboardButton("💰 ইউজারের ব্যালেন্স পরিবর্তন", callback_data="adm_change_bal")],
        [InlineKeyboardButton("📢 ব্রডকাস্ট নোটিশ", callback_data="adm_broadcast")],
        [InlineKeyboardButton("❌ ক্লোজ প্যানেল", callback_data="adm_close")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# --- বাটন রেসপন্স (Callback Queries) ---
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("wd_"):
        method = query.data.split("_")[1].upper()
        await query.edit_message_text(text=f"✅ আপনি {method} সিলেক্ট করেছেন। উইথড্র রিকোয়েস্টটি সাবমিট করা হচ্ছে...")
    elif query.data == "back_main":
        await query.edit_message_text(text="🔙 মেইন মেনুতে ফিরে এসেছেন। নিচের মেনু বাটন ব্যবহার করুন।")

    # অ্যাডমিন বাটন অ্যাকশন
    elif query.data == "adm_set_rate":
        if user_id != ADMIN_ID: return
        context.user_data['action'] = 'awaiting_rate_input'
        await query.edit_message_text("✍️ প্রতি সফল ওটিপির জন্য ইউজার কত টাকা পাবে তা লিখুন:\n*(যেমন: 2.20 বা 3.00)*", parse_mode="Markdown")

    elif query.data == "adm_change_bal":
        if user_id != ADMIN_ID: return
        context.user_data['action'] = 'awaiting_balance_input'
        await query.edit_message_text("👉 ইউজারের আইডি এবং টাকার পরিমাণ স্পেস দিয়ে লিখুন:\n`USER_ID AMOUNT`\n\n*উদাহরণ:* `12345678 50` (কমাতে চাইলে মাইনাস ফিগার দিন, যেমন `-30`)", parse_mode="Markdown")

    elif query.data == "adm_broadcast":
        if user_id != ADMIN_ID: return
        context.user_data['action'] = 'awaiting_broadcast_msg'
        await query.edit_message_text("📢 বোটের সকল ইউজারের কাছে যে নোটিশটি পাঠাতে চান তা টাইপ করে সেন্ড করুন:")

    elif query.data == "adm_close":
        await query.delete_message()

# --- টেক্সট ইনপুট হ্যান্ডলার ---
async def handle_text_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_action = context.user_data.get('action')

    # অ্যাডমিন রেসপন্স চেক
    if user_id == ADMIN_ID and user_action:
        # ১. ওটিপি রেট পরিবর্তন
        if user_action == 'awaiting_rate_input':
            try:
                new_rate = float(update.message.text)
                db.collection('settings').document('config').update({'otp_rate': new_rate})
                await update.message.reply_text(f"✅ ওটিপি রেট সফলভাবে আপডেট করা হয়েছে।\n🔥 এখন থেকে প্রতি সফল ওটিপিতে ইউজার পাবে: `{new_rate:.2f} BDT`", parse_mode="Markdown")
            except:
                await update.message.reply_text("❌ ভুল ইনপুট! শুধুমাত্র সংখ্যা বা দশমিক সংখ্যা লিখুন (যেমন: 2.50)।")
            context.user_data['action'] = None
            return

        # ২. ব্যালেন্স পরিবর্তন
        elif user_action == 'awaiting_balance_input':
            try:
                target_uid, amount = update.message.text.split()
                amount = float(amount)
                user_ref = db.collection('users').document(str(target_uid))
                user_doc = user_ref.get()
                
                if user_doc.exists:
                    current_bal = user_doc.to_dict().get('balance', 0.0)
                    new_bal = current_bal + amount
                    user_ref.update({'balance': new_bal})
                    await update.message.reply_text(f"✅ ইউজার `{target_uid}` এর ব্যালেন্স আপডেট হয়েছে।\n💰 পূর্বের ব্যালেন্স: {current_bal:.2f} BDT\n🔥 বর্তমান ব্যালেন্স: {new_bal:.2f} BDT", parse_mode="Markdown")
                else:
                    await update.message.reply_text("❌ এই আইডি ওয়ালা কোনো ইউজার ডেটাবেসে নেই।")
            except:
                await update.message.reply_text("❌ ইনপুট ফরমেট ভুল হয়েছে। সঠিক নিয়ম: `USER_ID AMOUNT`")
            context.user_data['action'] = None
            return

        # ৩. ব্রডকাস্ট নোটিশ
        elif user_action == 'awaiting_broadcast_msg':
            broadcast_text = update.message.text
            users_ref = db.collection('users').stream()
            success_count = 0
            
            await update.message.reply_text("⏳ ব্রডকাস্ট মেসেজ পাঠানো শুরু হয়েছে...")
            for user in users_ref:
                try:
                    uid = user.to_dict().get('id')
                    await context.bot.send_message(chat_id=uid, text=f"📢 **অফিসিয়াল নোটিশ:**\n\n{broadcast_text}", parse_mode="Markdown")
                    success_count += 1
                except:
                    pass
            await update.message.reply_text(f"✅ ব্রডকাস্ট সম্পন্ন! মোট {success_count} জন ইউজারের ইনবক্সে মেসেজ পৌঁছেছে।")
            context.user_data['action'] = None
            return

    # কিবোর্ড মেনু বাটন হ্যান্ডলিং
    text = update.message.text
    if text == "🎭 নাম্বার নিন":
        await get_number(update, context)
    elif text == "💸 ব্যালেন্স":
        await show_balance(update, context)
    elif text == "💰 টাকা উত্তোলন":
        await withdraw_money(update, context)
    elif text == "👑 অ্যাডমিন প্যানেল":
        await admin_panel(update, context)
    elif text == "🎁 My Referrals":
        await update.message.reply_text("🔗 রেফারেল সিস্টেম খুব শীঘ্রই লাইভ করা হবে।")
    elif text == "🧐 সাপোর্ট":
        await update.message.reply_text("🎯 যেকোনো সমস্যায় আমাদের অফিশিয়াল সাপোর্ট গ্রুপ বা মেইন অ্যাডমিনের সাথে যোগাযোগ করুন।")

# --- ডামি সার্ভার রানার ---
def run_dummy_server():
    try:
        server_address = ('', 8080)
        httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
        httpd.serve_forever()
    except: 
        pass

if __name__ == '__main__':
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    # বোট অ্যাপ্লিকেশন তৈরি
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # ব্যাকগ্রাউন্ড টাস্ক বা ক্রন জব হিসেবে ওটিপি লুপ চালু করা (প্রতি ১০ সেকেন্ড পর পর চলবে)
    job_queue = app.job_queue
    job_queue.run_repeating(check_otp_and_forward, interval=10, first=5)
    
    # হ্যান্ডলারস রেজিস্টার
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_inputs))
    
    print("Bot is successfully running...")
    app.run_polling()
