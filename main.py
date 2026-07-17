import logging
import os
import json
import asyncio
import sys
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import firebase_admin
from firebase_admin import credentials, firestore
import requests

# পাইথনের বিল্ট-ইন সার্ভার (Render পোর্টের জন্য)
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
ADMIN_ID = int(os.getenv('ADMIN_ID'))
OTP_GROUP_ID = "-1003656135640"
MAIN_CHANNEL_URL = "https://t.me/my1otpp"

# ফায়ারবেস ইনিশিয়ালাইজেশন
if not firebase_admin._apps:
    firebase_json = json.loads(os.getenv('FIREBASE_JSON'))
    cred = credentials.Certificate(firebase_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ডাইনামিক এপিআই গেটওয়ে হেল্পার ফাংশনসমূহ
def get_active_provider():
    """সবচেয়ে প্রথম অ্যাক্টিভ এপিআই প্রোভাইডারটি রিটার্ন করে"""
    providers = db.collection('api_providers').where('is_active', '==', True).limit(1).get()
    if providers:
        return providers[0].to_dict()
    return None

def get_bot_settings():
    settings_ref = db.collection('settings').document('config').get()
    if settings_ref.exists:
        data = settings_ref.to_dict()
        if 'services' not in data:
            data['services'] = {}
        if 'countries' not in data:
            data['countries'] = {}
        if 'fake_otp_enabled' not in data:
            data['fake_otp_enabled'] = False
        return data
    else:
        default_config = {
            'otp_rate': 2.50,
            'min_withdraw': 110.0,
            'countries': {"Montenegro": "me", "Guinea": "gn"},
            'services': {"Facebook": "fb", "Telegram": "tg"},
            'fake_otp_enabled': False
        }
        db.collection('settings').document('config').set(default_config)
        return default_config

def get_main_menu(user_id):
    keyboard = [
        ["🎭 Number নিন", "💸 Balance"],
        ["💰 Withdraw", "🎁 My Referrals"],
        ["🧐 Support"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 Admin Panel"])
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
        ["📢 ব্রডকাস্ট", "🔙 মেইন মেনু"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_inline_cancel():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")]])

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
                await update.message.reply_text(f"✅ ওটিপি রেট সফলভাবে `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'set_min_w':
            try:
                db.collection('settings').document('config').update({'min_withdraw': float(text)})
                await update.message.reply_text(f"✅ মিনিমাম উইথড্র `{text} BDT` করা হয়েছে।")
            except: await update.message.reply_text("❌ ভুল ইনপুট।")
        elif action == 'add_service':
            try:
                service_name = text.strip()
                service_code = service_name.lower()[:2]
                config = get_bot_settings()
                
                services_dict = config.get('services', {})
                services_dict[service_name] = service_code
                
                db.collection('settings').document('config').update({'services': services_dict})
                await update.message.reply_text(f"✅ সার্ভিস সফলভাবে যুক্ত হয়েছে: **{service_name}**")
            except Exception as e: 
                await update.message.reply_text("❌ কোনো ত্রুটি হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।")
        elif action == 'add_country_input':
            try:
                parts = text.strip().split()
                if len(parts) >= 2:
                    c_code = parts[-1]  
                    c_name = " ".join(parts[:-1]) 
                    
                    config = get_bot_settings()
                    countries_dict = config.get('countries', {})
                    countries_dict[c_name] = c_code.lower()
                    
                    db.collection('settings').document('config').update({'countries': countries_dict})
                    await update.message.reply_text(f"✅ দেশ সফলভাবে যুক্ত হয়েছে: {c_name} (Code/Range: {c_code})")
                else:
                    await update.message.reply_text("❌ ফরম্যাট ভুল। উদাহরণ: `Ivory Coast 225079`")
            except: 
                await update.message.reply_text("❌ কোনো ত্রুটি হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।")
        
        # --- নতুন এপিআই প্রোভাইডার যোগ করার ধাপসমূহ ---
        elif action == 'add_api_step1':
            context.user_data['temp_api_name'] = text.strip()
            context.user_data['adm_action'] = 'add_api_step2'
            await update.message.reply_text("🔑 এবার এই প্রোভাইডারের **API KEY / TOKEN** টি পাঠান:", reply_markup=get_inline_cancel())
            return
        elif action == 'add_api_step2':
            context.user_data['temp_api_key'] = text.strip()
            context.user_data['adm_action'] = 'add_api_step3'
            await update.message.reply_text("🌐 এবার এই প্রোভাইডারের **BASE URL** টি পাঠান:\n\n*(যেমন: `https://api.2oo9.cloud/MXS47FLFX0U/tnemn/@public/api`)*", reply_markup=get_inline_cancel())
            return
        elif action == 'add_api_step3':
            base_url = text.strip().rstrip('/')
            api_name = context.user_data.get('temp_api_name')
            api_key = context.user_data.get('temp_api_key')
            
            # ডেটাবেজে সেভ করা
            prov_id = api_name.lower().replace(" ", "_")
            db.collection('api_providers').document(prov_id).set({
                'id': prov_id,
                'name': api_name,
                'api_key': api_key,
                'base_url': base_url,
                'is_active': False
            })
            await update.message.reply_text(f"✅ **{api_name}** এপিআই সফলভাবে যুক্ত হয়েছে! এখন `🔌 Manage APIs` মেনু থেকে এটিকে Active করতে পারবেন।")
            
        elif action == 'user_info_search':
            tgt_user = db.collection('users').document(text).get()
            if tgt_user.exists:
                ud = tgt_user.to_dict()
                context.user_data['managed_user_id'] = text
                ref_count = len(ud.get('referrals', []))
                ref_income = ref_count * 0.10
                
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
            await update.message.reply_text("✍️ এবার কত টাকা উইথড্র করতে চান সেই সংখ্যাটি পাঠান:", reply_markup=get_inline_cancel())
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

    # কিবোর্ড ক্লিকের টেক্সট মেসেজ ক্যাচিং
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
    elif text == "⚙️ Add Service" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'add_service'
        await update.message.reply_text("✍️ জাস্ট আপনার সার্ভিস এর নামটি লিখে পাঠান।\n\n✍️ যেমন: `Facebook`", reply_markup=get_inline_cancel())
    elif text == "🗑️ Remove Service" and user_id == ADMIN_ID:
        config = get_bot_settings()
        services = config.get('services', {})
        if not services:
            await update.message.reply_text("❌ কোনো সার্ভিস উপলব্ধ নেই।")
            return
        keyboard = []
        for s_name in services.keys():
            keyboard.append([InlineKeyboardButton(f"🗑️ {s_name}", callback_data=f"rem_srv_{s_name}")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await update.message.reply_text("🗑️ **কোন সার্ভিসটি রিমুভ করতে চান সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "⚙️ Add Country" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'add_country_input'
        await update.message.reply_text("✍️ দেশের নাম ও প্রোভাইডার সাইটের রেঞ্জ কোড স্পেস দিয়ে পাঠান।\n\n✍️ উদাহরণ: `Ivory Coast 225079`", reply_markup=get_inline_cancel())
    elif text == "🗑️ Remove Country" and user_id == ADMIN_ID:
        config = get_bot_settings()
        countries = config.get('countries', {})
        if not countries:
            await update.message.reply_text("❌ কোনো দেশ উপলব্ধ নেই।")
            return
        keyboard = []
        for c_name in countries.keys():
            keyboard.append([InlineKeyboardButton(f"🗑️ {c_name}", callback_data=f"rem_cnt_{c_name}")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await update.message.reply_text("🗑️ **কোন দেশটি রিমুভ করতে চান সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # --- ফেক ওটিপি টগল বাটন হ্যান্ডলিং ---
    elif text.startswith("📢 Fake OTP:") and user_id == ADMIN_ID:
        config = get_bot_settings()
        current_status = config.get('fake_otp_enabled', False)
        new_status = not current_status
        db.collection('settings').document('config').update({'fake_otp_enabled': new_status})
        
        status_text = "চালু 🟢" if new_status else "বন্ধ 🔴"
        await update.message.reply_text(f"📢 ফেক ওটিপি লুপটি সফলভাবে **{status_text}** করা হয়েছে।", reply_markup=get_admin_menu())

    # --- এপিআই কন্ট্রোল প্যানেল ট্রিগার ---
    elif text == "🔌 Manage APIs" and user_id == ADMIN_ID:
        providers = db.collection('api_providers').stream()
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
            
        if not has_providers:
            msg_text += "❌ কোনো এপিআই প্রোভাইডার যুক্ত করা নেই।"
            
        keyboard.append([InlineKeyboardButton("➕ Add New API", callback_data="add_new_api")])
        keyboard.append([InlineKeyboardButton("❌ ক্লোজ", callback_data="cancel_action")])
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif text == "📊 Top 10 OTP (24h)" and user_id == ADMIN_ID:
        orders = db.collection('orders').where('status', '==', 'completed').stream()
        user_counts = {}
        for o in orders:
            od = o.to_dict()
            uid = od.get('user_id')
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
        users = db.collection('users').get()
        await update.message.reply_text(f"👥 **বোটে মোট রেজিস্টার্ড ইউজার:** {len(users)} জন।")
    elif text == "👤 User Information" and user_id == ADMIN_ID:
        context.user_data['adm_action'] = 'user_info_search'
        await update.message.reply_text("🔎 যে ইউজারের তথ্য দেখতে চান তার **Telegram User ID** পাঠান:", reply_markup=get_inline_cancel())
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
        await update.message.reply_text("📢 নোটিশটি টাইপ করে পাঠান:", reply_markup=get_inline_cancel())
    elif text == "🎭 Number নিন":
        config = get_bot_settings()
        services = config.get('services', {})
        keyboard = []
        for s_name, s_code in services.items():
            keyboard.append([InlineKeyboardButton(f"🎯 {s_name}", callback_data=f"usr_s_{s_code}")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await update.message.reply_text("⚡ **একটি সার্ভিস সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "💸 Balance":
        user_id = update.effective_user.id
        user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
        balance = user_data.get('balance', 0.0)
        total_otp = user_data.get('total_otp', 0)
        text = (f"💲 আপনার ব্যালেন্স\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔥 ব্যালেন্স: {balance:.2f} BDT\n💰 পেন্ডিং (উইথড্র): 0.00 BDT\n"
                f"💵 Total Income: {balance:.2f} BDT\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ মোট ওটিপি রিসিভ: {total_otp} টি")
        await update.message.reply_text(text)
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
        await update.message.reply_text("💳 **টাকা উত্তোলনের মেথড সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "🎁 My Referrals":
        user_data = db.collection('users').document(str(user_id)).get().to_dict() or {}
        refs = user_data.get('referrals', [])
        ref_count = len(refs)
        bot_uname = (await context.bot.get_me()).username
        refer_text = (
            f"🎁 ⚠️ **ধামাকা রেফার অফার! আনলিমিটেড ইনকাম করুন!** ⚠️ 🎁\n\n"
            f"👤 **Total Refer:** {ref_count} জন\n"
            f"😃 **Total Refer Income:** {ref_count * 0.10:.2f} BDT\n\n"
            f"🔗 **আপনার রেফার লিংক (কপি করতে ক্লিক করুন):**\n"
            f"`https://t.me/{bot_uname}?start={user_id}`\n\n"
            f"──────────────────────\n"
            f"🔥 **রেফারের সুবিধা:**\n"
            f"💸 প্রতি সফল ওটিপিতে আপনার রেফারকৃত ইউজারের কাছ থেকে পাবেন লাইফটাইম কমিশন ০.১০ পয়সা! এখনই শেয়ার করুন! 🎉"
        )
        await update.message.reply_text(refer_text, parse_mode="Markdown")
    elif text == "🧐 Support":
        support_card = (
            "📞 **গ্রাহক সেবা কেন্দ্র**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "সম্মানিত মেম্বার,\n"
            "আপনার যেকোনো সমস্যা বা জিজ্ঞাসার জন্য আমাদের সাপোর্ট টিমের সাথে যোগাযোগ করুন। আমরা দ্রুত সমাধানের চেষ্টা করব।\n\n"
            "⚠️ **নোট:** অযথা মেসেজ দেওয়া থেকে বিরত থাকুন। ধন্যবাদ!"
        )
        support_kbd = [
            [InlineKeyboardButton("➡️ 💁‍♂️ অ্যাডমিন সাপোর্ট", url="https://t.me/helptg10")],
            [InlineKeyboardButton("➡️ 📢 অফিসিয়াল চ্যানেল", url="https://t.me/helptg100")]
        ]
        await update.message.reply_text(support_card, reply_markup=InlineKeyboardMarkup(support_kbd), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("toggle_api_"):
        api_id = data.split("_")[2]
        all_apis = db.collection('api_providers').get()
        for a in all_apis:
            db.collection('api_providers').document(a.id).update({'is_active': False})
            
        db.collection('api_providers').document(api_id).update({'is_active': True})
        await query.edit_message_text("✅ এপিআই সফলভাবে পরিবর্তিত ও সক্রিয় হয়েছে।")
        
    elif data.startswith("del_api_"):
        api_id = data.split("_")[2]
        db.collection('api_providers').document(api_id).delete()
        await query.edit_message_text("🗑️ এপিআই প্রোভাইডার সফলভাবে রিমুভ করা হয়েছে।")
        
    elif data == "add_new_api":
        context.user_data['adm_action'] = 'add_api_step1'
        await query.edit_message_text("✍️ নতুন প্রোভাইডারের একটি **সুন্দর নাম** টাইপ করে পাঠান:\n\n*(যেমন: MnitNetwork)*", reply_markup=get_inline_cancel())

    elif data.startswith("rem_srv_"):
        s_name = data.split("_")[2]
        config = get_bot_settings()
        services = config.get('services', {})
        if s_name in services:
            del services[s_name]
            db.collection('settings').document('config').update({'services': services})
            await query.edit_message_text(f"✅ **{s_name}** সার্ভিসটি সফলভাবে রিমুভ করা হয়েছে।")
            
    elif data.startswith("rem_cnt_"):
        c_name = data.split("_")[2]
        config = get_bot_settings()
        countries = config.get('countries', {})
        if c_name in countries:
            del countries[c_name]
            db.collection('settings').document('config').update({'countries': countries})
            await query.edit_message_text(f"✅ **{c_name}** দেশটি সফলভাবে রিমুভ করা হয়েছে।")

    elif data.startswith("usr_s_"):
        s_code = data.split("_")[2]
        context.user_data['selected_service_code'] = s_code
        config = get_bot_settings()
        countries = config.get('countries', {})
        s_name = next((k for k, v in config['services'].items() if v == s_code), "Service")
        
        keyboard = []
        for c_name, c_code in countries.items():
            keyboard.append([InlineKeyboardButton(f"🌍 {c_name}", callback_data=f"usr_c_{c_code}")])
        keyboard.append([InlineKeyboardButton("⬅️ সার্ভিস তালিকায় ফিরে যান", callback_data="back_to_services")])
        keyboard.append([InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")])
        await query.edit_message_text(f"🌍 **{s_name}-এর জন্য দেশ সিলেক্ট করুন:**", reply_markup=InlineKeyboardMarkup(keyboard))

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
        
        active_api = get_active_provider()
        if not active_api:
            await query.edit_message_text("❌ বর্তমানে কোনো অ্যাক্টিভ এপিআই প্রোভাইডার সেট করা নেই। অ্যাডমিনের সাথে যোগাযোগ করুন।", reply_markup=get_inline_cancel())
            return
            
        try:
            api_payload = {
                "rid": c_code  
            }
            
            api_res = requests.post(
                f"{active_api['base_url']}/getnum", 
                headers={"mauthapi": active_api['api_key']}, 
                json=api_payload
            ).json()
            
            if api_res.get('meta', {}).get('code') == 200:
                number = api_res['data']['full_number']
                config = get_bot_settings()
                c_name = next((k for k, v in config['countries'].items() if v == c_code), "Country")
                s_name = next((k for k, v in config['services'].items() if v == s_code), "Service")
                
                db.collection('orders').document(str(number)).set({
                    'user_id': user_id, 'status': 'active', 'country_name': c_name, 'service_name': s_name, 'timestamp': datetime.utcnow()
                })
                
                num_box = (
                    f"🎯 **{s_name} (Allocated) ✅**\n"
                    f"🔄 Waiting for OTP........\n\n"
                    f"📱 `{number}`\n"
                    f"📱 `{number}`\n"
                    f"📱 `{number}`\n\n"
                    f"📥 ওটিপির জন্য অপেক্ষা করুন..."
                )
                action_buttons = [
                    [InlineKeyboardButton("📢 ওটিপি গ্রুপ", https://t.me/emsms10), InlineKeyboardButton("🔄 নাম্বার পরিবর্তন করুন", callback_data=f"change_num_{c_code}")],
                    [InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_action")]
                ]
                await query.edit_message_text(num_box, reply_markup=InlineKeyboardMarkup(action_buttons), parse_mode="Markdown")
            else:
                await query.edit_message_text("❌ দুঃখিত, বর্তমানে কোনো নাম্বার খালি নেই।", reply_markup=get_inline_cancel())
        except:
            await query.edit_message_text("❌ এপিআই প্রসেসিং ত্রুটি।", reply_markup=get_inline_cancel())
            
    elif data.startswith("w_method_"):
        method = data.split("_")[2]
        context.user_data['w_method'] = method
        context.user_data['adm_action'] = 'w_num_input'
        await query.edit_message_text(f"✍️ আপনার **{method.upper()}** নাম্বারটি টাইপ করে পাঠান:", reply_markup=get_inline_cancel())
        
    elif data.startswith("app_w_"):
        doc_id = data.split("_")[2]
        db.collection('withdraws').document(doc_id).update({'status': 'approved'})
        await query.edit_message_text("✅ উইথড্র রিকোয়েস্ট সফলভাবে অ্যাপ্রুভ করা হয়েছে।")
        
    elif data.startswith("u_action_"):
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
        context.user_data['adm_action'] = None
        cancel_text = "❌ **অনুরোধ বাতিল করা হয়েছে।**\nমূল মেনুতে ফিরে আসা হয়েছে।"
        try:
            await query.edit_message_text(cancel_text, parse_mode="Markdown")
        except:
            await query.message.reply_text(cancel_text, parse_mode="Markdown")

# --- রিয়েল ওটিপি চেকার ব্যাকগ্রাউন্ড টাস্ক ---
async def check_otp_and_forward(context: ContextTypes.DEFAULT_TYPE):
    active_api = get_active_provider()
    if not active_api:
        return
        
    url = f"{active_api['base_url']}/success-otp"
    try:
        data = requests.get(url, headers={"mauthapi": active_api['api_key']}).json()
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
                    service_name = order_data.get('service_name', 'Facebook')
                    country_name = order_data.get('country_name', 'Ivory Coast')
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
                        f"**Now Otp**\n"
                        f"📢 `Number 1 ❞` \n\n"
                        f"🔸 {country_name} | {service_name}\n\n"
                        f"👤 **User:** {user_data.get('name', 'User')}\n"
                        f"💰 **Balance:** {cur_bal:.2f} BDT\n"
                        f"✉️ **OTP Code:** `{otp_code}`\n"
                        f"──────────────────────\n"
                        f"🎁 *প্রতি ওটিপিতে ফ্রিতে ০.১০ পয়সা বোনাস পেতে এখনই বন্ধুদের রেফার করুন!* 🚀"
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

# --- ফেক ওটিপি লুপ ব্যাকগ্রাউন্ড টাস্ক ---
async def fake_otp_generator(context: ContextTypes.DEFAULT_TYPE):
    config = get_bot_settings()
    # যদি ফেক ওটিপি অন থাকে তবেই চলবে
    if not config.get('fake_otp_enabled', False):
        return

    # র্যান্ডম ডেটা জেনারেট করার জন্য লিস্ট
    fake_names = [
        "Sabbir", "Rahat", "Emon", "Tanvir", "Noyon", "Alamin", "Sujon", "Mim", "Riya", "Nipa", 
        "Hasan", "Arif", "Shakil", "Kamrul", "Sajid", "Rifat", "Sumon", "Rasel", "Fahim", "Naim"
    ]
    
    # বোটে সেট করা রিয়েল সার্ভিস ও দেশের তালিকা থেকেই র্যান্ডমলি বেছে নেবে
    services_list = list(config.get('services', {"Facebook": "fb", "Telegram": "tg"}).keys())
    countries_list = list(config.get('countries', {"Ivory Coast": "225079", "Afghanistan": "9374404"}).keys())
    
    # ফলব্যাক প্রোটেকশন
    if not services_list: services_list = ["Facebook", "Telegram", "WhatsApp", "IMO"]
    if not countries_list: countries_list = ["Ivory Coast", "Afghanistan", "Guinea", "Montenegro"]

    # র্যান্ডম ডেটা সিলেকশন
    rand_name = random.choice(fake_names)
    rand_service = random.choice(services_list)
    rand_country = random.choice(countries_list)
    rand_balance = round(random.uniform(10.50, 450.00), 2)
    
    # বিভিন্ন ফরম্যাটের ওটিপি কোড জেনারেশন (৪ থেকে ৬ ডিজিট)
    otp_formats = [
        str(random.randint(1000, 9999)),
        str(random.randint(10000, 99999)),
        str(random.randint(100000, 999999)),
        f"G-{random.randint(100000, 999999)}"
    ]
    rand_otp = random.choice(otp_formats)

    # আসল ওটিপির হুবহু ফরম্যাট (কোনো ডেটাবেজ আপডেট হবে না)
    fake_msg = (
        f"**Now Otp**\n"
        f"📢 `Number 1 ❞` \n\n"
        f"🔸 {rand_country} | {rand_service}\n\n"
        f"👤 **User:** {rand_name}\n"
        f"💰 **Balance:** {rand_balance:.2f} BDT\n"
        f"✉️ **OTP Code:** `{rand_otp}`\n"
        f"──────────────────────\n"
        f"🎁 *প্রতি ওটিপিতে ফ্রিতে ০.১০ পয়সা বোনাস পেতে এখনই বন্ধুদের রেফার করুন!* 🚀"
    )

    group_buttons = [
        [InlineKeyboardButton("🚀 Get Number", url=f"https://t.me/{(await context.bot.get_me()).username}")],
        [InlineKeyboardButton("📢 Main Channel", url=MAIN_CHANNEL_URL)]
    ]

    try:
        # শুধুমাত্র গ্রুপ চ্যাটে মেসেজ পাঠানো হচ্ছে
        await context.bot.send_message(
            chat_id=OTP_GROUP_ID, 
            text=fake_msg, 
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup(group_buttons)
        )
    except Exception as e:
        pass

# --- সার্ভার রানিং লাইভ পলিসি হ্যান্ডলার ---
class RenderServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is live on Render Server!")

def run_built_in_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), RenderServer)
    server.serve_forever()

def main():
    t = threading.Thread(target=run_built_in_server, daemon=True)
    t.start()

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # রিয়েল ওটিপি চেকার (১০ সেকেন্ড পরপর চলে)
    app.job_queue.run_repeating(check_otp_and_forward, interval=10, first=5)
    
    # ফেক ওটিপি জেনারেটর (১০ সেকেন্ড পরপর গ্রুপে মেসেজ পাঠাবে)
    app.job_queue.run_repeating(fake_otp_generator, interval=10, first=10)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_inputs))
    
    print("Now OTP Engine Running...")
    app.run_polling(close_loop=False)

if __name__ == '__main__':
    main()
