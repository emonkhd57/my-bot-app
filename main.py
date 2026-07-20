import logging
import os
import json
import asyncio
import sys
import random
import re
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import firebase_admin
from firebase_admin import credentials, firestore
import requests
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
SUPPORT_USERNAME = "helptg100"

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
    if _cached_config is None or (now - _config_last_fetch) > 1800:
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
    if _cached_providers is None or (now - _providers_last_fetch) > 1800:
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
    
    user_ref.set({
        'id': user_id, 'name': first_name, 'username': username,
        'balance': firestore.Increment(0),
        'pending_withdraw': firestore.Increment(0),
        'total_income': firestore.Increment(0),
        'total_otp': firestore.Increment(0),
        'referrals': firestore.ArrayUnion([]),
        'refer_income': firestore.Increment(0),
        'referred_by': referrer,
        'is_banned': False
    }, merge=True)

    if referrer:
        db.collection('users').document(str(referrer)).update({'referrals': firestore.ArrayUnion([str(user_id)])})
    
    text = "👋 হ্যালো! নাম্বার ওটিপি বোটে আপনাকে স্বাগতম।\n\nসরাসরি নাম্বার পেতে নিচের 🎭 Number নিন বাটন প্রেস করুন।"
    await update.message.reply_text(text, reply_markup=get_main_menu(user_id))

