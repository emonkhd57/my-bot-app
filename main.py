import logging
import os
import json
import asyncio
import sys
import random
import io
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import openpyxl
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

if sys.platform >= 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

COUNTRY_FLAGS = {
    "tanzania": "🇹🇿", "ivory coast": "🇨🇮", "montenegro": "🇲🇪", 
    "guinea": "🇬🇳", "sierra leone": "🇸🇱", "nigeria": "🇳🇬",
    "bangladesh": "🇧🇩", "india": "🇮🇳", "pakistan": "🇵🇰", "usa": "🇺🇸"
}

def get_premium_flag(name):
    clean_name = name.strip().lower()
    return COUNTRY_FLAGS.get(clean_name, "🏳️")

BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
OTP_GROUP_ID = "-1003656135640"
OTP_GROUP_URL = "https://t.me/emotp100"       
MAIN_CHANNEL_URL = "https://t.me/helptg100"   

if not firebase_admin._apps:
    firebase_json = json.loads(os.getenv('FIREBASE_JSON'))
    cred = credentials.Certificate(firebase_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ক্যাশ স্টোরেজ (অতিরিক্ত ডাটাবেজ রিড বন্ধ করার জন্য)
_CACHE = {
    "settings": None,
    "settings_time": 0,
    "providers": None,
    "providers_time": 0
}

def get_bot_settings():
    global _CACHE
    current_time = datetime.utcnow().timestamp()
    if _CACHE["settings"] and (current_time - _CACHE["settings_time"] < 300):
        return _CACHE["settings"]

    settings_ref = db.collection('settings').document('config').get()
    if settings_ref.exists:
        data = settings_ref.to_dict()
        if 'services' not in data: data['services'] = {}
        if 'countries' not in data: data['countries'] = {}
        if 'fake_otp_enabled' not in data: data['fake_otp_enabled'] = False
        if 'refer_commission' not in data: data['refer_commission'] = 0.10
        _CACHE["settings"] = data
        _CACHE["settings_time"] = current_time
        return data
    else:
        default_config = {
            'otp_rate': 0.70, 'min_withdraw': 110.0,
            'countries': {}, 'services': {}, 'fake_otp_enabled': False,
            'refer_commission': 0.10
        }
        db.collection('settings').document('config').set(default_config)
        _CACHE["settings"] = default_config
        _CACHE["settings_time"] = current_time
        return default_config

def get_active_providers():
    global _CACHE
    current_time = datetime.utcnow().timestamp()
    if _CACHE["providers"] and (current_time - _CACHE["providers_time"] < 300):
        return _CACHE["providers"]

    providers = db.collection('api_providers').where('is_active', '==', True).get()
    prov_list = [p.to_dict() for p in providers]
    _CACHE["providers"] = prov_list
    _CACHE["providers_time"] = current_time
    return prov_list

def get_service_emoji(service_name):
    srv = service_name.lower()
    if "telegram" in srv: return "✈️"
    elif "facebook" in srv or "fb" in srv: return "🌐"
    elif "whatsapp" in srv or "wa" in srv: return "💬"
    elif "imo" in srv: return "📞"
    elif "google" in srv or "gmail" in srv: return "📧"
    elif "tiktok" in srv: return "🎵"
    elif "instagram" in srv or "ig" in srv: return "📸"
    elif "twitter" in srv or "x" in srv: return "🐦"
    else: return "🎯"

def get_main_menu(user_id):
    keyboard = "🎭 Number নিন", "💸 Balance"], ["💰 Withdraw", "🎁 My Referrals"], ["🧐 Support"
    if user_id == ADMIN_ID: keyboard.append(["👑 Admin Panel"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_menu():
    config = get_bot_settings()
    fake_status = "ON 🟢" if config.get('fake_otp_enabled', False) else "OFF 🔴"
    keyboard = [
        ["💸 ওটিপি রেট", "⚙️ মিনিমাম উইথড্র"],
        ["👥 All User List", "📨 Withdraw Request"],
        ["⚙️ Add Service", "🗑️ Remove Service"],
        ["⚙️ Add Country", "🗑️ Remove Country"],
        ["🔌 Manage APIs", "👤 User Information"],
        ["📊 Top 10 OTP (24h)", f"📢 Fake OTP: {fake_status}"],
        ["🎁 Refer Commission", "📊 Excel Numbers"],
        ["📢 ব্রডকাস্ট", "🔙 মেইন মেনু"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_inline_cancel():
    return InlineKeyboardMarkup(InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action"))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "None"
    first_name = update.effective_user.first_name or "Unknown"
    args = context.args
    referrer = None
    
    if args and args[0].isdigit() and int(args[0]) != user_id:
        referrer = args[0]

    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        user_ref.set({
            'id': user_id, 'name': first_name, 'username': username,
            'balance': 0.0, 'pending_withdraw': 0.0, 'total_income': 0.0, 'total_otp': 0, 
            'referred_by': referrer, 'is_banned': False, 'referrals': []
        })
        if referrer:
            db.collection('users').document(str(referrer)).update({'referrals': firestore.ArrayUnion([str(user_id)])})
    else:
        user_ref.update({'username': username, 'name': first_name})
        if user_doc.to_dict().get('is_banned', False):
            await update.message.reply_text("❌ দুঃখিত, আপনাকে এই বোট থেকে ব্যান করা হয়েছে।")
            return
    
    text = "👋 হ্যালো! নাম্বার ওটিপি বোটে আপনাকে স্বাগতম।\n\nসরাসরি নাম্বার পেতে নিচের 🎭 Number নিন বাটন প্রেস করুন।"
    await update.message.reply_text(text, reply_markup=get_main_menu(user_id))

async def handle_text_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    action = context.user_data.get('adm_action')

    if user_id == ADMIN_ID and action:
        if action == 'set_rate':
            try:
                db.collection('settings').document('config').update({'otp_rate': float(text)})
                _CACHE["settings"] = None 
                await update.message.reply_text(f"✅ ওটিপি রেট সফলভাবে `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'set_min_w':
            try:
                db.collection('settings').document('config').update({'min_withdraw': float(text)})
                _CACHE["settings"] = None
                await update.message.reply_text(f"✅ মিনিমাম উইথড্র `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'set_ref_comm':
            try:
                comm_val = float(text)
                db.collection('settings').document('config').update({'refer_commission': comm_val})
                _CACHE["settings"] = None
                await update.message.reply_text(f"✅ রেফার কমিশন সফলভাবে `{comm_val} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট। সঠিক সংখ্যা লিখুন।")
        elif action == 'add_service':
            try:
                service_name = text.strip()
                service_code = service_name.lower()[:2]
                config = get_bot_settings()
                services_dict = config.get('services', {})
                services_dict[service_name] = service_code
                db.collection('settings').document('config').update({'services': services_dict})
                _CACHE["settings"] = None
                await update.message.reply_text(f"✅ সার্ভিস সফলভাবে যুক্ত হয়েছে: **{service_name}**")
            except: await update.message.reply_text("❌ কোনো ত্রুটি হয়েছে।")
        elif action == 'add_country_input':
            try:
                parts = text.strip().split()
                if len(parts) >= 2:
                    c_code = parts[-1]
                    c_name = " ".join(parts[:-1])
                    srv_target = context.user_data.get('target_add_country_service')
                    premium_flag = get_premium_flag(c_name)
                    
                    config = get_bot_settings()
                    countries_dict = config.get('countries', {})
                    
                    if srv_target not in countries_dict:
                        countries_dict[srv_target] = {}
                        
                    countries_dict[srv_target][c_name] = {"code": c_code.lower(), "flag": premium_flag}
                    db.collection('settings').document('config').update({'countries': countries_dict})
                    _CACHE["settings"] = None
                    await update.message.reply_text(f"✅ {srv_target} সার্ভিসের ভেতরে দেশ সফলভাবে যুক্ত হয়েছে: {premium_flag} {c_name} (Range: {c_code})")
                else:
                    await update.message.reply_text("❌ ফরম্যাট ভুল। উদাহরণ: `Ivory Coast 225079`")
            except Exception as e: await update.message.reply_text(f"❌ ত্রুটি হয়েছে: {str(e)}")
        
        elif action == 'xl_srv_input':
            config = get_bot_settings()
            services = config.get('services', {})
            matched_code = next((v for k, v in services.items() if k.lower() == text.strip().lower()), None)
            if matched_code:
                context.user_data['xl_temp_srv'] = text.strip()
                context.user_data['xl_temp_srv_code'] = matched_code
                context.user_data['adm_action'] = 'xl_cnt_input'
                await update.message.reply_text("🌍 এবার কোন দেশের নাম্বার আপলোড করছেন, সেই দেশের নামটি সঠিকভাবে লিখুন (যেমন: `Ivory Coast`):", reply_markup=get_inline_cancel())
            else:
                await update.message.reply_text("❌ এই নামের কোনো সার্ভিস বোটে যুক্ত নেই। অনুগ্রহ করে সঠিক সার্ভিস লিখুন।")
            return
            
        elif action == 'xl_cnt_input':
            config = get_bot_settings()
            countries = config.get('countries', {})
            srv_name = context.user_data.get('xl_temp_srv')
            srv_countries = countries.get(srv_name, {})
            
            matched_c_data = next((v for k, v in srv_countries.items() if k.lower() == text.strip().lower()), None)
            if matched_c_data:
                context.user_data['xl_temp_cnt'] = text.strip()
                context.user_data['xl_temp_cnt_code'] = matched_c_data['code']
                context.user_data['adm_action'] = 'xl_file_wait'
                await update.message.reply_text("📁 চমৎকার! এবার আপনার কাঙ্খিত **Excel (.xlsx)** ফাইলটি ডকুমেন্ট আকারে এখানে আপলোড করে পাঠান।", reply_markup=get_inline_cancel())
            else:
                await update.message.reply_text("❌ এই সার্ভিসের আন্ডারে এই নামের কোনো দেশ যুক্ত নেই। অনুগ্রহ করে সঠিক দেশের নাম লিখুন।")
            return

        elif action == 'add_api_step1':
            context.user_data['temp_api_name'] = text.strip()
            context.user_data['adm_action'] = 'add_api_step2'
            await update.message.reply_text("🔑 এবার এই প্রোভাইডারের **API KEY / TOKEN** টি পাঠান:", reply_markup=get_inline_cancel())
            return
        elif action == 'add_api_step2':
            context.user_data['temp_api_key'] = text.strip()
            context.user_data['adm_action'] = 'add_api_step3'
            await update.message.reply_text("🌐 এবার এই প্রোভাইডারের **BASE URL** টি পাঠান:\n\n*(যেমন: `https://api.example.com/api`)*", reply_markup=get_inline_cancel())
            return
        elif action == 'add_api_step3':
            base_url = text.strip().rstrip('/')
            api_name = context.user_data.get('temp_api_name')
            api_key = context.user_data.get('temp_api_key')
            prov_id = api_name.lower().replace(" ", "_")
            db.collection('api_providers').document(prov_id).set({
                'id': prov_id, 'name': api_name, 'api_key': api_key, 'base_url': base_url, 'is_active': False
            })
            _CACHE["providers"] = None
            await update.message.reply_text(f"✅ **{api_name}** এপিআই সফলভাবে যুক্ত হয়েছে!")
            
        elif action == 'user_info_search':
            search_query = text.strip().replace("@", "")
            tgt_user = None
            
            if search_query.isdigit():
                doc = db.collection('users').document(search_query).get()
                if doc.exists: tgt_user = doc
                
            if not tgt_user:
                users_by_uname = db.collection('users').where('username', '==', search_query).limit(1).get()
                if users_by_uname: tgt_user = users_by_uname[0]

            if tgt_user:
                ud = tgt_user.to_dict()
                context.user_data['managed_user_id'] = str(ud['id'])
                kbd = [
                    [InlineKeyboardButton("➕ ব্যালেন্স অ্যাড", callback_data="u_action_addbal"), InlineKeyboardButton("➖ ব্যালেন্স কাট", callback_data="u_action_cutbal")],
                    [InlineKeyboardButton("🚫 ব্যান করুন", callback_data="u_action_ban"), InlineKeyboardButton("🔓 আনব্যান করুন", callback_data="u_action_unban")],
                    [InlineKeyboardButton("❌ ক্লোজ", callback_data="cancel_action")]
                ]
                info_text = (
                    f"👤 **ইউজার ইনফরমেশন হিস্ট্রি**\n\n"
                    f"🆔 Telegram ID: `{ud['id']}`\n"
                    f"📛 নাম: {ud.get('name', 'Unknown')}\n"
                    f"🔗 ইউজারনেম: @{ud.get('username', 'None')}\n"
                    f"💰 বর্তমান ব্যালেন্স: {ud.get('balance', 0.0):.2f} BDT\n"
                    f"⏳ পেন্ডিং উইথড্র: {ud.get('pending_withdraw', 0.0):.2f} BDT\n"
                    f"✅ মোট ওটিপি রিসিভ: {ud.get('total_otp', 0)} টি\n"
                    f"🚫 অ্যাকাউন্ট স্ট্যাটাস: {'Banned' if ud.get('is_banned') else 'Active'}"
                )
                await update.message.reply_text(info_text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ এই আইডি বা ইউজারনেম দিয়ে কোনো ইউজার পাওয়া যায়নি।")
        elif action == 'add_bal_amount':
            try:
                tgt_id = context.user_data.get('managed_user_id')
                ref = db.collection('users').document(tgt_id)
                ud_data = ref.get().to_dict()
                current_bal = ud_data.get('balance', 0.0)
                current_inc = ud_data.get('total_income', 0.0)
                ref.update({
                    'balance': current_bal + float(text),
                    'total_income': current_inc + float(text)
                })
                await update.message.reply_text("✅ ব্যালেন্স সফলভাবে যোগ করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'cut_bal_amount':
            try:
                tgt_id = context.user_data.get('managed_user_id')
                ref = db.collection('users').document(tgt_id)
                current_bal = ref.get().to_dict().get('balance', 0.0)
                ref.update({'balance': max(0.0, current_bal - float(text))})
                await update.message.reply_text("✅ ব্যালেন্স সফলভাবে কেটে নেওয়া হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'broadcast':
            users = db.collection('users').limit(100).stream()
            count = 0
            for u in users:
                try: 
                    await context.bot.send_message(chat_id=u.to_dict()['id'], text=f"{text}")
                    count += 1
                except: pass
            await update.message.reply_text(f"✅ ব্রডকাস্ট সফল হয়েছে! মোট {count} জন ইউজারের কাছে নোটিশ পাঠানো হয়েছে।")
            
        context.user_data['adm_action'] = None
        return

    user_action = context.user_data.get('usr_action')
    if user_action == 'w_num_input':
        num_pattern = r'^(?:\+88|88)?(01[3-9]\d{8})$'
        match = re.search(num_pattern, text.strip())
        if not match:
            await update.message.reply_text("❌ ভুল নাম্বার! অনুগ্রহ করে সঠিক বিকাশ/নগদ ১১ ডিজিটের মোবাইল নাম্বারটি পেস্ট করুন বা লিখুন:")
            return
        context.user_data['w_num'] = match.group(1)
        context.user_data['usr_action'] = 'w_amount_input'
        await update.message.reply_text("✍️ কত টাকা উইথড্র করতে চান সেই সংখ্যাটি টাইপ করে পাঠান:", reply_markup=get_inline_cancel())
        return
        
    elif user_action == 'w_amount_input':
        try:
            amount = float(text)
            config = get_bot_settings()
            min_w = config.get('min_withdraw', 110.0)
            user_ref = db.collection('users').document(str(user_id))
            ud = user_ref.get().to_dict()
            
            if amount < min_w:
                await update.message.reply_text(f"❌ আপনার পর্যাপ্ত ব্যালেন্স নেই। মিনিমাম উইথড্র লিমিট: {min_w} BDT")
            elif amount > ud['balance']:
                await update.message.reply_text("❌ আপনার একাউন্টে পর্যাপ্ত ব্যালেন্স নেই।")
            else:
                user_ref.update({
                    'balance': ud['balance'] - amount,
                    'pending_withdraw': ud.get('pending_withdraw', 0.0) + amount
                })
                db.collection('withdraws').add({
                    'user_id': user_id, 'name': ud.get('name', 'User'), 'method': context.user_data.get('w_method'),
                    'number': context.user_data.get('w_num'), 'amount': amount, 'status': 'pending', 'timestamp': datetime.utcnow()
                })
                
                success_submit = (
                    "✅ **আপনার উইথড্র আবেদনটি সফলভাবে জমা হয়েছে!**\n\n"
                    "⚡ আগামী ৫ থেকে ৭ ঘণ্টার ভিতরে আপনার ওয়ালেটে পেমেন্ট পৌঁছে যাবে।\n\n"
                    "✨ আমাদের সাথে থাকার জন্য ধন্যবাদ! ✨"
                )
                await update.message.reply_text(success_submit)
        except: 
            await update.message.reply_text("❌ ভুল অ্যামাউন্ট ইনপুট।")
        context.user_data['usr_action'] = None
        return

    if text == "👑 Admin Panel" and user_id == ADMIN_ID:
        await update.message.reply_text("👑 **অ্যাডমিন কন্ট্রোল প্যানেল**", reply_markup=get_admin_menu())
    elif text == "🔙 মেইন মেনু" and user_id == ADMIN_ID:
        await update.message.reply_text("🔙 আপনি মেইন মেনুতে ফিরে এসেছেন।", reply_markup=get_main_menu(user_id))
    elif text == "💸 ওটিপি রেট" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'set_rate'
        await update.message.reply_text("✍️ নতুন ওটিপি রেট পাঠান:", reply_markup=get_inline_cancel())
    elif text == "⚙️ মিনিমাম উইথড্র" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'set_min_w'
        await update.message.reply_text("✍️ নতুন মিনিমাম উইথড্র লিমিট পাঠান:", reply_markup=get_inline_cancel())
    elif text == "🎁 Refer Commission" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'set_ref_comm'
        config = get_bot_settings()
        curr_comm = config.get('refer_commission', 0.10)
        await update.message.reply_text(f"✍️ বর্তমান রেফার কমিশন: `{curr_comm} BDT`\n\nনতুন রেফার কমিশন অ্যামাউন্ট লিখে পাঠান:", reply_markup=get_inline_cancel())
    elif text == "⚙️ Add Service" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'add_service'
        await update.message.reply_text("✍️ জাস্ট আপনার সার্ভিস এর নামটি লিখে পাঠান。\n\n✍️ যেমন: `Facebook`", reply_markup=get_inline_cancel())
    elif text == "🗑️ Remove Service" and user_id == ADMIN_ID:
        config = get_bot_settings()
        services = config.get('services', {})
        if not services:
            await update.message.reply_text("❌ কোনো সার্ভিস উপলব্ধ নেই।")
            return
        keyboard = [[InlineKeyboardButton(f"🗑️ {s_name}", callback_data=f"rem_srv_{s_name}")] for s_name in services.keys()]
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await update.message.reply_text("🗑️ **কোন সার্ভিসটি রিমুভ করতে চান সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif text == "⚙️ Add Country" and user_id == ADMIN_ID:
        config = get_bot_settings()
        services = config.get('services', {})
        if not services:
            await update.message.reply_text("❌ কোনো সার্ভিস উপলব্ধ নেই! প্রথমে সার্ভিস এড করুন।")
            return
        keyboard = [[InlineKeyboardButton(f"📱 {s_name}", callback_data=f"add_c_srv_{s_name}")] for s_name in services.keys()]
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await update.message.reply_text("👉 **কোন সার্ভিসের আন্ডারে দেশের নাম ও নাম্বার রেঞ্জ এড করতে চান?**", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif text == "🗑️ Remove Country" and user_id == ADMIN_ID:
        config = get_bot_settings()
        countries = config.get('countries', {})
        
        keyboard = []
        has_country = False
        
        for srv_name, srv_countries in countries.items():
            if isinstance(srv_countries, dict):
                for c_name, c_data in srv_countries.items():
                    has_country = True
                    flag = c_data.get('flag', '🏳️')
                    callback_id = f"rc_{srv_name.replace(' ', '__')}_{c_name.replace(' ', '__')}"
                    keyboard.append([InlineKeyboardButton(f"🗑️ [{srv_name}] {flag} {c_name}", callback_data=callback_id)])
        
        if not has_country:
            await update.message.reply_text("❌ ডাটাবেজে রিমুভ করার মতো কোনো দেশ খুঁজে পাওয়া যায়নি।")
            return
            
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await update.message.reply_text("🗑️ **কোন দেশটি রিমুভ করতে চান সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif text == "📢 ব্রডকাস্ট" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'broadcast'
        await update.message.reply_text("✍️ আপনি সকল ইউজারের কাছে যে নোটিশ বা মেসেজটি পাঠাতে চান তা টাইপ করে এখানে পাঠান:", reply_markup=get_inline_cancel())

    elif text.startswith("📢 Fake OTP:") and user_id == ADMIN_ID:
        config = get_bot_settings()
        current_status = config.get('fake_otp_enabled', False)
        new_status = not current_status
        db.collection('settings').document('config').update({'fake_otp_enabled': new_status})
        _CACHE["settings"] = None
        status_text = "চালু 🟢" if new_status else "বন্ধ 🔴"
        await update.message.reply_text(f"📢 ফেক ওটিপি লুপটি সফলভাবে **{status_text}** করা হয়েছে।", reply_markup=get_admin_menu())

    elif text == "🔌 Manage APIs" and user_id == ADMIN_ID:
        providers = db.collection('api_providers').limit(20).stream()
        keyboard = []
        msg_text = "🔌 **API Providers Manager**\n\n"
        has_providers = False
        for p in providers:
            has_providers = True
            pd = p.to_dict()
            status_emoji = "🟢 Active" if pd.get('is_active') else "🔴 Inactive"
            msg_text += f"📛 **{pd['name']}**\n📌 Status: {status_emoji}\n🌐 URL: `{pd['base_url']}`\n\n"
            keyboard.append([
                InlineKeyboardButton(f"⚡ Toggle {pd['name']}", callback_data=f"toggle_api_{pd['id']}"),
                InlineKeyboardButton(f"🗑️ Del", callback_data=f"del_api_{pd['id']}")
            ])
        if not has_providers: msg_text += "❌ কোনো এপিআই প্রোভাইডার যুক্ত করা নেই।"
        keyboard.append([InlineKeyboardButton("➕ Add New API", callback_data="add_new_api")])
        keyboard.append([InlineKeyboardButton("❌ ক্লোজ", callback_data="cancel_action")])
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif text == "📊 Excel Numbers" and user_id == ADMIN_ID:
        available_count = len(db.collection('excel_numbers').where('status', '==', 'available').limit(100).get())
        active_count = len(db.collection('excel_numbers').where('status', '==', 'active').limit(100).get())
        xl_text = (
            f"📊 **Excel Numbers Control Panel**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 বিক্রয়ের জন্য রেডি নাম্বার: {available_count} টি\n"
            f"⏳ ওটিপির জন্য ওয়েটিং নাম্বার: {active_count} টি\n\n"
        )
        kbd = [
            [InlineKeyboardButton("📤 Upload Excel File", callback_data="xl_upload_init")],
            [InlineKeyboardButton("🗑️ Clear Excel Database", callback_data="xl_clear_db")],
            [InlineKeyboardButton("❌ ক্লোজ", callback_data="cancel_action")]
        ]
        await update.message.reply_text(xl_text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif text == "📊 Top 10 OTP (24h)" and user_id == ADMIN_ID:
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        # সফল ওটিপির হিস্ট্রি কালেকশন থেকে ২৪ ঘণ্টার রেকর্ড ফেচ করা হচ্ছে
        history_docs = db.collection('otp_history').where('timestamp', '>=', twenty_four_hours_ago).limit(500).stream()
        user_counts = {}
        for h in history_docs:
            hd = h.to_dict()
            uid = hd.get('user_id')
            user_counts[uid] = user_counts.get(uid, 0) + 1
            
        sorted_users = sorted(user_counts.items(), key=lambda item: item[1], reverse=True)[:10]
        if not sorted_users:
            await update.message.reply_text("📊 গত ২৪ ঘণ্টায় কোনো সফল ওটিপি ট্রানজেকশন হয়নি।")
            return
            
        board_text = "📊 **Top 10 OTP Users (Last 24 Hours):**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for idx, (uid, count) in enumerate(sorted_users, 1):
            u_doc = db.collection('users').document(str(uid)).get()
            u_name = u_doc.to_dict().get('name', 'Unknown') if u_doc.exists else "Unknown User"
            board_text += f"{idx}. 👤 {u_name} | ID: `{uid}` ➔ **{count} টি OTP**\n"
        await update.message.reply_text(board_text, parse_mode="Markdown")

    elif text == "👥 All User List" and user_id == ADMIN_ID:
        users = db.collection('users').limit(50).get()
        if not users:
            await update.message.reply_text("👥 বোটে কোনো রেজিস্টার্ড ইউজার নেই।")
            return
        
        total_users_count = len(db.collection('users').get())
        list_text = f"👥 **মোট ইউজার সংখ্যা:** `{total_users_count}` জন\n━━━━━━━━━━━━━━━━━━━━━━\n"
        
        for idx, u in enumerate(users, 1):
            ud = u.to_dict()
            uid = ud.get('id')
            balance = ud.get('balance', 0.0)
            
            list_text += f"{idx}. ID: `{uid}` | Balance: `{balance:.2f} BDT`\n"
            
            if len(list_text) > 3500:
                await update.message.reply_text(list_text, parse_mode="Markdown")
                list_text = ""
        if list_text: await update.message.reply_text(list_text, parse_mode="Markdown")

    elif text == "👤 User Information" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'user_info_search'
        await update.message.reply_text("🔎 যে ইউজারের তথ্য দেখতে চান তার **Telegram User ID** অথবা **Username** লিখে পাঠান:", reply_markup=get_inline_cancel())
        
    elif text == "📨 Withdraw Request" and user_id == ADMIN_ID:
        reqs = db.collection('withdraws').where('status', '==', 'pending').limit(20).get()
        if not reqs:
            await update.message.reply_text("📥 কোনো পেন্ডিং উইথড্র রিকোয়েস্ট নেই।")
            return
        for r in reqs:
            rd = r.to_dict()
            kbd = [
                [InlineKeyboardButton("✅ Paid", callback_data=f"app_w_{r.id}"),
                 InlineKeyboardButton("❌ Reject (Refund)", callback_data=f"rej_w_{r.id}")]
            ]
            await update.message.reply_text(f"💰 **উইথড্র রিকোয়েস্ট:**\n👤 নাম: {rd.get('name', 'User')}\n🆔 ID: `{rd['user_id']}`\n📱 মেথড: {rd['method'].upper()}\n🔢 নাম্বার: `{rd['number']}`\n💵 পরিমাণ: {rd['amount']} BDT", reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")
            
    elif text == "🎭 Number নিন":
        config = get_bot_settings()
        services = config.get('services', {})
        otp_rate = config.get('otp_rate', 0.70)
        keyboard = []
        for s_name, s_code in services.items():
            s_emoji = get_service_emoji(s_name)
            keyboard.append([InlineKeyboardButton(f"{s_emoji} {s_name}  ➔  ➕ {otp_rate:.2f} BDT", callback_data=f"usr_s_{s_code}")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await update.message.reply_text("⚡ **একটি সার্ভিস সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif text == "💸 Balance":
        user_id = update.effective_user.id
        user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
        
        balance = user_data.get('balance', 0.0)
        pending_w = user_data.get('pending_withdraw', 0.0)
        total_inc = user_data.get('total_income', 0.0)
        total_otp = user_data.get('total_otp', 0)
        
        balance_card = (
            f"💵আপনার ব্যালেন্স\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵ব্যালেন্স: {balance:.2f} BDT\n"
            f"💸পেন্ডিং (উইথড্র): {pending_w:.2f} BDT\n"
            f" 💰Total Income: {total_inc:.2f} BDT\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📞মোট ওটিপি রিসিভ: {total_otp} টি"
        )
        await update.message.reply_text(balance_card)
        
    elif text == "💰 Withdraw":
        user_id = update.effective_user.id
        user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
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
        await update.message.reply_text(f"💳 **টাকা উত্তোলনের মেথড সিলেক্ট করুন (মিনিমাম লিমিট: {min_w} BDT):**", reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "🎁 My Referrals":
        user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
        refs = user_data.get('referrals', [])
        ref_count = len(refs)
        config = get_bot_settings()
        comm_val = config.get('refer_commission', 0.10)
        bot_uname = (await context.bot.get_me()).username
        refer_text = (
            f"🎁 ⚠️ **ধামাকা রেফার অফার! আনলিমিটেড ইনকাম করুন!** ⚠️ 🎁\n\n"
            f"👤 **Total Refer:** {ref_count} জন\n"
            f"😃 **Total Refer Income:** {ref_count * comm_val:.2f} BDT\n\n"
            f"🔗 **আপনার রেফার লিংক (কপি করতে ক্লিক করুন):**\n"
            f"`https://t.me/{bot_uname}?start={user_id}`\n\n"
            f"──────────────────────\n"
            f"🔥 **রেফারের সুবিধা:**\n"
            f"💸 প্রতি সফল ওটিপিতে আপনার রেফারকৃত ইউজারের কাছ থেকে পাবেন লাইফটাইম কমিশন {comm_val} টাকা! এখনই শেয়ার করুন! 🎉"
        )
        await update.message.reply_text(refer_text, parse_mode="Markdown")
    elif text == "🧐 Support":
        support_card = (
            "📞 **গ্রাহক সেবা কেন্দ্র**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "সম্মানিত মেম্বার,\n"
            "আপনার যেকোনো সমস্যা বা জিজ্ঞাসার জন্য আমাদের সাপোর্ট টিমের সাথে যোগাযোগ করুন।\n\n"
            "⚠️ **নোট:** অযথা মেসেজ দেওয়া থেকে বিরত থাকুন। ধন্যবাদ!"
        )
        support_kbd = [
            [InlineKeyboardButton("➡️ 💁‍♂️ অ্যাডমিন সাপোর্ট", url="https://t.me/helptg10")],
            [InlineKeyboardButton("➡️ 📢 অফিসিয়াল চ্যানেল", url="https://t.me/helptg100")]
        ]
        await update.message.reply_text(support_card, reply_markup=InlineKeyboardMarkup(support_kbd), parse_mode="Markdown")

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    action = context.user_data.get('adm_action')
    
    if user_id == ADMIN_ID and action == 'xl_file_wait':
        doc = update.message.document
        if not doc.file_name.endswith('.xlsx'):
            await update.message.reply_text("❌ এটি এক্সেল ফাইল নয়। অনুগ্রহ করে একটি `.xlsx` ফাইল ডকুমেন্ট আকারে আপলোড করুন।")
            return
            
        await update.message.reply_text("⏳ এক্সেল ফাইল থেকে নাম্বারগুলো ডাটাবেজে লোড করা হচ্ছে, দয়া করে অপেক্ষা করুন...")
        
        try:
            tg_file = await context.bot.get_file(doc.file_id)
            file_bytes = await tg_file.download_as_bytearray()
            
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
            sheet = wb.active
            
            srv_name = context.user_data.get('xl_temp_srv')
            srv_code = context.user_data.get('xl_temp_srv_code')
            cnt_name = context.user_data.get('xl_temp_cnt')
            cnt_code = context.user_data.get('xl_temp_cnt_code')
            
            added_count = 0
            for row in sheet.iter_rows(min_row=1, max_col=1, values_only=True):
                cell_value = row[0]
                if cell_value:
                    num_str = str(cell_value).strip().replace(" ", "").replace("-", "")
                    if not num_str.startswith("+"):
                        num_str = "+" + num_str
                        
                    doc_ref = db.collection('excel_numbers').document(num_str)
                    if not doc_ref.get().exists:
                        doc_ref.set({
                            'number': num_str,
                            'service_name': srv_name,
                            'service_code': srv_code,
                            'country_name': cnt_name,
                            'country_code': cnt_code,
                            'status': 'available',
                            'timestamp': datetime.utcnow()
                        })
                        added_count += 1
                        
            await update.message.reply_text(f"✅ সফলভাবে **{added_count}** টি নাম্বার এক্সেল থেকে **{srv_name} ({cnt_name})** এ লোড করা হয়েছে।")
        except Exception as e:
            await update.message.reply_text(f"❌ এক্সেল প্রসেস এরর: {str(e)}")
            
        context.user_data['adm_action'] = None

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("rc_"):
        await query.answer()
        parts = data.split("_")
        srv_name = parts[1].replace("__", " ")
        c_name = parts[2].replace("__", " ")
        
        config = get_bot_settings()
        countries = config.get('countries', {})
        
        if srv_name in countries and c_name in countries[srv_name]:
            del countries[srv_name][c_name]
            if not countries[srv_name]:
                del countries[srv_name]
                
            db.collection('settings').document('config').update({'countries': countries})
            _CACHE["settings"] = None
            await query.edit_message_text(f"✅ **{srv_name}** সার্ভিস থেকে **{c_name}** দেশটি সফলভাবে রিমুভ করা হয়েছে।")
        else:
            await query.edit_message_text("❌ দেশটি পাওয়া যায়নি বা ইতিমধ্যে রিমুভ হয়েছে।")
        return

    if data == "xl_upload_init":
        await query.answer()
        context.user_data['adm_action'] = 'xl_srv_input'
        await query.edit_message_text("📝 প্রথমে যে সার্ভিসের জন্য নাম্বার আপলোড করতে চান তার নাম লিখুন (যেমন: `Facebook`):", reply_markup=get_inline_cancel())
    elif data == "xl_clear_db":
        await query.answer()
        docs = db.collection('excel_numbers').limit(100).get()
        deleted = 0
        for doc in docs:
            db.collection('excel_numbers').document(doc.id).delete()
            deleted += 1
        await query.edit_message_text(f"🗑️ এক্সেল ডাটাবেজ থেকে মোট **{deleted}** টি নাম্বার রিমুভ করা হয়েছে।")
    elif data.startswith("toggle_api_"):
        await query.answer()
        api_id = data.split("_")[2]
        api_ref = db.collection('api_providers').document(api_id)
        api_doc = api_ref.get()
        if api_doc.exists:
            current_status = api_doc.to_dict().get('is_active', False)
            api_ref.update({'is_active': not current_status})
            _CACHE["providers"] = None
        await query.edit_message_text("✅ এপিআই প্রোভাইডারের সক্রিয়তা স্ট্যাটাস পরিবর্তিত হয়েছে।")
    elif data.startswith("del_api_"):
        await query.answer()
        api_id = data.split("_")[2]
        db.collection('api_providers').document(api_id).delete()
        _CACHE["providers"] = None
        await query.edit_message_text("🗑️ এপিআই প্রোভাইডার সফলভাবে রিমুভ করা হয়েছে।")
    elif data == "add_new_api":
        await query.answer()
        context.user_data['adm_action'] = 'add_api_step1'
        await query.edit_message_text("✍️ নতুন প্রোভাইডারের একটি **সুন্দর নাম** টাইপ করে পাঠান:", reply_markup=get_inline_cancel())
    elif data.startswith("rem_srv_"):
        await query.answer()
        s_name = data.split("_")[2]
        config = get_bot_settings()
        services = config.get('services', {})
        if s_name in services:
            del services[s_name]
            db.collection('settings').document('config').update({'services': services})
            _CACHE["settings"] = None
            await query.edit_message_text(f"✅ **{s_name}** সার্ভিসটি সফলভাবে রিমুভ করা হয়েছে।")
    elif data.startswith("add_c_srv_"):
        await query.answer()
        srv_name = data.split("_")[3]
        context.user_data['target_add_country_service'] = srv_name
        context.user_data['adm_action'] = 'add_country_input'
        await query.edit_message_text(f"✍️ **{srv_name}** সার্ভিসের জন্য দেশের নাম ও প্রোভাইডার রেঞ্জ কোড স্পেস দিয়ে পাঠান。\n\n✍️ উদাহরণ: `Ivory Coast 225079`", reply_markup=get_inline_cancel())
    elif data.startswith("usr_s_"):
        await query.answer()
        s_code = data.split("_")[2]
        context.user_data['selected_service_code'] = s_code
        config = get_bot_settings()
        countries = config.get('countries', {})
        s_name = next((k for k, v in config['services'].items() if v == s_code), "Service")
        
        srv_countries = countries.get(s_name, {})
        
        keyboard = []
        row = []
        for c_name, c_data in srv_countries.items():
            btn = InlineKeyboardButton(f"{c_data['flag']} {c_name}", callback_data=f"usr_c_{c_data['code']}_{c_name.replace(' ', '__')}")
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
            
        keyboard.append([InlineKeyboardButton("⬅️ সার্ভিস তালিকায় ফিরে যান", callback_data="back_to_services")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await query.edit_message_text(f"🌍 **{s_name}-এর জন্য দেশ সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "back_to_services":
        await query.answer()
        config = get_bot_settings()
        services = config.get('services', {})
        otp_rate = config.get('otp_rate', 0.70)
        keyboard = [[InlineKeyboardButton(f"{get_service_emoji(s_name)} {s_name}  ➔  ➕ {otp_rate:.2f} BDT", callback_data=f"usr_s_{s_code}")] for s_name, s_code in services.items()]
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await query.edit_message_text(f"⚡ **একটি সার্ভিস সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data.startswith("usr_c_") or data.startswith("change_num_"):
        await query.answer()
        parts = data.split("_")
        c_code = parts[2]
        c_name = parts[3].replace("__", " ") if len(parts) > 3 else "Country"
        s_code = context.user_data.get('selected_service_code')
        user_id = query.from_user.id
        await query.edit_message_text("⚡ ব্যাকগ্রাউন্ডে আপনার নাম্বার খোঁজা হচ্ছে...")
        
        config = get_bot_settings()
        s_name = next((k for k, v in config['services'].items() if v == s_code), "Service")
        premium_flag = get_premium_flag(c_name)
        
        number = None
        source_type = 'excel'
        provider_id_used = 'excel'
        
        xl_num_query = db.collection('excel_numbers').where('service_code', '==', s_code).where('country_code', '==', c_code).where('status', '==', 'available').limit(1).get()
        
        if xl_num_query:
            xl_doc = xl_num_query[0]
            number = xl_doc.id
            db.collection('excel_numbers').document(number).update({'status': 'active', 'user_id': user_id, 'timestamp': datetime.utcnow()})
        else:
            active_apis = get_active_providers()
            for active_api in active_apis:
                try:
                    api_res = requests.post(f"{active_api['base_url']}/getnum", headers={"mauthapi": active_api['api_key']}, json={"rid": c_code}, timeout=5).json()
                    if api_res.get('meta', {}).get('code') == 200:
                        number = api_res['data']['full_number']
                        source_type = 'api'
                        provider_id_used = active_api['id']
                        break
                except: continue
                
        if number:
            db.collection('orders').document(str(number)).set({
                'user_id': user_id, 'status': 'active', 'country_name': c_name, 'service_name': s_name, 'source': source_type, 'provider_id': provider_id_used, 'timestamp': datetime.utcnow()
            })
            
            num_box = (
                f"{premium_flag} <b>{c_name} Allocated</b> ✅\n\n"
                f"🔄 <b>Waiting for OTP...</b>"
            )
            
            action_buttons = [
                [InlineKeyboardButton(text=f" {number}", copy_text={"text": str(number)})],
                [InlineKeyboardButton(text=f" {number}", copy_text={"text": str(number)})],
                [InlineKeyboardButton(text=f" {number}", copy_text={"text": str(number)})],
                [
                    InlineKeyboardButton("✈️ ওটিপি গ্রুপ", url=OTP_GROUP_URL), 
                    InlineKeyboardButton("🔄 নাম্বার পরিবর্তন", callback_data=f"change_num_{c_code}_{c_name.replace(' ', '__')}")
                ],
                [
                    InlineKeyboardButton("🚫 বাতিল করুন", callback_data="cancel_action")
                ]
            ]
            
            await query.edit_message_text(text=num_box, reply_markup=InlineKeyboardMarkup(action_buttons), parse_mode="HTML")
            
        else:
            await query.edit_message_text("❌ বর্তমানে কোনো নাম্বার খালি নেই।", reply_markup=get_inline_cancel())
    
    elif data.startswith("w_method_"):
        await query.answer()
        context.user_data['w_method'] = data.split("_")[2]
        context.user_data['usr_action'] = 'w_num_input'
        await query.edit_message_text(f"✍️ আপনার {data.split('_')[2].upper()} নাম্বারটি টাইপ করে পাঠান:", reply_markup=get_inline_cancel())
        
    elif data.startswith("app_w_"):
        await query.answer()
        w_id = data.split("_")[2]
        w_ref = db.collection('withdraws').document(w_id)
        wd_data = w_ref.get().to_dict()
        
        w_ref.update({'status': 'approved'})
        
        user_ref = db.collection('users').document(str(wd_data['user_id']))
        ud_current = user_ref.get().to_dict()
        current_pend = ud_current.get('pending_withdraw', 0.0)
        user_ref.update({'pending_withdraw': max(0.0, current_pend - wd_data['amount'])})
        
        await query.edit_message_text("✅ উইথড্র রিকোয়েস্ট সফলভাবে অ্যাপ্রুভ (Paid) করা হয়েছে।")
        
        paid_sms = (
            f"🎉 **আপনার একাউন্টের টাকার এড করা হয়েছে !** 🎉\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💵 পরিমাণ: {wd_data['amount']:.2f} BDT\n"
            f"📱 পেমেন্ট মেথড: {wd_data['method'].upper()}\n"
            f"🔢 অ্যাকাউন্ট নাম্বার: {wd_data['number']}\n\n"
            f"✨ আমাদের সাথে থাকার জন্য ধন্যবাদ! ✨"
        )
        try: await context.bot.send_message(chat_id=wd_data['user_id'], text=paid_sms)
        except: pass
        
    elif data.startswith("rej_w_"):
        await query.answer()
        w_id = data.split("_")[2]
        w_ref = db.collection('withdraws').document(w_id)
        wd_data = w_ref.get().to_dict()
        
        w_ref.update({'status': 'rejected'})
        user_ref = db.collection('users').document(str(wd_data['user_id']))
        ud_current = user_ref.get().to_dict()
        current_bal = ud_current.get('balance', 0.0)
        current_pend = ud_current.get('pending_withdraw', 0.0)
        
        user_ref.update({
            'balance': current_bal + wd_data['amount'],
            'pending_withdraw': max(0.0, current_pend - wd_data['amount'])
        })
        
        await query.edit_message_text("❌ উইথড্র রিকোয়েস্ট রিজেক্ট করা হয়েছে এবং ব্যালেন্স রিফান্ড করা হয়েছে।")
        try: await context.bot.send_message(chat_id=wd_data['user_id'], text=f"❌ আপনার {wd_data['amount']:.2f} BDT এর উইথড্র রিকোয়েস্টটি বাতিল করা হয়েছে এবং ব্যালেন্স ফেরত দেওয়া হয়েছে।")
        except: pass
        
    elif data.startswith("u_action_"):
        await query.answer()
        act = data.split("_")[2]
        if act == 'addbal':
            context.user_data['adm_action'] = 'add_bal_amount'
            await query.message.reply_text("✍️ কত ব্যালেন্স অ্যাড করতে চান সেই সংখ্যাটি পাঠান:", reply_markup=get_inline_cancel())
        elif act == 'cutbal':
            context.user_data['adm_action'] = 'cut_bal_amount'
            await query.message.reply_text("✍️ কত ব্যালেন্স কাটতে চান সেই সংখ্যাটি পাঠান:", reply_markup=get_inline_cancel())
        elif act == 'ban':
            db.collection('users').document(context.user_data.get('managed_user_id')).update({'is_banned': True})
            await query.edit_message_text("✅ ইউজারকে সফলভাবে ব্যান করা হয়েছে।")
        elif act == 'unban':
            db.collection('users').document(context.user_data.get('managed_user_id')).update({'is_banned': False})
            await query.edit_message_text("✅ ইউজারকে সফলভাবে আনব্যান করা হয়েছে।")
    elif data == "cancel_action":
        await query.answer()
        context.user_data['adm_action'] = None
        context.user_data['usr_action'] = None
        await query.edit_message_text("❌ **অনুরোধ বাতিল করা হয়েছে।**\nমূল মেনুতে ফিরে আসা হয়েছে।")

REALTIME_ACTIVE_ORDERS = {}

def on_orders_snapshot(col_snapshot, changes, read_time):
    global REALTIME_ACTIVE_ORDERS
    for doc in col_snapshot:
        REALTIME_ACTIVE_ORDERS[doc.id] = doc.to_dict()
    current_doc_ids = {doc.id for doc in col_snapshot}
    for doc_id in list(REALTIME_ACTIVE_ORDERS.keys()):
        if doc_id not in current_doc_ids:
            del REALTIME_ACTIVE_ORDERS[doc_id]

def setup_firestore_listener():
    try:
        db.collection('orders').where('status', '==', 'active').on_snapshot(on_orders_snapshot)
    except Exception as e:
        print(f"Snapshot listener error: {e}")

async def check_otp_and_forward(context: ContextTypes.DEFAULT_TYPE):
    global REALTIME_ACTIVE_ORDERS
    if not REALTIME_ACTIVE_ORDERS:
        return  

    active_apis = get_active_providers()
    if not active_apis: 
        return
    
    for active_api in active_apis:
        url = f"{active_api['base_url']}/success-otp"
        try:
            res = requests.get(url, headers={"mauthapi": active_api['api_key']}, timeout=5)
            if res.status_code != 200:
                continue
            data = res.json()
            if data.get('meta', {}).get('code') == 200 and data['data']['otps']:
                config = get_bot_settings()
                otp_rate = config.get('otp_rate', 0.70)
                ref_comm = config.get('refer_commission', 0.10)
                bot_username = (await context.bot.get_me()).username
                
                for latest_otp in data['data']['otps']:
                    number = str(latest_otp['number'])
                    if not number.startswith("+"): number = "+" + number
                    
                    if number not in REALTIME_ACTIVE_ORDERS:
                        continue  

                    order_data = REALTIME_ACTIVE_ORDERS[number]
                    if order_data.get('source') == 'api' and order_data.get('provider_id') != active_api['id']:
                        continue
                        
                    otp_id = f"proc_{number}_{latest_otp.get('id', hash(latest_otp.get('message', '')))}"
                    
                    if db.collection('processed_otps').document(otp_id).get().exists: 
                        continue    
                    
                    user_id = order_data['user_id']
                    service_name = order_data.get('service_name', 'Facebook')
                    country_name = order_data.get('country_name', 'Ivory Coast')
                    clean_otp = "".join(re.findall(r'\d+', str(latest_otp['message'])))
                    
                    user_ref = db.collection('users').document(str(user_id))
                    user_data = user_ref.get().to_dict() or {}
                    
                    cur_bal = user_data.get('balance', 0.0) + otp_rate
                    cur_inc = user_data.get('total_income', 0.0) + otp_rate
                    
                    user_ref.update({
                        'balance': cur_bal, 
                        'total_income': cur_inc,
                        'total_otp': user_data.get('total_otp', 0) + 1
                    })

                    db.collection('processed_otps').document(otp_id).set({'timestamp': datetime.utcnow()})
                    
                    # ওটিপি সফলভাবে আসার পর ২৪ ঘণ্টার হিস্ট্রির জন্য একটি রেকর্ড সেভ রাখা হচ্ছে
                    db.collection('otp_history').add({
                        'user_id': user_id,
                        'number': number,
                        'service_name': service_name,
                        'timestamp': datetime.utcnow()
                    })
                    
                    referrer_id = user_data.get('referred_by')
                    if referrer_id:
                        ref_user_ref = db.collection('users').document(str(referrer_id))
                        if ref_user_ref.get().exists:
                            ref_ud = ref_user_ref.get().to_dict()
                            ref_user_ref.update({
                                'balance': ref_ud.get('balance', 0.0) + ref_comm,
                                'total_income': ref_ud.get('total_income', 0.0) + ref_comm
                            })

                    masked_number = "XXXXX" + number[-5:] if len(number) > 5 else number
                    balance_part = f"💰 Balance: {cur_bal:.2f} BDT"
                    add_part = f"+{otp_rate:.2f} BDT"
                    space_count = max(1, 45 - (len(balance_part) + len(add_part)))
                    spaced_line = f"{balance_part}{' ' * space_count}{add_part}"

                    success_msg = (
                        f"✨ **Now OTP**\n"
                        f"🔹 ━━━━━━━━━━━━━━━━━━━━ 🔹\n"
                        f"📱 Number: {masked_number}\n"
                        f"🌍 Country: {country_name}\n"
                        f"🎯 Service: {service_name}\n"
                        f"👤 User: {user_data.get('name', 'User')}\n"
                        f"{spaced_line}\n\n"
                        f" Otp Code : `{clean_otp}`\n\n"
                        f"🔹 ━━━━━━━━━━━━━━━━━━━━ 🔹\n"
                        f"🎁 প্রতি ওটিপিতে ফ্রিতে ০.১০ পয়সা বোনাস পেতে এখনই বন্ধুদের রেফার করুন! 🚀"
                    )
                    
                    group_buttons = [
                        InlineKeyboardButton("🚀 Get Number", url=f"https://t.me/{bot_username}?start=true"), 
                        InlineKeyboardButton("📢 Main Channel", url=MAIN_CHANNEL_URL)
                    ]
                    
                    try:
                        await context.bot.send_message(chat_id=user_id, text=success_msg, parse_mode="Markdown")
                        await context.bot.send_message(chat_id=OTP_GROUP_ID, text=success_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([group_buttons]))
                    except: 
                        pass
                    
                    # আপনার আগের নিয়ম অনুযায়ী মূল অর্ডারটি ডিলিট করে দেওয়া হচ্ছে
                    db.collection('orders').document(number).delete()
                    if order_data.get('source') == 'excel':
                        db.collection('excel_numbers').document(number).delete()
        except: 
            pass

async def auto_cleanup_expired_numbers(context: ContextTypes.DEFAULT_TYPE):
    try:
        ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)
        expired_orders = db.collection('orders').where('status', '==', 'active').where('timestamp', '<=', ten_minutes_ago).limit(50).stream()
        
        for order in expired_orders:
            order_data = order.to_dict()
            number = order.id
            db.collection('orders').document(number).delete()
            
            if order_data.get('source') == 'excel':
                excel_doc_ref = db.collection('excel_numbers').document(number)
                if excel_doc_ref.get().exists:
                    excel_doc_ref.delete()
    except Exception as e:
        print(f"Error in auto_cleanup_expired_numbers: {e}")

async def fake_otp_generator(context: ContextTypes.DEFAULT_TYPE):
    try:
        config = get_bot_settings()
        if config.get('fake_otp_enabled', False):
            fake_names = ["Sabbir", "Rahat", "Emon", "Tanvir", "Noyon", "Alamin", "Sujon", "Mim", "Riya", "Antor", "Ishrat"]
            services_dict = config.get('services', {"Facebook": "fb"})
            services_list = list(services_dict.keys()) if services_dict else ["Facebook"]
            
            countries_dict = config.get('countries', {})
            countries_list = []
            if countries_dict:
                for srv, c_dict in countries_dict.items():
                    if isinstance(c_dict, dict):
                        countries_list.extend(list(c_dict.keys()))
                        
            if not countries_list: 
                countries_list = ["Ivory Coast", "Guinea", "Nigeria", "Bangladesh"]
            
            otp_rate = config.get('otp_rate', 0.70)
            bot_username = (await context.bot.get_me()).username
            
            rand_name = random.choice(fake_names)
            rand_service = random.choice(services_list)
            rand_country = random.choice(countries_list)
            rand_balance = round(random.uniform(10.50, 450.00), 2)
            rand_otp = str(random.randint(10000, 99999))

            fake_num = "+" + "".join([str(random.randint(0, 9)) for _ in range(11)])
            masked_number = "XXXXX" + fake_num[-5:]

            balance_part = f"💰 Balance: {rand_balance:.2f} BDT"
            add_part = f"+{otp_rate:.2f} BDT"
            space_count = max(1, 45 - (len(balance_part) + len(add_part)))
            spaced_line = f"{balance_part}{' ' * space_count}{add_part}"

            fake_msg = (
                f"✨ **Now OTP**\n"
                f"🔹 ━━━━━━━━━━━━━━━━━━━━ 🔹\n"
                f"📱 Number: {masked_number}\n"
                f"🌍 Country: {rand_country}\n"
                f"🎯 Service: {rand_service}\n"
                f"👤 User: {rand_name}\n"
                f"{spaced_line}\n\n"
                f" Otp Code : `{rand_otp}`\n\n"
                f"🔹 ━━━━━━━━━━━━━━━━━━━━ 🔹\n"
                f"🎁 প্রতি ওটিপিতে ফ্রিতে ০.১০ পয়সা বোনাস পেতে এখনই বন্ধুদের রেফার করুন! 🚀"
            )
            group_buttons = [
                InlineKeyboardButton("🚀 Get Number", url=f"https://t.me/{bot_username}?start=true"), 
                InlineKeyboardButton("📢 Main Channel", url=MAIN_CHANNEL_URL)
            ]
            try: 
                await context.bot.send_message(chat_id=OTP_GROUP_ID, text=fake_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([group_buttons]))
            except: 
                pass
    except Exception as e:
        print(f"Fake OTP Error: {e}")
    
    next_delay = random.randint(30, 180)
    context.job_queue.run_once(fake_otp_generator, when=next_delay)

class RenderServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot Engine Core Online")

def run_built_in_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(('0.0.0.0', port), RenderServer).serve_forever()

def main():
    threading.Thread(target=run_built_in_server, daemon=True).start()
    
    setup_firestore_listener()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.job_queue.run_repeating(check_otp_and_forward, interval=10, first=5)
    app.job_queue.run_repeating(auto_cleanup_expired_numbers, interval=60, first=10)
    
    app.job_queue.run_once(fake_otp_generator, when=15)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_upload))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_inputs))
    
    print("Bot Running successfully with on_snapshot & caching...")
    app.run_polling(close_loop=False)

if __name__ == '__main__':
    main()
