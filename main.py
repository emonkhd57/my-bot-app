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
OTP_GROUP_ID = os.getenv('OTP_GROUP_ID')
MAIN_CHANNEL_URL = "https://t.me/your_main_channel"  # আপনার মেইন চ্যানেলের লিংক
BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnemn/@public/api"

firebase_json = json.loads(os.getenv('FIREBASE_JSON'))
cred = credentials.Certificate(firebase_json)
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- সেটিংস লোডার ---
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
    
    # রেফারেল ট্র্যাকিং
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
    
    text = ("👋 হ্যালো! নাম্বার ওটিপি বোটে আপনাকে স্বাগতম।\n\n"
            "সরাসরি নাম্বার পেতে নিচের 🎭 নাম্বার নিন বাটন প্রেস করুন।")
    await update.message.reply_text(text, reply_markup=get_main_menu(user_id))

# --- ব্যালেন্স ভিউ ---
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
    
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

# --- দেশ ও সার্ভিস নির্বাচন প্যানেল ---
async def select_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = get_bot_settings()
    countries = config.get('countries', {})
    
    keyboard = []
    for c_name in countries.keys():
        keyboard.append([InlineKeyboardButton(f"🌍 {c_name}", callback_data=f"sel_c_{countries[c_name]}")])
    keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
    
    await update.message.reply_text("⚡ দেশসমূহ লোড করা হচ্ছে... অনুগ্রহ করে অপেক্ষা করুন।\n\n🌍 **দেশ সিলেক্ট করুন:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# --- ওটিপি সফল হলে ফরওয়ার্ড ও ব্যালেন্স ডিস্ট্রিবিউশন ---
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
                    
                    # ১. ইউজারের ব্যালেন্স এবং রেফার বোনাস ডিস্ট্রিবিউশন
                    cur_bal = user_data.get('balance', 0.0) + otp_rate
                    user_ref.update({'balance': cur_bal, 'total_otp': user_data.get('total_otp', 0) + 1})
                    
                    # আপলাইন রেফারের বোনাস (০.১০ টাকা)
                    referrer_id = user_data.get('referred_by')
                    if referrer_id:
                        ref_user_ref = db.collection('users').document(str(referrer_id))
                        if ref_user_ref.get().exists:
                            ref_cur_bal = ref_user_ref.get().to_dict().get('balance', 0.0)
                            ref_user_ref.update({'balance': ref_cur_bal + 0.10})

                    # আকর্ষক রেফার মেসেজ ব্লক
                    refer_promo = (
                        f"📢 **রেফার করে আনলিমিটেড ইনকাম করুন!**\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🤝 আপনি কাউকে রেফার করলে তার প্রতি ওটিপি রিসিভে আপনি পাবেন নিশ্চিত **০.১০ পয়সা** বোনাস! \n\n"
                        f"🚀 **হিসাব করে দেখুন:**\n"
                        f"👥 ১ জন ইউজার ১০০ ওটিপি নিলে = আপনার **১০ টাকা** লাভ!\n"
                        f"🔥 ২০ জন একটিভ ইউজার ১০০ করে ওটিপি নিলে = দিনে **২০০ টাকা** একদম ফ্রিতে!\n\n"
                        f"🔗 আপনার রেফারেল লিংক: `https://t.me/{(await context.bot.get_me()).username}?start={user_id}`"
                    )

                    # ফরম্যাটেড ওটিপি টেক্সট
                    success_msg = (
                        f"🔥 **Now OTP Bot** ➔ `Number 1` 📢\n\n"
                        f"🌍 {country_name} | {service_name}\n"
                        f"✉️ OTP Code: `{otp_code}`\n\n"
                        f"👤 User: {user_data.get('name', 'User')}\n"
                        f"💰 Balance: {cur_bal:.2f} BDT\n\n"
                        f"{refer_promo}"
                    )
                    
                    # ২. ইউজার প্যানেলে পাঠানো (বাটন ছাড়া)
                    await context.bot.send_message(chat_id=user_id, text=success_msg, parse_mode="Markdown")
                    
                    # ৩. ওটিপি গ্রুপে ফরওয়ার্ডিং (ইনলাইন বাটন সহ)
                    group_buttons = [
                        [InlineKeyboardButton("🚀 Get Number", url=f"https://t.me/{(await context.bot.get_me()).username}")],
                        [InlineKeyboardButton("📢 Main Channel", url=MAIN_CHANNEL_URL)]
                    ]
                    await context.bot.send_message(
                        chat_id=OTP_GROUP_ID, 
                        text=success_msg, 
                        parse_mode="Markdown", 
                        reply_markup=InlineKeyboardMarkup(group_buttons)
                    )
                    
                    order_ref.update({'status': 'completed'})
    except Exception as e:
        print(f"Error in Loop: {e}")

# --- 👑 অ্যাডমিন কন্ট্রোল প্যানেল ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    keyboard = [
        [InlineKeyboardButton("💸 ওটিপি রেট পরিবর্তন", callback_data="adm_rate"),
         InlineKeyboardButton("➕ দেশ/সার্ভিস যুক্ত করুন", callback_data="adm_add_service")],
        [InlineKeyboardButton("📢 ব্রডকাস্ট নোটিশ", callback_data="adm_broad"),
         InlineKeyboardButton("❌ ক্লোজ প্যানেল", callback_data="cancel_action")]
    ]
    await update.message.reply_text("👑 **অ্যাডমিন কন্ট্রোল প্যানেল**\n\nনিচের বাটন চেপে কাজ সম্পন্ন করুন:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- বাটন রেসপন্স (CallbackQueryHandler) ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # দেশ সিলেক্ট করার পর সার্ভিস আনা
    if data.startswith("sel_c_"):
        c_code = data.split("_")[2]
        context.user_data['selected_country_code'] = c_code
        
        config = get_bot_settings()
        services = config.get('services', {})
        
        keyboard = []
        for s_name in services.keys():
            keyboard.append([InlineKeyboardButton(f"🎯 {s_name}", callback_data=f"sel_s_{services[s_name]}")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        
        await query.edit_message_text("🎯 **এবার আপনার কাঙ্ক্ষিত সার্ভিসটি সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))

    # সার্ভিস সিলেক্ট করার পর ব্যাকগ্রাউন্ডে এপিআই কল
    elif data.startswith("sel_s_"):
        s_code = data.split("_")[2]
        c_code = context.user_data.get('selected_country_code')
        user_id = query.from_user.id
        
        await query.edit_message_text("⚡ ব্যাকগ্রাউন্ডে আপনার নাম্বার খোঁজা হচ্ছে... অনুগ্রহ করে অপেক্ষা করুন।")
        
        # ডাইনামিক এপিআই রিকোয়েস্ট পাসিং
        try:
            api_res = requests.post(f"{BASE_URL}/getnum", headers={"mauthapi": API_KEY}, json={"rid": "26134", "country": c_code, "service": s_code}).json()
            if api_res.get('meta', {}).get('code') == 200:
                number = api_res['data']['full_number']
                
                # দেশ ও সার্ভিস এর রিভার্স সার্চ ডেকোরেশন
                config = get_bot_settings()
                c_name = next((k for k, v in config['countries'].items() if v == c_code), "Sierra Leone")
                s_name = next((k for k, v in config['services'].items() if v == s_code), "Instagram")
                
                db.collection('orders').document(str(number)).set({
                    'user_id': user_id, 
                    'status': 'active',
                    'country_name': c_name,
                    'service_name': s_name
                })
                
                await query.message.reply_text(f"✅ **নাম্বার পাওয়া গেছে:** `{number}`\n🌍 দেশ: {c_name}\n🎯 সার্ভিস: {s_name}\n\n⏳ ওটিপির জন্য অপেক্ষা করুন...", parse_mode="Markdown")
            else:
                await query.message.reply_text("❌ দুঃখিত, এই দেশ বা সার্ভিসে বর্তমানে কোনো নাম্বার খালি নেই।")
        except:
            await query.message.reply_text("❌ এপিআই প্রসেসিং ত্রুটি।")

    # অ্যাডমিন প্যানেল ইভেন্ট ট্র্যাকিং
    elif data == "adm_rate":
        context.user_data['adm_action'] = 'set_rate'
        await query.edit_message_text("✍️ নতুন ওটিপি রেট পাঠান (যেমন: 3.50):")
        
    elif data == "adm_add_service":
        context.user_data['adm_action'] = 'add_item'
        await query.edit_message_text("✍️ নতুন দেশ বা সার্ভিস অ্যাড করতে এভাবে লিখুন:\n\n**দেশের জন্য:** `country দেশ_নাম কোড`\n**সার্ভিসের জন্য:** `service সার্ভিস_নাম কোড`\n\n*উদাহরণ:* `country Bangladesh bd`")

    elif data == "adm_broad":
        context.user_data['adm_action'] = 'broadcast'
        await query.edit_message_text("📢 সকল ইউজারের কাছে পাঠানোর জন্য নোটিশটি টাইপ করে দিন:")
        
    elif data == "cancel_action":
        await query.message.delete()

# --- টেক্সট ইনপুট প্রসেসর ---
async def text_processor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    action = context.user_data.get('adm_action')

    if user_id == ADMIN_ID and action:
        if action == 'set_rate':
            try:
                db.collection('settings').document('config').update({'otp_rate': float(text)})
                await update.message.reply_text(f"✅ সফলভাবে নতুন রেট `{text} BDT` সেট করা হয়েছে।")
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
            except: await update.message.reply_text("❌ ফরম্যাট ভুল। সঠিক নিয়ম ফলো করুন।")
            
        elif action == 'broadcast':
            users = db.collection('users').stream()
            for u in users:
                try: await context.bot.send_message(chat_id=u.to_dict()['id'], text=f"📢 **নোটিশ:**\n\n{text}")
                except: pass
            await update.message.reply_text("✅ ব্রডকাস্ট সফল হয়েছে।")
            
        context.user_data['adm_action'] = None
        return

    # কিবোর্ড ট্রিগার
    if text == "🎭 নাম্বার নিন":
        await select_country(update, context)
    elif text == "💸 ব্যালেন্স":
        await show_balance(update, context)
    elif text == "👑 অ্যাডমিন প্যানেল" and user_id == ADMIN_ID:
        await admin_panel(update, context)
    elif text == "💰 টাকা উত্তোলন":
        await update.message.reply_text("📥 উইথড্র প্রসেস করার জন্য অ্যাডমিনের সাথে যোগাযোগ করুন।")
    elif text == "🧐 সাপোর্ট":
        await update.message.reply_text("🎯 যেকোনো প্রয়োজনে সাহায্য পেতে অ্যাডমিন আইডিতে মেসেজ করুন।")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # অটোমেটিক ওটিপি প্রসেসিং জব
    app.job_queue.run_repeating(check_otp_and_forward, interval=10, first=5)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_processor))
    
    print("Bot is successfully running...")
    app.run_polling()
