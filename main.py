import os
import subprocess
import sys
import random
import json
import re
import string
from datetime import datetime

# --- প্রয়োজনীয় লাইব্রেরি ইনস্টলেশন চেক ---
def install_packages():
    required = {"telebot": "pyTelegramBotAPI", "pyotp": "pyotp", "supabase": "supabase"}
    for module_name, package_name in required.items():
        try:
            __import__(module_name)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

install_packages()

import pyotp
import telebot
from telebot import types
from supabase import create_client, Client

# --- ⚙️ কনফিগারেশন ⚙️ ---
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
ADMIN_ID = 7036481355  # আপনার অ্যাডমিন আইডি
CHANNEL_USERNAME = "@helptg100"  # আপনার অফিশিয়াল চ্যানেেলের ইউজারনেম

bot = telebot.TeleBot(BOT_TOKEN)

# --- ☁️ Supabase ক্লাউড ডাটাবেজ কানেকশন ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "আপনার_সুপাবেজ_url_এখানে_দিন")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "আপনার_সুপাবেজ_key_এখানে_দিন")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ডাটাবেজ গ্লোবাল ভেরিয়েবল ---
users_db = {}
pending_tasks = {}
fb_pending_tasks = {} 
gmail_pending_tasks = {} 
username_to_id = {}
history_db = {"approved": 0, "rejected": 0}
global_config = {
    "rate_instagram": 3.0,
    "rate_gmail": 5.0,
    "rate_facebook": 4.50,
    "status_instagram": True,
    "status_gmail": True,
    "status_facebook": True,
    "task_password": "Emon@7"
}
pending_withdraws = {}
admin_states = {} 

# --- ক্লাউড ডাটাবেজ লোড ও সেভ ফাংশন ---
def load_database():
    global users_db, pending_tasks, fb_pending_tasks, gmail_pending_tasks, username_to_id, history_db, global_config, pending_withdraws
    try:
        response = supabase.table("bot_state").select("*").eq("id", 1).execute()
        if response.data:
            data = response.data[0]
            # সুপাবেজ থেকে জেসন ফরম্যাটে ডাটা ব্যাক আনা এবং ইন্টিজারে কনভার্ট করা
            users_db = {int(k): v for k, v in data.get("users_db", {}).items()}
            pending_tasks = data.get("pending_tasks", {})
            fb_pending_tasks = data.get("fb_pending_tasks", {})
            gmail_pending_tasks = data.get("gmail_pending_tasks", {})
            username_to_id = {k: int(v) for k, v in data.get("username_to_id", {}).items()}
            history_db = data.get("history_db", {"approved": 0, "rejected": 0})
            global_config = data.get("global_config", global_config)
            pending_withdraws = data.get("pending_withdraws", {})
            print("🚀 Cloud Data Loaded Successfully From Supabase!")
        else:
            save_database()
    except Exception as e:
        print(f"❌ Error loading cloud database: {e}")

def save_database():
    try:
        # পাইথনের ডিকশনারি ডাটা ক্লাউডে পুশ করা
        data_to_save = {
            "users_db": {str(k): v for k, v in users_db.items()}, # Key স্ট্রিং করা জরুরি জেসন এর জন্য
            "pending_tasks": pending_tasks,
            "fb_pending_tasks": fb_pending_tasks,
            "gmail_pending_tasks": gmail_pending_tasks,
            "username_to_id": username_to_id,
            "history_db": history_db,
            "global_config": global_config,
            "pending_withdraws": pending_withdraws
        }
        supabase.table("bot_state").update(data_to_save).eq("id", 1).execute()
        print("💾 Data Saved Successfully inside Supabase Cloud!")
    except Exception as e:
        print(f"❌ Error saving cloud database: {e}")

# প্রথমবার বটের ডাটা সুপাবেজ থেকে লোড করা
load_database()

# স্টেট ও সেশন ট্র্যাকিং ডাটা
user_current_acc = {}
user_withdraw_session = {}
user_fb_session = {} 

# --- নাম জেনারেশনের জন্য ডিকশনারি ও লিস্ট ---
INDIAN_FIRST_NAMES = ["raj", "priya", "amit", "rahul", "sneha", "deepak", "rohit", "pooja", "animesh", "vikram", "jyoti", "suresh"]
INDIAN_LAST_NAMES = ["lev", "gupta", "sharma", "kumar", "singh", "verma", "das", "mishra", "yadav", "joshi"]

USA_BOYS_FIRST = ["Arthur", "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas"]
USA_GIRLS_FIRST = ["Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica", "Sarah", "Karen"]
USA_LAST_NAMES = ["Souza", "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez"]

def generate_indian_username():
    f_name = random.choice(INDIAN_FIRST_NAMES)
    l_name = random.choice(INDIAN_LAST_NAMES)
    random_str = "".join(random.choices(string.ascii_lowercase, k=random.randint(2, 4)))
    random_num = random.randint(10, 99999)
    if random.choice([True, False]):
        return f"{f_name}{l_name}{random_num}"
    else:
        return f"{f_name}{random_str}{random_num}"

def register_user(user):
    uid = user.id
    uname = user.username.lower() if user.username else f"user_{uid}"
    username_to_id[uname] = uid
    if uid not in users_db:
        users_db[uid] = {
            "balance": 0.0, 
            "pending_withdraw": 0.0,
            "total_income": 0.0,
            "completed_tasks": 0,
            "review_tasks": 0,
            "username": uname, 
            "banned": False, 
            "referrals": 0,
            "refer_income": 0.0,
            "referred_by": None
        }
    else:
        users_db[uid]["username"] = uname
    save_database()
    return users_db[uid]

def is_user_joined(user_id):
    if user_id == ADMIN_ID:
        return True
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except:
        return True

def send_join_request(chat_id):
    join_kb = types.InlineKeyboardMarkup(row_width=1)
    join_kb.add(
        types.InlineKeyboardButton("📢 চ্যানেলে জয়েন করুন", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
        types.InlineKeyboardButton("✅ জয়েন করেছি", callback_data="check_join_status")
    )
    msg_text = (
        "⚠️ বট ব্যবহার করতে হলে অবশ্যই আমাদের চ্যানেলে জয়েন থাকতে হবে!\n\n"
        "দয়া করে নিচের লিংকে জয়েন করে '✅ জয়েন করেছি' বাটনে ক্লিক করুন।"
    )
    bot.send_message(chat_id, msg_text, reply_markup=join_kb)

def get_combined_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("📋 Pending Tasks/"))
        markup.add(types.KeyboardButton("⚙️ Change Task Pass"))
        markup.add(types.KeyboardButton("⚙️ Change Rate/"))
        markup.add(types.KeyboardButton("✅ Approval All /"))
        markup.add(types.KeyboardButton("❌ Rejected All /"))
        
        markup.add(types.KeyboardButton("📊 Dashboard >"), types.KeyboardButton("🔧 Task Switch/"))
        markup.add(types.KeyboardButton("💰 addbalance/"), types.KeyboardButton("📉 cutbalance/"))
        markup.add(types.KeyboardButton("🚫 banuser/"), types.KeyboardButton("🔓 unbanuser/"))
        markup.add(types.KeyboardButton("🔍 Search User/"), types.KeyboardButton("📢 Broadcast/"))
        markup.add(types.KeyboardButton("🏧 Withdraw Request/"), types.KeyboardButton("📋 User list /"))
        markup.add(types.KeyboardButton("📊 Sit list >"))
    else:
        markup.add(types.KeyboardButton("📝 কাজ ▶"), types.KeyboardButton("💵 ব্যালেন্স >"))
        markup.add(types.KeyboardButton("💰 টাকা উত্তোলন >"), types.KeyboardButton("🎁 My Referrals >"))
        markup.add(types.KeyboardButton("💬 সাপোর্ট >"), types.KeyboardButton("👶 আমি নতুন"))
    return markup

# --- ইউজার ডেটা না মুছে বট রিস্টার্ট বাটন বা কমান্ড ---
@bot.message_handler(commands=['botstart', 'start'])
def start_command(message):
    uid = message.from_user.id
    
    if uid in user_current_acc: del user_current_acc[uid]
    if uid in user_withdraw_session: del user_withdraw_session[uid]
    if uid in user_fb_session: del user_fb_session[uid]
    if message.chat.id in admin_states: del admin_states[message.chat.id]

    is_new = uid not in users_db
    user_data = register_user(message.from_user)
    
    if user_data["banned"]:
        bot.send_message(message.chat.id, "❌ আপনাকে এই বট থেকে ব্যান করা হয়েছে।")
        return

    if is_new and len(message.text.split()) > 1:
        ref_candidate = message.text.split()[1]
        if ref_candidate.isdigit():
            ref_id = int(ref_candidate)
            if ref_id in users_db and ref_id != uid:
                users_db[uid]["referred_by"] = ref_id
                users_db[ref_id]["referrals"] = users_db[ref_id].get("referrals", 0) + 1
                save_database()
                try: bot.send_message(ref_id, f"👥 🎉 আপনার রেফারেলে একজন নতুন সদস্য যুক্ত হয়েছেন!")
                except: pass

    if not is_user_joined(message.from_user.id):
        send_join_request(message.chat.id)
        return

    if message.text.startswith('/botstart'):
        welcome_text = "🔄 **বটটি সফলভাবে রিস্টার্ট করা হয়েছে!** আপনার পূর্বের কোনো ইউজার ডাটা বা ব্যালেন্স মোছা হয়নি।"
        bot.send_message(message.chat.id, welcome_text, reply_markup=get_combined_menu(message.from_user.id), parse_mode="Markdown")
    else:
        welcome_text = "👋 বটের মূল মেনু ওপেন হয়েছে। কাজ করতে নিচের বাটনগুলো ব্যবহার করুন।" if message.from_user.id != ADMIN_ID else "⚡ অ্যাডমিন কন্ট্রোল প্যানেল অ্যাক্টিветеড।"
        bot.send_message(message.chat.id, welcome_text, reply_markup=get_combined_menu(message.from_user.id), parse_mode="Markdown")

