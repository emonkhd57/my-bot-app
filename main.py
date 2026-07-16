import logging
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import firebase_admin
from firebase_admin import credentials, firestore
import requests

# --- এনভায়রনমেন্ট ভেরিয়েবল থেকে কনফিগারেশন ---
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
API_KEY = os.getenv('API_KEY')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnemn/@public/api"

# --- Firebase Setup (Render এনভায়রনমেন্ট থেকে) ---
firebase_json = json.loads(os.getenv('FIREBASE_JSON'))
cred = credentials.Certificate(firebase_json)
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- বাকি কোড ---
async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = f"{BASE_URL}/getnum"
    payload = {"rid": "26134"}
    headers = {"mauthapi": API_KEY}
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    
    if data['meta']['code'] == 200:
        number = data['data']['full_number']
        db.collection('orders').document(str(number)).set({
            'user_id': user_id,
            'number': number,
            'status': 'active'
        })
        await update.message.reply_text(f"✅ নাম্বার পাওয়া গেছে: {number}\nওটিপির জন্য অপেক্ষা করুন...")
    else:
        await update.message.reply_text("❌ দুঃখিত, বর্তমানে কোনো নাম্বার নেই।")

# --- ওটিপি ফরওয়ার্ডিং (অটোমেশন) ---
async def check_otp_and_forward(context: ContextTypes.DEFAULT_TYPE):
    url = f"{BASE_URL}/success-otp"
    headers = {"mauthapi": API_KEY}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        if data['meta']['code'] == 200 and data['data']['otps']:
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

# --- এডমিন ফিচারস ---
async def set_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        try:
            amount = float(context.args[0])
            db.collection('bot_state').document('1').set({'bonus_per_otp': amount}, merge=True)
            await update.message.reply_text(f"✅ বোনাস সেট করা হয়েছে: {amount} BDT")
        except:
            await update.message.reply_text("❌ ভুল কমান্ড! সঠিক ফরম্যাট: /setbonus 0.50")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        msg = " ".join(context.args)
        users = db.collection('users').stream()
        for user in users:
            try: await context.bot.send_message(chat_id=user.id, text=msg)
            except: continue
        await update.message.reply_text("✅ ব্রডকাস্ট সম্পন্ন হয়েছে।")

# --- মেইন মেনু ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.collection('users').document(str(update.effective_user.id)).set({'id': update.effective_user.id}, merge=True)
    keyboard = [["🎭 নাম্বার নিন", "💸 ব্যালেন্স"], ["💰 টাকা উত্তোলন", "🎁 My Referrals"], ["🧐 সাপোর্ট", "👶 আমি নতুন"], ["🏆 লিডারবোর্ড"]]
    await update.message.reply_text("👋 স্বাগতম! নিচে ক্লিক করুন:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# --- রানার ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.job_queue.run_repeating(check_otp_and_forward, interval=10, first=5)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setbonus", set_bonus))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.Text(["🎭 নাম্বার নিন"]), get_number))
    
    print("Bot is running...")
    app.run_polling()
