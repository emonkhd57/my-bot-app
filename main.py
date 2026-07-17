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

# পাইথনের বিল্ট-ইন সার্ভার (Render এর পোর্টের জন্য)
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- পাইথন asyncio লুপ ক্র্যাশ পলিসি ফিক্স ---
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
            'countries': {"Montenegro": "me", "GN (GUINEA)": "gn", "Madagascar": "mg", "Ivory coast": "ci"},
            'services': {"ইনস্টাগ্রাম": "ig", "ফেসবুক": "fb", "হোয়াটসঅ্যাপ": "wa", "টেলিগ্রাম": "tg"}
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
        ["👥 All User List", "📨 Withdraw Request"],
        ["⚙️ Add Service", "⚙️ Add Country"],
        ["👤 User Information", "📢 ব্রডকাস্ট"],
        ["🔙 মেইন মেনু"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    referrer = None
    if args and args[0].isdigit() and int(args[0]) != user_id:
        referrer = args[0]

    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        user_ref.set({
            'id': user_id, 
            'name': update.effective_user.first_name,
            'balance': 0.0,
            'total_otp': 0,
            'referred_by': referrer,
            'is_banned': False,
            'referrals': []
        })
        if referrer:
            db.collection('users').document(str(referrer)).update({
                'referrals': firestore.ArrayUnion([str(user_id)])
            })
    else:
        if user_doc.to_dict().get('is_banned', False):
            await update.message.reply_text("❌ দুঃখিত, আপনাকে এই বোট থেকে ব্যান করা হয়েছে।")
            return
    
    text = "👋 হ্যালো! নাম্বার ওটিপি বোটে আপনাকে স্বাগতম।\n\nসরাসরি নাম্বার পেতে নিচের 🎭 নাম্বার নিন বাটন প্রেস করুন।"
    await update.message.reply_text(text, reply_markup=get_main_menu(user_id))

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
    if user_data.get('is_banned', False): return

    balance = user_data.get('balance', 0.0)
    total_otp = user_data.get('total_otp', 0)
        
    text = (f"💲 আপনার ব্যালেন্স\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 ব্যালেন্স: {balance:.2f} BDT\n💰 পেন্ডিং (উইথড্র): 0.00 BDT\n"
            f"💵 Total Income: {balance:.2f} BDT\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ মোট ওটিপি রিসিভ: {total_otp} টি")
    await update.message.reply_text(text)

async def handle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
    if user_data.get('is_banned', False): return

    config = get_bot_settings()
    min_w = config.get('min_withdraw', 110.0)
    
    if user_data.get('balance', 0.0) < min_w:
        await update.message.reply_text(f"❌ আপনার পর্যাপ্ত ব্যালেন্স নেই। মিনিমাম উইথড্র লিমিট: {min_w} BDT")
        return
        
    keyboard = [
        [InlineKeyboardButton("📱 বিকাশ (Bkash)", callback_data="w_method_bkash")],
        [InlineKeyboardButton("💸 নগদ (Nagad)", callback_data="w_method_nagad")],
        [InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")]
    ]
    await update.message.reply_text("💳 **টাকা উত্তোলনের মেথড সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def select_service_first(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
    if user_data.get('is_banned', False): return

    config = get_bot_settings()
    services = config.get('services', {})
    keyboard = []
    for s_name, s_code in services.items():
        keyboard.append([InlineKeyboardButton(f"🎯 {s_name}", callback_data=f"usr_s_{s_code}")])
    keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
    
    await update.message.reply_text("⚡ **একটি সার্ভিস সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))

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
                    country_name = order_data.get('country_name', 'Montenegro')
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

                    success_msg = (
                        f"🔥 **Now OTP Bot** ➔ `Number 1` 📢\n\n🌍 {country_name} | {service_name}\n"
                        f"✉️ OTP Code: `{otp_code}`\n\n👤 User: {user_data.get('name', 'User')}\n"
                        f"💰 Balance: {cur_bal:.2f} BDT\n"
                        f"──────────────────────\n"
                        f"💡 প্রতি ওটিপিতে ০.১০ পয়সা ফ্রিতে পেতে চান? এখনই আপনার বন্ধুদের বোটের লিংক শেয়ার করে রেফার করা শুরু করুন! মেইন মেনুর 🎁 My Referrals বাটনে আপনার লিংকটি পেয়ে যাবেন। 🤑"
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
        elif action == 'set_min_w':
            try:
                db.collection('settings').document('config').update({'min_withdraw': float(text)})
                await update.message.reply_text(f"✅ মিনিমাম উইথড্র `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'add_service':
            try:
                name, code = text.split()
                config = get_bot_settings()
                config['services'][name] = code.lower()
                db.collection('settings').document('config').update({'services': config['services']})
                await update.message.reply_text(f"✅ সার্ভিস যুক্ত হয়েছে: {name} ({code})")
            except: await update.message.reply_text("❌ ফরম্যাট ভুল। উদাহরণ: `Facebook fb`")
        elif action == 'add_country':
            try:
                name, code = text.split(None, 1)
                config = get_bot_settings()
                config['countries'][name] = code.lower()
                db.collection('settings').document('config').update({'countries': config['countries']})
                await update.message.reply_text(f"✅ দেশ যুক্ত হয়েছে: {name} ({code})")
            except: await update.message.reply_text("❌ ফরম্যাট ভুল। উদাহরণ: `Bangladesh bd`")
        elif action == 'user_info_search':
            tgt_user = db.collection('users').document(text).get()
            if tgt_user.exists:
                ud = tgt_user.to_dict()
                context.user_data['managed_user_id'] = text
                ref_count = len(ud.get('referrals', []))
                ref_income = ref_count * 0.10 # কাল্পনিক বা ডায়নামিক হিসাব
                
                kbd = [
                    [InlineKeyboardButton("➕ ব্যালেন্স অ্যাড", callback_data="u_action_addbal"), InlineKeyboardButton("➖ ব্যালেন্স কাট", callback_data="u_action_cutbal")],
                    [InlineKeyboardButton("🚫 ব্যান করুন", callback_data="u_action_ban"), InlineKeyboardButton("🔓 আনব্যান করুন", callback_data="u_action_unban")],
                    [InlineKeyboardButton("❌ ক্লোজ", callback_data="cancel_action")]
                ]
                info_text = (
                    f"👤 **ইউজার ইনফরমেশন হিস্ট্রি**\n\n"
                    f"🆔 Telegram ID: `{ud['id']}`\n"
                    f"📛 নাম: {ud['name']}\n"
                    f"💰 বর্তমান ব্যালেন্স: {ud['balance']:.2f} BDT\n"
                    f"✅ মোট ওটিপি রিসিভ: {ud.get('total_otp', 0)} টি\n"
                    f"🎁 মোট সফল রেফার: {ref_count} জন\n"
                    f"💸 রেফারেল ইনকাম: {ref_income:.2f} BDT\n"
                    f"🚫 অ্যাকাউন্ট স্ট্যাটাস: {'Banned' if ud.get('is_banned') else 'Active'}"
                )
                await update.message.reply_text(info_text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ এই আইডি দিয়ে কোনো ইউজার পাওয়া যায়নি।")
        elif action == 'add_bal_amount':
            try:
                tgt_id = context.user_data.get('managed_user_id')
                ref = db.collection('users').document(tgt_id)
                ref.update({'balance': ref.get().to_dict()['balance'] + float(text)})
                await update.message.reply_text("✅ ব্যালেন্স সফলভাবে যোগ করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'cut_bal_amount':
            try:
                tgt_id = context.user_data.get('managed_user_id')
                ref = db.collection('users').document(tgt_id)
                ref.update({'balance': max(0.0, ref.get().to_dict()['balance'] - float(text))})
                await update.message.reply_text("✅ ব্যালেন্স সফলভাবে কেটে নেওয়া হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'broadcast':
            users = db.collection('users').stream()
            for u in users:
                try: await context.bot.send_message(chat_id=u.to_dict()['id'], text=f"📢 **নোটিশ:**\n\n{text}")
                except: pass
            await update.message.reply_text("✅ ব্রডকাস্ট সফল হয়েছে।")
        elif action == 'w_num_input':
            context.user_data['w_num'] = text
            context.user_data['adm_action'] = 'w_amount_input'
            await update.message.reply_text("✍️ এবার কত টাকা উইথড্র করতে চান সেই সংখ্যাটি পাঠান:")
            return
        elif action == 'w_amount_input':
            try:
                amount = float(text)
                user_ref = db.collection('users').document(str(user_id))
                ud = user_ref.get().to_dict()
                if amount > ud['balance']:
                    await update.message.reply_text("❌ আপনার একাউন্টে পর্যাপ্ত টাকা নেই।")
                else:
                    user_ref.update({'balance': ud['balance'] - amount})
                    db.collection('withdraws').add({
                        'user_id': user_id, 'name': ud['name'], 'method': context.user_data.get('w_method'),
                        'number': context.user_data.get('w_num'), 'amount': amount, 'status': 'pending'
                    })
                    await update.message.reply_text("✅ উইথড্র রিকোয়েস্ট সফলভাবে জমা হয়েছে। অ্যাডমিন চেক করে পে করবে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
            
        context.user_data['adm_action'] = None
        return

    # ইউজার টেক্সট বাটন ইভেন্ট হ্যান্ডলার
    if text == "👑 অ্যাডমিন প্যানেল" and user_id == ADMIN_ID:
        await update.message.reply_text("👑 **অ্যাডমিন কন্ট্রোল প্যানেল**", reply_markup=get_admin_menu())
    elif text == "🔙 মেইন মেনু" and user_id == ADMIN_ID:
        await update.message.reply_text("🔙 আপনি মেইন মেনুতে ফিরে এসেছেন।", reply_markup=get_main_menu(user_id))
    elif text == "💸 ওটিপি রেট" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'set_rate'
        await update.message.reply_text("✍️ নতুন ওটিপি রেট পাঠান:")
    elif text == "⚙️ মিনিমাম উইথড্র" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'set_min_w'
        await update.message.reply_text("✍️ নতুন মিনিমাম উইথড্র লিমিট পাঠান:")
    elif text == "⚙️ Add Service" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'add_service'
        await update.message.reply_text("✍️ সার্ভিস এর নাম ও কোড স্পেস দিয়ে পাঠান।\n\nউদাহরণ: `Facebook fb`")
    elif text == "⚙️ Add Country" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'add_country'
        await update.message.reply_text("✍️ দেশের নাম ও দেশের শর্ট কোড স্পেস দিয়ে পাঠান।\n\nউদাহরণ: `Montenegro me`")
    elif text == "👥 All User List" and user_id == ADMIN_ID:
        users = db.collection('users').get()
        await update.message.reply_text(f"👥 **বোটে মোট রেজিস্টার্ড ইউজার:** {len(users)} জন।")
    elif text == "👤 User Information" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'user_info_search'
        await update.message.reply_text("🔎 যে ইউজারের তথ্য দেখতে চান তার **Telegram User ID** পাঠান:")
    elif text == "📨 Withdraw Request" and user_id == ADMIN_ID:
        reqs = db.collection('withdraws').where('status', '==', 'pending').get()
        if not reqs:
            await update.message.reply_text("📥 কোনো পেন্ডিং উইথড্র রিকোয়েস্ট নেই।")
            return
        for r in reqs:
            rd = r.to_dict()
            kbd = [[InlineKeyboardButton("✅ Approve", callback_data=f"app_w_{r.id}")]]
            await update.message.reply_text(f"💰 **উইথড্র রিকোয়েস্ট:**\n👤 নাম: {rd['name']}\n🆔 ID: `{rd['user_id']}`\n📱 মেথড: {rd['method'].upper()}\n🔢 নাম্বার: `{rd['number']}`\n💵 পরিমাণ: {rd['amount']} BDT", reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")
    elif text == "📢 ব্রডকাস্ট" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'broadcast'
        await update.message.reply_text("📢 নোটিশটি টাইপ করে পাঠান:")
    elif text == "🎭 নাম্বার নিন":
        await select_service_first(update, context)
    elif text == "💸 ব্যালেন্স":
        await show_balance(update, context)
    elif text == "💰 টাকা উত্তোলন":
        await handle_withdraw(update, context)
    elif text == "🎁 My Referrals":
        user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
        refs = user_data.get('referrals', [])
        ref_count = len(refs)
        ref_income = ref_count * 0.0 # আপনি চাইলে রেফার ইনকাম ডায়নামিক করতে পারেন
        bot_uname = (await context.bot.get_me()).username
        
        refer_text = (
            f"🎁 ⚠️ **ধামাকা রেফার অফার! আনলিমিটেড ইনকাম করুন!** ⚠️ 🎁\n\n"
            f"👤 **Total Refer:** {ref_count} জন\n"
            f"😃 **Total Refer Income:** {ref_income:.2f} BDT\n\n"
            f"🔗 **আপনার রেফার লিংক (কপি করতে ক্লিক করুন):**\n"
            f"`https://t.me/{bot_uname}?start={user_id}`\n\n"
            f"──────────────────────\n"
            f"🔥 **রেফারের অবিশ্বাস্য সুবিধা:**\n"
            f"💸 রেফার করলে প্রতি otp তে ০.১০ পয়সা করে পাবেন রেফারকৃত ইউজারের কাছ থেকে। ১ ইউজার ১০০ otp নিলে ১০ টাকা পাবেন।\n\n"
            f"📈 ২০ টা রেফার করলে ১০০ টা করে ওটিপি নিলে user ২০০ টাকা পাবেন প্রতি দিন।\n\n"
            f"🚀 দেরি না করে এখনই লিংকটি আপনার বন্ধুদের সাথে শেয়ার করুন এবং লাইফটাইম কমিশন উপভোগ করুন! 🎉"
        )
        await update.message.reply_text(refer_text, parse_mode="Markdown")
    elif text == "🧐 সাপোর্ট":
        await update.message.reply_text("🧐 যেকোনো সমস্যায় সরাসরি অ্যাডমিনের সাথে যোগাযোগ করুন।")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("usr_s_"):
        s_code = data.split("_")[2]
        context.user_data['selected_service_code'] = s_code
        
        config = get_bot_settings()
        countries = config.get('countries', {})
        s_name = next((k for k, v in config['services'].items() if v == s_code), "Service")
        
        keyboard = []
        for c_name, c_code in countries.items():
            keyboard.append([InlineKeyboardButton(f"⭐ {c_name}", callback_data=f"usr_c_{c_code}")])
        keyboard.append([InlineKeyboardButton("⬅️ সার্ভিস তালিকায় ফিরে যান", callback_data="back_to_services")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        
        await query.edit_message_text(f"⭐ **{s_name}-এর জন্য দেশ সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "back_to_services":
        config = get_bot_settings()
        services = config.get('services', {})
        keyboard = []
        for s_name, s_code in services.items():
            keyboard.append([InlineKeyboardButton(f"🎯 {s_name}", callback_data=f"usr_s_{s_code}")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await query.edit_message_text("⚡ **একটি সার্ভিস সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("usr_c_") or data.startswith("change_num_"):
        c_code = data.split("_")[2]
        s_code = context.user_data.get('selected_service_code')
        user_id = query.from_user.id
        
        await query.edit_message_text("⚡ ব্যাকগ্রাউন্ডে আপনার নাম্বার খোঁজা হচ্ছে...")
        
        try:
            api_res = requests.post(f"{BASE_URL}/getnum", headers={"mauthapi": API_KEY}, json={"rid": "26134", "country": c_code, "service": s_code}).json()
            if api_res.get('meta', {}).get('code') == 200:
                number = api_res['data']['full_number']
                config = get_bot_settings()
                c_name = next((k for k, v in config['countries'].items() if v == c_code), "Country")
                s_name = next((k for k, v in config['services'].items() if v == s_code), "Service")
                
                db.collection('orders').document(str(number)).set({
                    'user_id': user_id, 'status': 'active', 'country_name': c_name, 'service_name': s_name
                })
                
                # একই নাম্বার ৩ বার দেখার প্রফেশনাল ভিউ (Auto-copy Layout)
                num_box = (
                    f"🎯 **{s_name} (Allocated) ✅**\n"
                    f"🔄 Waiting for OTP........\n\n"
                    f"📱 `{number}`\n"
                    f"📱 `{number}`\n"
                    f"📱 `{number}`\n\n"
                    f"📥 ওটিপির জন্য অপেক্ষা করুন..."
                )
                
                action_buttons = [
                    [InlineKeyboardButton("📢 ওটিপি গ্রুপ", url=MAIN_CHANNEL_URL), InlineKeyboardButton("🔄 নাম্বার পরিবর্তন করুন", callback_data=f"change_num_{c_code}")],
                    [InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")]
                ]
                
                await query.edit_message_text(num_box, reply_markup=InlineKeyboardMarkup(action_buttons), parse_mode="Markdown")
            else:
                await query.message.reply_text("❌ দুঃখিত, বর্তমানে কোনো নাম্বার খালি নেই।")
        except:
            await query.message.reply_text("❌ এপিআই প্রসেসিং ত্রুটি।")
            
    elif data.startswith("w_method_"):
        method = data.split("_")[2]
        context.user_data['w_method'] = method
        context.user_data['adm_action'] = 'w_num_input'
        await query.edit_message_text(f"✍️ আপনার **{method.upper()}** নাম্বারটি টাইপ করে পাঠান:")
        
    elif data.startswith("app_w_"):
        doc_id = data.split("_")[2]
        db.collection('withdraws').document(doc_id).update({'status': 'approved'})
        await query.edit_message_text("✅ উইথড্র রিকোয়েস্ট সফলভাবে অ্যাপ্রুভ করা হয়েছে।")
        
    elif data.startswith("u_action_"):
        act = data.split("_")[2]
        tgt_id = context.user_data.get('managed_user_id')
        if act == 'addbal':
            context.user_data['adm_action'] = 'add_bal_amount'
            await query.message.reply_text("✍️ কত ব্যালেন্স অ্যাড করতে চান সেই সংখ্যাটি পাঠান:")
        elif act == 'cutbal':
            context.user_data['adm_action'] = 'cut_bal_amount'
            await query.message.reply_text("✍️ কত ব্যালেন্স কাটতে চান সেই সংখ্যাটি পাঠান:")
        elif act == 'ban':
            db.collection('users').document(tgt_id).update({'is_banned': True})
            await query.edit_message_text("✅ ইউজারকে সফলভাবে ব্যান করা হয়েছে।")
        elif act == 'unban':
            db.collection('users').document(tgt_id).update({'is_banned': False})
            await query.edit_message_text("✅ ইউজারকে সফলভাবে আনব্যান করা হয়েছে।")
            
    elif data == "cancel_action":
        await query.message.delete()

# --- পাইথনের নিজস্ব বিল্ট-ইন সার্ভার হ্যান্ডলার ---
class RenderServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is perfectly running live on Render!")

def run_built_in_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), RenderServer)
    print(f"Built-in HTTP Server running on port {port}")
    server.serve_forever()

def main():
    # ব্যাকগ্রাউন্ডে বিল্ট-ইন সার্ভার চালু করা
    t = threading.Thread(target=run_built_in_server, daemon=True)
    t.start()

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
    app.run_polling(close_loop=False)

if __name__ == '__main__':
    main()