# --- 🎯 ইনলাইন কলব্যাক হ্যান্ডলার ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    if call.data == "check_join_status":
        if is_user_joined(uid):
            try: bot.delete_message(chat_id, message_id)
            except: pass
            welcome_text = "👋 জয়েন ভেরিফিকেশন সফল! বটের মূল মেনু ওপেন হয়েছে।" if uid != ADMIN_ID else "⚡ অ্যাডমিন কন্ট্রোল প্যানেল অ্যাক্টিветеড।"
            bot.send_message(chat_id, welcome_text, reply_markup=get_combined_menu(uid))
        else:
            bot.answer_callback_query(call.id, "❌ আপনি এখনো চ্যানেলে জয়েন করেননি! দয়া করে জয়েন করুন।", show_alert=True)
        return

    # --- উইথড্র মেথড সিলেকশন হ্যান্ডলার ---
    elif call.data in ["method_bkash", "method_nagad"]:
        method_name = "bKash" if call.data == "method_bkash" else "Nagad"
        
        if users_db[uid]["balance"] < 100.0:
            bot.answer_callback_query(call.id, f"❌ টাকা তোলা যাবে না! আপনার অ্যাকাউন্টে ন্যূনতম ১০০৳ থাকতে হবে।", show_alert=True)
            return
            
        bot.answer_callback_query(call.id)
        user_withdraw_session[uid] = {"method": method_name}
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ বাতিল"))
        
        msg = bot.send_message(chat_id, f"📱 আপনার **{method_name}** পার্সোনাল নম্বরটি দিন:", reply_markup=markup, parse_mode="Markdown")
        bot.register_next_step_handler(msg, user_withdraw_get_number)
        return

    elif call.data == "inline_pending_tasks":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📸 Instagram কাজ pending", callback_data="show_p_instagram"),
            types.InlineKeyboardButton("📧 Gmail কাজ pending", callback_data="show_p_gmail"),
            types.InlineKeyboardButton("🔵 Facebook কাজ pending", callback_data="show_p_facebook"),
            types.InlineKeyboardButton("❌ Cancel", callback_data="close_admin_inline")
        )
        bot.edit_message_text("📋 **কোন কাজের পেন্ডিং লিস্ট দেখতে চান? সিলেক্ট করুন:**", chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        return

    elif call.data == "show_p_instagram":
        if not pending_tasks:
            bot.answer_callback_query(call.id, "📭 ইনস্টাগ্রামের কোনো পেন্ডিং কাজ নেই।", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        for ig_user, data in list(pending_tasks.items()):
            tkb = types.InlineKeyboardMarkup(row_width=2)
            tkb.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"adm_apr_{ig_user}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{ig_user}")
            )
            details = f"📸 **Instagram Pending Task**\n━━━━━━━━━━━━━━━━━━━━\n👤 সাবমিট করেছে: @{data['tg_username']}\n📸 IG User: `{ig_user}`\n🔑 2FA Key: `{data['key']}`\n⚡ বর্তমান কোড: `{data['code']}`"
            bot.send_message(chat_id, details, reply_markup=tkb, parse_mode="Markdown")
        return

    elif call.data == "show_p_facebook":
        if not fb_pending_tasks:
            bot.answer_callback_query(call.id, "📭 ফেসবুকের কোনো পেন্ডিং কাজ নেই।", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        for fb_uid, data in list(fb_pending_tasks.items()):
            fkb = types.InlineKeyboardMarkup(row_width=2)
            fkb.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"fb_apr_{fb_uid}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"fb_rej_{fb_uid}")
            )
            details = (
                f"📥 **ফেসবুক পেন্ডিং কাজ**\n━━━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ Username: @{data['tg_username']}\n"
                f"🆔 User I.D: `{data['user_id']}`\n"
                f"👤 First name: `{data['first_name']}`\n"
                f"👤 Last name: `{data['last_name']}`\n"
                f"🔒 Password: `{data['password']}`\n"
                f"🔵 Facebook UID: `{fb_uid}`\n"
                f"🍪 Cookies:\n`{data.get('cookies', 'N/A')}`"
            )
            bot.send_message(chat_id, details, reply_markup=fkb, parse_mode="Markdown")
        return

    elif call.data == "show_p_gmail":
        if not gmail_pending_tasks:
            bot.answer_callback_query(call.id, "📭 জিমেইলের কোনো পেন্ডিং কাজ নেই।", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "📧 জিমেইলের পেন্ডিং কাজ বর্তমানে খালি আছে।")
        return

    elif call.data == "inline_change_rate":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"📸 Instagram (Current: {global_config.get('rate_instagram', 3.0)}৳)", callback_data="crate_instagram"),
            types.InlineKeyboardButton(f"📧 Gmail (Current: {global_config.get('rate_gmail', 5.0)}৳)", callback_data="crate_gmail"),
            types.InlineKeyboardButton(f"🔵 Facebook (Current: {global_config.get('rate_facebook', 4.50)}৳)", callback_data="crate_facebook"),
            types.InlineKeyboardButton("❌ Cancel", callback_data="close_admin_inline")
        )
        bot.edit_message_text("⚙️ **কোন কাজের রেট পরিবর্তন করতে চান? সিলেক্ট করুন:**", chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        return

    elif call.data in ["crate_instagram", "crate_gmail", "crate_facebook"]:
        job_type = call.data.split('_')[1]
        admin_states[chat_id] = f"change_rate_{job_type}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="inline_change_rate"))
        bot.edit_message_text(f"💰 **{job_type.capitalize()}** কাজের নতুন রেট ইনপুট দিন (যেমন: 4.50):", chat_id, message_id, reply_markup=markup)
        return

    elif call.data == "inline_sit_list":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📸 Instagram কাজ List", callback_data="sit_list_instagram"),
            types.InlineKeyboardButton("📧 Gmail কাজ List", callback_data="sit_list_gmail"),
            types.InlineKeyboardButton("🔵 Facebook কাজ List", callback_data="sit_list_facebook"),
            types.InlineKeyboardButton("❌ Cancel", callback_data="close_admin_inline")
        )
        bot.edit_message_text("📊 **পেন্ডিং ডাটাগুলো এক ক্লিকে ফোনে সিরিয়াল করতে অপশন বেছে নিন:**", chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        return

    elif call.data == "sit_list_instagram":
        if not pending_tasks:
            bot.answer_callback_query(call.id, "📭 ইনস্টাগ্রামের কোনো পেন্ডিং কাজ নেই।", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        serial_msg = "📸 **Instagram Pending Serial List**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        idx = 1
        for ig_user, data in pending_tasks.items():
            serial_msg += f"{idx}. ID: `{data['user_id']}` | User: `@{data['tg_username']}` | IG: `{ig_user}` | Pass: `{data['generated_pass']}` | Key: `{data['key']}`\n"
            idx += 1
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Sit List", callback_data="inline_sit_list"))
        bot.send_message(chat_id, serial_msg, reply_markup=markup, parse_mode="Markdown")
        return

    elif call.data == "sit_list_facebook":
        if not fb_pending_tasks:
            bot.answer_callback_query(call.id, "📭 ফেসবুকের কোনো পেন্ডিং কাজ নেই।", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        serial_msg = "🔵 **Facebook Pending Serial List**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        idx = 1
        for fb_uid, data in fb_pending_tasks.items():
            serial_msg += (
                f"{idx}. ID: `{data['user_id']}` | User: `@{data['tg_username']}` | "
                f"Name: `{data['first_name']} {data['last_name']}` | Pass: `{data['password']}` | "
                f"UID: `{fb_uid}` | Cookies: `{data.get('cookies', 'N/A')}`\n\n"
            )
            idx += 1
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Sit List", callback_data="inline_sit_list"))
        bot.send_message(chat_id, serial_msg, reply_markup=markup, parse_mode="Markdown")
        return

    elif call.data == "sit_list_gmail":
        bot.answer_callback_query(call.id, "📭 জিমেইল কাজের কোনো পেন্ডিং ডাটা নেই।", show_alert=True)
        return

    elif call.data == "close_admin_inline":
        bot.edit_message_text("❌ অপারেশন বাতিল করা হয়েছে।", chat_id, message_id)
        return

    if call.data.startswith('tswitch_'):
        if uid != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ আপনি অ্যাডমিন নন!")
            return
        task_type = call.data.split('_')[-1]
        key = f"status_{task_type}"
        global_config[key] = not global_config.get(key, True)
        save_database()
        
        status_ig = "🟢 ON" if global_config.get("status_instagram", True) else "🔴 OFF"
        status_gm = "🟢 ON" if global_config.get("status_gmail", True) else "🔴 OFF"
        status_fb = "🟢 ON" if global_config.get("status_facebook", True) else "🔴 OFF"
        
        sw_kb = types.InlineKeyboardMarkup(row_width=1)
        sw_kb.add(
            types.InlineKeyboardButton(f"📸 Instagram Task: {status_ig}", callback_data="tswitch_instagram"),
            types.InlineKeyboardButton(f"📩 Gmail Task: {status_gm}", callback_data="tswitch_gmail"),
            types.InlineKeyboardButton(f"🔵 Facebook Task: {status_fb}", callback_data="tswitch_facebook")
        )
        try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=sw_kb)
        except: pass
        bot.answer_callback_query(call.id, "🔧 সুইচ সফলভাবে পরিবর্তিত")
        return

    if call.data.startswith('adm_apr_'):
        target_ig_user = call.data.split('_')[-1]
        if target_ig_user in pending_tasks:
            task = pending_tasks[target_ig_user]
            t_uid = task["user_id"]
            rate = task.get("rate", global_config.get("rate_instagram", 3.0))
            if t_uid in users_db:
                users_db[t_uid]["balance"] += rate
                users_db[t_uid]["total_income"] += rate
                users_db[t_uid]["completed_tasks"] += 1
                if users_db[t_uid]["review_tasks"] > 0: users_db[t_uid]["review_tasks"] -= 1
                
                ref_id = users_db[t_uid].get("referred_by")
                if ref_id and ref_id in users_db:
                    commission = rate * 0.01
                    users_db[ref_id]["balance"] += commission
                    users_db[ref_id]["refer_income"] = users_db[ref_id].get("refer_income", 0.0) + commission
                    try: bot.send_message(ref_id, f"💰 রেফারেল কমিশন! আপনার রেফার করা মেম্বারের কাজ থেকে ১% কমিশন (৳{commission:.4f}) অ্যাকাউন্টে যোগ হয়েছে।")
                    except: pass
                    
            history_db["approved"] += 1
            try: bot.send_message(t_uid, f"✅ আপনার সাবমিট করা কাজ (IG: `{target_ig_user}`) এপ্রুভ হয়েছে! ৳{rate:.2f} যোগ করা হয়েছে।", parse_mode="Markdown")
            except: pass
            del pending_tasks[target_ig_user]
            save_database()
            try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) # বাটনগুলো গায়েব করার জন্য
            except: pass
            bot.answer_callback_query(call.id, "✅ কাজ এপ্রুভ করা হয়েছে")
        else: bot.answer_callback_query(call.id, "⚠️ কাজ খুঁজে পাওয়া যায়নি", show_alert=True)

    elif call.data.startswith('adm_rej_'):
        target_ig_user = call.data.split('_')[-1]
        if target_ig_user in pending_tasks:
            t_uid = pending_tasks[target_ig_user]["user_id"]
            if t_uid in users_db:
                if users_db[t_uid]["review_tasks"] > 0: users_db[t_uid]["review_tasks"] -= 1
            history_db["rejected"] += 1
            try: bot.send_message(t_uid, f"❌ আপনার সাবমিট করা কাজ (IG: `{target_ig_user}`) বাতিল করা হয়েছে।", parse_mode="Markdown")
            except: pass
            del pending_tasks[target_ig_user]
            save_database()
            try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) # বাটনগুলো গায়েব করার জন্য
            except: pass
            bot.answer_callback_query(call.id, "❌ কাজ রিজেক্ট করা হয়েছে")
        else: bot.answer_callback_query(call.id, "⚠️ কাজ খুঁজে পাওয়া যায়নি", show_alert=True)

    elif call.data.startswith('fb_apr_'):
        fb_uid_key = call.data.replace('fb_apr_', '')
        if fb_uid_key in fb_pending_tasks:
            task = fb_pending_tasks[fb_uid_key]
            t_uid = task["user_id"]
            rate = task.get("rate", global_config.get("rate_facebook", 4.50))
            if t_uid in users_db:
                users_db[t_uid]["balance"] += rate
                users_db[t_uid]["total_income"] += rate
                users_db[t_uid]["completed_tasks"] += 1
                if users_db[t_uid]["review_tasks"] > 0: users_db[t_uid]["review_tasks"] -= 1
                
                ref_id = users_db[t_uid].get("referred_by")
                if ref_id and ref_id in users_db:
                    commission = rate * 0.01
                    users_db[ref_id]["balance"] += commission
                    users_db[ref_id]["refer_income"] = users_db[ref_id].get("refer_income", 0.0) + commission
                    try: bot.send_message(ref_id, f"💰 রেফারেল কমিশন! আপনার রেফার করা মেম্বারের ফেসবুক কাজ থেকে ১০% কমিশন (৳{commission:.4f}) অ্যাকাউন্টে যোগ হয়েছে।")
                    except: pass
                    
            history_db["approved"] += 1
            try: bot.send_message(t_uid, f"✅ আপনার সাবমিট করা ফেসবুক কাজ (UID: `{fb_uid_key}`) এপ্রুভ হয়েছে! ৳{rate:.2f} যোগ করা হয়েছে।", parse_mode="Markdown")
            except: pass
            del fb_pending_tasks[fb_uid_key]
            save_database()
            try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) # বাটনগুলো গায়েব করার জন্য
            except: pass
            bot.answer_callback_query(call.id, "✅ ফেসবুক কাজ এপ্রুভড")
        else: bot.answer_callback_query(call.id, "⚠️ ফেসবুক কাজ খুঁজে পাওয়া যায়নি", show_alert=True)

    elif call.data.startswith('fb_rej_'):
        fb_uid_key = call.data.replace('fb_rej_', '')
        if fb_uid_key in fb_pending_tasks:
            t_uid = fb_pending_tasks[fb_uid_key]["user_id"]
            if t_uid in users_db:
                if users_db[t_uid]["review_tasks"] > 0: users_db[t_uid]["review_tasks"] -= 1
            history_db["rejected"] += 1
            try: bot.send_message(t_uid, f"❌ আপনার সাবমিট করা ফেসবুক কাজ (UID: `{fb_uid_key}`) রিজেক্ট করা হয়েছে।", parse_mode="Markdown")
            except: pass
            del fb_pending_tasks[fb_uid_key]
            save_database()
            try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) # বাটনগুলো গায়েব করার জন্য
            except: pass
            bot.answer_callback_query(call.id, "❌ ফেসবুক কাজ রিজেক্টেড")
        else: bot.answer_callback_query(call.id, "⚠️ ফেসবুক কাজ খুঁজে পাওয়া যায়নি", show_alert=True)

    elif call.data.startswith('wd_pay_'):
        wd_id = call.data.replace('wd_pay_', '')
        if wd_id in pending_withdraws:
            wd_data = pending_withdraws[wd_id]
            t_uid = wd_data["user_id"]
            if t_uid in users_db:
                users_db[t_uid]["pending_withdraw"] = max(0.0, users_db[t_uid]["pending_withdraw"] - wd_data["full_deduction"])
            try: bot.send_message(t_uid, f"🎉 অভিনন্দন! আপনার ৳{wd_data['amount']:.2f} উইথড্র রিকোয়েস্টটি সফলভাবে পরিশোধ (Paid) করা হয়েছে।")
            except: pass
            del pending_withdraws[wd_id]
            save_database()
            try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
            except: pass
            bot.answer_callback_query(call.id, "✅ Paid (Success)")
        else: bot.answer_callback_query(call.id, "⚠️ রিকোয়েস্ট ডাটা পাওয়া যায়নি!", show_alert=True)

    elif call.data.startswith('wd_rej_'):
        wd_id = call.data.replace('wd_rej_', '')
        if wd_id in pending_withdraws:
            wd_data = pending_withdraws[wd_id]
            t_uid = wd_data["user_id"]
            if t_uid in users_db:
                users_db[t_uid]["balance"] += wd_data["full_deduction"]
                users_db[t_uid]["pending_withdraw"] = max(0.0, users_db[t_uid]["pending_withdraw"] - wd_data["full_deduction"])
            try: bot.send_message(t_uid, f"❌ আপনার ৳{wd_data['amount']:.2f} উইথড্র রিকোয়েস্টটি রিজেক্ট/বাতিল করা হয়েছে এবং ব্যালেন্স ফেরত দেওয়া হয়েছে।")
            except: pass
            del pending_withdraws[wd_id]
            save_database()
            try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
            except: pass
            bot.answer_callback_query(call.id, "❌ Cancelled")
        else: bot.answer_callback_query(call.id, "⚠️ রিকোয়েস্ট ডাটা পাওয়া যায়নি!", show_alert=True)

    elif call.data.startswith('wd_back_'):
        wd_id = call.data.replace('wd_back_', '')
        if wd_id in pending_withdraws:
            wd_data = pending_withdraws[wd_id]
            t_uid = wd_data["user_id"]
            if t_uid in users_db:
                users_db[t_uid]["balance"] += wd_data["full_deduction"]
                users_db[t_uid]["pending_withdraw"] = max(0.0, users_db[t_uid]["pending_withdraw"] - wd_data["full_deduction"])
            try: bot.send_message(t_uid, f"🔄 আপনার উইথড্র রিকোয়েস্ট বাতিল করে ফি সহ ৳{wd_data['full_deduction']:.2f} আপনার মেইন ব্যালেন্সে ফেরত দেওয়া হয়েছে।")
            except: pass
            del pending_withdraws[wd_id]
            save_database()
            try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
            except: pass
            bot.answer_callback_query(call.id, "🔄 Balance Returned Success")
        else: bot.answer_callback_query(call.id, "⚠️ রিকোয়েস্ট ডাটা পাওয়া যায়নি!", show_alert=True)

