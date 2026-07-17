import logging
import os
import json
import asyncio
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import firebase_admin
from firebase_admin import credentials, firestore
import requests

# --- পাইথন asyncio লুপ ক্র্যাশ পলিসি ফিক্স (Render এর জন্য অত্যন্ত জরুরি) ---
if sys.platform >= 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

# --- কনফিগারেশন ---
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
API_KEY = os.getenv('API_KEY')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
OTP_GROUP_ID = os.getenv('OTP_GROUP_ID')
MAIN_CHANNEL_URL = "https://t.me/your_main_channel"
BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnemn/@public/api"

# ফায়ারবেস ইনিশিয়ালাইজেশন
if not firebase_admin._apps:
    firebase_json = json.loads(os.getenv('FIREBASE_JSON'))
    cred = credentials.Certificate(firebase_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

def get_bot_settings():
    settings_ref = db.collection('settings').document('config').get()
    if settings_ref.exists:
        return settings_ref.to_dict()
    else:
        default_config = {
            'otp_rate': 2.50,
            'min_withdraw': 110.0,
            'countries': {"Sierra Leone": "sl", "Armenia": "am", "Montenegro": "me", "Guinea": "gn"},
            'services': {"Instagram": "ig", "Telegram": "tg", "WhatsApp": "wa"}
        }
        db.collection('settings').document('config').set(default_config)
        return default_config

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    referrer = None
    if args and args[0].isdigit() and int(args[0]) != user_id:
        referrer = args[0]

    user_ref = db.collection('users').document(str(user_id))
    if not user_ref.get().exists:
        user_ref.set({
            'id': user_id, 
            'name': update.effective_user.first_name,
            'balance': 0.0,
            'total_otp': 0,
            'referred_by': referrer
        })
        if referrer:
            db.collection('users').document(str(referrer)).update({
                'referrals': firestore.ArrayUnion([str(user_id)])
            })
    
    text = "👋 হ্যালো! নাম্বার ওটিপি বোটে আপনাকে স্বাগতম।\n\nসরাসরি নাম্বার পেতে নিচের 🎭 নাম্বার নিন বাটন প্রেস করুন।"
    await update.message.reply_text(text, reply_markup=get_main_menu(user_id))

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
    balance = user_data.get('balance', 0.0)
    total_otp = user_data.get('total_otp', 0)
        
    text = (f"💲 আপনার ব্যালেন্স\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 ব্যালেন্স: {balance:.2f} BDT\n💰 পেন্ডিং (উইথড্র): 0.00 BDT\n"
            f"💵 Total Income: {balance:.2f} BDT\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ মোট ওটিপি রিসিভ: {total_otp} টি")
    await update.message.reply_text(text)

async def select_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = get_bot_settings()
    countries = config.get('countries', {})
    keyboard = []
    for c_name in countries.keys():
        keyboard.append([InlineKeyboardButton(f"🌍 {c_name}", callback_data=f"sel_c_{countries[c_name]}")])
    keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
    await update.message.reply_text("⚡ দেশসমূহ লোড করা হচ্ছে... অনুগ্রহ করে অপেক্ষা করুন।\n\n🌍 **দেশ সিলেক্ট করুন:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

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
                    order_data = order.to_dict()
                    user_id = order_data['user_id']
                    service_name = order_data.get('service_name', 'Instagram')
                    country_name = order_data.get('country_name', 'Sierra Leone')
                    otp_code = latest_otp['message']
                    
                    user_ref = db.collection('users').document(str(user_id))
                    user_data = user_ref.get().to_dict() or {}
                    
                    cur_bal = user_data.get('balance', 0.0) + otp_rate
                    user_ref.update({'balance': cur_bal, 'total_otp': user_data.get('total_otp', 0) + 1})
                    
                    referrer_id = user_data.get('referred_by')
                    if referrer_id:
                        ref_user_ref = db.collection('users').document(str(referrer_id))
                        if ref_user_ref.get().exists:
                            ref_cur_bal = ref_user_ref.get().to_dict().get('balance', 0.0)
                            ref_user_ref.update({'balance': ref_cur_bal + 0.10})

                    refer_promo = (
                        f"📢 **রেফার করে আনলিমিটেড ইনকাম করুন!**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🤝 আপনি কাউকে রেফার করলে তার প্রতি ওটিপি রিসিভে আপনি পাবেন নিশ্চিত **০.১০ পয়সা** বোনাস! \n\n"
                        f"🚀 **হিসাব করে দেখুন:**\n👥 ১ জন ইউজার ১০০ ওটিপি নিলে = আপনার **১০ টাকা** লাভ!\n"
                        f"🔥 ২০ জন একটিভ ইউজার ১০০ করে ওটিপি নিলে = দিনে **২০০ টাকা** একদম ফ্রিতে!\n\n"
                        f"🔗 আপনার রেফারেল লিংক: `https://t.me/{(await context.bot.get_me()).username}?start={user_id}`"
                    )

                    success_msg = (
                        f"🔥 **Now OTP Bot** ➔ `Number 1` 📢\n\n🌍 {country_name} | {service_name}\n"
                        f"✉️ OTP Code: `{otp_code}`\n\n👤 User: {user_data.get('name', 'User')}\n"
                        f"💰 Balance: {cur_bal:.2f} BDT\n\n{refer_promo}"
                    )
                    
                    await context.bot.send_message(chat_id=user_id, text=success_msg, parse_mode="Markdown")
                    
                    group_buttons = [
                        [InlineKeyboardButton("🚀 Get Number", url=f"https://t.me/{(await context.bot.get_me()).username}")],
                        [InlineKeyboardButton("📢 Main Channel", url=MAIN_CHANNEL_URL)]
                    ]
                    await context.bot.send_message(chat_id=OTP_GROUP_ID, text=success_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(group_buttons))
                    order_ref.update({'status': 'completed'})
    except:
        pass

async def handle_text_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    action = context.user_data.get('adm_action')

    if user_id == ADMIN_ID and action:
        if action == 'set_rate':
            try:
                db.collection('settings').document('config').update({'otp_rate': float(text)})
                await update.message.reply_text(f"✅ ওটিপি রেট সফলভাবে `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'add_item':
            try:
                parts = text.split()
                type_item, name, code = parts[0].lower(), parts[1], parts[2]
                config = get_bot_settings()
                if type_item == 'country':
                    config['countries'][name] = code
                    db.collection('settings').document('config').update({'countries': config['countries']})
                elif type_item == 'service':
                    config['services'][name] = code
                    db.collection('settings').document('config').update({'services': config['services']})
                await update.message.reply_text(f"✅ সফলভাবে নতুন {type_item} হিসেবে `{name}` যুক্ত করা হয়েছে।")
            except: await update.message.reply_text("❌ ফরম্যাট ভুল।")
        elif action == 'broadcast':
            users = db.collection('users').stream()
            for u in users:
                try: await context.bot.send_message(chat_id=u.to_dict()['id'], text=f"📢 **নোটিশ:**\n\n{text}")
                except: pass
            await update.message.reply_text("✅ ব্রডকাস্ট সফল হয়েছে।")
        context.user_data['adm_action'] = None
        return

    if text == "👑 অ্যাডমিন প্যানেল" and user_id == ADMIN_ID:
        await update.message.reply_text("👑 **অ্যাডমিন কন্ট্রোল প্যানেল**", reply_markup=get_admin_menu())
    elif text == "🔙 মেইন মেনু" and user_id == ADMIN_ID:
        await update.message.reply_text("🔙 আপনি মেইন মেনুতে ফিরে এসেছেন।", reply_markup=get_main_menu(user_id))
    elif text == "💸 ওটিপি রেট" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'set_rate'
        await update.message.reply_text("✍️ নতুন ওটিপি রেট পাঠান:")
    elif text == "📢 ব্রডকাস্ট" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'broadcast'
        await update.message.reply_text("📢 নোটিশটি টাইপ করে পাঠান:")
    elif text == "🎭 নাম্বার নিন":
        await select_country(update, context)
    elif text == "💸 ব্যালেন্স":
        await show_balance(update, context)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("sel_c_"):
        context.user_data['selected_country_code'] = data.split("_")[2]
        config = get_bot_settings()
        services = config.get('services', {})
        keyboard = []
        for s_name in services.keys():
            keyboard.append([InlineKeyboardButton(f"🎯 {s_name}", callback_data=f"sel_s_{services[s_name]}")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await query.edit_message_text("🎯 **এবার আপনার কাঙ্ক্ষিত সার্ভিসটি সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("sel_s_"):
        s_code = data.split("_")[2]
        c_code = context.user_data.get('selected_country_code')
        user_id = query.from_user.id
        await query.edit_message_text("⚡ ব্যাকগ্রাউন্ডে আপনার নাম্বার খোঁজা হচ্ছে...")
        
        try:
            api_res = requests.post(f"{BASE_URL}/getnum", headers={"mauthapi": API_KEY}, json={"rid": "26134", "country": c_code, "service": s_code}).json()
            if api_res.get('meta', {}).get('code') == 200:
                number = api_res['data']['full_number']
                config = get_bot_settings()
                c_name = next((k for k, v in config['countries'].items() if v == c_code), "Sierra Leone")
                s_name = next((k for k, v in config['services'].items() if v == s_code), "Instagram")
                
                db.collection('orders').document(str(number)).set({
                    'user_id': user_id, 'status': 'active', 'country_name': c_name, 'service_name': s_name
                })
                await query.message.reply_text(f"✅ **নাম্বার:** `{number}`\n🌍 দেশ: {c_name}\n🎯 সার্ভিস: {s_name}\n\n⏳ ওটিপির জন্য অপেক্ষা করুন...", parse_mode="Markdown")
            else:
                await query.message.reply_text("❌ দুঃখিত, বর্তমানে কোনো নাম্বার খালি নেই।")
        except:
            await query.message.reply_text("❌ এপিআই প্রসেসিং ত্রুটি।")
    elif data == "cancel_action":
        await query.message.delete()

def main():
    # রানিং লুপ হ্যান্ডলিং ফিক্স
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.job_queue.run_repeating(check_otp_and_forward, interval=10, first=5)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_inputs))
    
    print("Bot starting via run_polling...")
    app.run_polling(close_loop=False) # লুপ ক্লোজিং এরর প্রটেকশন

if __name__ == '__main__':
    main()