async def handle_text_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    adm_action = context.user_data.get('adm_action')
    usr_action = context.user_data.get('usr_action')

    # ADMIN ACTIONS
    if user_id == ADMIN_ID and adm_action:
        if adm_action == 'set_rate':
            try:
                db.collection('settings').document('config').update({'otp_rate': float(text)})
                clear_cache()
                await update.message.reply_text(f"✅ ওটিপি রেট সফলভাবে `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif adm_action == 'set_min_w':
            try:
                db.collection('settings').document('config').update({'min_withdraw': float(text)})
                clear_cache()
                await update.message.reply_text(f"✅ মিনিমাম উইথড্র `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif adm_action == 'set_ref_bonus':
            try:
                db.collection('settings').document('config').update({'refer_bonus': float(text)})
                clear_cache()
                await update.message.reply_text(f"✅ রেফার বোনাস সফলভাবে `{text} BDT` সেট করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif adm_action == 'add_service':
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
        elif adm_action == 'remove_service':
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
        elif adm_action == 'add_country_input':
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
        elif adm_action == 'remove_country_input':
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
        elif adm_action == 'user_info':
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
                        f"📞 Total OTP: {ud.get('total_otp', 0)} টি"
                    )
                    await update.message.reply_text(info, parse_mode="Markdown")
                else:
                    await update.message.reply_text("❌ এই আইডি-র কোনো ইউজার ডাটাবেজে নেই।")
            except: await update.message.reply_text("❌ ভুল ইউজার আইডি।")
        elif adm_action == 'add_api_provider':
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
        elif adm_action == 'broadcast':
            users_docs = db.collection('users').select(['id']).stream()
            count = 0
            for u in users_docs:
                try: 
                    await context.bot.send_message(chat_id=u.to_dict()['id'], text=f"{text}")
                    count += 1
                except: pass
            await update.message.reply_text(f"✅ মোট {count} জনের কাছে নোটিশ পাঠানো হয়েছে।")
            
        context.user_data['adm_action'] = None
        return

    # USER ACTIONS (WITHDRAW)
    if usr_action == 'withdraw_amount':
        try:
            amount = float(text)
            config = get_bot_settings()
            min_w = config.get('min_withdraw', 110.0)
            user_doc = db.collection('users').document(str(user_id)).get().to_dict() or {}
            bal = user_doc.get('balance', 0.0)

            if amount < min_w:
                await update.message.reply_text(f"❌ মিনিমাম উইথড্র অ্যামাউন্ট {min_w} BDT।")
                return
            if amount > bal:
                await update.message.reply_text("❌ আপনার পর্যাপ্ত ব্যালেন্স নেই।")
                return

            context.user_data['w_amount'] = amount
            context.user_data['usr_action'] = 'withdraw_num'
            await update.message.reply_text("📱 আপনার পেমেন্ট নাম্বারটি (Bkash/Nagad/Rocket) পাঠান:", reply_markup=get_inline_cancel())
            return
        except:
            await update.message.reply_text("❌ সঠিক সংখ্যা ইনপুট দিন।")
            return

    elif usr_action == 'withdraw_num':
        w_number = text.strip()
        amount = context.user_data.get('w_amount', 0.0)
        method = context.user_data.get('w_method', 'Bkash/Nagad')

        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'balance': firestore.Increment(-amount),
            'pending_withdraw': firestore.Increment(amount)
        })

        db.collection('withdraws').add({
            'user_id': user_id,
            'name': update.effective_user.first_name,
            'amount': amount,
            'number': w_number,
            'method': method,
            'status': 'pending',
            'created_at': time.time()
        })

        context.user_data['usr_action'] = None
        await update.message.reply_text("✅ আপনার উইথড্র রিকোয়েস্ট সফলভাবে জমা হয়েছে! অ্যাডমিন চেক করে পেমেন্ট সম্পন্ন করবে।")
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
        count_query = db.collection('users').count()
        results = count_query.get()
        total_users = results[0][0].value
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
        count_query = db.collection('excel_numbers').where('status', '==', 'available').count().get()
        avail = count_query[0][0].value
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

    # USER BUTTONS
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
        bal = user_data.get('balance', 0.0)
        pending = user_data.get('pending_withdraw', 0.0)
        income = user_data.get('total_income', 0.0)
        tot_otp = user_data.get('total_otp', 0)
        
        balance_card = (
            f"💵**আপনার ব্যালেন্স**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵**ব্যালেন্স:** {bal:.2f} BDT\n"
            f"💸**পেন্ডিং (উইথড্র):** {pending:.2f} BDT\n"
            f" 💰**Total Income:** {income:.2f} BDT\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📞**মোট ওটিপি রিসিভ:** {tot_otp} টি"
        )
        await update.message.reply_text(balance_card)

    elif text == "🎁 My Referrals":
        user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
        referrals = user_data.get('referrals', [])
        total_refer = len(referrals) if isinstance(referrals, list) else 0
        refer_income = user_data.get('refer_income', 0.0)
        bot_username = (await context.bot.get_me()).username

        refer_card = (
            f"🎁 **My Referrals**\n"
            f"👤 Total Refer: {total_refer}\n"
            f"😃 Total Refer Income: {refer_income:.2f} BDT\n"
            f"🔗 আপনার রেফার লিংক:\n"
            f"https://t.me/{bot_username}?start={user_id}\n\n"
            f"ℹ️ আপনার রেফারেল লিংক ব্যবহার করে যে যত OTP নিবে প্রতিটি OTP জন্য আপনি ১০ পয়সা করে পাবেন💥"
        )
        await update.message.reply_text(refer_card, disable_web_page_preview=True)

    elif text == "💰 Withdraw":
        config = get_bot_settings()
        min_w = config.get('min_withdraw', 110.0)
        kbd = [
            [InlineKeyboardButton("Bkash", callback_data="w_m_bkash"), InlineKeyboardButton("Nagad", callback_data="w_m_nagad")],
            [InlineKeyboardButton("Rocket", callback_data="w_m_rocket")],
            [InlineKeyboardButton("❌ বাতিল", callback_data="cancel_action")]
        ]
        await update.message.reply_text(f"💰 **উইথড্র মাধ্যম নির্বাচন করুন:**\n\n📌 মিনিমাম উইথড্র: `{min_w} BDT`", reply_markup=InlineKeyboardMarkup(kbd))

    elif text == "🧐 Support":
        kbd = [[InlineKeyboardButton("💬 Admin Support", url=f"https://t.me/{SUPPORT_USERNAME}")]]
        await update.message.reply_text("🧐 যেকোনো প্রয়োজনে আমাদের অ্যাডমিন সাপোর্টে যোগাযোগ করুন:", reply_markup=InlineKeyboardMarkup(kbd))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # NEW FIXED: Add/Remove Country Admin Callbacks
    if data.startswith("adm_add_c_srv_"):
        await query.answer()
        s_name = data.replace("adm_add_c_srv_", "")
        context.user_data['target_add_country_service'] = s_name
        context.user_data['adm_action'] = 'add_country_input'
        await query.edit_message_text(f"✍️ **{s_name}** এর জন্য দেশের নাম এবং কোড দিন।\nউদাহরণ: `Ivory Coast 225079`", reply_markup=get_inline_cancel())

    elif data.startswith("adm_rem_c_srv_"):
        await query.answer()
        s_name = data.replace("adm_rem_c_srv_", "")
        context.user_data['target_rem_country_service'] = s_name
        context.user_data['adm_action'] = 'remove_country_input'
        await query.edit_message_text(f"✍️ **{s_name}** থেকে যে দেশটি মুছতে চান তার নাম টাইপ করুন:", reply_markup=get_inline_cancel())

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
        source_type = 'api'
        provider_id_used = 'api'
        
        active_apis = get_active_providers()
        for active_api in active_apis:
            try:
                api_res = requests.post(f"{active_api['base_url']}/getnum", headers={"mauthapi": active_api['api_key']}, json={"rid": c_code}, timeout=5).json()
                if api_res.get('meta', {}).get('code') == 200:
                    number = api_res['data']['full_number']
                    provider_id_used = active_api['id']
                    break
            except: continue
                
        if number:
            if not str(number).startswith("+"): number = "+" + str(number)
            expire_at = time.time() + 600
            
            _active_orders_memory[number] = {
                'user_id': user_id, 
                'user_name': query.from_user.first_name or "User",
                'service_name': s_name, 
                'country_name': c_name,
                'source': source_type, 
                'provider_id': provider_id_used, 
                'expire_at': expire_at
            }
            
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

    elif data.startswith("w_m_"):
        method = data.split("_")[2].capitalize()
        context.user_data['w_method'] = method
        context.user_data['usr_action'] = 'withdraw_amount'
        await query.edit_message_text(f"💵 কত টাকা উইথড্র করতে চান তা লিখুন (Method: {method}):")

    elif data.startswith("w_app_") or data.startswith("w_rej_"):
        req_id = data.split("_")[2]
        doc_ref = db.collection('withdraws').document(req_id)
        w_doc = doc_ref.get()
        
        if w_doc.exists:
            w_data = w_doc.to_dict()
            u_id = str(w_data['user_id'])
            amt = w_data['amount']

            if data.startswith("w_app_"):
                doc_ref.update({'status': 'approved'})
                db.collection('users').document(u_id).update({'pending_withdraw': firestore.Increment(-amt)})
                await query.edit_message_text("✅ উইথড্র রিকোয়েস্ট **Approve** করা হয়েছে।")
                try: await context.bot.send_message(chat_id=u_id, text=f"✅ আপনার {amt} BDT উইথড্র রিকোয়েস্ট সফলভাবে সম্পন্ন হয়েছে!")
                except: pass
            else:
                doc_ref.update({'status': 'rejected'})
                db.collection('users').document(u_id).update({
                    'balance': firestore.Increment(amt),
                    'pending_withdraw': firestore.Increment(-amt)
                })
                await query.edit_message_text("❌ উইথড্র রিকোয়েস্ট **Reject** করা হয়েছে ও ব্যালেন্স ফেরত দেওয়া হয়েছে।")
                try: await context.bot.send_message(chat_id=u_id, text=f"❌ আপনার {amt} BDT উইথড্র রিকোয়েস্ট বাতিল করা হয়েছে এবং টাকা ফেরত দেওয়া হয়েছে।")
                except: pass
            
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
                        user_name = order_data.get('user_name', 'User')
                        service_name = order_data['service_name']
                        country_name = order_data['country_name']
                        clean_otp = "".join(re.findall(r'\d+', str(latest_otp['message'])))
                        
                        user_ref = db.collection('users').document(str(user_id))
                        user_ref.update({
                            'balance': firestore.Increment(otp_rate),
                            'total_income': firestore.Increment(otp_rate),
                            'total_otp': firestore.Increment(1)
                        })

                        user_doc = user_ref.get().to_dict() or {}
                        referrer_id = user_doc.get('referred_by')
                        if referrer_id:
                            db.collection('users').document(str(referrer_id)).update({
                                'balance': firestore.Increment(ref_bonus),
                                'total_income': firestore.Increment(ref_bonus),
                                'refer_income': firestore.Increment(ref_bonus)
                            })

                        _processed_otps_set.add(otp_id)
                        del _active_orders_memory[number]
                        
                        masked_number = "XXXXX" + number[-5:] if len(number) > 5 else number

                        success_msg = (
                            f"✨ **Now OTP**\n"
                            f"🔹 ━━━━━━━━━━━━━━━━━━━━ 🔹\n"
                            f"📱 Number: {masked_number}\n"
                            f"🌍 Country: {country_name}\n"
                            f"🎯 Service: {service_name}\n"
                            f"👤 User: {user_name}\n"
                            f"💰 Balance Add: +{otp_rate:.2f} BDT\n\n"
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
    rand_otp = str(random.randint(10000, 99999))

    fake_num = "+" + "".join([str(random.randint(0, 9)) for _ in range(11)])
    masked_number = "XXXXX" + fake_num[-5:]

    fake_msg = (
        f"✨ **Now OTP**\n"
        f"🔹 ━━━━━━━━━━━━━━━━━━━━ 🔹\n"
        f"📱 Number: {masked_number}\n"
        f"🌍 Country: {rand_country}\n"
        f"🎯 Service: {rand_service}\n"
        f"👤 User: {rand_name}\n"
        f"💰 Balance Add: +{otp_rate:.2f} BDT\n\n"
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