# --- 📱 টেক্সট ও কীবোর্ড রিকোয়েস্ট হ্যান্ডলিং ---
@bot.message_handler(func=lambda msg: True)
def handle_menu_clicks(message):
    uid = message.from_user.id
    user_data = register_user(message.from_user)
    if user_data["banned"]: return

    text = message.text

    if uid == ADMIN_ID and message.chat.id in admin_states and admin_states[message.chat.id].startswith("change_rate_"):
        if text == "❌ বাতিল":
            del admin_states[message.chat.id]
            start_command(message)
            return
        job_type = admin_states[message.chat.id].replace("change_rate_", "")
        try:
            new_rate = float(text.strip())
            global_config[f"rate_{job_type}"] = new_rate
            save_database()
            del admin_states[message.chat.id]
            bot.send_message(ADMIN_ID, f"✅ সফলভাবে **{job_type.upper()}** কাজের রেট পরিবর্তন হয়ে **৳{new_rate:.2f}** হয়েছে।", reply_markup=get_combined_menu(ADMIN_ID))
        except:
            bot.send_message(ADMIN_ID, "⚠️ ভুল ইনপুট! দয়া করে শুধুমাত্র সংখ্যায় রেটটি লিখুন (যেমন: 4.50):")
        return

    if uid == ADMIN_ID and message.chat.id in admin_states and admin_states[message.chat.id] == "change_task_password":
        if text == "❌ বাতিল":
            del admin_states[message.chat.id]
            start_command(message)
            return
        new_pass = text.strip()
        global_config["task_password"] = new_pass
        save_database()
        del admin_states[message.chat.id]
        bot.send_message(ADMIN_ID, f"✅ **কাজের পাসওয়ার্ড সফলভাবে আপডেট হয়েছে!**\nএখন থেকে সব কাজের নিচে পাসওয়ার্ড হিসেবে শো করবে: `{new_pass}`", reply_markup=get_combined_menu(ADMIN_ID), parse_mode="Markdown")
        return

    if not is_user_joined(uid):
        send_join_request(message.chat.id)
        return

    if text == "👶 আমি নতুন":
        help_kb = types.InlineKeyboardMarkup(row_width=1)
        help_kb.add(types.InlineKeyboardButton("📢 অফিশিয়াল চ্যানেল", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"))
        bot.send_message(
            message.chat.id, 
            "কাজের ভিডিও বা কাজ নিয়ে যত কিছু প্রশ্ন আসে সব আমাদের অফিসিয়াল চ্যানেলে পাওয়া যাবে।", 
            reply_markup=help_kb
        )
        return

    if uid == ADMIN_ID:
        if text == "📊 Dashboard >":
            total_users = len(users_db)
            total_bal = sum(u["balance"] for u in users_db.values())
            total_p_wd = sum(u.get("pending_withdraw", 0.0) for u in users_db.values())
            dashboard = (
                f"📊 **বট ড্যাশবোর্ড ওভারভিউ:**\n━━━━━━━━━━━━━━━━━━\n"
                f"👥 মোট মেম্বার: {total_users} জন\n⏳ মোট পেন্ডিং কাজ (IG): {len(pending_tasks)} টি\n"
                f"⏳ মোট পেন্ডিং কাজ (FB): {len(fb_pending_tasks)} টি\n"
                f"💰 মেম্বারদের মোট মেইন ব্যালেন্স: ৳{total_bal:.2f}\n🏧 মোট পেন্ডিং উইথড্র: ৳{total_p_wd:.2f}\n"
                f"🔒 টাস্ক পাসওয়ার্ড: `{global_config.get('task_password', 'Emon@7')}`\n"
                f"📸 IG রেট: ৳{global_config.get('rate_instagram', 3.0):.2f} | {'🟢 চালু' if global_config.get('status_instagram', True) else '🔴 বন্ধ'}\n"
                f"📩 Gmail রেট: ৳{global_config.get('rate_gmail', 5.0):.2f} | {'🟢 চালু' if global_config.get('status_gmail', True) else '🔴 বন্ধ'}\n"
                f"🔵 FB রেট: ৳{global_config.get('rate_facebook', 4.50):.2f} | {'🟢 চালু' if global_config.get('status_facebook', True) else '🔴 বন্ধ'}\n"
                f"━━━━━━━━━━━━━━━━━━\n✅ টোটাল এপ্রুভড: {history_db['approved']} টি\n❌ টোটাল রিজেক্টেড: {history_db['rejected']} টি"
            )
            bot.send_message(ADMIN_ID, dashboard, parse_mode="Markdown")
            return

        elif text == "⚙️ Change Task Pass":
            admin_states[message.chat.id] = "change_task_password"
            c_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            c_kb.add(types.KeyboardButton("❌ বাতিল"))
            bot.send_message(ADMIN_ID, f"🔑 **কাজের কাস্টম পাসওয়ার্ড লিখুন:**\n(বর্তমান সেট করা আছে: `{global_config.get('task_password', 'Emon@7')}`)\n\nআপনি এখানে যা লিখে দেবেন সকল ইউজারের কাজের নিচে সেই পাসওয়ার্ডটি অটোমেটিক সেট হয়ে যাবে।", reply_markup=c_kb, parse_mode="Markdown")
            return

        elif text == "🏧 Withdraw Request/":
            if not pending_withdraws:
                bot.send_message(ADMIN_ID, "📭 বর্তমানে কোনো উইথড্র রিকোয়েস্ট পেন্ডিং নেই।")
                return
            bot.send_message(ADMIN_ID, f"🏧 **মোট পেন্ডিং উইথড্র:** {len(pending_withdraws)} টি")
            for wd_id, data in list(pending_withdraws.items()):
                wd_kb = types.InlineKeyboardMarkup(row_width=3)
                wd_kb.add(
                    types.InlineKeyboardButton("✅ Paid", callback_data=f"wd_pay_{wd_id}"), 
                    types.InlineKeyboardButton("❌ Cancel", callback_data=f"wd_rej_{wd_id}"),
                    types.InlineKeyboardButton("🔄 Balance Back", callback_data=f"wd_back_{wd_id}")
                )
                details = f"👤 মেম্বার: @{data['tg_username']}\n💰 মেথড: {data['method'].upper()}\n💵 উইথড্র অ্যামাউন্ট: ৳{data['amount']:.2f}\n📉 ফি সহ মোটূর্তন: ৳{data['full_deduction']:.2f}\n📱 পেমেন্ট নম্বর: `{data['number']}`"
                bot.send_message(ADMIN_ID, details, reply_markup=wd_kb, parse_mode="Markdown")
            return

        elif text == "✅ Approval All /":
            c_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            c_kb.add(types.KeyboardButton("❌ বাতিল"))
            msg = bot.send_message(ADMIN_ID, "📝 **যেসব IG Username অথবা Facebook UID বাল্ক এপ্রুভ করতে চান, প্রতি লাইনে একটি করে দিন:**\n\n(উদাহরণ):\n61591762949874\npriya917716\n61591762949718", reply_markup=c_kb)
            bot.register_next_step_handler(msg, admin_process_bulk_approve)
            return

        elif text == "❌ Rejected All /":
            c_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            c_kb.add(types.KeyboardButton("❌ বাতিল"))
            msg = bot.send_message(ADMIN_ID, "📝 **যেসব IG Username অথবা Facebook UID বাল্ক রিজেক্ট করতে চান, প্রতি লাইনে একটি করে দিন:**\n\n(উদাহরণ):\n61591762949874\npriya917716", reply_markup=c_kb)
            bot.register_next_step_handler(msg, admin_process_bulk_reject)
            return

        elif text == "🔧 Task Switch/":
            status_ig = "🟢 ON" if global_config.get("status_instagram", True) else "🔴 OFF"
            status_gm = "🟢 ON" if global_config.get("status_gmail", True) else "🔴 OFF"
            status_fb = "🟢 ON" if global_config.get("status_facebook", True) else "🔴 OFF"
            sw_kb = types.InlineKeyboardMarkup(row_width=1)
            sw_kb.add(
                types.InlineKeyboardButton(f"📸 Instagram Task: {status_ig}", callback_data="tswitch_instagram"),
                types.InlineKeyboardButton(f"📩 Gmail Task: {status_gm}", callback_data="tswitch_gmail"),
                types.InlineKeyboardButton(f"🔵 Facebook Task: {status_fb}", callback_data="tswitch_facebook")
            )
            bot.send_message(ADMIN_ID, "🔧 **ইন্ডিভিজুয়ালি কাজ অন/অф করতে নিচের বাটনে ক্লিক করুন:**", reply_markup=sw_kb, parse_mode="Markdown")
            return

        elif text == "📢 Broadcast/":
            c_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            c_kb.add(types.KeyboardButton("❌ বাতিল"))
            msg = bot.send_message(ADMIN_ID, "📢 **সব মেম্বারকে পাঠানোর জন্য আপনার নোটিশ/মেসেজটি লিখুন:**", reply_markup=c_kb, parse_mode="Markdown")
            bot.register_next_step_handler(msg, admin_broadcast_process)
            return

        elif text == "🔍 Search User/":
            c_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            c_kb.add(types.KeyboardButton("❌ বাতিল"))
            msg = bot.send_message(ADMIN_ID, "🔍 **ইউজারের Telegram ID অথবা @Username টি ইনপুট দিন:**", reply_markup=c_kb)
            bot.register_next_step_handler(msg, admin_search_user_process)
            return

        elif text == "⚙️ Change Rate/":
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton(f"📸 Instagram (Current: {global_config.get('rate_instagram', 3.0)}৳)", callback_data="crate_instagram"),
                types.InlineKeyboardButton(f"📧 Gmail (Current: {global_config.get('rate_gmail', 5.0)}৳)", callback_data="crate_gmail"),
                types.InlineKeyboardButton(f"🔵 Facebook (Current: {global_config.get('rate_facebook', 4.50)}৳)", callback_data="crate_facebook"),
                types.InlineKeyboardButton("❌ Cancel", callback_data="close_admin_inline")
            )
            bot.send_message(ADMIN_ID, "⚙️ **কোন কাজের রেট পরিবর্তন করতে চান? সিলেক্ট করুন:**", reply_markup=markup, parse_mode="Markdown")
            return

        elif text == "📋 Pending Tasks/":
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("📸 Instagram কাজ pending", callback_data="show_p_instagram"),
                types.InlineKeyboardButton("📧 Gmail কাজ pending", callback_data="show_p_gmail"),
                types.InlineKeyboardButton("🔵 Facebook কাজ pending", callback_data="show_p_facebook"),
                types.InlineKeyboardButton("❌ Cancel", callback_data="close_admin_inline")
            )
            bot.send_message(ADMIN_ID, "📋 **কোন কাজের পেন্ডিং লিস্ট দেখতে চান? সিলেক্ট করুন:**", reply_markup=markup, parse_mode="Markdown")
            return

        elif text == "💰 addbalance/":
            c_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            c_kb.add(types.KeyboardButton("❌ বাতিল"))
            msg = bot.send_message(ADMIN_ID, "💰 **ব্যালেন্স অ্যাড করতে ইউজারের ID এবং অ্যামাউন্ট দিন (যেমন: 7036481355 50):**", reply_markup=c_kb)
            bot.register_next_step_handler(msg, admin_add_balance_process)
            return

        elif text == "📉 cutbalance/":
            c_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            c_kb.add(types.KeyboardButton("❌ বাতিল"))
            msg = bot.send_message(ADMIN_ID, "📉 **ব্যালেন্স কাটতে ইউজারের ID এবং অ্যামাউন্ট দিন (যেমন: 7036481355 20):**", reply_markup=c_kb)
            bot.register_next_step_handler(msg, admin_cut_balance_process)
            return

        elif text == "🚫 banuser/":
            c_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            c_kb.add(types.KeyboardButton("❌ বাতিল"))
            msg = bot.send_message(ADMIN_ID, "🚫 **ব্যান করতে ইউজারের Telegram ID দিন:**", reply_markup=c_kb)
            bot.register_next_step_handler(msg, admin_ban_user_process)
            return

        elif text == "🔓 unbanuser/":
            c_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            c_kb.add(types.KeyboardButton("❌ বাতিল"))
            msg = bot.send_message(ADMIN_ID, "🔓 **আনব্যান করতে ইউজারের Telegram ID দিন:**", reply_markup=c_kb)
            bot.register_next_step_handler(msg, admin_unban_user_process)
            return

        elif text == "📋 User list /":
            total_u = len(users_db)
            if total_u == 0:
                bot.send_message(ADMIN_ID, "👤 ডাটাবেজে বর্তমানে কোনো ইউজার নেই।")
                return
            list_msg = f"👥 ✨ **Premium Registered User List** ✨ 👥\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            serial = 1
            for u_id, u_info in users_db.items():
                list_msg += f"🏅 `{serial:02d}`. 👤 ID: `{u_id}` | `@{u_info['username']}` | 💰 Balance: `৳{u_info['balance']:.2f}`\n"
                serial += 1
                if len(list_msg) > 3500:
                    bot.send_message(ADMIN_ID, list_msg, parse_mode="Markdown")
                    list_msg = ""
            if list_msg:
                list_msg += f"\n━━━━━━━━━━━━━━━━━━━━━━━\n📈 *Total Members Across System:* `{total_u}` 👑"
                bot.send_message(ADMIN_ID, list_msg, parse_mode="Markdown")
            return

        elif text == "📊 Sit list >":
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("📸 Instagram কাজ List", callback_data="sit_list_instagram"),
                types.InlineKeyboardButton("📧 Gmail কাজ List", callback_data="sit_list_gmail"),
                types.InlineKeyboardButton("🔵 Facebook কাজ List", callback_data="sit_list_facebook"),
                types.InlineKeyboardButton("❌ Cancel", callback_data="close_admin_inline")
            )
            bot.send_message(ADMIN_ID, "📊 **Sit List মেনু: পেন্ডিং কাজ এক ক্লিকে ফোনে সিরিয়াল করতে অপশন বেছে নিন:**", reply_markup=markup, parse_mode="Markdown")
            return

    # --- মেম্বারদের বাটন অপশন সমূহ ---
    if text == "💵 ব্যালেন্স >":
        balance_design = (
            f"💵 **আপনার ব্যালেন্স**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵ব্যালেন্স: {user_data['balance']:.2f} BDT\n"
            f"💸পেন্ডিং (উইথড্র): {user_data.get('pending_withdraw', 0.0):.2f} BDT\n"
            f"💰Total Income: {user_data.get('total_income', 0.0):.2f} BDT\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅সম্পন্ন কাজ: {user_data['completed_tasks']} টি\n"
            f"⏳রিভিউতে আছে: {user_data['review_tasks']} টি"
        )
        bot.send_message(message.chat.id, balance_design, parse_mode="Markdown")

    elif text == "💬 সাপোর্ট >":
        support_design = (
            f"📞 **গ্রাহক সেবা কেন্দ্র**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"সম্মানিত মেম্বার,\n"
            f"আপনার যেকোনো সমস্যা বা জিজ্ঞাসার জন্য আমাদের সাপোর্ট টিমের সাথে যোগাযোগ করুন। আমরা দ্রুত সমাধানের চেষ্টা করব।\n\n"
            f"⚠️ **নোট:** অযথা মেসেজ দেওয়া থেকে বিরত থাকুন।\n"
            f"ধন্যবাদ!"
        )
        sup_kb = types.InlineKeyboardMarkup(row_width=1)
        sup_kb.add(
            types.InlineKeyboardButton("✅ 🧑‍✈️ অ্যাডমিন সাপোর্ট", url="https://t.me/helptg10"),
            types.InlineKeyboardButton("📢 অফিশিয়াল চ্যানেল", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}")
        )
        bot.send_message(message.chat.id, support_design, reply_markup=sup_kb, parse_mode="Markdown")

    elif text == "🎁 My Referrals >":
        ref_link = f"https://t.me/{bot.get_me().username}?start={uid}"
        refer_design = (
            f"🎁 **My Referrals**\n"
            f"👤 Total Refer: {user_data.get('referrals', 0)}\n"
            f" 😃 Total Refer Income: {user_data.get('refer_income', 0.0):.2f} BDT\n"
            f"🔗 **আপনার রেফার লিংক:**\n"
            f"`{ref_link}`\n\n"
            f"ℹ️ আপনি আপনার প্রতিটি রেফারেলের সম্পূর্ণ করা কাজ থেকে আয়ের ১০% কমিশন পাবেন আজীবন।\n"
            f"📌 বিস্তারিত জানতে নিচের Rules বাটনে চাপ দিন ⤵️"
        )
        ref_kb = types.InlineKeyboardMarkup(row_width=1)
        ref_kb.add(
            types.InlineKeyboardButton("📜 Rules", callback_data="ref_rules_view"),
            types.InlineKeyboardButton("👥 Team Leaderboard", callback_data="ref_leaderboard_view")
        )
        bot.send_message(message.chat.id, refer_design, reply_markup=ref_kb, parse_mode="Markdown")

    elif text == "💰 টাকা উত্তোলন >":
        method_kb = types.InlineKeyboardMarkup(row_width=1)
        method_kb.add(
            types.InlineKeyboardButton(" bKash বিকাশ ৳ -> সর্বনিম্ন: ১০০৳", callback_data="method_bkash"),
            types.InlineKeyboardButton(" Nagad নগদ ৳ -> সর্বনিম্ন: ১০০৳", callback_data="method_nagad"),
            types.InlineKeyboardButton("⬅️ ফিরে যান", callback_data="check_join_status")
        )
        withdraw_msg = "📥 **টাকা তোলার মাধ্যম সিলেক্ট করুন:**"
        bot.send_message(message.chat.id, withdraw_msg, reply_markup=method_kb, parse_mode="Markdown")

    elif text == "📝 কাজ ▶":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        markup.add(types.KeyboardButton("📸 ইনস্টাগ্রাম কাজ >"), types.KeyboardButton("📩 Gmail কাজ"), types.KeyboardButton("🔵 Facebook কাজ"), types.KeyboardButton("❌ বাতিল"))
        bot.send_message(message.chat.id, "সিলেক্ট করুন:", reply_markup=markup)

    elif text == "🔵 Facebook কাজ" and global_config.get("status_facebook", True):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        markup.add(types.KeyboardButton("Anymail/Number 📱✉"), types.KeyboardButton("❌ বাতিল"))
        bot.send_message(message.chat.id, "🔹 সিলেক্ট করুন:", reply_markup=markup)

    elif text.startswith("Anymail/Number") and global_config.get("status_facebook", True):
        current_fb_rate = global_config.get("rate_facebook", 4.50)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        markup.add(types.KeyboardButton(f"📘 0 fnd account | {current_fb_rate:.2f} ৳"), types.KeyboardButton("🔙 ফিরে যান"))
        bot.send_message(message.chat.id, "🔹 সিলেক্ট করুন:", reply_markup=markup)

    elif text.startswith("📘 0 fnd account") and global_config.get("status_facebook", True):
        if random.choice([True, False]):
            first_name = random.choice(USA_BOYS_FIRST)
        else:
            first_name = random.choice(USA_GIRLS_FIRST)
        last_name = random.choice(USA_LAST_NAMES)
        
        password = global_config.get("task_password", "Emon@7")
        
        user_fb_session[uid] = {
            "first_name": first_name,
            "last_name": last_name,
            "password": password
        }
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        markup.add(types.KeyboardButton("Send UID"), types.KeyboardButton("❓ কিভাবে কাজ করব"), types.KeyboardButton("❌ বাতিল"))
        
        msg_text = f"👤 First name: {first_name}\n👤 Last name: {last_name}\n🔒 Password: {password}\n\n📱 উপরের তথ্য দিয়ে অ্যাকাউন্ট খুলে নিচে Send UID বাটনে চাপ দিন😁"
        bot.send_message(message.chat.id, msg_text, reply_markup=markup)

    elif text == "Send UID" and global_config.get("status_facebook", True):
        if uid not in user_fb_session:
            bot.send_message(message.chat.id, "⚠️ সেশন এক্সপায়ার হয়েছে। আবার শুরু করুন।", reply_markup=get_combined_menu(uid))
            return
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ বাতিল"))
        msg = bot.send_message(message.chat.id, "📝 আপনার ফেসবুক অ্যাকাউন্টের ১৪ থেকে ১৬ সংখ্যার UID-টি দিন:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_fb_uid_input)

    elif text == "🔙 ফিরে যান":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        markup.add(types.KeyboardButton("Anymail/Number 📱✉"), types.KeyboardButton("❌ বাতিল"))
        bot.send_message(message.chat.id, "সিলেক্ট করুন:", reply_markup=markup)

    elif text == "📸 ইনস্টাগ্রাম কাজ >" and global_config.get("status_instagram", True):
        current_rate = global_config.get("rate_instagram", 3.0)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        markup.add(types.KeyboardButton(f"📸 ইনস্টাগ্রাম 2fa (৳{current_rate:.2f})"), types.KeyboardButton("⬅️ ফিরে যান"))
        bot.send_message(message.chat.id, "🔘 সিলেক্ট করুন:", reply_markup=markup)
        
    elif text.startswith("📸 ইনস্টাগ্রাম 2fa") and global_config.get("status_instagram", True):
        gen_user = generate_indian_username()
        gen_pass = global_config.get("task_password", "Emon@7")
        user_current_acc[uid] = {"user": gen_user, "pass": gen_pass}
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        markup.add(types.KeyboardButton("🔐 2FA Set"), types.KeyboardButton("⬅️ ফিরে যান"))
        msg_text = f"👤Username: `{gen_user}`\n🔓Password: `{gen_pass}`\n\n📱উপরের বিবরণ কপি করে অ্যাকাউন্ট খুলুন। তারপর নিচে 2FA Set বাটনে ক্লিক করুন।"
        sent_msg = bot.send_message(message.chat.id, msg_text, reply_markup=markup, parse_mode="Markdown")
        user_current_acc[uid]["msg_to_delete"] = sent_msg.message_id
        
    elif text == "🔐 2FA Set" and global_config.get("status_instagram", True):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ বাতিল"))
        msg = bot.send_message(message.chat.id, "🔑 **2FA Key টি দিন:** 👇", reply_markup=markup, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_2fa_key)
        
    elif text in ["⬅️ ফিরে যান", "❌ বাতিল"]:
        if uid in user_withdraw_session: del user_withdraw_session[uid]
        if uid in user_fb_session: del user_fb_session[uid]
        if message.chat.id in admin_states: del admin_states[message.chat.id]
        start_command(message)

# --- 🔵 ফেসবুক কাজ স্টেপ-বাই-স্টেপ হ্যান্ডলিং ফাংশন ---
def process_fb_uid_input(message):
    uid = message.from_user.id
    if message.text == "❌ বাতিল" or message.text.startswith('/'):
        if uid in user_fb_session: del user_fb_session[uid]
        start_command(message)
        return
    
    fb_uid = message.text.strip()
    if not fb_uid.isdigit() or not (14 <= len(fb_uid) <= 16):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ বাতিল"))
        msg = bot.send_message(message.chat.id, "❌ ভুল UID! দয়া করে ১৪ থেকে ১৬ সংখ্যার সঠিক ফেসবুক UID দিন:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_fb_uid_input)
        return
        
    if uid in user_fb_session:
        user_fb_session[uid]["uid"] = fb_uid
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ বাতিল"))
        msg = bot.send_message(message.chat.id, "🍪 এবার আপনার ফেসবুক অ্যাকাউন্টের **Cookies** পেস্ট করুন:", reply_markup=markup, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_fb_cookies_input)

def process_fb_cookies_input(message):
    uid = message.from_user.id
    if message.text == "❌ বাতিল" or message.text.startswith('/'):
        if uid in user_fb_session: del user_fb_session[uid]
        start_command(message)
        return

    cookies_data = message.text.strip()
    if len(cookies_data) < 10:  
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ বাতিল"))
        msg = bot.send_message(message.chat.id, "❌ ভুল কুকিজ! দয়া করে সঠিক ফেসবুক কুকিজ পেস্ট করুন:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_fb_cookies_input)
        return

    if uid in user_fb_session:
        user_fb_session[uid]["cookies"] = cookies_data
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        markup.add(types.KeyboardButton("কাজ শেষ"), types.KeyboardButton("❌ বাতিল"))
        msg = bot.send_message(message.chat.id, "✅ ফেসবুক কুকিজ গ্রহণ করা হয়েছে। কাজ সম্পন্ন করতে নিচের 'কাজ শেষ' বাটনে চাপ দিন।", reply_markup=markup)
        bot.register_next_step_handler(msg, process_fb_final_submit)

def process_fb_final_submit(message):
    uid = message.from_user.id
    if message.text == "❌ বাতিল" or message.text.startswith('/'):
        if uid in user_fb_session: del user_fb_session[uid]
        start_command(message)
        return

    if message.text == "কাজ শেষ":
        if uid in user_fb_session:
            fb_data = user_fb_session[uid]
            fb_uid_key = fb_data["uid"]
            submit_rate = global_config.get("rate_facebook", 4.50)
            
            fb_pending_tasks[fb_uid_key] = {
                "user_id": uid,
                "tg_username": users_db[uid]["username"],
                "first_name": fb_data["first_name"],
                "last_name": fb_data["last_name"],
                "password": fb_data["password"],
                "cookies": fb_data.get("cookies", "N/A"),
                "rate": submit_rate
            }
            users_db[uid]["review_tasks"] += 1
            save_database()
            
            fkb = types.InlineKeyboardMarkup(row_width=2)
            fkb.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"fb_apr_{fb_uid_key}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"fb_rej_{fb_uid_key}")
            )
            admin_details = (
                f"📥 **নতুন ফেসবুক কাজ জমা এসেছে!**\n━━━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ Username: @{users_db[uid]['username']}\n"
                f"🆔 User I.D: `{uid}`\n"
                f"👤 First name: `{fb_data['first_name']}`\n"
                f"👤 Last name: `{fb_data['last_name']}`\n"
                f"🔒 Password: `{fb_data['password']}`\n"
                f"🔵 Facebook UID: `{fb_uid_key}`\n"
                f"🍪 Cookies:\n`{fb_data.get('cookies', 'N/A')}`"
            )
            bot.send_message(ADMIN_ID, admin_details, reply_markup=fkb, parse_mode="Markdown")
            
            del user_fb_session[uid]
            bot.send_message(message.chat.id, "✅ আপনার কাজ সম্পন্ন হয়েছে!\n\nএটি এডমিন প্যানেলে রিভিউতে আছে। সব ঠিক থাকলে ১২-৭২ ঘণ্টার মধ্যে পেমেন্ট আপনার ব্যালেন্সে যুক্ত করে দেওয়া হবে।", reply_markup=get_combined_menu(uid))
        else:
            bot.send_message(message.chat.id, "⚠️ সেশন এক্সপায়ার হয়েছে। আবার শুরু করুন।", reply_markup=get_combined_menu(uid))

# --- বাল্ক বা অল প্রসেসিং লজিক ---
def admin_process_bulk_approve(message):
    if message.text == "❌ বাতিল":
        start_command(message)
        return
    lines = message.text.split('\n')
    approved_count = 0
    not_found = []
    
    for line in lines:
        target_id_key = line.strip()
        if not target_id_key: continue
        
        if target_id_key in fb_pending_tasks:
            task = fb_pending_tasks[target_id_key]
            t_uid = task["user_id"]
            rate = task.get("rate", global_config.get("rate_facebook", 4.50))
            if t_uid in users_db:
                users_db[t_uid]["balance"] += rate
                users_db[t_uid]["total_income"] += rate
                users_db[t_uid]["completed_tasks"] += 1
                if users_db[t_uid]["review_tasks"] > 0: users_db[t_uid]["review_tasks"] -= 1
                
                ref_id = users_db[t_uid].get("referred_by")
                if ref_id and ref_id in users_db:
                    commission = rate * 0.01
                    users_db[ref_id]["balance"] += commission
                    users_db[ref_id]["refer_income"] = users_db[ref_id].get("refer_income", 0.0) + commission
                try: bot.send_message(t_uid, f"✅ আপনার সাবমিট করা ফেসবুক কাজ (UID: `{target_id_key}`) এপ্রুভ হয়েছে! ৳{rate:.2f} যোগ করা হয়েছে।")
                except: pass
            del fb_pending_tasks[target_id_key]
            approved_count += 1
            
        elif target_id_key in pending_tasks:
            task = pending_tasks[target_id_key]
            t_uid = task["user_id"]
            rate = task.get("rate", global_config.get("rate_instagram", 3.0))
            if t_uid in users_db:
                users_db[t_uid]["balance"] += rate
                users_db[t_uid]["total_income"] += rate
                users_db[t_uid]["completed_tasks"] += 1
                if users_db[t_uid]["review_tasks"] > 0: users_db[t_uid]["review_tasks"] -= 1
                
                ref_id = users_db[t_uid].get("referred_by")
                if ref_id and ref_id in users_db:
                    commission = rate * 0.01
                    users_db[ref_id]["balance"] += commission
                    users_db[ref_id]["refer_income"] = users_db[ref_id].get("refer_income", 0.0) + commission
                try: bot.send_message(t_uid, f"✅ আপনার সাবমিট করা কাজ ({target_id_key}) এপ্রুভ হয়েছে! ৳{rate:.2f} যোগ করা হয়েছে।")
                except: pass
            del pending_tasks[target_id_key]
            approved_count += 1
        else:
            not_found.append(target_id_key)
            
    history_db["approved"] += approved_count
    save_database()
    
    res = f"✅ সফলভাবে {approved_count}টি কাজ অল-এপ্রুভ করা হয়েছে।"
    if not_found:
        res += f"\n⚠️ এই আইডি/ইউজারনেমগুলো পেন্ডিংয়ে মিল পাওয়া যায়নি: {', '.join(not_found)}"
    bot.send_message(ADMIN_ID, res, reply_markup=get_combined_menu(ADMIN_ID))

def admin_process_bulk_reject(message):
    if message.text == "❌ বাতিল":
        start_command(message)
        return
    lines = message.text.split('\n')
    rejected_count = 0
    not_found = []
    
    for line in lines:
        target_id_key = line.strip()
        if not target_id_key: continue
        
        if target_id_key in fb_pending_tasks:
            t_uid = fb_pending_tasks[target_id_key]["user_id"]
            if t_uid in users_db:
                if users_db[t_uid]["review_tasks"] > 0: users_db[t_uid]["review_tasks"] -= 1
                try: bot.send_message(t_uid, f"❌ আপনার সাবমিট করা ফেসবুক কাজ (UID: `{target_id_key}`) বাতিল করা হয়েছে।")
                except: pass
            del fb_pending_tasks[target_id_key]
            rejected_count += 1
            
        elif target_id_key in pending_tasks:
            t_uid = pending_tasks[target_id_key]["user_id"]
            if t_uid in users_db:
                if users_db[t_uid]["review_tasks"] > 0: users_db[t_uid]["review_tasks"] -= 1
                try: bot.send_message(t_uid, f"❌ আপনার সাবমিট করা কাজ ({target_id_key}) বাতিল করা হয়েছে।")
                except: pass
            del pending_tasks[target_id_key]
            rejected_count += 1
        else:
            not_found.append(target_id_key)
            
    history_db["rejected"] += rejected_count
    save_database()
    
    res = f"❌ সফলভাবে {rejected_count}টি কাজ অল-বাতিল/রিজেক্ট করা হয়েছে।"
    if not_found:
        res += f"\n⚠️ এই আইডি/ইউজারনেমগুলো পেন্ডিংয়ে মিল পাওয়া যায়নি: {', '.join(not_found)}"
    bot.send_message(ADMIN_ID, res, reply_markup=get_combined_menu(ADMIN_ID))

# --- উইথড্র প্রসেস ---
def user_withdraw_get_number(message):
    uid = message.from_user.id
    if message.text == "❌ বাতিল" or message.text.startswith('/'):
        if uid in user_withdraw_session: del user_withdraw_session[uid]
        start_command(message)
        return
    
    num = message.text.strip()
    if not re.match(r"^01[3-9]\d{8}$", num):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ বাতিল"))
        msg = bot.send_message(message.chat.id, "❌ **ভুল নম্বর! শুধুমাত্র ১১ ডিজিটের সঠিক পেমেন্ট নম্বর দিন:**", reply_markup=markup)
        bot.register_next_step_handler(msg, user_withdraw_get_number)
        return

    user_withdraw_session[uid]["number"] = num
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("❌ বাতিল"))
    msg = bot.send_message(message.chat.id, "💵 **কত টাকা তুলতে চান তা সংখ্যায় লিখুন (ন্যূনতম ১০০ টাকা):**", reply_markup=markup)
    bot.register_next_step_handler(msg, user_withdraw_get_amount)

def user_withdraw_get_amount(message):
    uid = message.from_user.id
    if message.text == "❌ বাতিল" or message.text.startswith('/'):
        if uid in user_withdraw_session: del user_withdraw_session[uid]
        start_command(message)
        return
    try:
        amount = float(message.text.strip())
        udata = users_db[uid]
        min_required = 100.0  
        full_deduction = amount 

        if amount < min_required:
            bot.send_message(message.chat.id, f"❌ **সর্বনিম্ন উইথড্র সীমা {min_required} টাকা!**", reply_markup=get_combined_menu(uid))
            if uid in user_withdraw_session: del user_withdraw_session[uid]
            return
        if udata["balance"] < full_deduction:
            bot.send_message(message.chat.id, f"❌ **আপনার মেইন ব্যালেন্স পর্যাপ্ত নয়! প্রয়োজন ৳{full_deduction:.2f}**", reply_markup=get_combined_menu(uid))
            if uid in user_withdraw_session: del user_withdraw_session[uid]
            return

        wd_id = f"wd_{int(datetime.now().timestamp())}_{random.randint(100,999)}"
        session = user_withdraw_session[uid]
        pending_withdraws[wd_id] = {
            "user_id": uid, "tg_username": udata["username"], "method": session["method"],
            "number": session["number"], "amount": amount, "full_deduction": full_deduction
        }
        udata["pending_withdraw"] = udata.get("pending_withdraw", 0.0) + full_deduction
        udata["balance"] -= full_deduction
        save_database()
        
        bot.send_message(message.chat.id, f"✅ **আপনার উইথড্র রিকোয়েস্টটি সফল হয়েছে!**\n💰 পরিমাণ: ৳{amount:.2f}\n📱 নম্বর: `{session['number']}`", reply_markup=get_combined_menu(uid), parse_mode="Markdown")
        
        wd_kb = types.InlineKeyboardMarkup(row_width=3)
        wd_kb.add(
            types.InlineKeyboardButton("✅ Paid", callback_data=f"wd_pay_{wd_id}"), 
            types.InlineKeyboardButton("❌ Cancel", callback_data=f"wd_rej_{wd_id}"),
            types.InlineKeyboardButton("🔄 Balance Back", callback_data=f"wd_back_{wd_id}")
        )
        admin_alert = f"🏧 **নতুন উইথড্র রিকোয়েস্ট!**\n👤 মেম্বার: @{udata['username']}\n💰 মেথড: {session['method'].upper()}\n💵 পরিমাণ: ৳{amount:.2f}\n📱 নম্বর: `{session['number']}`"
        bot.send_message(ADMIN_ID, admin_alert, reply_markup=wd_kb, parse_mode="Markdown")
        del user_withdraw_session[uid]
    except:
        bot.send_message(message.chat.id, "❌ ভুল ইনপুট! শুধুমাত্র সংখ্যায় টাকার পরিমাণ লিখুন।", reply_markup=get_combined_menu(uid))
        if uid in user_withdraw_session: del user_withdraw_session[uid]

# --- অন্যান্য অ্যাডমিন ব্যাকএন্ড লজিক ---
def admin_add_balance_process(message):
    if message.text == "❌ বাতিল":
        start_command(message)
        return
    try:
        parts = message.text.split()
        target_id = int(parts[0])
        amount = float(parts[1])
        if target_id in users_db:
            users_db[target_id]["balance"] += amount
            save_database()
            bot.send_message(ADMIN_ID, f"✅ ইউজার `{target_id}` এর অ্যাকাউন্টে ৳{amount:.2f} অ্যাড করা হয়েছে।", reply_markup=get_combined_menu(ADMIN_ID), parse_mode="Markdown")
            try: bot.send_message(target_id, f"💰 অ্যাডমিন আপনার অ্যাকাউন্টে ৳{amount:.2f} যোগ করেছেন।")
            except: pass
        else:
            bot.send_message(ADMIN_ID, "❌ এই ইউজার আইডিটি ডাটাবেজে পাওয়া যায়নি।", reply_markup=get_combined_menu(ADMIN_ID))
    except:
        bot.send_message(ADMIN_ID, "❌ ফরম্যাট ভুল! সঠিক উদাহরণ: `7036481355 50`", reply_markup=get_combined_menu(ADMIN_ID), parse_mode="Markdown")

def admin_cut_balance_process(message):
    if message.text == "❌ বাতিল":
        start_command(message)
        return
    try:
        parts = message.text.split()
        target_id = int(parts[0])
        amount = float(parts[1])
        if target_id in users_db:
            users_db[target_id]["balance"] = max(0.0, users_db[target_id]["balance"] - amount)
            save_database()
            bot.send_message(ADMIN_ID, f"📉 ইউজার `{target_id}` এর অ্যাকাউন্ট থেকে ৳{amount:.2f} কেটে নেওয়া হয়েছে।", reply_markup=get_combined_menu(ADMIN_ID), parse_mode="Markdown")
            try: bot.send_message(target_id, f"📉 আপনার অ্যাকাউন্ট থেকে ৳{amount:.2f} কেটে নেওয়া হয়েছে।")
            except: pass
        else:
            bot.send_message(ADMIN_ID, "❌ এই ইউজার আইডিটি ডাটাবেজে পাওয়া যায়নি।", reply_markup=get_combined_menu(ADMIN_ID))
    except:
        bot.send_message(ADMIN_ID, "❌ ফরম্যাট ভুল! সঠিক উদাহরণ: `7036481355 20`", reply_markup=get_combined_menu(ADMIN_ID), parse_mode="Markdown")

def admin_ban_user_process(message):
    if message.text == "❌ বাতিল":
        start_command(message)
        return
    try:
        target_id = int(message.text.strip())
        if target_id in users_db:
            users_db[target_id]["banned"] = True
            save_database()
            bot.send_message(ADMIN_ID, f"🚫 ইউজার `{target_id}` সফলভাবে ব্যানড হয়েছে।", reply_markup=get_combined_menu(ADMIN_ID), parse_mode="Markdown")
        else:
            bot.send_message(ADMIN_ID, "❌ এই ইউজার আইডিটি ডাটাবেজে পাওয়া যায়নি।", reply_markup=get_combined_menu(ADMIN_ID))
    except:
        bot.send_message(ADMIN_ID, "❌ শুধুমাত্র সঠিক সংখ্যা (Telegram ID) দিন।", reply_markup=get_combined_menu(ADMIN_ID))

def admin_unban_user_process(message):
    if message.text == "❌ বাতিল":
        start_command(message)
        return
    try:
        target_id = int(message.text.strip())
        if target_id in users_db:
            users_db[target_id]["banned"] = False
            save_database()
            bot.send_message(ADMIN_ID, f"🔓 ইউজার `{target_id}` সফলভাবে আনব্যানড হয়েছে।", reply_markup=get_combined_menu(ADMIN_ID), parse_mode="Markdown")
        else:
            bot.send_message(ADMIN_ID, "❌ এই ইউজার আইডিটি ডাটাবেজে পাওয়া যায়নি।", reply_markup=get_combined_menu(ADMIN_ID))
    except:
        bot.send_message(ADMIN_ID, "❌ শুধুমাত্র সঠিক সংখ্যা (Telegram ID) দিন।", reply_markup=get_combined_menu(ADMIN_ID))

def admin_search_user_process(message):
    if message.text == "❌ বাতিল":
        start_command(message)
        return
    query = message.text.strip().lower()
    target_uid = None
    if query.isdigit(): target_uid = int(query)
    else:
        clean_username = query.replace("@", "")
        target_uid = username_to_id.get(clean_username)

    if target_uid and target_uid in users_db:
        u = users_db[target_uid]
        info = (
            f"🔍 **ইউজার ডিটেইলস পাওয়া গেছে:**\n━━━━━━━━━━━━━━━━━━\n"
            f"👤 ইউজার আইডি: `{target_uid}`\n"
            f"🏷 ইউজারনেম: @{u['username']}\n"
            f"💵 ব্যালেন্স: ৳{u['balance']:.2f}\n"
            f"⏳ পেন্ডিং উইথড্র: ৳{u.get('pending_withdraw', 0.0):.2f}\n"
            f"💰 সর্বমোট আয়: ৳{u.get('total_income', 0.0):.2f}\n"
            f"✅ সম্পন্ন কাজ: {u['completed_tasks']} টি\n"
            f"🚫 স্ট্যাটাস: {'ব্যানড (Banned)' if u.get('banned', False) else 'সক্রিয় (Active)'}"
        )
        bot.send_message(ADMIN_ID, info, reply_markup=get_combined_menu(ADMIN_ID), parse_mode="Markdown")
    else:
        bot.send_message(ADMIN_ID, "❌ দুঃখিত! ডাটাবেজে এই অ্যাকাউন্ট পাওয়া যায়নি।", reply_markup=get_combined_menu(ADMIN_ID))

def admin_broadcast_process(message):
    if message.text == "❌ বাতিল":
        start_command(message)
        return
    bot.send_message(ADMIN_ID, "⏳ ব্রডকাস্টিং শুরু হয়েছে...")
    success, fail = 0, 0
    for uid in list(users_db.keys()):
        try:
            bot.copy_message(uid, ADMIN_ID, message.message_id)
            success += 1
        except: fail += 1
    bot.send_message(ADMIN_ID, f"📢 **ব্রডকাস্ট সম্পন্ন!**\n✅ সফল: {success} জন\n❌ ব্যর্থ: {fail} জন", reply_markup=get_combined_menu(ADMIN_ID))

def process_2fa_key(message):
    if message.text in ["❌ বাতিল", "⬅️ ফিরে যান"] or message.text.startswith('/'):
        start_command(message)
        return
    raw_key = message.text.strip().replace(" ", "")
    uid = message.from_user.id
    acc_info = user_current_acc.get(uid, {"user": "N/A", "pass": "N/A"})
    ig_user = acc_info["user"]
    submit_rate = global_config.get("rate_instagram", 3.0)
    try:
        totp = pyotp.TOTP(raw_key)
        current_code = totp.now()
        pending_tasks[ig_user] = {
            "user_id": uid, "tg_username": users_db[uid]["username"],
            "generated_pass": acc_info["pass"], "key": raw_key, "code": current_code, "rate": submit_rate
        }
        users_db[uid]["review_tasks"] += 1
        save_database()
        if "msg_to_delete" in acc_info:
            try: bot.delete_message(message.chat.id, acc_info["msg_to_delete"])
            except: pass
        bot.send_message(message.chat.id, f"কোডটি কপি করুন ⤵\n\n`{current_code}`", parse_mode="Markdown")
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("✅ অ্যাকাউন্ট খোলা শেষ"))
        msg = bot.send_message(message.chat.id, "অ্যাকাউন্ট খোলা শেষ হলে নিচের বাটনে চাপ দিন:", reply_markup=markup)
        bot.register_next_step_handler(msg, lambda m: start_command(m))
    except:
        bot.send_message(message.chat.id, "❌ ভুল 2FA Key!", reply_markup=get_combined_menu(uid))

# ---- రেন্ডারের জন্য পোর্ট সচল রাখার ব্যাকগ্রাউন্ড সার্ভার ----
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer

def run_dummy_server():
    try:
        server_address = ('', 8080)
        httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
        print("Dummy port server started successfully on 8080.")
        httpd.serve_forever()
    except Exception as e:
        print(f"Port Server error: {e}")

if __name__ == '__main__':
    print("Starting background dummy web port...")
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    print("Bot is running perfectly...")
    bot.remove_webhook()
    bot.infinity_polling()
