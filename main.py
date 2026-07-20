import logging
import os
import json
import asyncio
import sys
import random
import io
import re
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import openpyxl
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

if sys.platform == 'win32':
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
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
OTP_GROUP_ID = "-1003656135640"
OTP_GROUP_URL = "https://t.me/emotp100"       
MAIN_CHANNEL_URL = "https://t.me/helptg100"   

if not firebase_admin._apps:
    firebase_json = json.loads(os.getenv('FIREBASE_JSON'))
    cred = credentials.Certificate(firebase_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ==================== ULTRA ZERO-READ CACHE ====================
_cached_config = None
_config_last_fetch = 0

_cached_providers = None
_providers_last_fetch = 0

_active_orders_memory = {} 
_processed_otps_set = set()

def clear_cache():
    global _cached_config, _cached_providers
    _cached_config = None
    _cached_providers = None

def get_bot_settings():
    global _cached_config, _config_last_fetch
    now = time.time()
    if _cached_config is None or (now - _config_last_fetch) > 600:
        settings_ref = db.collection('settings').document('config').get()
        if settings_ref.exists:
            _cached_config = settings_ref.to_dict()
        else:
            _cached_config = {
                'otp_rate': 0.70, 'min_withdraw': 110.0, 'refer_bonus': 0.10,
                'countries': {}, 'services': {}, 'fake_otp_enabled': False
            }
            db.collection('settings').document('config').set(_cached_config)
        _config_last_fetch = now
    return _cached_config

def get_active_providers():
    global _cached_providers, _providers_last_fetch
    now = time.time()
    if _cached_providers is None or (now - _providers_last_fetch) > 600:
        providers = db.collection('api_providers').where('is_active', '==', True).get()
        _cached_providers = [p.to_dict() for p in providers]
        _providers_last_fetch = now
    return _cached_providers

# ======================================================================

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
    keyboard = [["🎭 Number নিন", "💸 Balance"], ["💰 Withdraw", "🎁 My Referrals"], ["🧐 Support"]]
    if user_id == ADMIN_ID: 
        keyboard.append(["👑 Admin Panel"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_menu():
    config = get_bot_settings()
    fake_status = "ON 🟢" if config.get('fake_otp_enabled', False) else "OFF 🔴"
    keyboard = [
        ["💸 ওটিপি রেট", "⚙️ মিনিমাম উইথড্র", "🎁 রেফার বোনাস"],
        ["👥 All User List", "📨 Withdraw Request"],
        ["⚙️ Add Service", "🗑️ Remove Service"],
        ["⚙️ Add Country", "🗑️ Remove Country"],
        ["🔌 Manage APIs", "👤 User Information"],
        ["📊 Top 10 OTP (24h)", f"📢 Fake OTP: {fake_status}"],
        ["📊 Excel Numbers", "📢 ব্রডকাস্ট"],
        ["🔙 মেইন মেনু"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_inline_cancel():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "None"
    first_name = update.effective_user.first_name or "Unknown"
    args = context.args
    referrer = args[0] if args and args[0].isdigit() and int(args[0]) != user_id else None

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
                clear_cache()
                await update.message.reply_text(f"✅ ওটিপি রেট সফলভাবে `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'set_min_w':
            try:
                db.collection('settings').document('config').update({'min_withdraw': float(text)})
                clear_cache()
                await update.message.reply_text(f"✅ মিনিমাম উইথড্র `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'set_ref_bonus':
            try:
                db.collection('settings').document('config').update({'refer_bonus': float(text)})
                clear_cache()
                await update.message.reply_text(f"✅ রেফার বোনাস সফলভাবে `{text} BDT` সেট করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'add_service':
            try:
                service_name = text.strip()
                service_code = service_name.lower()[:2]
                config = get_bot_settings()
                services_dict = config.get('services', {})
                services_dict[service_name] = service_code
                db.collection('settings').document('config').update({'services': services_dict})
                clear_cache()
                await update.message.reply_text(f"✅ সার্ভিস সফলভাবে যুক্ত হয়েছে: **{service_name}**")
            except: await update.message.reply_text("❌ কোনো ত্রুটি হয়েছে।")
        elif action == 'remove_service':
            try:
                s_name = text.strip()
                config = get_bot_settings()
                services_dict = config.get('services', {})
                if s_name in services_dict:
                    del services_dict[s_name]
                    db.collection('settings').document('config').update({'services': services_dict})
                    clear_cache()
                    await update.message.reply_text(f"✅ **{s_name}** সার্ভিসটি মুছে ফেলা হয়েছে।")
                else:
                    await update.message.reply_text("❌ সার্ভিসটি পাওয়া যায়নি।")
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
                    if srv_target not in countries_dict: countries_dict[srv_target] = {}
                        
                    countries_dict[srv_target][c_name] = {"code": c_code.lower(), "flag": premium_flag}
                    db.collection('settings').document('config').update({'countries': countries_dict})
                    clear_cache()
                    await update.message.reply_text(f"✅ {srv_target} সার্ভিসের ভেতরে দেশ যুক্ত হয়েছে: {premium_flag} {c_name} (Code: {c_code})")
                else:
                    await update.message.reply_text("❌ ফরম্যাট ভুল। উদাহরণ: `Ivory Coast 225079`")
            except Exception as e: await update.message.reply_text(f"❌ ত্রুটি হয়েছে: {str(e)}")
        elif action == 'remove_country_input':
            try:
                c_name = text.strip()
                srv_target = context.user_data.get('target_rem_country_service')
                config = get_bot_settings()
                countries_dict = config.get('countries', {})
                if srv_target in countries_dict and c_name in countries_dict[srv_target]:
                    del countries_dict[srv_target][c_name]
                    db.collection('settings').document('config').update({'countries': countries_dict})
                    clear_cache()
                    await update.message.reply_text(f"✅ {srv_target} থেকে **{c_name}** মুছে ফেলা হয়েছে।")
                else:
                    await update.message.reply_text("❌ পাওয়া যায়নি।")
            except: await update.message.reply_text("❌ কোনো ত্রুটি হয়েছে।")
        elif action == 'user_info':
            try:
                u_id = text.strip()
                udoc = db.collection('users').document(u_id).get()
                if udoc.exists:
                    ud = udoc.to_dict()
                    info = (
                        f"👤 **ইউজার ইনফরমেশন**\n\n"
                        f"🆔 ID: `{ud.get('id')}`\n"
                        f"🏷️ Name: {ud.get('name')}\n"
                        f"👤 Username: @{ud.get('username')}\n"
                        f"💵 Balance: {ud.get('balance', 0.0):.2f} BDT\n"
                        f"📞 Total OTP: {ud.get('total_otp', 0)} টি\n"
                        f"👥 Referrals: {len(ud.get('referrals', []))} জন"
                    )
                    await update.message.reply_text(info, parse_mode="Markdown")
                else:
                    await update.message.reply_text("❌ এই আইডি-র কোনো ইউজার ডাটাবেজে নেই।")
            except: await update.message.reply_text("❌ ভুল ইউজার আইডি।")
        elif action == 'add_api_provider':
            try:
                parts = text.strip().split()
                if len(parts) == 3:
                    p_name, p_url, p_key = parts[0], parts[1], parts[2]
                    p_id = p_name.lower().replace(" ", "_")
                    db.collection('api_providers').document(p_id).set({
                        'id': p_id, 'name': p_name, 'base_url': p_url, 'api_key': p_key, 'is_active': True
                    })
                    clear_cache()
                    await update.message.reply_text(f"✅ নতুন API প্রোভাইডার যুক্ত হয়েছে: **{p_name}**")
                else:
                    await update.message.reply_text("❌ ফরম্যাট ভুল! দিন: `Name BaseURL APIKey`")
            except: await update.message.reply_text("❌ কোনো ত্রুটি হয়েছে।")
        elif action == 'broadcast':
            users = db.collection('users').stream()
            count = 0
            for u in users:
                try: 
                    await context.bot.send_message(chat_id=u.to_dict()['id'], text=f"{text}")
                    count += 1
                except: pass
            await update.message.reply_text(f"✅ মোট {count} জনের কাছে নোটিশ পাঠানো হয়েছে।")
            
        context.user_data['adm_action'] = None
        return

    user_action = context.user_data.get('usr_action')
    if user_action == 'w_num_input':
        num_pattern = r'^(?:\+88|88)?(01[3-9]\d{8})$'
        match = re.search(num_pattern, text.strip())
        if not match:
            await update.message.reply_text("❌ ভুল নাম্বার! সঠিক ১১ ডিজিটের নাম্বার দিন:")
            return
        context.user_data['w_num'] = match.group(1)
        context.user_data['usr_action'] = 'w_amount_input'
        await update.message.reply_text("✍️ এবার কত টাকা উইথড্র করতে চান টাইপ করুন:", reply_markup=get_inline_cancel())
        return
        
    elif user_action == 'w_amount_input':
        try:
            amount = float(text)
            config = get_bot_settings()
            min_w = config.get('min_withdraw', 110.0)
            user_ref = db.collection('users').document(str(user_id))
            ud = user_ref.get().to_dict()
            
            if amount < min_w:
                await update.message.reply_text(f"❌ মিনিমাম উইথড্র লিমিট: {min_w} BDT")
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
                await update.message.reply_text("✅ আপনার উইথড্র আবেদনটি জমা হয়েছে!")
        except: 
            await update.message.reply_text("❌ ভুল ইনপুট।")
        context.user_data['usr_action'] = None
        return

    # Admin Menu Commands
    if text == "👑 Admin Panel" and user_id == ADMIN_ID:
        await update.message.reply_text("👑 **অ্যাডমিন কন্ট্রোল প্যানেল**", reply_markup=get_admin_menu())
    elif text == "🔙 মেইন মেনু" and user_id == ADMIN_ID:
        await update.message.reply_text("🔙 মেইন মেনু:", reply_markup=get_main_menu(user_id))
    elif text == "💸 ওটিপি রেট" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'set_rate'
        await update.message.reply_text("✍️ নতুন ওটিপি রেট পাঠান:", reply_markup=get_inline_cancel())
    elif text == "⚙️ মিনিমাম উইথড্র" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'set_min_w'
        await update.message.reply_text("✍️ নতুন মিনিমাম উইথড্র লিমিট পাঠান:", reply_markup=get_inline_cancel())
    elif text == "🎁 রেফার বোনাস" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'set_ref_bonus'
        await update.message.reply_text("✍️ নতুন রেফার বোনাস এর পরিমাণ পাঠান (যেমন: 0.10):", reply_markup=get_inline_cancel())
    elif text == "⚙️ Add Service" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'add_service'
        await update.message.reply_text("✍️ সার্ভিস এর নামটি লিখে পাঠান (যেমন: `Facebook`):", reply_markup=get_inline_cancel())
    elif text == "🗑️ Remove Service" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'remove_service'
        await update.message.reply_text("✍️ যে সার্ভিসটি মুছে ফেলতে চান তার নাম টাইপ করুন:", reply_markup=get_inline_cancel())
    elif text == "⚙️ Add Country" and user_id == ADMIN_ID:
        config = get_bot_settings()
        services = config.get('services', {})
        kbd = [[InlineKeyboardButton(s, callback_data=f"adm_add_c_srv_{s}")] for s in services.keys()]
        kbd.append([InlineKeyboardButton("❌ বাতিল", callback_data="cancel_action")])
        await update.message.reply_text("কোন সার্ভিসের ভেতরে দেশ যোগ করতে চান?", reply_markup=InlineKeyboardMarkup(kbd))
    elif text == "🗑️ Remove Country" and user_id == ADMIN_ID:
        config = get_bot_settings()
        services = config.get('services', {})
        kbd = [[InlineKeyboardButton(s, callback_data=f"adm_rem_c_srv_{s}")] for s in services.keys()]
        kbd.append([InlineKeyboardButton("❌ বাতিল", callback_data="cancel_action")])
        await update.message.reply_text("কোন সার্ভিসের ভেতরের দেশ মুছতে চান?", reply_markup=InlineKeyboardMarkup(kbd))
    elif text == "👤 User Information" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'user_info'
        await update.message.reply_text("✍️ ইউজারের টেলিগ্রাম ID দিন:", reply_markup=get_inline_cancel())
    elif text == "🔌 Manage APIs" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'add_api_provider'
        await update.message.reply_text("✍️ API যোগ করতে এই ফরম্যাটে পাঠান:\n`Name BaseURL APIKey`", reply_markup=get_inline_cancel())
    elif text == "👥 All User List" and user_id == ADMIN_ID:
        users = db.collection('users').stream()
        total_users = sum(1 for _ in users)
        await update.message.reply_text(f"👥 **মোট রেজিষ্টার্ড ইউজার:** {total_users} জন")
    elif text == "📨 Withdraw Request" and user_id == ADMIN_ID:
        reqs = db.collection('withdraws').where('status', '==', 'pending').get()
        if not reqs:
            await update.message.reply_text("✅ কোনো পেন্ডিং উইথড্র রিকোয়েস্ট নেই।")
            return
        for r in reqs:
            data = r.to_dict()
            msg = (
                f"📨 **উইথড্র রিকোয়েস্ট**\n"
                f"👤 Name: {data.get('name')}\n"
                f"🆔 User ID: `{data.get('user_id')}`\n"
                f"📱 Method: {data.get('method')}\n"
                f"📞 Number: `{data.get('number')}`\n"
                f"💵 Amount: {data.get('amount')} BDT"
            )
            kbd = [
                [InlineKeyboardButton("✅ Approve", callback_data=f"w_app_{r.id}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"w_rej_{r.id}")]
            ]
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kbd))
    elif text == "📊 Top 10 OTP (24h)" and user_id == ADMIN_ID:
        users = db.collection('users').order_by('total_otp', direction=firestore.Query.DESCENDING).limit(10).get()
        top_text = "📊 **Top 10 OTP Generators:**\n\n"
        for idx, u in enumerate(users, 1):
            ud = u.to_dict()
            top_text += f"{idx}. {ud.get('name')} - {ud.get('total_otp', 0)} টি OTP\n"
        await update.message.reply_text(top_text)
    elif text == "📊 Excel Numbers" and user_id == ADMIN_ID:
        xls = db.collection('excel_numbers').get()
        avail = sum(1 for x in xls if x.to_dict().get('status') == 'available')
        await update.message.reply_text(f"📊 **Excel Numbers:**\n\nমোট এভেইলএবল নাম্বার: {avail} টি")
    elif text.startswith("📢 Fake OTP:") and user_id == ADMIN_ID:
        config = get_bot_settings()
        curr = config.get('fake_otp_enabled', False)
        db.collection('settings').document('config').update({'fake_otp_enabled': not curr})
        clear_cache()
        await update.message.reply_text(f"📢 ফেক ওটিপি এখন: {'বন্ধ 🔴' if curr else 'চালু 🟢'}", reply_markup=get_admin_menu())
    elif text == "📢 ব্রডকাস্ট" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'broadcast'
        await update.message.reply_text("✍️ যে নোটিশটি সকল ইউজারকে পাঠাতে চান তা লিখে পাঠান:", reply_markup=get_inline_cancel())

    # User Buttons
    elif text == "🎭 Number নিন":
        config = get_bot_settings()
        services = config.get('services', {})
        otp_rate = config.get('otp_rate', 0.70)
        keyboard = []
        for s_name, s_code in services.items():
            s_emoji = get_service_emoji(s_name)
            keyboard.append([InlineKeyboardButton(f"{s_emoji} {s_name}  ➔  ➕ {otp_rate:.2f} BDT", callback_data=f"usr_s_{s_code}")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await update.message.reply_text("⚡ **সার্ভিস সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif text == "💸 Balance":
        user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
        balance_card = (
            f"💵 **আপনার ব্যালেন্স**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 ব্যালেন্স: {user_data.get('balance', 0.0):.2f} BDT\n"
            f"💸 পেন্ডিং: {user_data.get('pending_withdraw', 0.0):.2f} BDT\n"
            f"💰 Total Income: {user_data.get('total_income', 0.0):.2f} BDT\n"
            f"📞 মোট ওটিপি: {user_data.get('total_otp', 0)} টি"
        )
        await update.message.reply_text(balance_card, parse_mode="Markdown")
        
    elif text == "💰 Withdraw":
        user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
        config = get_bot_settings()
        min_w = config.get('min_withdraw', 110.0)
        if user_data.get('balance', 0.0) < min_w:
            await update.message.reply_text(f"❌ পর্যাপ্ত ব্যালেন্স নেই। মিনিমাম: {min_w} BDT")
            return
        keyboard = [
            [InlineKeyboardButton("📱 বিকাশ (Bkash)", callback_data="w_method_bkash")],
            [InlineKeyboardButton("💸 নগদ (Nagad)", callback_data="w_method_nagad")],
            [InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")]
        ]
        await update.message.reply_text(f"💳 **মেথড সিলেক্ট করুন (মিনিমাম: {min_w} BDT):**", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "🎁 My Referrals":
        user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
        refs = user_data.get('referrals', [])
        bot_uname = (await context.bot.get_me()).username
        refer_text = (
            f"🎁 **রেফার এরিয়া**\n\n"
            f"👤 Total Refer: {len(refs)} জন\n"
            f"🔗 রেফার লিংক:\n"
            f"https://t.me/{bot_uname}?start={user_id}"
        )
        await update.message.reply_text(refer_text)

    elif text == "🧐 Support":
        support_card = "📞 **গ্রাহক সেবা কেন্দ্র**\n\nযেকোনো সমস্যায় সাপোর্ট টিমে যোগাযোগ করুন।"
        support_kbd = [
            [InlineKeyboardButton("➡️ অ্যাডমিন সাপোর্ট", url="https://t.me/helptg10")],
            [InlineKeyboardButton("➡️ অফিসিয়াল চ্যানেল", url="https://t.me/helptg100")]
        ]
        await update.message.reply_text(support_card, reply_markup=InlineKeyboardMarkup(support_kbd), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("w_app_"):
        await query.answer()
        doc_id = data.replace("w_app_", "")
        w_doc = db.collection('withdraws').document(doc_id).get()
        if w_doc.exists:
            wd = w_doc.to_dict()
            db.collection('withdraws').document(doc_id).update({'status': 'approved'})
            u_ref = db.collection('users').document(str(wd['user_id']))
            u_data = u_ref.get().to_dict() or {}
            u_ref.update({'pending_withdraw': max(0.0, u_data.get('pending_withdraw', 0.0) - wd['amount'])})
            try: await context.bot.send_message(chat_id=wd['user_id'], text=f"✅ আপনার {wd['amount']} BDT উইথড্র এপ্রুভ করা হয়েছে!")
            except: pass
            await query.edit_message_text("✅ Approved!")

    elif data.startswith("w_rej_"):
        await query.answer()
        doc_id = data.replace("w_rej_", "")
        w_doc = db.collection('withdraws').document(doc_id).get()
        if w_doc.exists:
            wd = w_doc.to_dict()
            db.collection('withdraws').document(doc_id).update({'status': 'rejected'})
            u_ref = db.collection('users').document(str(wd['user_id']))
            u_data = u_ref.get().to_dict() or {}
            u_ref.update({
                'balance': u_data.get('balance', 0.0) + wd['amount'],
                'pending_withdraw': max(0.0, u_data.get('pending_withdraw', 0.0) - wd['amount'])
            })
            try: await context.bot.send_message(chat_id=wd['user_id'], text=f"❌ আপনার {wd['amount']} BDT উইথড্র রিজেক্ট করা হয়েছে এবং ব্যালেন্স ফেরত দেওয়া হয়েছে।")
            except: pass
            await query.edit_message_text("❌ Rejected!")

    elif data.startswith("adm_add_c_srv_"):
        await query.answer()
        srv_name = data.replace("adm_add_c_srv_", "")
        context.user_data['adm_action'] = 'add_country_input'
        context.user_data['target_add_country_service'] = srv_name
        await query.edit_message_text(f"✍️ **{srv_name}** এর জন্য দেশের নাম ও কোড দিন:\nউদাহরণ: `Ivory Coast 225079`")

    elif data.startswith("adm_rem_c_srv_"):
        await query.answer()
        srv_name = data.replace("adm_rem_c_srv_", "")
        context.user_data['adm_action'] = 'remove_country_input'
        context.user_data['target_rem_country_service'] = srv_name
        await query.edit_message_text(f"✍️ **{srv_name}** থেকে যে দেশের নাম মুছতে চান তা টাইপ করুন:")

    elif data.startswith("w_method_"):
        await query.answer()
        method = "Bkash" if "bkash" in data else "Nagad"
        context.user_data['w_method'] = method
        context.user_data['usr_action'] = 'w_num_input'
        await query.edit_message_text(f"📱 আপনার **{method}** নাম্বারটি লিখে পাঠান:")

    elif data.startswith("usr_s_"):
        await query.answer()
        s_code = data.split("_")[2]
        context.user_data['selected_service_code'] = s_code
        config = get_bot_settings()
        s_name = next((k for k, v in config['services'].items() if v == s_code), "Service")
        srv_countries = config.get('countries', {}).get(s_name, {})
        
        keyboard = []
        row = []
        for c_name, c_data in srv_countries.items():
            row.append(InlineKeyboardButton(f"{c_data['flag']} {c_name}", callback_data=f"usr_c_{c_data['code']}_{c_name.replace(' ', '__')}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
            
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await query.edit_message_text(f"🌍 **{s_name}-এর জন্য দেশ সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data.startswith("usr_c_") or data.startswith("change_num_"):
        await query.answer()
        parts = data.split("_")
        c_code = parts[2]
        c_name = parts[3].replace("__", " ") if len(parts) > 3 else "Country"
        s_code = context.user_data.get('selected_service_code')
        user_id = query.from_user.id
        await query.edit_message_text("⚡ ব্যাকগ্রাউন্ডে নাম্বার খোঁজা হচ্ছে...")
        
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
            db.collection('excel_numbers').document(number).update({'status': 'active', 'user_id': user_id})
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
            if not str(number).startswith("+"): number = "+" + str(number)
            expire_at = time.time() + 600
            
            _active_orders_memory[number] = {
                'user_id': user_id, 'service_name': s_name, 'country_name': c_name,
                'source': source_type, 'provider_id': provider_id_used, 'expire_at': expire_at
            }
            
            db.collection('orders').document(str(number)).set({
                'user_id': user_id, 'status': 'active', 'country_name': c_name,
                'service_name': s_name, 'source': source_type, 'provider_id': provider_id_used,
                'timestamp': datetime.utcnow()
            })
            
            num_box = (
                f"{premium_flag} <b>{c_name} Allocated</b> ✅\n\n"
                f"🔄 <b>Waiting for OTP...</b>"
            )
            
            action_buttons = [
                [InlineKeyboardButton(text=f"📋 {number}", copy_text={"text": str(number)})],
                [InlineKeyboardButton(text=f"📋 {number}", copy_text={"text": str(number)})],
                [InlineKeyboardButton(text=f"📋 {number}", copy_text={"text": str(number)})],
                [
                    InlineKeyboardButton("✈️ ওটিপি গ্রুপ", url=OTP_GROUP_URL), 
                    InlineKeyboardButton("🔄 নাম্বার পরিবর্তন", callback_data=f"change_num_{c_code}_{c_name.replace(' ', '__')}")
                ],
                [InlineKeyboardButton("🚫 বাতিল করুন", callback_data="cancel_action")]
            ]
            await query.edit_message_text(text=num_box, reply_markup=InlineKeyboardMarkup(action_buttons), parse_mode="HTML")
        else:
            await query.edit_message_text("❌ বর্তমানে কোনো নাম্বার খালি নেই।", reply_markup=get_inline_cancel())
            
    elif data == "cancel_action":
        await query.answer()
        context.user_data['adm_action'] = None
        context.user_data['usr_action'] = None
        await query.edit_message_text("❌ বাতিল করা হয়েছে।")

# ==================== PURE ZERO FIREBASE READ OTP CHECK ====================
async def check_otp_and_forward(context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    expired_nums = [num for num, data in _active_orders_memory.items() if now > data['expire_at']]
    for num in expired_nums:
        del _active_orders_memory[num]

    active_apis = get_active_providers()
    if not active_apis or not _active_orders_memory: return
    
    for active_api in active_apis:
        url = f"{active_api['base_url']}/success-otp"
        try:
            res = requests.get(url, headers={"mauthapi": active_api['api_key']}, timeout=5).json()
            if res.get('meta', {}).get('code') == 200 and res['data']['otps']:
                config = get_bot_settings()
                otp_rate = config.get('otp_rate', 0.70)
                ref_bonus = config.get('refer_bonus', 0.10)
                bot_username = (await context.bot.get_me()).username
                
                for latest_otp in res['data']['otps']:
                    number = str(latest_otp['number'])
                    if not number.startswith("+"): number = "+" + number
                    
                    otp_id = f"{number}_{latest_otp.get('id', hash(latest_otp.get('message', '')))}"
                    
                    if otp_id in _processed_otps_set: continue
                    
                    if number in _active_orders_memory:
                        order_data = _active_orders_memory[number]
                        user_id = order_data['user_id']
                        service_name = order_data['service_name']
                        country_name = order_data['country_name']
                        clean_otp = "".join(re.findall(r'\d+', str(latest_otp['message'])))
                        
                        user_ref = db.collection('users').document(str(user_id))
                        user_doc = user_ref.get()
                        if not user_doc.exists: continue
                        user_data = user_doc.to_dict()
                        
                        cur_bal = user_data.get('balance', 0.0) + otp_rate
                        cur_inc = user_data.get('total_income', 0.0) + otp_rate
                        
                        user_ref.update({
                            'balance': cur_bal, 
                            'total_income': cur_inc,
                            'total_otp': user_data.get('total_otp', 0) + 1
                        })

                        referrer_id = user_data.get('referred_by')
                        if referrer_id:
                            ref_user_ref = db.collection('users').document(str(referrer_id))
                            ref_doc = ref_user_ref.get()
                            if ref_doc.exists:
                                ref_data = ref_doc.to_dict()
                                ref_user_ref.update({
                                    'balance': ref_data.get('balance', 0.0) + ref_bonus,
                                    'total_income': ref_data.get('total_income', 0.0) + ref_bonus
                                })

                        _processed_otps_set.add(otp_id)
                        del _active_orders_memory[number]
                        
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
                            f"🎁 প্রতি ওটিপিতে ফ্রিতে {ref_bonus:.2f} টাকা বোনাস পেতে এখনই বন্ধুদের রেফার করুন! 🚀"
                        )
                        group_buttons = [InlineKeyboardButton("🚀 Get Number", url=f"https://t.me/{bot_username}?start=true"), InlineKeyboardButton("📢 Main Channel", url=MAIN_CHANNEL_URL)]
                        
                        await context.bot.send_message(chat_id=user_id, text=success_msg, parse_mode="Markdown")
                        await context.bot.send_message(chat_id=OTP_GROUP_ID, text=success_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([group_buttons]))
        except: pass

async def fake_otp_generator(context: ContextTypes.DEFAULT_TYPE):
    config = get_bot_settings()
    if not config.get('fake_otp_enabled', False): return

    fake_names = ["Sabbir", "Rahat", "Emon", "Tanvir", "Noyon", "Alamin", "Sujon", "Mim", "Riya"]
    services_dict = config.get('services', {"Facebook": "fb"})
    services_list = list(services_dict.keys()) if services_dict else ["Facebook"]
    
    countries_dict = config.get('countries', {})
    countries_list = []
    if countries_dict:
        for srv, c_dict in countries_dict.items():
            if isinstance(c_dict, dict):
                countries_list.extend(list(c_dict.keys()))
                
    if not countries_list: countries_list = ["Ivory Coast", "Guinea", "Nigeria", "Bangladesh"]
    
    otp_rate = config.get('otp_rate', 0.70)
    ref_bonus = config.get('refer_bonus', 0.10)
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
        f"🎁 প্রতি ওটিপিতে ফ্রিতে {ref_bonus:.2f} টাকা বোনাস পেতে এখনই বন্ধুদের রেফার করুন! 🚀"
    )
    group_buttons = [InlineKeyboardButton("🚀 Get Number", url=f"https://t.me/{bot_username}?start=true"), InlineKeyboardButton("📢 Main Channel", url=MAIN_CHANNEL_URL)]
    try: 
        await context.bot.send_message(chat_id=OTP_GROUP_ID, text=fake_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([group_buttons]))
    except: pass

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
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.job_queue.run_repeating(check_otp_and_forward, interval=10, first=5)
    app.job_queue.run_repeating(fake_otp_generator, interval=600, first=10)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_inputs))
    
    print("Bot Running successfully...")
    app.run_polling(close_loop=False)

if __name__ == '__main__':
    main()
