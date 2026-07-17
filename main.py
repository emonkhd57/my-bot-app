import logging
import os
import json
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import firebase_admin
from firebase_admin import credentials, firestore
import requests

# --- কনফিগারেশন ---
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
API_KEY = os.getenv('API_KEY')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
OTP_GROUP_ID = os.getenv('OTP_GROUP_ID')
BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnemn/@public/api"

firebase_json = json.loads(os.getenv('FIREBASE_JSON'))
cred = credentials.Certificate(firebase_json)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ডেটাবেস থেকে গ্লোবাল কনফিগ নেওয়া
def get_bot_settings():
    settings_ref = db.collection('settings').document('config').get()
    if settings_ref.exists:
        return settings_ref.to_dict()
    else:
        default_config = {
            'otp_rate': 2.50,
            'min_withdraw': 110.0,
            'method_bkash': True,
            'method_nagad': True,
            'method_usdt': True
        }
        db.collection('settings').document('config').set(default_config)
        return default_config

# --- মেনু কিবোর্ডসমূহ ---
def get_main_menu(user_id):
    keyboard = [
        ["🎭 নাম্বার নিন", "💸 ব্যালেন্স"],
        ["💰 টাকা উত্তোলন", "🎁 My Referrals"],
        ["🧐 সাপোর্ট"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 অ্যাডমিন প্যানেল"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_menu():
    keyboard = [
        ["💸 ওটিপি রেট", "⚙️ মিনিমাম উইথড্র"],
        ["💰 ব্যালেন্স এডিট", "🔍 ইউজার স্ট্যাটাস"],
        ["🏆 টপ ১০ ইউজার", "🛠 মেথড অন/অফ"],
        ["📢 ব্রডকাস্ট", "🔙 মেইন মেনু"]
    ]
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
    config = get_bot_settings()
    min_wd = config.get('min_withdraw', 110.0)
    
    text = f"📥 **টাকা তোলার মাধ্যম সিলেক্ট করুন:**\n(সর্বনিম্ন উইথড্র: {min_wd} BDT)\n\n"
    keyboard = []
    
    if config.get('method_usdt', True):
        text += "💳 USDT (BEP-20) -> চালু আছে\n"
    if config.get('method_bkash', True):
        text += "📱 বিকাশ -> চালু আছে\n"
    if config.get('method_nagad', True):
        text += "📱 নগদ -> চালু আছে\n"
        
    await update.message.reply_text(text, parse_mode="Markdown")

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

async def check_otp_and_forward(context: ContextTypes.DEFAULT_TYPE):
    url = f"{BASE_URL}/success-otp"
    try:
        data = requests.get(url, headers={"mauthapi": API_KEY}).json()
        if data.get('meta', {}).get('code') == 200 and data['data']['otps']:
            config = get_bot_settings()
            otp_rate = config.get('otp_rate', 2.50)
            
            for latest_otp in data['data']['otps']:
                number = latest_otp['number']
                order_ref = db.collection('orders').document(str(number))
                order = order_ref.get()
                
                if order.exists and order.to_dict().get('status') == 'active':
                    user_id = order.to_dict()['user_id']
                    otp_code = latest_otp['message']
                    
                    await context.bot.send_message(
                        chat_id=user_id, 
                        text=f"🔔 **নতুন ওটিপি এসেছে!**\n📱 নাম্বার: `{number}`\n✉️ কোড: `{otp_code}`\n💰 আপনার ব্যালেন্সে **+{otp_rate:.2f} BDT** যোগ হয়েছে।",
                        parse_mode="Markdown"
                    )
                    
                    await context.bot.send_message(
                        chat_id=OTP_GROUP_ID, 
                        text=f"🔔 **গ্রুপ ওটিপি ফরওয়ার্ড!**\n📱 নাম্বার: `{number}`\n✉️ কোড: `{otp_code}`\n👤 ইউজার আইডি: `{user_id}`",
                        parse_mode="Markdown"
                    )
                    
                    user_ref = db.collection('users').document(str(user_id))
                    user_doc = user_ref.get()
                    if user_doc.exists:
                        current_bal = user_doc.to_dict().get('balance', 0.0)
                        current_otp_count = user_doc.to_dict().get('total_otp', 0)
                        user_ref.update({
                            'balance': current_bal + otp_rate,
                            'total_otp': current_otp_count + 1
                        })
                    
                    order_ref.update({'status': 'completed', 'otp_code': otp_code})
    except Exception as e:
        print(f"OTP Loop Error: {e}")

# --- 👑 অ্যাডমিন প্যানেল মেইন ভিউ ---
async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    users_ref = db.collection('users').stream()
    total_users = sum(1 for _ in users_ref)
    
    orders_ref = db.collection('orders').where('status', '==', 'completed').stream()
    total_success_otp = sum(1 for _ in orders_ref)

    config = get_bot_settings()

    text = (f"👑 ━━ **অ্যাডমিন কন্ট্রোল প্যানেল** ━━\n\n"
            f"📊 মোট বোট ইউজার: `{total_users}` জন\n"
            f"✅ মোট সফল ওটিপি: `{total_success_otp}` টি\n"
            f"💵 ওটিপি রেট: `{config.get('otp_rate'):.2f} BDT`\n"
            f"⚙️ মিনিমাম উইথড্র: `{config.get('min_withdraw'):.2f} BDT`\n\n"
            f"👇 নিচের মেনু বাটন ব্যবহার করে বোট নিয়ন্ত্রণ করুন:")

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_menu())

# --- অল-ইন-ওয়ান টেক্সট ইনপুট ও কিবোর্ড হ্যান্ডলার ---
async def handle_text_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    user_action = context.user_data.get('action')

    # অ্যাডমিন প্যানেল ইনপুট প্রোসেসিং
    if user_id == ADMIN_ID:
        if user_action == 'awaiting_rate':
            try:
                db.collection('settings').document('config').update({'otp_rate': float(text)})
                await update.message.reply_text(f"✅ ওটিপি রেট সফলভাবে `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট। সঠিক সংখ্যা দিন।")
            context.user_data['action'] = None
            return
        
        elif user_action == 'awaiting_min_wd':
            try:
                db.collection('settings').document('config').update({'min_withdraw': float(text)})
                await update.message.reply_text(f"✅ সর্বনিম্ন উইথড্র লিমিট `{text} BDT` সেট করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট। সঠিক সংখ্যা দিন।")
            context.user_data['action'] = None
            return

        elif user_action == 'awaiting_bal_edit':
            try:
                target_uid, amount = text.split()
                user_ref = db.collection('users').document(str(target_uid))
                if user_ref.get().exists:
                    cur_bal = user_ref.get().to_dict().get('balance', 0.0)
                    user_ref.update({'balance': cur_bal + float(amount)})
                    await update.message.reply_text(f"✅ ইউজার `{target_uid}` এর ব্যালেন্সে `{amount}` আপডেট করা হয়েছে।")
                else: await update.message.reply_text("❌ ইউজার পাওয়া যায়নি।")
            except: await update.message.reply_text("❌ ভুল ফরম্যাট। নিয়ম: `USER_ID AMOUNT`")
            context.user_data['action'] = None
            return

        elif user_action == 'awaiting_user_status':
            user_ref = db.collection('users').document(str(text.strip())).get()
            if user_ref.exists:
                ud = user_ref.to_dict()
                await update.message.reply_text(f"🔍 **ইউজার তথ্য:**\n🆔 আইডি: `{ud.get('id')}`\n💰 ব্যালেন্স: `{ud.get('balance'):.2f} BDT`\n✅ মোট ওটিপি: `{ud.get('total_otp')} টি`", parse_mode="Markdown")
            else: await update.message.reply_text("❌ এই আইডির কোনো ইউজার ডেটাবেসে নেই।")
            context.user_data['action'] = None
            return

        elif user_action == 'awaiting_method_toggle':
            config = get_bot_settings()
            method = text.strip().lower()
            if method in ['bkash', 'nagad', 'usdt']:
                key = f"method_{method}"
                new_status = not config.get(key, True)
                db.collection('settings').document('config').update({key: new_status})
                await update.message.reply_text(f"✅ {method.upper()} মেথডটি এখন {'**চালু**' if new_status else '**বন্ধ**'} করা হয়েছে।", parse_mode="Markdown")
            else: await update.message.reply_text("❌ ভুল মেথড নাম। শুধুমাত্র লিখুন: `bkash`, `nagad` অথবা `usdt`")
            context.user_data['action'] = None
            return

        elif user_action == 'awaiting_broadcast':
            users = db.collection('users').stream()
            count = 0
            for u in users:
                try:
                    await context.bot.send_message(chat_id=u.to_dict().get('id'), text=f"📢 **অফিসিয়াল নোটিশ:**\n\n{text}", parse_mode="Markdown")
                    count += 1
                except: pass
            await update.message.reply_text(f"✅ সফলভাবে {count} জন ইউজারের কাছে নোটিশ পাঠানো হয়েছে।")
            context.user_data['action'] = None
            return

    # অ্যাডমিন কিবোর্ড মেনু বাটন ক্লিক চেক
    if text == "👑 অ্যাডমিন প্যানেল" and user_id == ADMIN_ID:
        await show_admin_panel(update, context)
        return
    elif text == "🔙 মেইন মেনু" and user_id == ADMIN_ID:
        await update.message.reply_text("🔙 আপনি মেইন মেনুতে ফিরে এসেছেন।", reply_markup=get_main_menu(user_id))
        return
    elif text == "💸 ওটিপি রেট" and user_id == ADMIN_ID:
        context.user_data['action'] = 'awaiting_rate'
        await update.message.reply_text("✍️ প্রতি সফল ওটিপির নতুন রেট (টাকা) কত হবে তা লিখে পাঠান:")
        return
    elif text == "⚙️ মিনিমাম উইথড্র" and user_id == ADMIN_ID:
        context.user_data['action'] = 'awaiting_min_wd'
        await update.message.reply_text("✍️ সর্বনিম্ন উইথড্রর পরিমাণ কত টাকা হবে তা লিখে পাঠান:")
        return
    elif text == "💰 ব্যালেন্স এডিট" and user_id == ADMIN_ID:
        context.user_data['action'] = 'awaiting_bal_edit'
        await update.message.reply_text("👉 ইউজারের আইডি এবং টাকার পরিমাণ স্পেস দিয়ে লিখুন:\n`USER_ID AMOUNT` (কমাতে মাইনাস দিন)")
        return
    elif text == "🔍 ইউজার স্ট্যাটাস" and user_id == ADMIN_ID:
        context.user_data['action'] = 'awaiting_user_status'
        await update.message.reply_text("🔍 যে ইউজারের তথ্য দেখতে চান তার Telegram ID লিখে পাঠান:")
        return
    elif text == "📢 ব্রডকাস্ট" and user_id == ADMIN_ID:
        context.user_data['action'] = 'awaiting_broadcast'
        await update.message.reply_text("📢 সকল ইউজারের উদ্দেশ্যে পাঠানো নোটিশটি টাইপ করে পাঠান:")
        return
    elif text == "🛠 মেথড অন/অফ" and user_id == ADMIN_ID:
        context.user_data['action'] = 'awaiting_method_toggle'
        await update.message.reply_text("🛠 কোন মেথডটি অন/অফ করতে চান তার নাম ছোট হাতের অক্ষরে লিখে পাঠান:\n👉 লিখুন: `bkash` বা `nagad` বা `usdt`")
        return
    elif text == "🏆 টপ ১০ ইউজার" and user_id == ADMIN_ID:
        # ডেটাবেস থেকে সর্ট করে সবচেয়ে বেশি ওটিপি নেওয়া ১০ ইউজার খোঁজা
        users_ref = db.collection('users').order_by('total_otp', direction=firestore.Query.DESCENDING).limit(10).stream()
        leaderboard = "🏆 **সবচেয়ে বেশি ওটিপি নেওয়া টপ ১০ ইউজার:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        rank = 1
        for u in users_ref:
            ud = u.to_dict()
            leaderboard += f"{rank}. 👤 ID: `{ud.get('id')}` ➔ 📱 ওটিপি: `{ud.get('total_otp', 0)}` টি\n"
            rank += 1
        await update.message.reply_text(leaderboard, parse_mode="Markdown")
        return

    # --- সাধারণ ইউজার কিবোর্ড মেনু চেক ---
    if text == "🎭 নাম্বার নিন":
        await get_number(update, context)
    elif text == "💸 ব্যালেন্স":
        await show_balance(update, context)
    elif text == "💰 টাকা উত্তোলন":
        await withdraw_money(update, context)
    elif text == "🎁 My Referrals":
        await update.message.reply_text("🔗 আপনার রেফারেল লিংক শীঘ্রই আপডেট করা হবে।")
    elif text == "🧐 সাপোর্ট":
        await update.message.reply_text("🎯 যেকোনো সমস্যার জন্য অ্যাডমিনের সাথে সরাসরি যোগাযোগ করুন।")

# --- ডামি সার্ভার রানার ---
def run_dummy_server():
    try:
        server_address = ('', 8080)
        httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
        httpd.serve_forever()
    except: pass

if __name__ == '__main__':
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # ব্যাকগ্রাউন্ড ওটিপি প্রসেসিং জব (প্রতি ১০ সেকেন্ডে রান হবে)
    job_queue = app.job_queue
    job_queue.run_repeating(check_otp_and_forward, interval=10, first=5)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_inputs))
    
    print("Bot is successfully running with Custom Keyboard Admin Panel...")
    app.run_polling()
