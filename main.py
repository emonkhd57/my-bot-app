import asyncio
import io
import re
import json
import html
import os  # <--- Webhook & PORT à¦à¦° à¦œà¦¨à§à¦¯ à¦‡à¦®à§à¦ªà§‹à¦°à§à¦Ÿ à¦¯à§‹à¦— à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡
import httpx
import pyotp
import random
import string
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from telegram.error import TelegramError

# ==================== CONFIG SECTION ====================

BOT_TOKEN = "8747963961:AAF-If960VRwEjH_P3Ar6sFgFsP41oajP9M"

# ==================== VOLTX SMS API CONFIGURATION ====================
API_KEY = "M48R9YJS4ES"
BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api"
HEADERS = {"mauthapi": API_KEY, "Content-Type": "application/json"}

USER_DATA_FILE = "users.json"
PAID_SMS_FILE = "paid_sms.json"
STATS_FILE = "user_stats.json"
REFERRAL_DATA_FILE = "referral_data.json"
BANNED_USERS_FILE = "banned_users.json"
WITHDRAW_DATA_FILE = "withdraw_requests.json"
ACTIVITY_LOGS_FILE = "activity_logs.json"
DATA_RANGE_FILE = "datarange.json"
SYSTEM_CONFIG_FILE = "system_config.json"
USER_OTP_RATE_FILE = "user_otp_rates.json"
REQUIRED_CHANNELS_FILE = "required_channels.json"
FAKE_OTP_CONFIG_FILE = "fake_otp_config.json"

# ==================== MULTIPLE ADMINS CONFIGURATION ====================
ADMINS = [6129481361]

OTP_GROUP_ID = -1003364053482

# ==================== WELCOME MESSAGE CONFIGURATION ====================
WELCOME_MESSAGE = """âš¡ï¸ðŸ’Ž ð—ªð—˜ð—Ÿð—–ð—¢ð— ð—˜ ð—§ð—¢ ð—©ð—¢ð—Ÿð—§ ð—« ð—¦ð— ð—¦ ðŸ’Žâš¡ï¸

ðŸŒ Premium Virtual Number Platform
ðŸ“© Instant OTP Delivery
ðŸš€ Fast Verification Service
ðŸ” Secure & Anonymous Access

ðŸ“² Facebook â€¢ WhatsApp â€¢ Telegram â€¢ Instagram

âœ¨ And More...

ðŸ’Ž Enjoy Premium Quality Service With
âš¡ï¸ ð—©ð—¢ð—Ÿð—§ ð—« ð—¦ð— ð—¦ âš¡ï¸"""

# ==================== OTP RATE CONFIGURATION ====================
DEFAULT_OTP_RATE = 0.20

# ==================== REFERRAL / WITHDRAW CONFIGURATION ====================
REFERRAL_PRICE = 0
DEFAULT_MIN_WITHDRAW = 50
DEFAULT_MAX_WITHDRAW = 10000
DEFAULT_PAYMENT_METHODS = {
    "BKASH": True,
    "NAGAD": True,
    "ROCKET": True,
    "BINANCE": True
}

# ==================== SUPPORT & DEVELOPER LINKS ====================
SUPPORT_LINK = "https://t.me/BLACKCHATMK"
DEVELOPER_LINK = "https://t.me/Cyber982"

request_queue = asyncio.Queue()
MAX_WORKERS = 5000

client_async = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=5.0),
    headers=HEADERS,
    limits=httpx.Limits(max_connections=1000, max_keepalive_connections=200)
)

active_numbers = {}
last_range = {}
CHECK_INTERVAL = 2

# ==================== SERVICE CACHE ====================
_services_cache = {"services": {}, "timestamp": 0}
CACHE_TTL = 30

# ==================== COUNTRY HOTNESS TRACKING ====================
_country_otp_timestamps = {}
HOT_THRESHOLD = 5
HOT_WINDOW = timedelta(minutes=30)

def update_country_otp_count(number: str):
    prefix = get_country_prefix_from_number(number)
    if not prefix:
        return
    now = datetime.now()
    if prefix not in _country_otp_timestamps:
        _country_otp_timestamps[prefix] = []
    ts_list = _country_otp_timestamps[prefix]
    ts_list.append(now)
    cutoff = now - HOT_WINDOW
    _country_otp_timestamps[prefix] = [t for t in ts_list if t > cutoff]

def get_country_prefix_from_number(number: str) -> str:
    clean = re.sub(r'\D', '', str(number))
    prefixes = sorted(COUNTRY_PREFIX_MAP.keys(), key=len, reverse=True)
    for p in prefixes:
        if clean.startswith(p):
            return p
    return ""

def is_country_hot(prefix: str) -> bool:
    if prefix not in _country_otp_timestamps:
        return False
    now = datetime.now()
    cutoff = now - HOT_WINDOW
    recent = [t for t in _country_otp_timestamps[prefix] if t > cutoff]
    _country_otp_timestamps[prefix] = recent
    return len(recent) >= HOT_THRESHOLD

# ==================== COUNTRY PREFIX MAP ====================
COUNTRY_PREFIX_MAP = {
    "2376": ("ðŸ‡¨ðŸ‡²", "Cameroon"), "2250": ("ðŸ‡¨ðŸ‡®", "Ivory Coast"),
    "2613": ("ðŸ‡²ðŸ‡¬", "Madagascar"), "4077": ("ðŸ‡·ðŸ‡´", "Romania"),
    "237": ("ðŸ‡¨ðŸ‡²", "Cameroon"), "225": ("ðŸ‡¨ðŸ‡®", "Ivory Coast"),
    "261": ("ðŸ‡²ðŸ‡¬", "Madagascar"), "20": ("ðŸ‡ªðŸ‡¬", "Egypt"),
    "27": ("ðŸ‡¿ðŸ‡¦", "South Africa"), "234": ("ðŸ‡³ðŸ‡¬", "Nigeria"),
    "254": ("ðŸ‡°ðŸ‡ª", "Kenya"), "233": ("ðŸ‡¬ðŸ‡­", "Ghana"),
    "212": ("ðŸ‡²ðŸ‡¦", "Morocco"), "213": ("ðŸ‡©ðŸ‡¿", "Algeria"),
    "216": ("ðŸ‡¹ðŸ‡³", "Tunisia"), "218": ("ðŸ‡±ðŸ‡¾", "Libya"),
    "249": ("ðŸ‡¸ðŸ‡©", "Sudan"), "251": ("ðŸ‡ªðŸ‡¹", "Ethiopia"),
    "252": ("ðŸ‡¸ðŸ‡´", "Somalia"), "253": ("ðŸ‡©ðŸ‡¯", "Djibouti"),
    "255": ("ðŸ‡¹ðŸ‡¿", "Tanzania"), "256": ("ðŸ‡ºðŸ‡¬", "Uganda"),
    "257": ("ðŸ‡§ðŸ‡®", "Burundi"), "258": ("ðŸ‡²ðŸ‡¿", "Mozambique"),
    "260": ("ðŸ‡¿ðŸ‡²", "Zambia"), "263": ("ðŸ‡¿ðŸ‡¼", "Zimbabwe"),
    "264": ("ðŸ‡³ðŸ‡¦", "Namibia"), "265": ("ðŸ‡²ðŸ‡¼", "Malawi"),
    "266": ("ðŸ‡±ðŸ‡¸", "Lesotho"), "267": ("ðŸ‡§ðŸ‡¼", "Botswana"),
    "268": ("ðŸ‡¸ðŸ‡¿", "Eswatini"), "269": ("ðŸ‡°ðŸ‡²", "Comoros"),
    "220": ("ðŸ‡¬ðŸ‡²", "Gambia"), "221": ("ðŸ‡¸ðŸ‡³", "Senegal"),
    "222": ("ðŸ‡²ðŸ‡·", "Mauritania"), "223": ("ðŸ‡²ðŸ‡±", "Mali"),
    "224": ("ðŸ‡¬ðŸ‡³", "Guinea"), "226": ("ðŸ‡§ðŸ‡«", "Burkina Faso"),
    "227": ("ðŸ‡³ðŸ‡ª", "Niger"), "228": ("ðŸ‡¹ðŸ‡¬", "Togo"),
    "229": ("ðŸ‡§ðŸ‡¯", "Benin"), "230": ("ðŸ‡²ðŸ‡º", "Mauritius"),
    "231": ("ðŸ‡±ðŸ‡·", "Liberia"), "232": ("ðŸ‡¸ðŸ‡±", "Sierra Leone"),
    "235": ("ðŸ‡¹ðŸ‡©", "Chad"), "236": ("ðŸ‡¨ðŸ‡«", "Central African Republic"),
    "238": ("ðŸ‡¨ðŸ‡»", "Cape Verde"), "239": ("ðŸ‡¸ðŸ‡¹", "Sao Tome and Principe"),
    "240": ("ðŸ‡¬ðŸ‡¶", "Equatorial Guinea"), "241": ("ðŸ‡¬ðŸ‡¦", "Gabon"),
    "242": ("ðŸ‡¨ðŸ‡¬", "Congo"), "243": ("ðŸ‡¨ðŸ‡©", "DR Congo"),
    "244": ("ðŸ‡¦ðŸ‡´", "Angola"), "245": ("ðŸ‡¬ðŸ‡¼", "Guinea-Bissau"),
    "247": ("ðŸ‡¸ðŸ‡­", "Saint Helena"), "248": ("ðŸ‡¸ðŸ‡¨", "Seychelles"),
    "250": ("ðŸ‡·ðŸ‡¼", "Rwanda"), "290": ("ðŸ‡¸ðŸ‡­", "Saint Helena"),
    "291": ("ðŸ‡ªðŸ‡·", "Eritrea"), "40": ("ðŸ‡·ðŸ‡´", "Romania"),
    "44": ("ðŸ‡¬ðŸ‡§", "United Kingdom"), "33": ("ðŸ‡«ðŸ‡·", "France"),
    "49": ("ðŸ‡©ðŸ‡ª", "Germany"), "39": ("ðŸ‡®ðŸ‡¹", "Italy"),
    "34": ("ðŸ‡ªðŸ‡¸", "Spain"), "31": ("ðŸ‡³ðŸ‡±", "Netherlands"),
    "32": ("ðŸ‡§ðŸ‡ª", "Belgium"), "41": ("ðŸ‡¨ðŸ‡­", "Switzerland"),
    "43": ("ðŸ‡¦ðŸ‡¹", "Austria"), "46": ("ðŸ‡¸ðŸ‡ª", "Sweden"),
    "47": ("ðŸ‡³ðŸ‡´", "Norway"), "45": ("ðŸ‡©ðŸ‡°", "Denmark"),
    "358": ("ðŸ‡«ðŸ‡®", "Finland"), "351": ("ðŸ‡µðŸ‡¹", "Portugal"),
    "353": ("ðŸ‡®ðŸ‡ª", "Ireland"), "36": ("ðŸ‡­ðŸ‡º", "Hungary"),
    "48": ("ðŸ‡µðŸ‡±", "Poland"), "380": ("ðŸ‡ºðŸ‡¦", "Ukraine"),
    "370": ("ðŸ‡±ðŸ‡¹", "Lithuania"), "371": ("ðŸ‡±ðŸ‡»", "Latvia"),
    "372": ("ðŸ‡ªðŸ‡ª", "Estonia"), "373": ("ðŸ‡²ðŸ‡©", "Moldova"),
    "374": ("ðŸ‡¦ðŸ‡²", "Armenia"), "375": ("ðŸ‡§ðŸ‡¾", "Belarus"),
    "376": ("ðŸ‡¦ðŸ‡©", "Andorra"), "377": ("ðŸ‡²ðŸ‡¨", "Monaco"),
    "381": ("ðŸ‡·ðŸ‡¸", "Serbia"), "382": ("ðŸ‡²ðŸ‡ª", "Montenegro"),
    "385": ("ðŸ‡­ðŸ‡·", "Croatia"), "386": ("ðŸ‡¸ðŸ‡®", "Slovenia"),
    "387": ("ðŸ‡§ðŸ‡¦", "Bosnia and Herzegovina"), "389": ("ðŸ‡²ðŸ‡°", "North Macedonia"),
    "350": ("ðŸ‡¬ðŸ‡®", "Gibraltar"), "352": ("ðŸ‡±ðŸ‡º", "Luxembourg"),
    "354": ("ðŸ‡®ðŸ‡¸", "Iceland"), "355": ("ðŸ‡¦ðŸ‡±", "Albania"),
    "356": ("ðŸ‡²ðŸ‡¹", "Malta"), "357": ("ðŸ‡¨ðŸ‡¾", "Cyprus"),
    "359": ("ðŸ‡§ðŸ‡¬", "Bulgaria"), "421": ("ðŸ‡¸ðŸ‡°", "Slovakia"),
    "420": ("ðŸ‡¨ðŸ‡¿", "Czech Republic"), "298": ("ðŸ‡«ðŸ‡´", "Faroe Islands"),
    "299": ("ðŸ‡¬ðŸ‡±", "Greenland"), "1": ("ðŸ‡ºðŸ‡¸", "United States"),
    "7": ("ðŸ‡·ðŸ‡º", "Russia"), "91": ("ðŸ‡®ðŸ‡³", "India"),
    "92": ("ðŸ‡µðŸ‡°", "Pakistan"), "880": ("ðŸ‡§ðŸ‡©", "Bangladesh"),
    "86": ("ðŸ‡¨ðŸ‡³", "China"), "81": ("ðŸ‡¯ðŸ‡µ", "Japan"),
    "82": ("ðŸ‡°ðŸ‡·", "South Korea"), "84": ("ðŸ‡»ðŸ‡³", "Vietnam"),
    "66": ("ðŸ‡¹ðŸ‡­", "Thailand"), "62": ("ðŸ‡®ðŸ‡©", "Indonesia"),
    "60": ("ðŸ‡²ðŸ‡¾", "Malaysia"), "65": ("ðŸ‡¸ðŸ‡¬", "Singapore"),
    "63": ("ðŸ‡µðŸ‡­", "Philippines"), "95": ("ðŸ‡²ðŸ‡²", "Myanmar"),
    "94": ("ðŸ‡±ðŸ‡°", "Sri Lanka"), "977": ("ðŸ‡³ðŸ‡µ", "Nepal"),
    "93": ("ðŸ‡¦ðŸ‡«", "Afghanistan"), "98": ("ðŸ‡®ðŸ‡·", "Iran"),
    "90": ("ðŸ‡¹ðŸ‡·", "Turkey"), "964": ("ðŸ‡®ðŸ‡¶", "Iraq"),
    "963": ("ðŸ‡¸ðŸ‡¾", "Syria"), "961": ("ðŸ‡±ðŸ‡§", "Lebanon"),
    "962": ("ðŸ‡¯ðŸ‡´", "Jordan"), "965": ("ðŸ‡°ðŸ‡¼", "Kuwait"),
    "966": ("ðŸ‡¸ðŸ‡¦", "Saudi Arabia"), "967": ("ðŸ‡¾ðŸ‡ª", "Yemen"),
    "968": ("ðŸ‡´ðŸ‡²", "Oman"), "971": ("ðŸ‡¦ðŸ‡ª", "UAE"),
    "972": ("ðŸ‡®ðŸ‡±", "Israel"), "973": ("ðŸ‡§ðŸ‡­", "Bahrain"),
    "974": ("ðŸ‡¶ðŸ‡¦", "Qatar"), "994": ("ðŸ‡¦ðŸ‡¿", "Azerbaijan"),
    "995": ("ðŸ‡¬ðŸ‡ª", "Georgia"), "996": ("ðŸ‡°ðŸ‡¬", "Kyrgyzstan"),
    "992": ("ðŸ‡¹ðŸ‡¯", "Tajikistan"), "993": ("ðŸ‡¹ðŸ‡²", "Turkmenistan"),
    "998": ("ðŸ‡ºðŸ‡¿", "Uzbekistan"), "855": ("ðŸ‡°ðŸ‡­", "Cambodia"),
    "856": ("ðŸ‡±ðŸ‡¦", "Laos"), "976": ("ðŸ‡²ðŸ‡³", "Mongolia"),
    "850": ("ðŸ‡°ðŸ‡µ", "North Korea"), "55": ("ðŸ‡§ðŸ‡·", "Brazil"),
    "52": ("ðŸ‡²ðŸ‡½", "Mexico"), "54": ("ðŸ‡¦ðŸ‡·", "Argentina"),
    "57": ("ðŸ‡¨ðŸ‡´", "Colombia"), "51": ("ðŸ‡µðŸ‡ª", "Peru"),
    "58": ("ðŸ‡»ðŸ‡ª", "Venezuela"), "56": ("ðŸ‡¨ðŸ‡±", "Chile"),
    "593": ("ðŸ‡ªðŸ‡¨", "Ecuador"), "591": ("ðŸ‡§ðŸ‡´", "Bolivia"),
    "595": ("ðŸ‡µðŸ‡¾", "Paraguay"), "598": ("ðŸ‡ºðŸ‡¾", "Uruguay"),
    "502": ("ðŸ‡¬ðŸ‡¹", "Guatemala"), "503": ("ðŸ‡¸ðŸ‡»", "El Salvador"),
    "504": ("ðŸ‡­ðŸ‡³", "Honduras"), "506": ("ðŸ‡¨ðŸ‡·", "Costa Rica"),
    "507": ("ðŸ‡µðŸ‡¦", "Panama"), "509": ("ðŸ‡­ðŸ‡¹", "Haiti"),
    "501": ("ðŸ‡§ðŸ‡¿", "Belize"), "61": ("ðŸ‡¦ðŸ‡º", "Australia"),
    "64": ("ðŸ‡³ðŸ‡¿", "New Zealand"), "675": ("ðŸ‡µðŸ‡¬", "Papua New Guinea"),
    "679": ("ðŸ‡«ðŸ‡¯", "Fiji"), "1246": ("ðŸ‡§ðŸ‡§", "Barbados"),
    "1876": ("ðŸ‡¯ðŸ‡²", "Jamaica"), "53": ("ðŸ‡¨ðŸ‡º", "Cuba"),
    "592": ("ðŸ‡¬ðŸ‡¾", "Guyana"),
}

def get_country_by_prefix(prefix: str):
    if prefix in COUNTRY_PREFIX_MAP:
        return COUNTRY_PREFIX_MAP[prefix]
    sorted_prefixes = sorted(COUNTRY_PREFIX_MAP.keys(), key=len, reverse=True)
    for p in sorted_prefixes:
        if prefix.startswith(p):
            return COUNTRY_PREFIX_MAP[p]
    return ("ðŸŒ", "Unknown")

# ==================== SYSTEM CONFIG ====================
def load_system_config():
    if not os.path.exists(SYSTEM_CONFIG_FILE):
        default_config = {
            "min_withdraw": DEFAULT_MIN_WITHDRAW,
            "max_withdraw": DEFAULT_MAX_WITHDRAW,
            "payment_methods": DEFAULT_PAYMENT_METHODS.copy(),
            "otp_rate": DEFAULT_OTP_RATE
        }
        save_system_config(default_config)
        return default_config
    try:
        with open(SYSTEM_CONFIG_FILE, "r") as f:
            config = json.load(f)
            if "otp_rate" not in config:
                config["otp_rate"] = DEFAULT_OTP_RATE
                save_system_config(config)
            return config
    except:
        return {
            "min_withdraw": DEFAULT_MIN_WITHDRAW,
            "max_withdraw": DEFAULT_MAX_WITHDRAW,
            "payment_methods": DEFAULT_PAYMENT_METHODS.copy(),
            "otp_rate": DEFAULT_OTP_RATE
        }

def save_system_config(config):
    with open(SYSTEM_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def update_min_withdraw(new_min):
    config = load_system_config()
    config["min_withdraw"] = new_min
    save_system_config(config)

def update_otp_rate(new_rate):
    config = load_system_config()
    config["otp_rate"] = new_rate
    save_system_config(config)

def get_otp_rate():
    config = load_system_config()
    return config.get("otp_rate", DEFAULT_OTP_RATE)

def toggle_payment_method(method_name):
    config = load_system_config()
    if method_name in config["payment_methods"]:
        config["payment_methods"][method_name] = not config["payment_methods"][method_name]
        save_system_config(config)
        return config["payment_methods"][method_name]
    return None

def get_enabled_payment_methods():
    config = load_system_config()
    return [name for name, enabled in config["payment_methods"].items() if enabled]

# ==================== PER-USER OTP RATE FUNCTIONS ====================
def load_user_otp_rates():
    if not os.path.exists(USER_OTP_RATE_FILE):
        with open(USER_OTP_RATE_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(USER_OTP_RATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_user_otp_rates(data):
    with open(USER_OTP_RATE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_user_otp_rate(user_id):
    rates = load_user_otp_rates()
    uid_str = str(user_id)
    if uid_str in rates:
        try:
            rate = float(rates[uid_str])
            if rate > 0:
                return rate
        except:
            pass
    return get_otp_rate()

def set_user_otp_rate(user_id, rate):
    rates = load_user_otp_rates()
    uid_str = str(user_id)
    if rate > 0:
        rates[uid_str] = rate
    else:
        if uid_str in rates:
            del rates[uid_str]
    save_user_otp_rates(rates)

# ==================== FAKE OTP CONFIG FUNCTIONS ====================
def load_fake_otp_config():
    if not os.path.exists(FAKE_OTP_CONFIG_FILE):
        default = {
            "enabled": False,
            "service": "facebook",
            "range": "",
            "interval": 10,
            "running": False,
            "otp_digits": 6
        }
        save_fake_otp_config(default)
        return default
    try:
        with open(FAKE_OTP_CONFIG_FILE, "r") as f:
            config = json.load(f)
            if "otp_digits" not in config:
                config["otp_digits"] = 6
                save_fake_otp_config(config)
            return config
    except:
        default = {"enabled": False, "service": "facebook", "range": "", "interval": 10, "running": False, "otp_digits": 6}
        save_fake_otp_config(default)
        return default

def save_fake_otp_config(config):
    with open(FAKE_OTP_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def update_fake_otp_config(**kwargs):
    config = load_fake_otp_config()
    for key, value in kwargs.items():
        config[key] = value
    save_fake_otp_config(config)

# ==================== REQUIRED CHANNELS / GROUPS FUNCTIONS ====================
STYLES = ["primary", "success", "danger"]

def load_required_channels():
    if not os.path.exists(REQUIRED_CHANNELS_FILE):
        with open(REQUIRED_CHANNELS_FILE, "w") as f:
            json.dump([], f)
        return []
    try:
        with open(REQUIRED_CHANNELS_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_required_channels(data):
    with open(REQUIRED_CHANNELS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def add_required_channel(link, label=None, chat_id=None):
    channels = load_required_channels()
    for ch in channels:
        if ch.get("link") == link:
            return False, "à¦à¦‡ à¦²à¦¿à¦‚à¦• à¦‡à¦¤à¦¿à¦®à¦§à§à¦¯à§‡ à¦†à¦›à§‡à¥¤"
    if not label:
        label = link.replace("https://t.me/", "").replace("@", "")
        if label.startswith("+"):
            label = "Channel " + label
        else:
            label = "@" + label
    style_index = len(channels) % len(STYLES)
    style = STYLES[style_index]
    entry = {"link": link, "label": label, "style": style}
    if chat_id:
        entry["chat_id"] = chat_id
    else:
        username_match = re.search(r'(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_]+)', link)
        if username_match:
            entry["username"] = username_match.group(1)
        else:
            return False, "à¦²à¦¿à¦‚à¦• à¦¥à§‡à¦•à§‡ à¦šà§à¦¯à¦¾à¦Ÿ à¦†à¦‡à¦¡à¦¿ à¦¬à§‡à¦° à¦•à¦°à¦¾ à¦¯à¦¾à§Ÿà¦¨à¦¿à¥¤ à¦…à¦¨à§à¦—à§à¦°à¦¹ à¦•à¦°à§‡ à¦šà§à¦¯à¦¾à¦Ÿ à¦†à¦‡à¦¡à¦¿ à¦¸à¦¹ à¦¯à§‹à¦— à¦•à¦°à§à¦¨ à¦…à¦¥à¦¬à¦¾ à¦¸à¦ à¦¿à¦• à¦²à¦¿à¦‚à¦• à¦¦à¦¿à¦¨à¥¤"
    channels.append(entry)
    save_required_channels(channels)
    return True, "à¦¸à¦«à¦²à¦­à¦¾à¦¬à§‡ à¦¯à§‹à¦— à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤"

def remove_required_channel(link_or_label):
    channels = load_required_channels()
    new_channels = []
    removed = False
    for ch in channels:
        if ch.get("link") == link_or_label or ch.get("label") == link_or_label:
            removed = True
            continue
        new_channels.append(ch)
    if removed:
        save_required_channels(new_channels)
        return True, "à¦¸à¦°à¦¾à¦¨à§‹ à¦¹à§Ÿà§‡à¦›à§‡à¥¤"
    return False, "à¦•à§‹à¦¨à§‹ à¦®à§à¦¯à¦¾à¦š à¦ªà¦¾à¦“à§Ÿà¦¾ à¦¯à¦¾à§Ÿà¦¨à¦¿à¥¤"

def get_all_required_channels():
    return load_required_channels()

async def resolve_chat_id_from_username(bot, username):
    try:
        chat = await bot.get_chat(f"@{username}")
        return chat.id
    except:
        return None

async def check_user_joined(bot, user_id, channel_entry):
    chat_id = channel_entry.get("chat_id")
    if not chat_id:
        username = channel_entry.get("username")
        if username:
            chat_id = await resolve_chat_id_from_username(bot, username)
            if chat_id:
                channel_entry["chat_id"] = chat_id
                channels = load_required_channels()
                for ch in channels:
                    if ch.get("link") == channel_entry.get("link"):
                        ch["chat_id"] = chat_id
                        break
                save_required_channels(channels)
            else:
                return False, f"âŒ à¦šà§à¦¯à¦¾à¦Ÿ à¦†à¦‡à¦¡à¦¿ à¦¬à§‡à¦° à¦•à¦°à¦¾ à¦¯à¦¾à§Ÿà¦¨à¦¿: {channel_entry.get('link')}"
    if not chat_id:
        return False, f"âŒ à¦šà§à¦¯à¦¾à¦Ÿ à¦†à¦‡à¦¡à¦¿ à¦…à¦¨à§à¦ªà¦¸à§à¦¥à¦¿à¦¤: {channel_entry.get('link')}"

    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ("member", "administrator", "creator"):
            return True, None
        else:
            return False, None
    except TelegramError as e:
        return False, f"âš ï¸ à¦¬à¦Ÿ à¦šà§‡à¦• à¦•à¦°à¦¤à§‡ à¦ªà¦¾à¦°à§‡à¦¨à¦¿: {str(e)[:100]}"

async def verify_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    channels = load_required_channels()
    if not channels:
        await query.edit_message_text("âœ… à¦•à§‹à¦¨à§‹ à¦šà§‡à¦• à¦•à¦°à¦¾à¦° à¦šà§à¦¯à¦¾à¦¨à§‡à¦² à¦¨à§‡à¦‡à¥¤ à¦†à¦ªà¦¨à¦¿ à¦¸à¦°à¦¾à¦¸à¦°à¦¿ à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦•à¦°à¦¤à§‡ à¦ªà¦¾à¦°à§‡à¦¨à¥¤")
        await show_main_menu(update, context, uid)
        return

    failed = []
    for ch in channels:
        ok, error = await check_user_joined(context.bot, uid, ch)
        if not ok:
            failed.append(ch.get("label", ch.get("link", "Unknown")))

    if failed:
        msg = "âŒ **à¦­à§‡à¦°à¦¿à¦«à¦¿à¦•à§‡à¦¶à¦¨ à¦¬à§à¦¯à¦°à§à¦¥!**\n\nà¦†à¦ªà¦¨à¦¿ à¦¨à¦¿à¦šà§‡à¦° à¦šà§à¦¯à¦¾à¦¨à§‡à¦²/à¦—à§à¦°à§à¦ªà¦—à§à¦²à§‹à¦¤à§‡ à¦œà§Ÿà§‡à¦¨ à¦•à¦°à§‡à¦¨à¦¨à¦¿:\n" + "\n".join(f"â€¢ {label}" for label in failed)
        msg += "\n\nà¦œà§Ÿà§‡à¦¨ à¦•à¦°à¦¾à¦° à¦ªà¦° à¦†à¦¬à¦¾à¦° **Verify** à¦¬à¦¾à¦Ÿà¦¨ à¦•à§à¦²à¦¿à¦• à¦•à¦°à§à¦¨à¥¤"
        await query.edit_message_text(msg, parse_mode="Markdown")
        return

    user_data = get_user(uid)
    user_data["verified"] = True
    all_data = load_data(USER_DATA_FILE)
    all_data[str(uid)] = user_data
    save_data(all_data)

    await query.edit_message_text("âœ… **à¦­à§‡à¦°à¦¿à¦«à¦¿à¦•à§‡à¦¶à¦¨ à¦¸à¦®à§à¦ªà§‚à¦°à§à¦£!**\n\nà¦†à¦ªà¦¨à¦¿ à¦à¦–à¦¨ à¦¬à¦Ÿà§‡à¦° à¦¸à¦¬ à¦«à¦¿à¦šà¦¾à¦° à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦•à¦°à¦¤à§‡ à¦ªà¦¾à¦°à¦¬à§‡à¦¨à¥¤")
    await show_main_menu(update, context, uid)

# ==================== ASYNC HELPERS ====================
async def fetch_services_cached():
    global _services_cache
    now = datetime.now().timestamp()
    if _services_cache["services"] and (now - _services_cache["timestamp"]) < CACHE_TTL:
        return _services_cache["services"]
    try:
        r = await client_async.get(f"{BASE_URL}/liveaccess")
        data = r.json()
        if data.get("meta", {}).get("code") == 200:
            services_data = data.get("data", {}).get("services", [])
            services = {}
            for svc in services_data:
                sid = svc.get("sid", "").lower()
                ranges = svc.get("ranges", [])
                if sid and ranges:
                    services[sid] = ranges
            _services_cache["services"] = services
            _services_cache["timestamp"] = now
            print(f"[services] cache updated â€” {len(services)} service(s)")
            return services
    except Exception as e:
        print(f"[services] fetch error: {e}")
    return _services_cache["services"]

async def get_number_from_api(rid: str):
    try:
        payload = {"rid": str(rid)}
        r = await client_async.post(f"{BASE_URL}/getnum", json=payload)
        result = r.json()
        if result.get("meta", {}).get("code") == 200:
            data = result["data"]
            return data.get("full_number"), data.get("country")
        return None, None
    except Exception as e:
        print(f"get_number error: {e}")
        return None, None

# ==================== CHECK IF USER IS ADMIN ====================
def is_admin(user_id):
    return user_id in ADMINS

# ==================== WITHDRAW DATA FUNCTIONS ====================
def load_withdraw_requests():
    if not os.path.exists(WITHDRAW_DATA_FILE):
        with open(WITHDRAW_DATA_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(WITHDRAW_DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_withdraw_requests(data):
    with open(WITHDRAW_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def generate_payment_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))

# ==================== BANNED USERS ====================
def load_banned_users():
    if not os.path.exists(BANNED_USERS_FILE):
        with open(BANNED_USERS_FILE, "w") as f:
            json.dump([], f)
        return []
    try:
        with open(BANNED_USERS_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_banned_users(banned_list):
    with open(BANNED_USERS_FILE, "w") as f:
        json.dump(banned_list, f, indent=4)

def is_user_banned(uid):
    banned_list = load_banned_users()
    return str(uid) in banned_list

def ban_user(uid):
    banned_list = load_banned_users()
    uid_str = str(uid)
    if uid_str not in banned_list:
        banned_list.append(uid_str)
        save_banned_users(banned_list)
        return True
    return False

def unban_user(uid):
    banned_list = load_banned_users()
    uid_str = str(uid)
    if uid_str in banned_list:
        banned_list.remove(uid_str)
        save_banned_users(banned_list)
        return True
    return False

# ==================== REFERRAL DATA ====================
def load_referral_data():
    if not os.path.exists(REFERRAL_DATA_FILE):
        with open(REFERRAL_DATA_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(REFERRAL_DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_referral_data(data):
    with open(REFERRAL_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def update_referral_count(uid, count):
    referral_data = load_referral_data()
    uid_str = str(uid)
    if uid_str not in referral_data:
        referral_data[uid_str] = {"referral_count": 0}
    referral_data[uid_str]["referral_count"] = count
    save_referral_data(referral_data)

def get_referral_count(uid):
    referral_data = load_referral_data()
    uid_str = str(uid)
    return referral_data.get(uid_str, {}).get("referral_count", 0)

# ==================== DATA RANGE FILE ====================
def load_range_db():
    if not os.path.exists(DATA_RANGE_FILE):
        return {}
    try:
        with open(DATA_RANGE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_range_db(data):
    with open(DATA_RANGE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_number_range_info(uid, number, range_text):
    db = load_range_db()
    flag, name = get_country_info(number)
    db[normalize_number(number)] = {
        "user_id": str(uid),
        "number": f"+{normalize_number(number)}",
        "range": range_text,
        "country": f"{flag} {name}"
    }
    save_range_db(db)

# ==================== COUNTRY INFO ====================
def get_country_info(number):
    number = str(number).strip()
    clean_num = re.sub(r'\D', '', number)
    sorted_prefixes = sorted(COUNTRY_PREFIX_MAP.keys(), key=len, reverse=True)
    for prefix in sorted_prefixes:
        if clean_num.startswith(prefix):
            return COUNTRY_PREFIX_MAP[prefix]
    return ("ðŸŒ", "Unknown")

# ==================== SERVICE DETECTION ====================
def detect_service(full_sms):
    if not full_sms:
        return "SMS SERVICE"
    sms_lower = full_sms.lower()
    service_keywords = {
        "facebook": "FACEBOOK", "fb": "FACEBOOK",
        "instagram": "INSTAGRAM", "insta": "INSTAGRAM",
        "tiktok": "TIKTOK",
        "twitter": "TWITTER", "x.com": "TWITTER",
        "snapchat": "SNAPCHAT", "snap": "SNAPCHAT",
        "whatsapp": "WHATSAPP",
        "telegram": "TELEGRAM",
        "discord": "DISCORD",
        "messenger": "MESSENGER",
        "linkedin": "LINKEDIN",
        "google": "GOOGLE", "gmail": "GOOGLE",
        "amazon": "AMAZON",
        "microsoft": "MICROSOFT", "outlook": "MICROSOFT",
        "yahoo": "YAHOO",
        "paypal": "PAYPAL",
        "binance": "BINANCE",
        "coinbase": "COINBASE",
        "spotify": "SPOTIFY",
        "netflix": "NETFLIX",
        "uber": "UBER",
        "apple": "APPLE", "icloud": "APPLE",
        "bkash": "BKASH",
        "nagad": "NAGAD",
        "stripe": "STRIPE",
        "line": "LINE",
        "wechat": "WECHAT",
        "viber": "VIBER",
        "signal": "SIGNAL",
        "pubg": "PUBG",
        "free fire": "FREE FIRE",
    }
    for keyword, service_name in sorted(service_keywords.items(), key=lambda x: len(x[0]), reverse=True):
        if keyword in sms_lower:
            return service_name
    return "SMS SERVICE"

# ==================== KEYBOARDS ====================
def main_keyboard(user_id):
    keyboard = [
        [KeyboardButton(text="ðŸ“ž GET NUMBER")],
        [KeyboardButton(text="ðŸ” SEARCH OTP")],
        [KeyboardButton(text="âš¡ GET 2FA"), KeyboardButton(text="ðŸ’° BALANCE")],
        [KeyboardButton(text="REFER AND EARN"), KeyboardButton(text="ðŸ‘¤ PROFILE")],
        [KeyboardButton(text="ðŸ† LEADERBOARD")],
        [KeyboardButton(text="ðŸ’¬ SUPPORT")]
    ]
    if is_admin(user_id):
        keyboard.append([KeyboardButton(text="âš™ï¸ ADMIN PANEL âš™ï¸")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def cancel_keyboard():
    keyboard = [[KeyboardButton("âŒ CANCEL")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_main_keyboard():
    keyboard = [
        [KeyboardButton("ðŸ‘¥ USER MANAGEMENT")],
        [KeyboardButton("âš™ï¸ SYSTEM CONFIGURATION")],
        [KeyboardButton("ðŸ”— REQUIRED CHANNELS")],
        [KeyboardButton("âš¡ FAKE OTP")],
        [KeyboardButton("ðŸ”™ BACK TO MAIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def user_management_keyboard():
    keyboard = [
        [KeyboardButton("ðŸ“¢ SEND MESSAGE TO ALL USERS")],
        [KeyboardButton("ðŸ†” ALL USER ID")],
        [KeyboardButton("ðŸ“œ BAN USER LIST")],
        [KeyboardButton("ðŸ’° ALL USER BALANCE")],
        [KeyboardButton("ðŸ‘¥ USER LIST (ALL)")],
        [KeyboardButton("ðŸ”™ BACK TO ADMIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def system_config_keyboard():
    keyboard = [
        [KeyboardButton("ðŸ“ˆ TODAY ALL STATUS"), KeyboardButton("ðŸ‘¤ USER STATUS CHECK")],
        [KeyboardButton("â›” BAN USER"), KeyboardButton("ðŸ”“ UNBAN USER")],
        [KeyboardButton("ðŸ“œ BAN USER LIST")],
        [KeyboardButton("âž– REMOVE BALANCE"), KeyboardButton("âž• ADD BALANCE")],
        [KeyboardButton("âš™ï¸ CHANGE MIN WITHDRAW")],
        [KeyboardButton("ðŸ’³ TOGGLE PAYMENT METHODS")],
        [KeyboardButton("ðŸ’² CHANGE OTP PRICE")],
        [KeyboardButton("ðŸ”§ SET USER OTP RATE"), KeyboardButton("ðŸ“‹ VIEW USER OTP RATE")],
        [KeyboardButton("ðŸ”™ BACK TO ADMIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def required_channels_keyboard():
    keyboard = [
        [KeyboardButton("âž• ADD CHANNEL")],
        [KeyboardButton("âŒ REMOVE CHANNEL")],
        [KeyboardButton("ðŸ“‹ LIST CHANNELS")],
        [KeyboardButton("ðŸ”™ BACK TO ADMIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def fake_otp_keyboard():
    config = load_fake_otp_config()
    status = "âœ… à¦šà¦¾à¦²à§" if config.get("running", False) else "âŒ à¦¬à¦¨à§à¦§"
    keyboard = [
        [KeyboardButton(f"ðŸ“Š STATUS: {status}")],
        [KeyboardButton("â–¶ï¸ START")],
        [KeyboardButton("â¹ STOP")],
        [KeyboardButton("âš™ï¸ SETTINGS")],
        [KeyboardButton("ðŸ”™ BACK TO ADMIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def withdraw_method_keyboard():
    enabled_methods = get_enabled_payment_methods()
    if not enabled_methods:
        enabled_methods = ["BKASH", "NAGAD", "ROCKET", "BINANCE"]
    buttons = []
    for method in enabled_methods:
        if method == "BKASH":
            buttons.append([KeyboardButton("ðŸ“± BKASH")])
        elif method == "NAGAD":
            buttons.append([KeyboardButton("ðŸ’µ NAGAD")])
        elif method == "ROCKET":
            buttons.append([KeyboardButton("ðŸš€ ROCKET")])
        elif method == "BINANCE":
            buttons.append([KeyboardButton("ðŸ¦ BINANCE")])
    buttons.append([KeyboardButton("âŒ CANCEL")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ==================== HELPER FUNCTIONS ====================
def format_balance(balance):
    return f"{balance:.2f}"

def extract_otp(text):
    if not text or text == "No Content":
        return "N/A"
    spaced_otp = re.search(r'\b(\d{3}\s\d{3})\b', text)
    if spaced_otp:
        return spaced_otp.group(1).replace(" ", "")
    match = re.search(r'\b(\d{4,8})\b', text)
    return match.group(1) if match else "N/A"

def normalize_number(num):
    return re.sub(r'\D', '', str(num))

def mask_number(num):
    if len(num) > 6:
        return f"{num[:4]}****{num[-6:]}"
    return num

def get_date_reset_time():
    now = datetime.now()
    today_midnight = datetime(now.year, now.month, now.day, 0, 0, 0)
    return today_midnight

def is_valid_bangladesh_number(number):
    number = re.sub(r'\D', '', str(number))
    return len(number) == 11 and number.startswith('01')

def is_range_request(param):
    return 'X' in param.upper() or param.replace('X', '').replace('x', '').isdigit()

def is_referral_request(param):
    return param.isdigit()

# ==================== DATABASE ====================
def load_data(filename=USER_DATA_FILE):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data, filename=USER_DATA_FILE):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

def get_user(uid):
    uid = str(uid)
    data = load_data()
    if uid not in data:
        data[uid] = {"user_id": uid, "balance": 0.0, "total_numbers": 0, "referral_count": 0, "verified": False}
        save_data(data)
    return data[uid]

async def update_db_balance(uid, amount):
    uid = str(uid)
    data = load_data()
    if uid in data:
        data[uid]["balance"] = round(data[uid].get("balance", 0.0) + amount, 2)
        save_data(data)
        return data[uid]["balance"]
    return 0.0

def get_all_users():
    data = load_data(USER_DATA_FILE)
    return list(data.keys()) if data else []

def user_exists(uid):
    data = load_data(USER_DATA_FILE)
    return str(uid) in data

# ==================== STATS ====================
def load_stats():
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=4)

def add_number_taken(uid, count=1):
    uid = str(uid)
    stats = load_stats()
    if uid not in stats:
        stats[uid] = {"numbers_taken": [], "otps_received": []}
    now = datetime.now().isoformat()
    for _ in range(count):
        stats[uid]["numbers_taken"].append(now)
    log_global_activity(uid, "NUMBER_TAKEN", {"count": count})
    save_stats(stats)

def add_otp_received(uid):
    uid = str(uid)
    stats = load_stats()
    if uid not in stats:
        stats[uid] = {"numbers_taken": [], "otps_received": []}
    stats[uid]["otps_received"].append(datetime.now().isoformat())
    save_stats(stats)

def get_user_stats(uid):
    uid = str(uid)
    stats = load_stats()
    user_stats = stats.get(uid, {"numbers_taken": [], "otps_received": []})
    now = datetime.now()
    today_midnight = get_date_reset_time()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    numbers_taken = user_stats.get("numbers_taken", [])
    otps_received = user_stats.get("otps_received", [])
    today_numbers = sum(1 for t in numbers_taken if datetime.fromisoformat(t) >= today_midnight)
    today_otps = sum(1 for t in otps_received if datetime.fromisoformat(t) >= today_midnight)
    last24h_numbers = sum(1 for t in numbers_taken if datetime.fromisoformat(t) > last_24h)
    last24h_otps = sum(1 for t in otps_received if datetime.fromisoformat(t) > last_24h)
    last7d_numbers = sum(1 for t in numbers_taken if datetime.fromisoformat(t) > last_7d)
    last7d_otps = sum(1 for t in otps_received if datetime.fromisoformat(t) > last_7d)
    total_numbers = len(numbers_taken)
    total_otps = len(otps_received)
    return {
        "total_numbers": total_numbers, "total_otps": total_otps,
        "today_numbers": today_numbers, "today_otps": today_otps,
        "last24h_numbers": last24h_numbers, "last24h_otps": last24h_otps,
        "last7d_numbers": last7d_numbers, "last7d_otps": last7d_otps
    }

def log_global_activity(uid, action, details):
    if not os.path.exists(ACTIVITY_LOGS_FILE):
        with open(ACTIVITY_LOGS_FILE, "w") as f:
            json.dump([], f)
    try:
        with open(ACTIVITY_LOGS_FILE, "r") as f:
            logs = json.load(f)
    except:
        logs = []
    now = datetime.now()
    logs.append({
        "uid": str(uid), "action": action, "details": details,
        "timestamp": now.isoformat(),
        "date": now.strftime("%d/%m/%Y"),
        "time": now.strftime("%H:%M:%S")
    })
    with open(ACTIVITY_LOGS_FILE, "w") as f:
        json.dump(logs, f, indent=4)

def get_global_system_stats():
    stats = load_stats()
    now = datetime.now()
    today_midnight = datetime(now.year, now.month, now.day)
    last_7d = now - timedelta(days=7)
    total_n = total_o = today_n = today_o = seven_n = seven_o = 0
    for uid in stats:
        u = stats[uid]
        n_list = u.get("numbers_taken", [])
        o_list = u.get("otps_received", [])
        total_n += len(n_list)
        total_o += len(o_list)
        for t in n_list:
            dt = datetime.fromisoformat(t)
            if dt >= today_midnight: today_n += 1
            if dt >= last_7d: seven_n += 1
        for t in o_list:
            dt = datetime.fromisoformat(t)
            if dt >= today_midnight: today_o += 1
            if dt >= last_7d: seven_o += 1
    return today_n, today_o, seven_n, seven_o, total_n, total_o

# ==================== LEADERBOARD ====================
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    stats_data = load_stats()
    today_midnight = get_date_reset_time()
    user_data_all = load_data(USER_DATA_FILE)
    user_today_counts = []
    for uid_str, user_stats in stats_data.items():
        otps_received = user_stats.get("otps_received", [])
        today_count = 0
        for ts in otps_received:
            try:
                dt = datetime.fromisoformat(ts)
                if dt >= today_midnight:
                    today_count += 1
            except:
                continue
        if today_count > 0:
            name = user_data_all.get(uid_str, {}).get("full_name")
            if not name:
                name = user_data_all.get(uid_str, {}).get("username")
            if not name:
                name = f"User {uid_str}"
            user_today_counts.append((uid_str, today_count, html.escape(name)))
    user_today_counts.sort(key=lambda x: x[1], reverse=True)
    top10 = user_today_counts[:10]
    if not top10:
        msg = (
            "<b>ðŸ† TOP 10 OTP LEADERBOARD ðŸ†</b>\n"
            "â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\n"
            "âŒ à¦†à¦œ à¦ªà¦°à§à¦¯à¦¨à§à¦¤ à¦•à§‡à¦‰ OTP à¦ªà¦¾à§Ÿà¦¨à¦¿à¥¤\n"
        )
    else:
        msg = (
            "<b>ðŸ† TOP 10 OTP RECEIVERS (TODAY) ðŸ†</b>\n"
            "â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\n"
        )
        for idx, (uid_str, count, name) in enumerate(top10, 1):
            if idx == 1:
                medal = "ðŸ¥‡"
            elif idx == 2:
                medal = "ðŸ¥ˆ"
            elif idx == 3:
                medal = "ðŸ¥‰"
            else:
                medal = f"{idx}ï¸âƒ£"
            msg += f"{medal} <b>{name}</b>\n   ðŸ”‘ <code>{count}</code> OTPs\n\n"
        msg += (
            "â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
            "ðŸ“Š <i>à¦ªà§à¦°à¦¤à¦¿à¦¦à¦¿à¦¨ à¦°à¦¾à¦¤ à§§à§¨à¦Ÿà¦¾à§Ÿ à¦°à¦¿à¦¸à§‡à¦Ÿ à¦¹à§Ÿ</i>"
        )
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=main_keyboard(uid))

# ==================== 2FA ====================
def generate_2fa_code(secret_key):
    try:
        clean_secret = secret_key.replace(" ", "").strip()
        totp = pyotp.TOTP(clean_secret)
        otp = totp.now()
        return otp, clean_secret
    except:
        return None, None

async def get_2fa_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    context.user_data["mode"] = "get_2fa"
    await update.message.reply_text(
        "âš¡ <b>GET 2FA CODE</b> âš¡\n\n"
        "<blockquote>ðŸ”‘ ENTER YOUR 2FA SECRET KEY:</blockquote>",
        parse_mode="HTML"
    )

async def process_2fa_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    secret_key = update.message.text.strip()
    context.user_data["mode"] = None
    otp_code, clean_key = generate_2fa_code(secret_key)
    if otp_code is None:
        await update.message.reply_text(
            "âŒ <b>INVALID 2FA SECRET KEY</b>\n\nâš ï¸ Please send a valid base32 key.",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
        return
    now = datetime.now()
    final_msg = (
        "âœ… <b>2FA CODE GENERATED!</b>\n\n"
        f"<blockquote>ðŸ”‘ KEY: <code>{clean_key}</code></blockquote>\n"
        f"<blockquote>ðŸ”¢ CODE: <code>{otp_code}</code></blockquote>\n"
        f"<blockquote>â³ EXPIRES IN: 30 SECONDS</blockquote>\n"
        f"ðŸ“… {now.strftime('%d %B, %Y')} | {now.strftime('%I:%M %p')}"
    )
    await update.message.reply_text(final_msg, parse_mode="HTML")

# ==================== GET NUMBER â€” SERVICE SELECTION ====================
_SVC_STYLES = ["danger", "primary", "success", "danger", "primary", "success",
               "danger", "primary", "success", "danger", "primary", "success"]
_RANGE_EMOJIS = [
    "ðŸš€", "ðŸ”¥", "âœ¨", "ðŸ’Ž", "ðŸ“±", "âš¡", "ðŸŒŸ", "ðŸ’«", "â­", "ðŸŒ€",
    "ðŸŒˆ", "ðŸ€", "ðŸ’¥", "ðŸŽ¯", "ðŸ”®", "ðŸ’¡", "ðŸª„", "ðŸŽ¨", "ðŸ†", "ðŸŽ–ï¸"
]

def get_range_emoji(range_str):
    hash_val = hash(range_str) % len(_RANGE_EMOJIS)
    return _RANGE_EMOJIS[hash_val]

def get_flag_by_prefix(range_str):
    prefix = re.sub(r'[^0-9]', '', range_str)
    if not prefix:
        return None
    sorted_prefixes = sorted(COUNTRY_PREFIX_MAP.keys(), key=len, reverse=True)
    for p in sorted_prefixes:
        if prefix.startswith(p):
            return COUNTRY_PREFIX_MAP[p][0]
    return None

def _build_services_keyboard(services):
    buttons = []
    emoji_map = {
        "whatsapp": "ðŸ’š", "facebook": "ðŸ“˜", "discord": "ðŸŽ®", "telegram": "âœˆï¸",
        "instagram": "ðŸ“¸", "twitter": "ðŸ¦", "tiktok": "ðŸŽµ", "snapchat": "ðŸ‘»",
        "google": "ðŸ”", "gmail": "ðŸ“§", "outlook": "ðŸ“§", "yahoo": "ðŸ”®",
        "binance": "ðŸ’°", "coinbase": "â‚¿", "paypal": "ðŸ’³", "amazon": "ðŸ›’",
        "netflix": "ðŸŽ¬", "spotify": "ðŸŽ§", "uber": "ðŸš—", "apple": "ðŸŽ",
        "icloud": "â˜ï¸", "microsoft": "ðŸªŸ", "bkash": "ðŸ’¸", "nagad": "ðŸ’µ",
        "rocket": "ðŸš€", "upay": "ðŸ¦", "line": "ðŸ’¬", "wechat": "ðŸ’¬",
        "viber": "ðŸ“ž", "signal": "ðŸ”’", "pubg": "ðŸŽ¯", "freefire": "ðŸ”¥"
    }
    for i, svc in enumerate(services.keys()):
        emoji = emoji_map.get(svc, "ðŸ“¡")
        display = f"{emoji} {svc.capitalize()}"
        color = _SVC_STYLES[i % len(_SVC_STYLES)]
        buttons.append([InlineKeyboardButton(display, callback_data=f"svc_{svc}", style=color)])
    buttons.append([InlineKeyboardButton("âš™ï¸ CUSTOM RANGE", callback_data="custom_range", style="danger")])
    buttons.append([InlineKeyboardButton("ðŸ”™ BACK TO MAIN", callback_data="back_to_main")])
    return InlineKeyboardMarkup(buttons)

def _build_countries_keyboard(ranges, service):
    country_map = {}
    for r in ranges:
        prefix = re.sub(r'[^0-9]', '', r)
        if not prefix:
            continue
        country_prefix = get_country_prefix_from_number(prefix)
        if not country_prefix:
            continue
        if country_prefix not in country_map:
            flag, name = get_country_by_prefix(country_prefix)
            country_map[country_prefix] = {
                "flag": flag,
                "name": name,
                "rid": prefix,
                "hot": is_country_hot(country_prefix)
            }
    if not country_map:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("âŒ à¦•à§‹à¦¨ à¦¦à§‡à¦¶ à¦‰à¦ªà¦²à¦¬à§à¦§ à¦¨à§‡à¦‡", callback_data="back_services", style="danger")
        ]])
        return keyboard
    
    hot_countries = [c for c in country_map.values() if c["hot"]]
    non_hot_countries = [c for c in country_map.values() if not c["hot"]]
    countries = hot_countries + non_hot_countries
    
    btns = []
    clrs = ["primary", "success", "danger", "primary", "success", "danger"]
    ci = 0
    for info in countries:
        label = f"{info['flag']} {info['name']}"
        if info["hot"]:
            label += " ðŸ”¥"
        color = clrs[ci % len(clrs)]
        ci += 1
        callback_data = f"hot_range_{info['rid']}_{service}"
        btns.append(InlineKeyboardButton(label, callback_data=callback_data, style=color))
    
    rows = [btns[j:j+2] for j in range(0, len(btns), 2)]
    rows.append([InlineKeyboardButton("â—€ï¸ BACK", callback_data="back_services", style="danger")])
    return InlineKeyboardMarkup(rows)

async def show_app_selection(update, context):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    services = await fetch_services_cached()
    if not services:
        await update.message.reply_text(
            "âš ï¸ <b>à¦•à§‹à¦¨à§‹ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦‰à¦ªà¦²à¦¬à§à¦§ à¦¨à§‡à¦‡</b>\nâ³ à¦•à¦¿à¦›à§à¦•à§à¦·à¦£ à¦ªà¦° à¦†à¦¬à¦¾à¦° à¦šà§‡à¦·à§à¦Ÿà¦¾ à¦•à¦°à§à¦¨à¥¤",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
        return
    # ===== UPDATED: à¦à¦–à¦¨ à§ªà¦Ÿà¦¿ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¦à§‡à¦–à¦¾à¦¬à§‡: facebook, instagram, whatsapp, telegram =====
    allowed = ["facebook", "instagram", "whatsapp", "telegram"]
    filtered_services = {k: v for k, v in services.items() if k in allowed}
    if not filtered_services:
        await update.message.reply_text(
            "âš ï¸ <b>à¦•à§‹à¦¨à§‹ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦‰à¦ªà¦²à¦¬à§à¦§ à¦¨à§‡à¦‡</b>\nâ³ à¦•à¦¿à¦›à§à¦•à§à¦·à¦£ à¦ªà¦° à¦†à¦¬à¦¾à¦° à¦šà§‡à¦·à§à¦Ÿà¦¾ à¦•à¦°à§à¦¨à¥¤",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
        return
    context.user_data["la_services"] = filtered_services
    keyboard = _build_services_keyboard(filtered_services)
    await update.message.reply_text(
        "ðŸ“¡âœ¨ ð—¦ð—˜ð—Ÿð—˜ð—–ð—§ ð—¬ð—¢ð—¨ð—¥ ð—¦ð—˜ð—¥ð—©ð—œð—–ð—˜ âœ¨ðŸ“¡\n\n"
        "<blockquote>âœ¨ à¦¨à¦¿à¦š à¦¥à§‡à¦•à§‡ à¦†à¦ªà¦¨à¦¾à¦° à¦ªà¦›à¦¨à§à¦¦à§‡à¦° <b>Service</b> à¦¨à¦¿à¦°à§à¦¬à¦¾à¦šà¦¨ à¦•à¦°à§à¦¨:</blockquote>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ==================== AUTO OTP MONITOR (REAL) ====================
async def monitor_loop(app):
    sent_otps = set()
    while True:
        try:
            r = await client_async.get(f"{BASE_URL}/success-otp")
            result = r.json()
            if result.get("meta", {}).get("code") == 200:
                data_obj = result.get("data")
                if isinstance(data_obj, dict) and "otps" in data_obj:
                    otps = data_obj.get("otps", [])
                elif isinstance(data_obj, list):
                    otps = data_obj
                else:
                    otps = []
                paid_data = load_data(PAID_SMS_FILE)
                paid_keys_set = set(paid_data.keys())
                for otp in otps:
                    number = otp.get("number")
                    if not number:
                        continue
                    full_sms = otp.get("message", "No SMS Content")
                    otp_time = otp.get("time", "")
                    otp_code = extract_otp(full_sms)
                    key = f"{normalize_number(number)}_{otp_time}"
                    if key in sent_otps:
                        continue
                    num = normalize_number(number)
                    sms_key = f"{num}_{full_sms[:50]}"
                    if num in active_numbers and sms_key not in paid_keys_set:
                        sent_otps.add(key)
                        details = active_numbers[num]
                        uid = details["uid"]
                        service_name = detect_service(full_sms)
                        is_free_service = service_name in ("TELEGRAM", "WHATSAPP")
                        if not is_free_service:
                            user_rate = get_user_otp_rate(uid)
                            await update_db_balance(uid, user_rate)
                            add_otp_received(uid)
                            log_global_activity(uid, "OTP_RECEIVED", {"number": num, "otp": otp_code, "sms": full_sms})
                            update_country_otp_count(num)
                        else:
                            log_global_activity(uid, "OTP_RECEIVED_FREE", {"number": num, "otp": otp_code, "service": service_name})
                        paid_keys_set.add(sms_key)
                        paid_data[sms_key] = {"uid": uid, "otp": otp_code}
                        num_range_info = active_numbers.get(num, {}).get("range", "")
                        if not num_range_info:
                            num_range_info = (num[:-3] + 'XXX') if len(num) > 3 else (num + 'XXX')
                        country_flag, country_name = get_country_info(num)
                        clean_num = num.replace('+', '').strip()
                        full_number = f"+{clean_num}"
                        masked_number = f"+{mask_number(clean_num)}"
                        safe_full_sms = html.escape(str(full_sms))
                        safe_otp_code = html.escape(str(otp_code))
                        if is_free_service:
                            balance_msg = "âš ï¸ à¦à¦‡ OTPâ€‘à¦¤à§‡ à¦•à§‹à¦¨à§‹ à¦Ÿà¦¾à¦•à¦¾ à¦¯à§‹à¦— à¦•à¦°à¦¾ à¦¹à¦¬à§‡ à¦¨à¦¾ (Telegram/WhatsApp)"
                        else:
                            user_rate = get_user_otp_rate(uid)
                            balance_msg = f"ðŸ’µ ADD BALANCE FOR {user_rate:.2f} BDT"
                        user_msg = (
                            f"âœ… <b>OTP RECEIVE SUCCESSFUL</b> âœ…\n\n"
                            f"<blockquote>ðŸ“¶ RANGE: <code>{num_range_info}</code></blockquote>\n"
                            f"<blockquote>ðŸŒ COUNTRY: <code>{country_flag} {country_name}</code></blockquote>\n"
                            f"<blockquote>ðŸ“± SERVICE: <code>{service_name}</code></blockquote>\n"
                            f"<blockquote>ðŸ“ž NUMBER: <code>{full_number}</code></blockquote>\n"
                            f"<blockquote>ðŸ”‘ OTP: <code>{safe_otp_code}</code></blockquote>\n\n"
                            f"<blockquote>ðŸ“© FULL SMS:\n<code>{safe_full_sms}</code></blockquote>\n\n"
                            f"<b>{balance_msg}</b>"
                        )
                        group_msg = (
                            f"âœ… <b>OTP RECEIVE SUCCESSFUL</b> âœ…\n\n"
                            f"<blockquote>ðŸ“¶ RANGE: <code>{num_range_info}</code></blockquote>\n"
                            f"<blockquote>ðŸŒ COUNTRY: <code>{country_flag} {country_name}</code></blockquote>\n"
                            f"<blockquote>ðŸ“± SERVICE: <code>{service_name}</code></blockquote>\n"
                            f"<blockquote>ðŸ“ž NUMBER: <code>{masked_number}</code></blockquote>\n"
                            f"<blockquote>ðŸ”‘ OTP: <code>{safe_otp_code}</code></blockquote>\n\n"
                            f"<blockquote>ðŸ“© FULL SMS:\n<code>{safe_full_sms}</code></blockquote>"
                        )
                        group_buttons = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("â€¼ï¸ PANEL", url="https://t.me/VoltXSMS1Bot", style="danger"),
                                InlineKeyboardButton("ðŸ“¢ CHANNEL", url="https://t.me/hunterxvoltx", style="success")
                            ]
                        ])
                        try:
                            await app.bot.send_message(uid, user_msg, parse_mode="HTML")
                        except Exception as e:
                            print(f"âŒ User Message Send Fail: {e}")
                        try:
                            await app.bot.send_message(OTP_GROUP_ID, group_msg, parse_mode="HTML", reply_markup=group_buttons)
                        except Exception as e:
                            print(f"âŒ Group Send Fail: {e}")
                        save_data(paid_data, PAID_SMS_FILE)
                current_time = datetime.now()
                for num_key in list(active_numbers.keys()):
                    entry = active_numbers[num_key]
                    if 'timestamp' not in entry:
                        entry['timestamp'] = current_time
                    elif (current_time - entry['timestamp']).total_seconds() > 3600:
                        del active_numbers[num_key]
        except Exception as e:
            print(f"Monitor Error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

# ==================== FAKE OTP LOOP ====================
async def fake_otp_loop(app):
    """Background task to generate fake OTPs based on config."""
    while True:
        try:
            config = load_fake_otp_config()
            if config.get("running", False):
                service = config.get("service", "facebook")
                interval = config.get("interval", 10)
                range_str = config.get("range", "")
                otp_digits = config.get("otp_digits", 6)
                
                services = await fetch_services_cached()
                if not services:
                    ranges = ["880XXX"]
                else:
                    if service not in services:
                        service = list(services.keys())[0] if services else "facebook"
                    ranges = services.get(service, ["880XXX"])
                
                if range_str:
                    prefix = re.sub(r'[^0-9]', '', range_str)
                    if not prefix:
                        prefix = "880"
                    num_len = 10 + random.randint(0, 2)
                    remaining = num_len - len(prefix)
                    if remaining < 0:
                        remaining = 4
                    random_digits = ''.join(random.choices(string.digits, k=remaining))
                    fake_number = prefix + random_digits
                else:
                    if not ranges:
                        ranges = ["880XXX"]
                    chosen_range = random.choice(ranges)
                    prefix = re.sub(r'[^0-9]', '', chosen_range)
                    if not prefix:
                        prefix = "880"
                    num_len = 10 + random.randint(0, 2)
                    remaining = num_len - len(prefix)
                    if remaining < 0:
                        remaining = 4
                    random_digits = ''.join(random.choices(string.digits, k=remaining))
                    fake_number = prefix + random_digits
                
                otp_code = ''.join(random.choices(string.digits, k=otp_digits))
                
                service_display = service.upper()
                sms_templates = {
                    "facebook": f"Your Facebook verification code is: {otp_code}",
                    "instagram": f"Your Instagram confirmation code: {otp_code}",
                    "whatsapp": f"Your WhatsApp code: {otp_code}",
                    "telegram": f"Your Telegram login code: {otp_code}",
                    "google": f"Your Google verification code: {otp_code}",
                    "binance": f"Your Binance 2FA code: {otp_code}",
                    "apple": f"Your Apple ID code: {otp_code}",
                    "default": f"Your verification code is: {otp_code}"
                }
                sms_text = sms_templates.get(service, sms_templates["default"])
                
                country_flag, country_name = get_country_info(fake_number)
                range_display = prefix + ('X' * (len(fake_number) - len(prefix)))
                num_range_info = range_display
                masked_number = f"+{mask_number(fake_number)}"
                safe_full_sms = html.escape(sms_text)
                safe_otp_code = html.escape(otp_code)
                
                group_msg = (
                    f"âœ… <b>OTP RECEIVE SUCCESSFUL</b> âœ…\n\n"
                    f"<blockquote>ðŸ“¶ RANGE: <code>{num_range_info}</code></blockquote>\n"
                    f"<blockquote>ðŸŒ COUNTRY: <code>{country_flag} {country_name}</code></blockquote>\n"
                    f"<blockquote>ðŸ“± SERVICE: <code>{service_display}</code></blockquote>\n"
                    f"<blockquote>ðŸ“ž NUMBER: <code>{masked_number}</code></blockquote>\n"
                    f"<blockquote>ðŸ”‘ OTP: <code>{safe_otp_code}</code></blockquote>\n\n"
                    f"<blockquote>ðŸ“© FULL SMS:\n<code>{safe_full_sms}</code></blockquote>"
                )
                
                group_buttons = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("â€¼ï¸ PANEL", url="https://t.me/VoltXSMS1Bot", style="danger"),
                        InlineKeyboardButton("ðŸ“¢ CHANNEL", url="https://t.me/hunterxvoltx", style="success")
                    ]
                ])
                
                try:
                    await app.bot.send_message(OTP_GROUP_ID, group_msg, parse_mode="HTML", reply_markup=group_buttons)
                    log_global_activity("SYSTEM", "FAKE_OTP_SENT", {"service": service, "number": fake_number, "otp": otp_code})
                except Exception as e:
                    print(f"âŒ Fake OTP send failed: {e}")
                
                await asyncio.sleep(interval)
            else:
                await asyncio.sleep(5)
        except Exception as e:
            print(f"Fake OTP loop error: {e}")
            await asyncio.sleep(5)

# ==================== WORKER & API ====================
async def fast_allocate_number(query, context, rid, service, range_display):
    uid = query.from_user.id
    if is_user_banned(uid):
        await query.message.edit_text("ðŸš« YOU ARE BANNED ðŸš«")
        return
    try:
        num, country = await get_number_from_api(rid)
    except Exception as e:
        await query.message.edit_text(f"âŒ Server error: {str(e)[:100]}")
        return
    if not num:
        await query.message.edit_text(
            "âŒ <b>Number à¦ªà¦¾à¦“à¦¯à¦¼à¦¾ à¦¯à¦¾à¦¯à¦¼à¦¨à¦¿à¥¤</b>\n\n"
            "<blockquote>âš ï¸ à¦à¦‡ range-à¦ à¦à¦–à¦¨ number à¦¨à§‡à¦‡ à¦¬à¦¾ server busyà¥¤\n"
            "à¦†à¦°à§‡à¦•à¦Ÿà¦¿ range à¦šà§‡à¦·à§à¦Ÿà¦¾ à¦•à¦°à§à¦¨à¥¤</blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("ðŸ”™ BACK", callback_data="back_services", style="danger")
            ]])
        )
        return
    clean_num = normalize_number(num)
    add_number_taken(uid, 1)
    last_range[uid] = rid
    active_numbers[clean_num] = {"uid": uid, "range": range_display, "timestamp": datetime.now()}
    save_number_range_info(uid, clean_num, range_display)
    country_flag, country_name = get_country_info(clean_num)
    text = (
        f"âœ… <b>YOUR NUMBER</b> âœ…\n\n"
        f"<blockquote>ðŸŒ COUNTRY: <code>{country_flag} {html.escape(country_name)}</code></blockquote>\n"
        f"<blockquote>ðŸ“¶ RANGE: <code>{range_display}</code></blockquote>\n"
        f"<blockquote>ðŸ“± SERVICE: <code>{service.upper()}</code></blockquote>\n"
        f"<blockquote>ðŸ“ž NUMBER: <code>{num}</code></blockquote>\n\n"
        f"<b>ðŸ“© SMS STATUS: â³ WAITING...</b>"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("ðŸ”„ SAME RANGE", callback_data=f"same_range_{rid}_{service}", style="success")],
        [InlineKeyboardButton("ðŸ“¢ OTP GROUP", url="https://t.me/Davil_Otp_Group", style="primary")],
        [InlineKeyboardButton("â—€ï¸ BACK", callback_data="back_to_services")]
    ])
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        print(f"fast_allocate edit error: {e}")

async def worker():
    while True:
        task = await request_queue.get()
        try:
            if task['type'] == 'process_numbers':
                await process_numbers(task['update'], task['context'], task['range_text'], task['count'], task.get('service', ''))
            elif task['type'] == 'search_otp':
                await perform_otp_search(task['update'], task['context'], task['target_num'])
            elif task['type'] == 'auto_number':
                await process_auto_number(task['update'], task['context'], task['range_text'])
        except Exception as e:
            print(f"Worker Error: {e}")
        finally:
            request_queue.task_done()

async def process_auto_number(update, context, range_text):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    if is_user_banned(uid):
        await context.bot.send_message(chat_id=chat_id, text="ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    status_msg = await context.bot.send_message(chat_id=chat_id, text="ðŸ” SEARCHING...")
    rid = re.sub(r'[^0-9]', '', range_text)
    if not rid:
        await status_msg.edit_text("âŒ INVALID RANGE! Send numbers only.")
        return
    try:
        num, country = await get_number_from_api(rid)
        if not num:
            await status_msg.edit_text("âŒ NO NUMBERS FOUND. TRY A VALID RANGE.")
            return
        clean_num = normalize_number(num)
        add_number_taken(uid, 1)
        last_range[uid] = rid
        active_numbers[clean_num] = {"uid": uid, "range": range_text, "timestamp": datetime.now()}
        save_number_range_info(uid, clean_num, range_text)
        country_flag, country_name = get_country_info(clean_num)
        final_text = (
            f"âœ… <b>YOUR NUMBER DETAILS</b> âœ…\n\n"
            f"<blockquote>ðŸŒ COUNTRY: <code>{country_flag} {country_name}</code></blockquote>\n"
            f"<blockquote>ðŸ“¶ RANGE: <code>{range_text}</code></blockquote>\n\n"
            f"<blockquote>ðŸ“ž NUMBER: <code>{num}</code></blockquote>\n\n"
            f"<b>ðŸ“© SMS STATUS: â³ WAITING...</b>"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ðŸ”„ SAME RANGE", callback_data=f"same_range_{rid}_CUSTOM", style="success")],
            [InlineKeyboardButton("ðŸ“¢ OTP GROUP", url="https://t.me/Davil_Otp_Group", style="primary")],
            [InlineKeyboardButton("â—€ï¸ BACK", callback_data="back_to_services")]
        ])
        await status_msg.edit_text(final_text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        print(f"Auto Number Error: {e}")
        await status_msg.edit_text(f"âŒ Error: {str(e)}")

async def process_numbers(update_or_query, context, range_text, count, service=""):
    if isinstance(update_or_query, Update) and update_or_query.callback_query:
        uid = update_or_query.callback_query.from_user.id
        chat_id = update_or_query.callback_query.message.chat_id
    else:
        uid = update_or_query.effective_user.id
        chat_id = update_or_query.effective_chat.id
    if is_user_banned(uid):
        await context.bot.send_message(chat_id=chat_id, text="ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    status_msg = await context.bot.send_message(chat_id=chat_id, text="ðŸ” SEARCHING . . .")
    rid = re.sub(r'[^0-9]', '', range_text)
    if not rid:
        await status_msg.edit_text("âŒ INVALID RANGE!")
        return
    try:
        add_number_taken(uid, count)
        last_range[uid] = rid
        num, country = await get_number_from_api(rid)
        if not num:
            await status_msg.edit_text("âŒ NO NUMBERS FOUND. TRY A VALID RANGE.")
            return
        clean_num = normalize_number(num)
        active_numbers[clean_num] = {"uid": uid, "range": range_text, "timestamp": datetime.now()}
        save_number_range_info(uid, clean_num, range_text)
        country_flag, country_name = get_country_info(clean_num)
        final_text = (
            f"âœ… <b>YOUR NUMBER DETAILS</b> âœ…\n\n"
            f"<blockquote>ðŸŒ COUNTRY: <code>{country_flag} {country_name}</code></blockquote>\n"
            f"<blockquote>ðŸ“¶ RANGE: <code>{range_text}</code></blockquote>\n"
            f"{f'<blockquote>ðŸ“± SERVICE: <code>{service.upper()}</code></blockquote>' if service else ''}\n"
            f"<blockquote>ðŸ“ž NUMBER: <code>{num}</code></blockquote>\n\n"
            f"<b>ðŸ“© SMS STATUS: â³ WAITING...</b>"
        )
        svc = service if service else "CUSTOM"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ðŸ”„ SAME RANGE", callback_data=f"same_range_{rid}_{svc}", style="success")],
            [InlineKeyboardButton("ðŸ“¢ OTP GROUP", url="https://t.me/Davil_Otp_Group", style="primary")],
            [InlineKeyboardButton("â—€ï¸ BACK", callback_data="back_to_services")]
        ])
        await status_msg.edit_text(final_text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        print(f"Process Number Error: {e}")
        await status_msg.edit_text(f"âŒ System Error: {str(e)}")

async def perform_otp_search(update, context, target_num):
    uid = str(update.effective_user.id)
    if is_user_banned(int(uid)):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(int(uid)))
        return
    status_msg = await update.message.reply_text("ðŸ” SEARCHING IN SERVER...")
    try:
        r = await client_async.get(f"{BASE_URL}/success-otp")
        res = r.json()
        if res.get("meta", {}).get("code") == 200:
            data_obj = res.get("data")
            if isinstance(data_obj, dict) and "otps" in data_obj:
                all_otps = data_obj.get("otps", [])
            elif isinstance(data_obj, list):
                all_otps = data_obj
            else:
                all_otps = []
            found_otps = [o for o in all_otps if normalize_number(o.get("number", "")) == target_num]
            if not found_otps:
                error_msg = (
                    "â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\nâŒ NO OTP FOUND\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\n"
                    f"ðŸ“ž NUMBER:\n`+{target_num}`\n\nâ³ PLEASE TRY AGAIN LATER\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”"
                )
                await status_msg.edit_text(error_msg, parse_mode="Markdown")
                await update.message.reply_text("ðŸ”™ RETURNING TO MAIN MENU...", reply_markup=main_keyboard(int(uid)))
            else:
                await status_msg.delete()
                paid_data = load_data(PAID_SMS_FILE)
                for o in found_otps:
                    full_sms = o.get('message', "No Content Found")
                    otp_code = extract_otp(full_sms)
                    otp_time = o.get('time', "")
                    key = f"{target_num}_{otp_time}"
                    if key in paid_data:
                        payment_status = "âŒ ALREADY PAID"
                    else:
                        service_name = detect_service(full_sms)
                        is_free = service_name in ("TELEGRAM", "WHATSAPP")
                        if not is_free:
                            user_rate = get_user_otp_rate(int(uid))
                            await update_db_balance(uid, user_rate)
                            add_otp_received(uid)
                            payment_status = f"ðŸ’µ ADD BALANCE FOR {user_rate:.2f} BDT"
                        else:
                            payment_status = "âš ï¸ à¦à¦‡ OTPâ€‘à¦¤à§‡ à¦•à§‹à¦¨à§‹ à¦Ÿà¦¾à¦•à¦¾ à¦¯à§‹à¦— à¦•à¦°à¦¾ à¦¹à§Ÿà¦¨à¦¿ (Telegram/WhatsApp)"
                        paid_data[key] = {"uid": uid, "otp": otp_code}
                    save_data(paid_data, PAID_SMS_FILE)
                    country_flag, country_name = get_country_info(target_num)
                    service_name = detect_service(full_sms)
                    msg = (
                        f"âœ… <b>OTP FOUND!</b>\n\n"
                        f"<blockquote>ðŸŒ COUNTRY: <code>{country_flag} {country_name}</code></blockquote>\n"
                        f"<blockquote>ðŸ“± SERVICE: <code>{service_name}</code></blockquote>\n"
                        f"<blockquote>ðŸ“ž NUMBER: <code>+{target_num}</code></blockquote>\n"
                        f"<blockquote>ðŸ”‘ OTP: <code>{html.escape(otp_code)}</code></blockquote>\n\n"
                        f"<blockquote>ðŸ“© FULL SMS:\n<code>{html.escape(str(full_sms))}</code></blockquote>\n\n"
                        f"<b>{payment_status}</b>"
                    )
                    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=main_keyboard(int(uid)))
        else:
            await status_msg.edit_text("âŒ SERVER RETURNED AN ERROR.")
            await update.message.reply_text("ðŸ”™ Returning to Main Menu...", reply_markup=main_keyboard(int(uid)))
    except Exception as e:
        try:
            await status_msg.edit_text(f"âŒ Error: {str(e)}")
        except:
            await update.message.reply_text(f"âŒ Error: {str(e)}")
        await update.message.reply_text("ðŸ”™ Returning to Main Menu...", reply_markup=main_keyboard(int(uid)))

# ==================== REFER AND EARN ====================
async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    user_data = get_user(uid)
    bot_info = await context.bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start={uid}"
    successful_refers = get_referral_count(uid)
    total_reward = float(successful_refers) * REFERRAL_PRICE
    refer_msg = (
        f"ðŸŽ <b>REFER AND EARN SYSTEM</b> ðŸŽ\n\n"
        f"<blockquote>ðŸš€ INVITE FRIENDS &amp; EARN {int(REFERRAL_PRICE)} BDT EACH! ðŸ’¸</blockquote>\n\n"
        f"<b>ðŸ”— YOUR REFERRAL LINK:</b>\n"
        f"<blockquote><code>{referral_link}</code></blockquote>\n\n"
        f"<b>ðŸ“Š YOUR STATS:</b>\n"
        f"<blockquote>ðŸ‘¥ TOTAL REFERS: {successful_refers}\n"
        f"ðŸ’° TOTAL EARNED: {format_balance(total_reward)} BDT</blockquote>\n\n"
        f"âœ¨ <b>SHARE LINK &amp; EARN MONEY!</b> âœ¨"
    )
    await update.message.reply_text(
        refer_msg,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("ðŸ‘¥ YOUR REFERRAL", callback_data=f"my_ref_{uid}", style="primary")
        ]])
    )

# ==================== WITHDRAW FUNCTIONS ====================
async def withdraw_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    if text == "âŒ CANCEL":
        context.user_data["withdraw_mode"] = None
        await update.message.reply_text("âŒ WITHDRAW CANCELLED", reply_markup=main_keyboard(uid))
        return
    method_map = {"ðŸ“± BKASH": "BKASH", "ðŸ’µ NAGAD": "NAGAD", "ðŸš€ ROCKET": "ROCKET", "ðŸ¦ BINANCE": "BINANCE"}
    if text in method_map:
        method = method_map[text]
        config = load_system_config()
        if not config["payment_methods"].get(method, False):
            await update.message.reply_text("âš ï¸ à¦à¦‡ à¦®à§‡à¦¥à¦¡ à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨à§‡ à¦¬à¦¨à§à¦§ à¦†à¦›à§‡à¥¤ à¦…à¦¨à§à¦¯ à¦®à§‡à¦¥à¦¡ à¦¨à¦¿à¦°à§à¦¬à¦¾à¦šà¦¨ à¦•à¦°à§à¦¨à¥¤", reply_markup=withdraw_method_keyboard())
            return
        balance = get_user(uid)['balance']
        context.user_data["withdraw_method"] = method
        context.user_data["withdraw_mode"] = "amount"
        min_with = config["min_withdraw"]
        max_with = config["max_withdraw"]
        msg = (
            f"<blockquote>ðŸ’¸ SEND YOUR AMOUNT!\n"
            f"ðŸ’µ TOTAL BALANCE: {format_balance(balance)} BDT</blockquote>\n\n"
            f"<blockquote>ðŸ“‰ MINIMUM WITHDRAW {min_with} BDT</blockquote>\n"
            f"<blockquote>ðŸ“ˆ MAXIMUM WITHDRAW {max_with} BDT</blockquote>"
        )
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=cancel_keyboard())
    else:
        await update.message.reply_text("âš ï¸ PLEASE SELECT A VALID PAYMENT METHOD!", reply_markup=withdraw_method_keyboard())

async def withdraw_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    if text == "âŒ CANCEL":
        context.user_data["withdraw_mode"] = None
        await update.message.reply_text("âŒ WITHDRAW CANCELLED", reply_markup=main_keyboard(uid))
        return
    try:
        amount = float(text)
    except:
        await update.message.reply_text("âš ï¸ PLEASE SEND A VALID AMOUNT!", reply_markup=cancel_keyboard())
        return
    balance = get_user(uid)['balance']
    config = load_system_config()
    min_with = config["min_withdraw"]
    max_with = config["max_withdraw"]
    if amount < min_with or amount > max_with:
        await update.message.reply_text(f"ðŸ“‰ MIN: {min_with} BDT | MAX: {max_with} BDT", reply_markup=cancel_keyboard())
        return
    if amount > balance:
        await update.message.reply_text("ðŸš« INSUFFICIENT BALANCE!", reply_markup=cancel_keyboard())
        return
    context.user_data["withdraw_amount"] = amount
    context.user_data["withdraw_mode"] = "number"
    await update.message.reply_text(
        "ðŸ“ž PLEASE SEND YOUR PAYMENT NUMBER!\n\n<blockquote>ðŸ”¢ EXAMPLE: 017XXXXXXXX</blockquote>",
        parse_mode="HTML", reply_markup=cancel_keyboard()
    )

async def withdraw_number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    if text == "âŒ CANCEL":
        context.user_data["withdraw_mode"] = None
        await update.message.reply_text("âŒ WITHDRAW CANCELLED", reply_markup=main_keyboard(uid))
        return
    if not is_valid_bangladesh_number(text):
        await update.message.reply_text("âš ï¸ PLEASE SEND VALID NUMBER! 017XXXXXXXX", reply_markup=cancel_keyboard())
        return
    method = context.user_data.get("withdraw_method")
    amount = context.user_data.get("withdraw_amount")
    payment_number = text
    payment_id = generate_payment_id()
    context.user_data["temp_withdraw"] = {
        "method": method, "amount": amount,
        "number": payment_number, "payment_id": payment_id
    }
    msg = (
        "âœ¨ <b>YOUR PAYMENT DETAILS!</b> âœ¨\n\n"
        f"<blockquote>ðŸ“ METHOD: {method}\n"
        f"ðŸ“ž NUMBER: {payment_number}\n\n"
        f"âœ… CORRECT â†’ CONFIRM\nâŒ WRONG â†’ CANCEL</blockquote>"
    )
    await update.message.reply_text(
        msg, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("âŒ CANCEL", callback_data="withdraw_cancel", style="danger"),
            InlineKeyboardButton("âœ… CONFIRM", callback_data="withdraw_confirm", style="success")
        ]])
    )

async def process_withdraw_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()
    temp_data = context.user_data.get("temp_withdraw")
    if not temp_data:
        await query.message.reply_text("âš ï¸ SESSION EXPIRED.", reply_markup=main_keyboard(uid))
        return
    method = temp_data["method"]
    amount = temp_data["amount"]
    payment_number = temp_data["number"]
    payment_id = temp_data["payment_id"]
    new_balance = await update_db_balance(uid, -amount)
    wr = load_withdraw_requests()
    wr[str(payment_id)] = {
        "user_id": uid, "method": method, "amount": amount,
        "number": payment_number, "payment_id": payment_id,
        "status": "pending", "timestamp": datetime.now().isoformat()
    }
    save_withdraw_requests(wr)
    await query.message.edit_text(
        f"âœ… <b>WITHDRAWAL REQUEST SUBMITTED</b> âœ…\n\n"
        f"<blockquote>ðŸ“ METHOD: <code>{method}</code>\n"
        f"ðŸ“ž NUMBER: <code>{payment_number}</code>\n"
        f"ðŸ’° AMOUNT: <code>{format_balance(amount)} BDT</code>\n"
        f"ðŸ†” ID: <code>{payment_id}</code></blockquote>",
        parse_mode="HTML"
    )
    await context.bot.send_message(uid, "ðŸŽ‰ <b>WITHDRAW REQUEST SUBMITTED!</b>", parse_mode="HTML", reply_markup=main_keyboard(uid))
    admin_msg = (
        f"âœ… <b>NEW WITHDRAWAL REQUEST</b>\n\n"
        f"<blockquote>ðŸ†” USER: <code>{uid}</code>\n"
        f"ðŸ“ METHOD: <code>{method}</code>\n"
        f"ðŸ“ž NUMBER: <code>{payment_number}</code>\n"
        f"ðŸ’° AMOUNT: <code>{format_balance(amount)} BDT</code>\n"
        f"ðŸ†” ID: <code>{payment_id}</code></blockquote>"
    )
    admin_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("âŒ REJECT", callback_data=f"admin_reject_{payment_id}", style="danger"),
        InlineKeyboardButton("âœ… APPROVE", callback_data=f"admin_approve_{payment_id}", style="success")
    ]])
    for admin_id in ADMINS:
        try:
            await context.bot.send_message(admin_id, admin_msg, parse_mode="HTML", reply_markup=admin_kb)
        except Exception as e:
            print(f"Admin notify fail {admin_id}: {e}")
    context.user_data["temp_withdraw"] = None
    context.user_data["withdraw_mode"] = None

async def process_withdraw_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()
    context.user_data["temp_withdraw"] = None
    context.user_data["withdraw_mode"] = None
    await query.message.edit_text("âŒ WITHDRAW CANCELLED")
    await context.bot.send_message(uid, "ðŸ”¹ PLEASE USE THE BUTTONS BELOW:", reply_markup=main_keyboard(uid))

# ==================== ADMIN PANEL - WITHDRAW APPROVAL ====================
async def admin_approve_withdraw(update, context, payment_id):
    query = update.callback_query
    await query.answer()
    wr = load_withdraw_requests()
    if payment_id not in wr:
        await query.message.reply_text("âš ï¸ REQUEST NOT FOUND!")
        return
    rd = wr[payment_id]
    uid = rd["user_id"]
    method = rd["method"]
    amount = rd["amount"]
    payment_number = rd["number"]
    wr[payment_id]["status"] = "approved"
    save_withdraw_requests(wr)
    try:
        await context.bot.send_message(
            uid,
            f"ðŸŽ‰ <b>WITHDRAWAL APPROVED!</b>\n\n"
            f"<blockquote>ðŸ“ METHOD: <code>{method}</code>\n"
            f"ðŸ“ž NUMBER: <code>{payment_number}</code>\n"
            f"ðŸ’° AMOUNT: <code>{format_balance(amount)} BDT</code></blockquote>",
            parse_mode="HTML"
        )
    except:
        pass
    await query.message.edit_text(f"âœ… APPROVED | User: {uid} | Amount: {format_balance(amount)} BDT")

async def admin_reject_withdraw(update, context, payment_id):
    query = update.callback_query
    await query.answer()
    wr = load_withdraw_requests()
    if payment_id not in wr:
        await query.message.reply_text("âš ï¸ REQUEST NOT FOUND!")
        return
    rd = wr[payment_id]
    uid = rd["user_id"]
    amount = rd["amount"]
    wr[payment_id]["status"] = "rejected"
    save_withdraw_requests(wr)
    try:
        await context.bot.send_message(uid, "âŒ **WITHDRAWAL REQUEST REJECTED**\n\nContact admin for more info.", parse_mode="Markdown")
    except:
        pass
    await query.message.edit_text(f"âŒ REJECTED | User: {uid} | Amount: {format_balance(amount)} BDT")

# ==================== ADMIN PANEL - BALANCE MANAGEMENT ====================
async def admin_add_balance_start(update, context):
    context.user_data["add_balance_mode"] = True
    context.user_data["remove_balance_mode"] = False
    await update.message.reply_text("ðŸ’° SEND USER ID TO ADD BALANCE:")

async def admin_remove_balance_start(update, context):
    context.user_data["remove_balance_mode"] = True
    context.user_data["add_balance_mode"] = False
    await update.message.reply_text("ðŸ’¸ SEND USER ID TO REMOVE BALANCE:")

async def process_add_balance_user(update, context):
    uid_to_add = update.message.text.strip()
    if not uid_to_add.isdigit():
        await update.message.reply_text("âŒ INVALID USER ID!")
        return
    uid_to_add_int = int(uid_to_add)
    if not user_exists(uid_to_add_int):
        await update.message.reply_text("âŒ USER NOT FOUND!")
        context.user_data["add_balance_mode"] = False
        return
    context.user_data["pending_add_user"] = uid_to_add_int
    await update.message.reply_text("ðŸ’µ SEND AMOUNT TO ADD:")

async def process_remove_balance_user(update, context):
    uid_to_remove = update.message.text.strip()
    if not uid_to_remove.isdigit():
        await update.message.reply_text("âŒ INVALID USER ID!")
        return
    uid_to_remove_int = int(uid_to_remove)
    if not user_exists(uid_to_remove_int):
        await update.message.reply_text("âŒ USER NOT FOUND!")
        context.user_data["remove_balance_mode"] = False
        return
    context.user_data["pending_remove_user"] = uid_to_remove_int
    await update.message.reply_text("ðŸ’¸ SEND AMOUNT TO REMOVE:")

async def process_add_balance_amount(update, context):
    try:
        amount = float(update.message.text.strip())
        if amount <= 0: raise ValueError
    except:
        await update.message.reply_text("âŒ INVALID AMOUNT!")
        return
    uid = context.user_data.get("pending_add_user")
    if not uid:
        context.user_data["add_balance_mode"] = False
        await update.message.reply_text("âš ï¸ SESSION EXPIRED.")
        return
    old_balance = get_user(uid).get("balance", 0)
    new_balance = await update_db_balance(uid, amount)
    await update.message.reply_text(
        f"âœ… **ADD BALANCE SUCCESSFUL**\nðŸ†” USER: `{uid}`\n"
        f"ðŸ’° ADDED: `{format_balance(amount)} BDT`\n"
        f"ðŸ“ˆ NEW BALANCE: `{format_balance(new_balance)} BDT`",
        parse_mode="Markdown"
    )
    try:
        await context.bot.send_message(uid, f"ðŸŽ‰ ADMIN ADDED `{format_balance(amount)} BDT` TO YOUR ACCOUNT!\nðŸ’µ NEW BALANCE: `{format_balance(new_balance)} BDT`", parse_mode="Markdown")
    except:
        pass
    context.user_data["add_balance_mode"] = False
    context.user_data["pending_add_user"] = None

async def process_remove_balance_amount(update, context):
    try:
        amount = float(update.message.text.strip())
        if amount <= 0: raise ValueError
    except:
        await update.message.reply_text("âŒ INVALID AMOUNT!")
        return
    uid = context.user_data.get("pending_remove_user")
    if not uid:
        context.user_data["remove_balance_mode"] = False
        await update.message.reply_text("âš ï¸ SESSION EXPIRED.")
        return
    old_balance = get_user(uid).get("balance", 0)
    if amount > old_balance:
        await update.message.reply_text(f"âŒ INSUFFICIENT BALANCE! Current: {format_balance(old_balance)} BDT")
        context.user_data["remove_balance_mode"] = False
        context.user_data["pending_remove_user"] = None
        return
    new_balance = await update_db_balance(uid, -amount)
    await update.message.reply_text(
        f"âœ… **REMOVE BALANCE SUCCESSFUL**\nðŸ†” USER: `{uid}`\n"
        f"ðŸ’¸ REMOVED: `{format_balance(amount)} BDT`\n"
        f"ðŸ“‰ NEW BALANCE: `{format_balance(new_balance)} BDT`",
        parse_mode="Markdown"
    )
    try:
        await context.bot.send_message(uid, f"âš ï¸ ADMIN REMOVED `{format_balance(amount)} BDT` FROM YOUR ACCOUNT!\nðŸ’µ NEW BALANCE: `{format_balance(new_balance)} BDT`", parse_mode="Markdown")
    except:
        pass
    context.user_data["remove_balance_mode"] = False
    context.user_data["pending_remove_user"] = None

# ==================== ADMIN PANEL - BAN/UNBAN ====================
async def admin_ban_user_start(update, context):
    context.user_data["admin_ban_mode"] = True
    context.user_data["admin_unban_mode"] = False
    await update.message.reply_text("ðŸš« SEND TELEGRAM ID TO BAN USER:")

async def admin_unban_user_start(update, context):
    context.user_data["admin_unban_mode"] = True
    context.user_data["admin_ban_mode"] = False
    await update.message.reply_text("ðŸ”“ SEND TELEGRAM ID TO UNBAN USER:")

async def process_ban_user(update, context):
    uid_to_ban = update.message.text.strip()
    if not uid_to_ban.isdigit():
        await update.message.reply_text("âŒ INVALID USER ID!")
        return
    uid_to_ban_int = int(uid_to_ban)
    if not user_exists(uid_to_ban_int):
        await update.message.reply_text("âŒ USER NOT FOUND!")
        context.user_data["admin_ban_mode"] = False
        return
    if is_user_banned(uid_to_ban_int):
        await update.message.reply_text("âš ï¸ USER IS ALREADY BANNED!")
        context.user_data["admin_ban_mode"] = False
        return
    ban_user(uid_to_ban_int)
    try:
        await context.bot.send_message(uid_to_ban_int, "ðŸš« **YOU HAVE BEEN BANNED**\nðŸ“ž Contact support.", parse_mode="Markdown")
    except:
        pass
    await update.message.reply_text(f"âœ… USER `{uid_to_ban}` BANNED!", parse_mode="Markdown", reply_markup=system_config_keyboard())
    context.user_data["admin_ban_mode"] = False

async def process_unban_user(update, context):
    uid_to_unban = update.message.text.strip()
    if not uid_to_unban.isdigit():
        await update.message.reply_text("âŒ INVALID USER ID!")
        return
    uid_to_unban_int = int(uid_to_unban)
    if not is_user_banned(uid_to_unban_int):
        await update.message.reply_text("âš ï¸ THIS USER IS NOT BANNED!")
        context.user_data["admin_unban_mode"] = False
        return
    unban_user(uid_to_unban_int)
    try:
        await context.bot.send_message(uid_to_unban_int, "âœ… **YOU HAVE BEEN UNBANNED!** Use /start", parse_mode="Markdown")
    except:
        pass
    await update.message.reply_text(f"âœ… USER `{uid_to_unban}` UNBANNED!", parse_mode="Markdown", reply_markup=system_config_keyboard())
    context.user_data["admin_unban_mode"] = False

async def show_banned_users_list(update, context):
    banned_list = load_banned_users()
    if not banned_list:
        await update.message.reply_text("ðŸ“œ NO BANNED USERS.", reply_markup=system_config_keyboard())
        return
    text = "ðŸ“œ **BANNED USER LIST**\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\n"
    for i, uid in enumerate(banned_list, 1):
        text += f"{i}. `{uid}`\n"
    text += f"\nðŸ“Š Total: {len(banned_list)}"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=system_config_keyboard())

# ==================== ADMIN PANEL - SYSTEM CONFIG ====================
async def admin_change_min_withdraw_start(update, context):
    context.user_data["admin_min_withdraw_mode"] = True
    await update.message.reply_text("ðŸ’µ à¦¸à§‡à¦¨à§à¦¡ à¦¦à§à¦¯ à¦¨à¦¿à¦‰ à¦®à¦¿à¦¨à¦¿à¦®à¦¾à¦® à¦‰à¦‡à¦¥à¦¡à§à¦° à¦…à§à¦¯à¦¾à¦®à¦¾à¦‰à¦¨à§à¦Ÿ (à¦¶à§à¦§à§ à¦¸à¦‚à¦–à§à¦¯à¦¾):\n\nà¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦®à¦¾à¦¨: " + str(load_system_config()["min_withdraw"]), reply_markup=cancel_keyboard())

async def admin_change_min_withdraw_amount(update, context):
    if not context.user_data.get("admin_min_withdraw_mode"):
        return
    try:
        new_min = float(update.message.text.strip())
        if new_min < 0:
            raise ValueError
        update_min_withdraw(new_min)
        await update.message.reply_text(f"âœ… à¦®à¦¿à¦¨à¦¿à¦®à¦¾à¦® à¦‰à¦‡à¦¥à¦¡à§à¦° à¦…à§à¦¯à¦¾à¦®à¦¾à¦‰à¦¨à§à¦Ÿ à¦ªà¦°à¦¿à¦¬à¦°à§à¦¤à¦¨ à¦•à¦°à§‡ {new_min} BDT à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=system_config_keyboard())
    except:
        await update.message.reply_text("âŒ à¦­à§à¦¯à¦¾à¦²à¦¿à¦¡ à¦…à§à¦¯à¦¾à¦®à¦¾à¦‰à¦¨à§à¦Ÿ à¦¦à¦¿à¦¨à¥¤", reply_markup=system_config_keyboard())
    finally:
        context.user_data["admin_min_withdraw_mode"] = False

async def admin_change_otp_rate_start(update, context):
    context.user_data["admin_otp_rate_mode"] = True
    current_rate = get_otp_rate()
    await update.message.reply_text(
        f"ðŸ’² à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ OTP à¦°à§‡à¦Ÿ: `{current_rate:.2f} BDT`\n\nà¦¸à§‡à¦¨à§à¦¡ à¦¦à§à¦¯ à¦¨à¦¿à¦‰ à¦°à§‡à¦Ÿ (à¦¶à§à¦§à§ à¦¸à¦‚à¦–à§à¦¯à¦¾, à¦¯à§‡à¦®à¦¨: `0.25`):\n\n<blockquote>à¦¸à¦¾à¦¬à¦§à¦¾à¦¨: à¦à¦Ÿà¦¿ à¦¸à¦¬ à¦¨à¦¤à§à¦¨ OTP-à¦¤à§‡ à¦ªà§à¦°à¦¯à§‹à¦œà§à¦¯ à¦¹à¦¬à§‡à¥¤</blockquote>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )

async def admin_change_otp_rate_amount(update, context):
    if not context.user_data.get("admin_otp_rate_mode"):
        return
    try:
        new_rate = float(update.message.text.strip())
        if new_rate <= 0:
            raise ValueError
        update_otp_rate(new_rate)
        await update.message.reply_text(f"âœ… OTP à¦°à§‡à¦Ÿ à¦ªà¦°à¦¿à¦¬à¦°à§à¦¤à¦¨ à¦•à¦°à§‡ `{new_rate:.2f} BDT` à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤\n\nà¦¨à¦¤à§à¦¨ OTP à¦—à§à¦²à§‹ à¦à¦‡ à¦¹à¦¾à¦°à§‡ à¦¯à§à¦•à§à¦¤ à¦¹à¦¬à§‡à¥¤", parse_mode="HTML", reply_markup=system_config_keyboard())
    except:
        await update.message.reply_text("âŒ à¦­à§à¦¯à¦¾à¦²à¦¿à¦¡ à¦°à§‡à¦Ÿ à¦¦à¦¿à¦¨ (à¦¯à§‡à¦®à¦¨: 0.25)à¥¤", reply_markup=system_config_keyboard())
    finally:
        context.user_data["admin_otp_rate_mode"] = False

# ==================== ADMIN PANEL - PER-USER OTP RATE ====================
async def admin_set_user_otp_rate_start(update, context):
    context.user_data["admin_set_otp_rate_mode"] = "user"
    await update.message.reply_text(
        "ðŸ”§ **SET USER OTP RATE**\n\n"
        "à¦¦à§Ÿà¦¾ à¦•à¦°à§‡ à¦‡à¦‰à¦œà¦¾à¦° à¦†à¦‡à¦¡à¦¿ à¦‡à¦¨à¦ªà§à¦Ÿ à¦¦à¦¿à¦¨ (à¦¶à§à¦§à§ à¦¸à¦‚à¦–à§à¦¯à¦¾):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )

async def admin_set_user_otp_rate_user(update, context):
    uid_str = update.message.text.strip()
    if uid_str == "âŒ CANCEL":
        context.user_data["admin_set_otp_rate_mode"] = None
        await update.message.reply_text("âŒ à¦…à¦ªà¦¾à¦°à§‡à¦¶à¦¨ à¦¬à¦¾à¦¤à¦¿à¦² à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=system_config_keyboard())
        return
    if not uid_str.isdigit():
        await update.message.reply_text("âŒ à¦­à§à¦¯à¦¾à¦²à¦¿à¦¡ à¦‡à¦‰à¦œà¦¾à¦° à¦†à¦‡à¦¡à¦¿ à¦¦à¦¿à¦¨ (à¦¶à§à¦§à§ à¦¸à¦‚à¦–à§à¦¯à¦¾)!", reply_markup=cancel_keyboard())
        return
    uid_int = int(uid_str)
    if not user_exists(uid_int):
        await update.message.reply_text("âŒ à¦à¦‡ à¦‡à¦‰à¦œà¦¾à¦°à¦Ÿà¦¿ à¦°à§‡à¦œà¦¿à¦¸à§à¦Ÿà¦¾à¦°à§à¦¡ à¦¨à§Ÿà¥¤ à¦†à¦¬à¦¾à¦° à¦šà§‡à¦·à§à¦Ÿà¦¾ à¦•à¦°à§à¦¨à¥¤", reply_markup=cancel_keyboard())
        return
    context.user_data["admin_set_otp_rate_user"] = uid_int
    context.user_data["admin_set_otp_rate_mode"] = "rate"
    current_rate = get_user_otp_rate(uid_int)
    global_rate = get_otp_rate()
    await update.message.reply_text(
        f"à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦‡à¦‰à¦œà¦¾à¦° à¦°à§‡à¦Ÿ: `{current_rate:.2f} BDT`\n"
        f"à¦—à§à¦²à§‹à¦¬à¦¾à¦² à¦°à§‡à¦Ÿ: `{global_rate:.2f} BDT`\n\n"
        "à¦¨à¦¤à§à¦¨ à¦°à§‡à¦Ÿ à¦‡à¦¨à¦ªà§à¦Ÿ à¦¦à¦¿à¦¨ (à¦¶à§à¦§à§ à¦¸à¦‚à¦–à§à¦¯à¦¾, à¦¯à§‡à¦®à¦¨: 0.25):\n"
        "à¦°à§‡à¦Ÿ 0 à¦¦à¦¿à¦²à§‡ à¦•à¦¾à¦¸à§à¦Ÿà¦® à¦°à§‡à¦Ÿ à¦®à§à¦›à§‡ à¦¯à¦¾à¦¬à§‡ à¦à¦¬à¦‚ à¦—à§à¦²à§‹à¦¬à¦¾à¦² à¦°à§‡à¦Ÿ à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦¹à¦¬à§‡à¥¤",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )

async def admin_set_user_otp_rate_amount(update, context):
    if context.user_data.get("admin_set_otp_rate_mode") != "rate":
        return
    uid = context.user_data.get("admin_set_otp_rate_user")
    if not uid:
        context.user_data["admin_set_otp_rate_mode"] = None
        await update.message.reply_text("âš ï¸ à¦¸à§‡à¦¶à¦¨ à¦¶à§‡à¦·à¥¤ à¦†à¦¬à¦¾à¦° à¦šà§‡à¦·à§à¦Ÿà¦¾ à¦•à¦°à§à¦¨à¥¤", reply_markup=system_config_keyboard())
        return
    text = update.message.text.strip()
    if text == "âŒ CANCEL":
        context.user_data["admin_set_otp_rate_mode"] = None
        context.user_data["admin_set_otp_rate_user"] = None
        await update.message.reply_text("âŒ à¦…à¦ªà¦¾à¦°à§‡à¦¶à¦¨ à¦¬à¦¾à¦¤à¦¿à¦² à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=system_config_keyboard())
        return
    try:
        rate = float(text)
        if rate < 0:
            raise ValueError
    except:
        await update.message.reply_text("âŒ à¦­à§à¦¯à¦¾à¦²à¦¿à¦¡ à¦°à§‡à¦Ÿ à¦‡à¦¨à¦ªà§à¦Ÿ à¦¦à¦¿à¦¨ (à¦¯à§‡à¦®à¦¨: 0.25)!", reply_markup=cancel_keyboard())
        return
    set_user_otp_rate(uid, rate)
    if rate > 0:
        await update.message.reply_text(
            f"âœ… à¦‡à¦‰à¦œà¦¾à¦° `{uid}` à¦à¦° à¦œà¦¨à§à¦¯ OTP à¦°à§‡à¦Ÿ `{rate:.2f} BDT` à¦¸à§‡à¦Ÿ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤",
            parse_mode="Markdown",
            reply_markup=system_config_keyboard()
        )
    else:
        await update.message.reply_text(
            f"âœ… à¦‡à¦‰à¦œà¦¾à¦° `{uid}` à¦à¦° à¦•à¦¾à¦¸à§à¦Ÿà¦® OTP à¦°à§‡à¦Ÿ à¦®à§à¦›à§‡ à¦«à§‡à¦²à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤ à¦à¦–à¦¨ à¦—à§à¦²à§‹à¦¬à¦¾à¦² à¦°à§‡à¦Ÿ `{get_otp_rate():.2f} BDT` à¦ªà§à¦°à¦¯à§‹à¦œà§à¦¯ à¦¹à¦¬à§‡à¥¤",
            parse_mode="Markdown",
            reply_markup=system_config_keyboard()
        )
    context.user_data["admin_set_otp_rate_mode"] = None
    context.user_data["admin_set_otp_rate_user"] = None

async def admin_view_user_otp_rate_start(update, context):
    context.user_data["admin_view_otp_rate_mode"] = True
    await update.message.reply_text(
        "ðŸ“‹ **VIEW USER OTP RATE**\n\n"
        "à¦¦à§Ÿà¦¾ à¦•à¦°à§‡ à¦‡à¦‰à¦œà¦¾à¦° à¦†à¦‡à¦¡à¦¿ à¦‡à¦¨à¦ªà§à¦Ÿ à¦¦à¦¿à¦¨ (à¦¶à§à¦§à§ à¦¸à¦‚à¦–à§à¦¯à¦¾):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )

async def admin_view_user_otp_rate(update, context):
    if not context.user_data.get("admin_view_otp_rate_mode"):
        return
    uid_str = update.message.text.strip()
    if uid_str == "âŒ CANCEL":
        context.user_data["admin_view_otp_rate_mode"] = None
        await update.message.reply_text("âŒ à¦…à¦ªà¦¾à¦°à§‡à¦¶à¦¨ à¦¬à¦¾à¦¤à¦¿à¦² à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=system_config_keyboard())
        return
    if not uid_str.isdigit():
        await update.message.reply_text("âŒ à¦­à§à¦¯à¦¾à¦²à¦¿à¦¡ à¦‡à¦‰à¦œà¦¾à¦° à¦†à¦‡à¦¡à¦¿ à¦¦à¦¿à¦¨ (à¦¶à§à¦§à§ à¦¸à¦‚à¦–à§à¦¯à¦¾)!", reply_markup=cancel_keyboard())
        return
    uid_int = int(uid_str)
    if not user_exists(uid_int):
        await update.message.reply_text("âŒ à¦à¦‡ à¦‡à¦‰à¦œà¦¾à¦°à¦Ÿà¦¿ à¦°à§‡à¦œà¦¿à¦¸à§à¦Ÿà¦¾à¦°à§à¦¡ à¦¨à§Ÿà¥¤", reply_markup=system_config_keyboard())
        context.user_data["admin_view_otp_rate_mode"] = None
        return
    custom_rate = get_user_otp_rate(uid_int)
    global_rate = get_otp_rate()
    rates = load_user_otp_rates()
    has_custom = str(uid_int) in rates and rates[str(uid_int)] > 0
    msg = (
        f"ðŸ“Š **USER OTP RATE INFO**\n"
        f"ðŸ†” à¦‡à¦‰à¦œà¦¾à¦°: `{uid_int}`\n"
        f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
        f"ðŸŽ¯ à¦•à¦¾à¦¸à§à¦Ÿà¦® à¦°à§‡à¦Ÿ: `{custom_rate:.2f} BDT`\n"
        f"ðŸŒ à¦—à§à¦²à§‹à¦¬à¦¾à¦² à¦°à§‡à¦Ÿ: `{global_rate:.2f} BDT`\n"
        f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
        f"ðŸ”¹ { 'à¦à¦‡ à¦‡à¦‰à¦œà¦¾à¦°à§‡à¦° à¦œà¦¨à§à¦¯ à¦•à¦¾à¦¸à§à¦Ÿà¦® à¦°à§‡à¦Ÿ à¦¸à¦•à§à¦°à¦¿à§Ÿà¥¤' if has_custom else 'à¦à¦‡ à¦‡à¦‰à¦œà¦¾à¦°à§‡à¦° à¦œà¦¨à§à¦¯ à¦•à¦¾à¦¸à§à¦Ÿà¦® à¦°à§‡à¦Ÿ à¦¨à§‡à¦‡, à¦—à§à¦²à§‹à¦¬à¦¾à¦² à¦°à§‡à¦Ÿ à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦¹à¦¬à§‡à¥¤' }"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=system_config_keyboard())
    context.user_data["admin_view_otp_rate_mode"] = None

# ==================== ADMIN PANEL - SHOW ALL USERS ====================
async def admin_show_all_users(update, context):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    user_db = load_data(USER_DATA_FILE)
    all_uids = list(user_db.keys())
    total_users = len(all_uids)
    if total_users == 0:
        await update.message.reply_text("ðŸ“Š à¦®à§‹à¦Ÿ à¦‡à¦‰à¦œà¦¾à¦°: 0\nà¦•à§‹à¦¨à§‹ à¦‡à¦‰à¦œà¦¾à¦° à¦°à§‡à¦œà¦¿à¦¸à§à¦Ÿà¦¾à¦°à§à¦¡ à¦¨à§‡à¦‡à¥¤", reply_markup=user_management_keyboard())
        return
    user_list_sorted = sorted(all_uids, key=int)
    if total_users <= 50:
        lines = [f"{i+1}. `{uid}`" for i, uid in enumerate(user_list_sorted)]
        user_list_text = "\n".join(lines)
        msg = f"ðŸ“Š **à¦®à§‹à¦Ÿ à¦‡à¦‰à¦œà¦¾à¦°:** `{total_users}`\n\n**à¦‡à¦‰à¦œà¦¾à¦° à¦²à¦¿à¦¸à§à¦Ÿ:**\n{user_list_text}"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=user_management_keyboard())
    else:
        content = f"Total Users: {total_users}\n\n" + "\n".join(user_list_sorted)
        f = io.BytesIO(content.encode())
        f.name = f"all_users_{total_users}.txt"
        await update.message.reply_document(
            document=f,
            caption=f"ðŸ“Š à¦®à§‹à¦Ÿ à¦‡à¦‰à¦œà¦¾à¦°: {total_users}\nà¦‡à¦‰à¦œà¦¾à¦° à¦†à¦‡à¦¡à¦¿ à¦²à¦¿à¦¸à§à¦Ÿ à¦¸à¦‚à¦¯à§à¦•à§à¦¤à¥¤",
            reply_markup=user_management_keyboard()
        )

# ==================== ADMIN PANEL - TOGGLE PAYMENT METHODS ====================
async def admin_toggle_payment_methods(update, context):
    config = load_system_config()
    methods = config["payment_methods"]
    buttons = []
    for method, enabled in methods.items():
        status = "âœ…" if enabled else "âŒ"
        buttons.append([InlineKeyboardButton(f"{status} {method}", callback_data=f"toggle_method_{method}")])
    buttons.append([InlineKeyboardButton("ðŸ”™ BACK", callback_data="back_to_admin_panel")])
    await update.message.reply_text(
        "ðŸ’³ à¦ªà§‡à¦®à§‡à¦¨à§à¦Ÿ à¦®à§‡à¦¥à¦¡ à¦Ÿà¦—à¦² à¦•à¦°à§à¦¨:\n\nà¦¸à¦¬à§à¦œ à¦šà¦¿à¦¹à§à¦¨ à¦®à¦¾à¦¨à§‡ à¦¸à¦šà¦², à¦²à¦¾à¦² à¦®à¦¾à¦¨à§‡ à¦¬à¦¨à§à¦§à¥¤\nà¦•à§à¦²à¦¿à¦• à¦•à¦°à§‡ à¦šà§‡à¦žà§à¦œ à¦•à¦°à§à¦¨à¥¤",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_toggle_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("toggle_method_"):
        method = data.replace("toggle_method_", "")
        new_state = toggle_payment_method(method)
        status = "à¦¸à¦šà¦² âœ…" if new_state else "à¦¬à¦¨à§à¦§ âŒ"
        await query.edit_message_text(f"âœ… {method} à¦®à§‡à¦¥à¦¡ à¦à¦–à¦¨ {status}à¥¤", reply_markup=query.message.reply_markup)
        config = load_system_config()
        methods = config["payment_methods"]
        buttons = []
        for m, enabled in methods.items():
            st = "âœ…" if enabled else "âŒ"
            buttons.append([InlineKeyboardButton(f"{st} {m}", callback_data=f"toggle_method_{m}")])
        buttons.append([InlineKeyboardButton("ðŸ”™ BACK", callback_data="back_to_admin_panel")])
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
    elif data == "back_to_admin_panel":
        await query.message.delete()
        await query.message.chat.send_message("âš™ï¸ System Configuration:", reply_markup=system_config_keyboard())

# ==================== ADMIN PANEL - REQUIRED CHANNELS ====================
async def admin_add_channel_start(update, context):
    context.user_data["add_channel_mode"] = True
    await update.message.reply_text(
        "âž• **ADD CHANNEL/GROUP**\n\n"
        "à¦«à¦°à¦®à§à¦¯à¦¾à¦Ÿ: `à¦²à¦¿à¦‚à¦•|à¦²à§‡à¦¬à§‡à¦²` (à¦²à§‡à¦¬à§‡à¦² à¦à¦šà§à¦›à¦¿à¦•)\n"
        "à¦‰à¦¦à¦¾à¦¹à¦°à¦£: `https://t.me/Davil_Earn_Master|ðŸ“¢ à¦†à¦®à¦¾à¦¦à§‡à¦° à¦šà§à¦¯à¦¾à¦¨à§‡à¦²`\n"
        "à¦¯à¦¦à¦¿ à¦²à§‡à¦¬à§‡à¦² à¦¨à¦¾ à¦¦à§‡à¦¨, à¦¤à¦¾à¦¹à¦²à§‡ à¦²à¦¿à¦‚à¦• à¦¥à§‡à¦•à§‡ à¦¸à§à¦¬à§Ÿà¦‚à¦•à§à¦°à¦¿à§Ÿ à¦¤à§ˆà¦°à¦¿ à¦¹à¦¬à§‡à¥¤\n\n"
        "à¦ªà§à¦°à¦¾à¦‡à¦­à§‡à¦Ÿ à¦²à¦¿à¦‚à¦•à§‡à¦° à¦œà¦¨à§à¦¯: `à¦²à¦¿à¦‚à¦•|à¦šà§à¦¯à¦¾à¦Ÿ_à¦†à¦‡à¦¡à¦¿|à¦²à§‡à¦¬à§‡à¦²`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )

async def admin_process_add_channel(update, context):
    if not context.user_data.get("add_channel_mode"):
        return
    text = update.message.text.strip()
    if text == "âŒ CANCEL":
        context.user_data["add_channel_mode"] = None
        await update.message.reply_text("âŒ à¦¬à¦¾à¦¤à¦¿à¦² à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=required_channels_keyboard())
        return
    parts = text.split("|")
    link = parts[0].strip()
    label = None
    chat_id = None
    if len(parts) > 1:
        if parts[1].strip().isdigit():
            chat_id = int(parts[1].strip())
            if len(parts) > 2:
                label = parts[2].strip()
        else:
            label = parts[1].strip()
    if len(parts) > 2 and not chat_id:
        label = parts[1].strip()
        if parts[2].strip().isdigit():
            chat_id = int(parts[2].strip())
    success, msg = add_required_channel(link, label, chat_id)
    if success:
        await update.message.reply_text(f"âœ… {msg}", reply_markup=required_channels_keyboard())
    else:
        await update.message.reply_text(f"âŒ {msg}", reply_markup=cancel_keyboard())
    context.user_data["add_channel_mode"] = None

async def admin_remove_channel_start(update, context):
    context.user_data["remove_channel_mode"] = True
    await update.message.reply_text(
        "âŒ **REMOVE CHANNEL/GROUP**\n\n"
        "à¦¦à§Ÿà¦¾ à¦•à¦°à§‡ à¦¯à§‡ à¦²à¦¿à¦‚à¦• à¦¬à¦¾ à¦²à§‡à¦¬à§‡à¦² à¦°à¦¿à¦®à§à¦­ à¦•à¦°à¦¤à§‡ à¦šà¦¾à¦¨ à¦¤à¦¾ à¦¦à¦¿à¦¨:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )

async def admin_process_remove_channel(update, context):
    if not context.user_data.get("remove_channel_mode"):
        return
    text = update.message.text.strip()
    if text == "âŒ CANCEL":
        context.user_data["remove_channel_mode"] = None
        await update.message.reply_text("âŒ à¦¬à¦¾à¦¤à¦¿à¦² à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=required_channels_keyboard())
        return
    success, msg = remove_required_channel(text)
    if success:
        await update.message.reply_text(f"âœ… {msg}", reply_markup=required_channels_keyboard())
    else:
        await update.message.reply_text(f"âŒ {msg}", reply_markup=cancel_keyboard())
    context.user_data["remove_channel_mode"] = None

async def admin_list_channels(update, context):
    channels = get_all_required_channels()
    if not channels:
        await update.message.reply_text("ðŸ“‹ à¦•à§‹à¦¨à§‹ à¦šà§à¦¯à¦¾à¦¨à§‡à¦²/à¦—à§à¦°à§à¦ª à¦¯à§‹à¦— à¦•à¦°à¦¾ à¦¹à§Ÿà¦¨à¦¿à¥¤", reply_markup=required_channels_keyboard())
        return
    text = "ðŸ“‹ **à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦šà§à¦¯à¦¾à¦¨à§‡à¦²/à¦—à§à¦°à§à¦ª à¦²à¦¿à¦¸à§à¦Ÿ:**\n\n"
    for i, ch in enumerate(channels, 1):
        link = ch.get("link", "N/A")
        label = ch.get("label", "N/A")
        style = ch.get("style", "primary")
        cid = ch.get("chat_id", "N/A")
        text += f"{i}. à¦²à§‡à¦¬à§‡à¦²: `{label}`\n   à¦²à¦¿à¦‚à¦•: `{link}`\n   à¦¸à§à¦Ÿà¦¾à¦‡à¦²: `{style}`\n   chat_id: `{cid}`\n\n"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=required_channels_keyboard())

# ==================== ADMIN PANEL - FAKE OTP ====================
async def admin_fake_otp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show fake OTP management menu."""
    await update.message.reply_text(
        "âš¡ **FAKE OTP SYSTEM** âš¡\n\n"
        "à¦à¦–à¦¾à¦¨ à¦¥à§‡à¦•à§‡ à¦«à§‡à¦• OTP à¦šà¦¾à¦²à§/à¦¬à¦¨à§à¦§ à¦à¦¬à¦‚ à¦¸à§‡à¦Ÿà¦¿à¦‚à¦¸ à¦ªà¦°à¦¿à¦¬à¦°à§à¦¤à¦¨ à¦•à¦°à¦¤à§‡ à¦ªà¦¾à¦°à§‡à¦¨à¥¤\n"
        "à¦«à§‡à¦• OTP à¦—à§à¦°à§à¦ªà§‡ à¦°à¦¿à§Ÿà§‡à¦² OTP-à¦à¦° à¦®à¦¤à§‹ à¦¦à§‡à¦–à¦¾à¦¬à§‡, à¦•à¦¿à¦¨à§à¦¤à§ à¦‡à¦‰à¦œà¦¾à¦°à¦¦à§‡à¦° à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸à§‡ à¦•à§‹à¦¨à§‹ à¦ªà§à¦°à¦­à¦¾à¦¬ à¦ªà§œà¦¬à§‡ à¦¨à¦¾à¥¤",
        reply_markup=fake_otp_keyboard()
    )

async def admin_fake_otp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start fake OTP generation."""
    config = load_fake_otp_config()
    if config.get("running", False):
        await update.message.reply_text("âš ï¸ à¦«à§‡à¦• OTP à¦‡à¦¤à¦¿à¦®à¦§à§à¦¯à§‡ à¦šà¦¾à¦²à§ à¦†à¦›à§‡à¥¤")
        return
    config["running"] = True
    save_fake_otp_config(config)
    await update.message.reply_text("âœ… **à¦«à§‡à¦• OTP à¦šà¦¾à¦²à§ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤**\n\nà¦¶à§€à¦˜à§à¦°à¦‡ à¦—à§à¦°à§à¦ªà§‡ à¦«à§‡à¦• OTP à¦†à¦¸à¦¾ à¦¶à§à¦°à§ à¦¹à¦¬à§‡à¥¤", reply_markup=fake_otp_keyboard())

async def admin_fake_otp_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop fake OTP generation."""
    config = load_fake_otp_config()
    if not config.get("running", False):
        await update.message.reply_text("âš ï¸ à¦«à§‡à¦• OTP à¦‡à¦¤à¦¿à¦®à¦§à§à¦¯à§‡ à¦¬à¦¨à§à¦§ à¦†à¦›à§‡à¥¤")
        return
    config["running"] = False
    save_fake_otp_config(config)
    await update.message.reply_text("â¹ **à¦«à§‡à¦• OTP à¦¬à¦¨à§à¦§ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤**", reply_markup=fake_otp_keyboard())

async def admin_fake_otp_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings submenu with options to set service, range, interval, otp digits."""
    config = load_fake_otp_config()
    service = config.get("service", "facebook")
    range_val = config.get("range", "Not set (auto)")
    interval = config.get("interval", 10)
    otp_digits = config.get("otp_digits", 6)
    status = "âœ… à¦šà¦²à¦›à§‡" if config.get("running", False) else "âŒ à¦¬à¦¨à§à¦§"
    msg = (
        f"âš™ï¸ **à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦¸à§‡à¦Ÿà¦¿à¦‚à¦¸**\n\n"
        f"ðŸ“± à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸: `{service}`\n"
        f"ðŸ“¶ à¦°à§‡à¦žà§à¦œ: `{range_val}`\n"
        f"â± à¦‡à¦¨à§à¦Ÿà¦¾à¦°à¦­à§à¦¯à¦¾à¦²: `{interval} à¦¸à§‡à¦•à§‡à¦¨à§à¦¡`\n"
        f"ðŸ”¢ OTP à¦¡à¦¿à¦œà¦¿à¦Ÿ: `{otp_digits}`\n"
        f"ðŸ“Š à¦¸à§à¦Ÿà§à¦¯à¦¾à¦Ÿà¦¾à¦¸: {status}\n\n"
        "à¦¨à¦¿à¦šà§‡à¦° à¦¬à¦¾à¦Ÿà¦¨à¦—à§à¦²à§‹à¦° à¦®à¦¾à¦§à§à¦¯à¦®à§‡ à¦ªà¦°à¦¿à¦¬à¦°à§à¦¤à¦¨ à¦•à¦°à§à¦¨:"
    )
    keyboard = [
        [KeyboardButton("ðŸ“± SET SERVICE")],
        [KeyboardButton("ðŸ“¶ SET RANGE")],
        [KeyboardButton("â± SET INTERVAL")],
        [KeyboardButton("ðŸ”¢ SET OTP DIGITS")],
        [KeyboardButton("ðŸ”™ BACK TO FAKE OTP")]
    ]
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    context.user_data["fake_otp_settings_mode"] = True

async def admin_fake_otp_set_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ðŸ“± **à¦¨à¦¤à§à¦¨ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸à§‡à¦° à¦¨à¦¾à¦® à¦²à¦¿à¦–à§à¦¨** (à¦¯à§‡à¦®à¦¨: facebook, instagram, whatsapp, telegram):\n\nà¦¬à¦°à§à¦¤à¦®à¦¾à¦¨: " + load_fake_otp_config().get("service", "facebook"), reply_markup=cancel_keyboard())
    context.user_data["fake_otp_setting"] = "service"

async def admin_fake_otp_set_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ðŸ“¶ **à¦¨à¦¤à§à¦¨ à¦°à§‡à¦žà§à¦œ à¦²à¦¿à¦–à§à¦¨** (à¦¯à§‡à¦®à¦¨: 880XXX) à¦…à¦¥à¦¬à¦¾ à¦«à¦¾à¦à¦•à¦¾ à¦°à¦¾à¦–à¦¤à§‡ 'auto' à¦²à¦¿à¦–à§à¦¨ (API à¦¥à§‡à¦•à§‡ à¦°à§‡à¦žà§à¦œ à¦¨à§‡à¦¬à§‡):\n\nà¦¬à¦°à§à¦¤à¦®à¦¾à¦¨: " + (load_fake_otp_config().get("range") or "auto"), reply_markup=cancel_keyboard())
    context.user_data["fake_otp_setting"] = "range"

async def admin_fake_otp_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("â± **à¦¨à¦¤à§à¦¨ à¦‡à¦¨à§à¦Ÿà¦¾à¦°à¦­à§à¦¯à¦¾à¦² (à¦¸à§‡à¦•à§‡à¦¨à§à¦¡) à¦²à¦¿à¦–à§à¦¨** (à¦¶à§à¦§à§ à¦¸à¦‚à¦–à§à¦¯à¦¾, à¦¯à§‡à¦®à¦¨: 10):\n\nà¦¬à¦°à§à¦¤à¦®à¦¾à¦¨: " + str(load_fake_otp_config().get("interval", 10)), reply_markup=cancel_keyboard())
    context.user_data["fake_otp_setting"] = "interval"

async def admin_fake_otp_set_otp_digits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ðŸ”¢ **OTP à¦¡à¦¿à¦œà¦¿à¦Ÿ à¦¸à¦‚à¦–à§à¦¯à¦¾ à¦²à¦¿à¦–à§à¦¨** (à§ª-à§®-à¦à¦° à¦®à¦§à§à¦¯à§‡, à¦¯à§‡à¦®à¦¨: 6):\n\nà¦¬à¦°à§à¦¤à¦®à¦¾à¦¨: " + str(load_fake_otp_config().get("otp_digits", 6)), reply_markup=cancel_keyboard())
    context.user_data["fake_otp_setting"] = "otp_digits"

async def admin_fake_otp_process_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process user input for settings."""
    setting = context.user_data.get("fake_otp_setting")
    if not setting:
        return
    text = update.message.text.strip()
    if text == "âŒ CANCEL":
        context.user_data["fake_otp_setting"] = None
        context.user_data["fake_otp_settings_mode"] = False
        await update.message.reply_text("âŒ à¦¬à¦¾à¦¤à¦¿à¦² à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=fake_otp_keyboard())
        return
    
    config = load_fake_otp_config()
    if setting == "service":
        config["service"] = text.lower()
        save_fake_otp_config(config)
        await update.message.reply_text(f"âœ… à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ `{text}` à¦¸à§‡à¦Ÿ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=fake_otp_keyboard())
    elif setting == "range":
        if text.lower() == "auto":
            config["range"] = ""
        else:
            config["range"] = text
        save_fake_otp_config(config)
        await update.message.reply_text(f"âœ… à¦°à§‡à¦žà§à¦œ `{text}` à¦¸à§‡à¦Ÿ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=fake_otp_keyboard())
    elif setting == "interval":
        try:
            val = int(text)
            if val < 1:
                raise ValueError
            config["interval"] = val
            save_fake_otp_config(config)
            await update.message.reply_text(f"âœ… à¦‡à¦¨à§à¦Ÿà¦¾à¦°à¦­à§à¦¯à¦¾à¦² `{val}` à¦¸à§‡à¦•à§‡à¦¨à§à¦¡ à¦¸à§‡à¦Ÿ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=fake_otp_keyboard())
        except:
            await update.message.reply_text("âŒ à¦­à§à¦¯à¦¾à¦²à¦¿à¦¡ à¦¸à¦‚à¦–à§à¦¯à¦¾ à¦¦à¦¿à¦¨ (à§§ à¦¬à¦¾ à¦¤à¦¾à¦° à¦¬à§‡à¦¶à¦¿)à¥¤", reply_markup=cancel_keyboard())
            return
    elif setting == "otp_digits":
        try:
            val = int(text)
            if val < 4 or val > 8:
                raise ValueError
            config["otp_digits"] = val
            save_fake_otp_config(config)
            await update.message.reply_text(f"âœ… OTP à¦¡à¦¿à¦œà¦¿à¦Ÿ `{val}` à¦¸à§‡à¦Ÿ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", reply_markup=fake_otp_keyboard())
        except:
            await update.message.reply_text("âŒ à§ª-à§®-à¦à¦° à¦®à¦§à§à¦¯à§‡ à¦­à§à¦¯à¦¾à¦²à¦¿à¦¡ à¦¸à¦‚à¦–à§à¦¯à¦¾ à¦¦à¦¿à¦¨à¥¤", reply_markup=cancel_keyboard())
            return
    context.user_data["fake_otp_setting"] = None
    context.user_data["fake_otp_settings_mode"] = False

# ==================== SHOW MAIN MENU HELPER ====================
async def show_main_menu(update, context, uid):
    await context.bot.send_message(chat_id=uid, text="ðŸ”¹ PLEASE USE THE BUTTONS BELOW:", reply_markup=main_keyboard(uid))

# ==================== MESSAGE HANDLER ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id
    text = update.message.text.strip()
    
    # Fake OTP settings processing
    if context.user_data.get("fake_otp_setting") and is_admin(uid):
        await admin_fake_otp_process_setting(update, context)
        return
    
    # Withdraw flow
    if context.user_data.get("withdraw_mode") == "select_method":
        await withdraw_method_selected(update, context)
        return
    if context.user_data.get("withdraw_mode") == "amount":
        await withdraw_amount_received(update, context)
        return
    if context.user_data.get("withdraw_mode") == "number":
        await withdraw_number_received(update, context)
        return
    
    # Admin balance
    if context.user_data.get("add_balance_mode") and is_admin(uid):
        if context.user_data.get("pending_add_user"):
            await process_add_balance_amount(update, context)
        else:
            await process_add_balance_user(update, context)
        return
    if context.user_data.get("remove_balance_mode") and is_admin(uid):
        if context.user_data.get("pending_remove_user"):
            await process_remove_balance_amount(update, context)
        else:
            await process_remove_balance_user(update, context)
        return
    
    # Admin ban/unban
    if context.user_data.get("admin_ban_mode") and is_admin(uid):
        await process_ban_user(update, context)
        return
    if context.user_data.get("admin_unban_mode") and is_admin(uid):
        await process_unban_user(update, context)
        return
    
    # Admin change min withdraw
    if context.user_data.get("admin_min_withdraw_mode") and is_admin(uid):
        await admin_change_min_withdraw_amount(update, context)
        return
    
    # Admin change OTP rate
    if context.user_data.get("admin_otp_rate_mode") and is_admin(uid):
        await admin_change_otp_rate_amount(update, context)
        return

    # Admin set user OTP rate
    if context.user_data.get("admin_set_otp_rate_mode") == "user" and is_admin(uid):
        await admin_set_user_otp_rate_user(update, context)
        return
    if context.user_data.get("admin_set_otp_rate_mode") == "rate" and is_admin(uid):
        await admin_set_user_otp_rate_amount(update, context)
        return

    # Admin view user OTP rate
    if context.user_data.get("admin_view_otp_rate_mode") and is_admin(uid):
        await admin_view_user_otp_rate(update, context)
        return

    # Admin add/remove channel
    if context.user_data.get("add_channel_mode") and is_admin(uid):
        await admin_process_add_channel(update, context)
        return
    if context.user_data.get("remove_channel_mode") and is_admin(uid):
        await admin_process_remove_channel(update, context)
        return
    
    # Fake OTP settings menu navigation (admin)
    if context.user_data.get("fake_otp_settings_mode") and is_admin(uid):
        if text == "ðŸ“± SET SERVICE":
            await admin_fake_otp_set_service(update, context)
            return
        elif text == "ðŸ“¶ SET RANGE":
            await admin_fake_otp_set_range(update, context)
            return
        elif text == "â± SET INTERVAL":
            await admin_fake_otp_set_interval(update, context)
            return
        elif text == "ðŸ”¢ SET OTP DIGITS":
            await admin_fake_otp_set_otp_digits(update, context)
            return
        elif text == "ðŸ”™ BACK TO FAKE OTP":
            context.user_data["fake_otp_settings_mode"] = False
            await admin_fake_otp_menu(update, context)
            return
    
    # CUSTOM RANGE
    if context.user_data.get("mode") == "custom_range":
        context.user_data["mode"] = None
        range_text = text.strip().upper()
        if not re.search(r'\d', range_text):
            await update.message.reply_text(
                "âŒ <b>INVALID RANGE!</b>\n\n"
                "<blockquote>à¦¸à¦ à¦¿à¦• à¦‰à¦¦à¦¾à¦¹à¦°à¦£: <code>234XXX</code> à¦¬à¦¾ <code>26134</code></blockquote>",
                parse_mode="HTML",
                reply_markup=main_keyboard(uid)
            )
            return
        await request_queue.put({
            'type': 'process_numbers',
            'update': update,
            'context': context,
            'range_text': range_text,
            'count': 1,
            'service': 'CUSTOM'
        })
        return
    
    # Ban check
    if not is_admin(uid) and is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    
    # Cancel
    if text == "âŒ CANCEL":
        context.user_data.clear()
        await update.message.reply_text("âŒ CANCELLED", reply_markup=main_keyboard(uid))
        return
    
    # Main menu buttons
    if text == "ðŸ‘¤ PROFILE":
        user_data = get_user(uid)
        stats = get_user_stats(uid)
        user = update.effective_user
        full_name = html.escape(user.full_name)
        username = html.escape(user.username or "No username")
        profile_text = (
            f"ðŸ‘¤ <b>YOUR PROFILE</b>\n\n"
            f"<blockquote>ðŸ·ï¸ NAME: <b>{full_name}</b></blockquote>\n"
            f"<blockquote>ðŸ†” USERNAME: @{username}</blockquote>\n"
            f"<blockquote>ðŸ—ï¸ TELEGRAM ID: <code>{uid}</code></blockquote>\n\n"
            f"<blockquote>ðŸ’µ BALANCE: <b>{format_balance(user_data.get('balance', 0))} BDT</b></blockquote>\n\n"
            f"âœ¨ <b>TODAY</b>\n"
            f"<blockquote>ðŸ“± NUMBERS: {stats['today_numbers']}\nðŸ”‘ OTPS: {stats['today_otps']}</blockquote>\n\n"
            f"ðŸ”¥ <b>LAST 7 DAYS</b>\n"
            f"<blockquote>ðŸ“± NUMBERS: {stats['last7d_numbers']}\nðŸ”‘ OTPS: {stats['last7d_otps']}</blockquote>\n\n"
            f"ðŸŒ <b>ALL TIME</b>\n"
            f"<blockquote>ðŸ“± NUMBERS: {stats['total_numbers']}\nðŸ”‘ OTPS: {stats['total_otps']}</blockquote>"
        )
        await update.message.reply_text(profile_text, parse_mode="HTML")
        return
    
    if text == "ðŸ’° BALANCE":
        balance = get_user(uid)['balance']
        await update.message.reply_text(
            f"ðŸ’° <b>YOUR CURRENT BALANCE</b>\n\n"
            f"<blockquote>ðŸ’µ TOTAL: <b>{format_balance(balance)} BDT</b></blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("ðŸ’¸ WITHDRAW", callback_data="withdraw_start", style="primary")
            ]])
        )
        return
    
    if text == "REFER AND EARN":
        await refer_command(update, context)
        return
    
    if text == "ðŸ” SEARCH OTP":
        context.user_data["mode"] = "search_otp"
        await update.message.reply_text("ðŸ” **ENTER THE NUMBER TO SEARCH OTP:**", parse_mode="Markdown")
        return
    
    if context.user_data.get("mode") == "search_otp":
        context.user_data["mode"] = None
        await request_queue.put({'type': 'search_otp', 'update': update, 'context': context, 'target_num': normalize_number(text)})
        return
    
    if text == "âš¡ GET 2FA":
        await get_2fa_code(update, context)
        return
    
    if text == "ðŸ“ž GET NUMBER":
        await show_app_selection(update, context)
        return
    
    if context.user_data.get("mode") == "get_2fa":
        await process_2fa_key(update, context)
        return
    
    if text == "ðŸ† LEADERBOARD":
        await leaderboard_command(update, context)
        return
    
    if text == "ðŸ’¬ SUPPORT":
        support_text = "ðŸ’¬ SUPPORT ðŸŽ§\n\nCLICK THE BUTTON BELOW TO CONTACT SUPPORT ðŸ“©"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ðŸ’¬ SUPPORT", url=SUPPORT_LINK, style="primary")],
            [InlineKeyboardButton("ðŸ‘¨â€ðŸ’» DEVELOPER BY", url=DEVELOPER_LINK, style="danger")]
        ])
        await update.message.reply_text(support_text, reply_markup=keyboard, parse_mode="Markdown")
        return
    
    # Admin panel
    if text == "âš™ï¸ ADMIN PANEL âš™ï¸" and is_admin(uid):
        context.user_data["admin_mode"] = "main"
        await update.message.reply_text(
            "âŒ¬â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”âŒ¬\n   WELCOME ADMIN PANEL\nâŒ¬â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”âŒ¬",
            reply_markup=admin_main_keyboard()
        )
        return
    
    if text == "ðŸ”™ BACK TO MAIN" and context.user_data.get("admin_mode"):
        context.user_data["admin_mode"] = None
        await update.message.reply_text("ðŸ”™ Back to main menu.", reply_markup=main_keyboard(uid))
        return
    
    if text == "ðŸ”™ BACK TO ADMIN":
        context.user_data["user_management_mode"] = None
        context.user_data["system_config_mode"] = None
        context.user_data["required_channels_mode"] = None
        context.user_data["fake_otp_settings_mode"] = False
        context.user_data["admin_mode"] = "main"
        await update.message.reply_text("ðŸ”™ Back to admin panel.", reply_markup=admin_main_keyboard())
        return
    
    if text == "ðŸ‘¥ USER MANAGEMENT" and context.user_data.get("admin_mode") == "main" and is_admin(uid):
        context.user_data["user_management_mode"] = "main"
        await update.message.reply_text("ðŸ‘¥ User Management:", reply_markup=user_management_keyboard())
        return
    
    if text == "âš™ï¸ SYSTEM CONFIGURATION" and context.user_data.get("admin_mode") == "main" and is_admin(uid):
        context.user_data["system_config_mode"] = "main"
        await update.message.reply_text("âš™ï¸ System Configuration:", reply_markup=system_config_keyboard())
        return

    if text == "ðŸ”— REQUIRED CHANNELS" and context.user_data.get("admin_mode") == "main" and is_admin(uid):
        context.user_data["required_channels_mode"] = "main"
        await update.message.reply_text("ðŸ”— Required Channels / Groups Management:", reply_markup=required_channels_keyboard())
        return

    if text == "âš¡ FAKE OTP" and context.user_data.get("admin_mode") == "main" and is_admin(uid):
        await admin_fake_otp_menu(update, context)
        return

    if text == "â–¶ï¸ START" and context.user_data.get("admin_mode") == "main" and is_admin(uid):
        await admin_fake_otp_start(update, context)
        return

    if text == "â¹ STOP" and context.user_data.get("admin_mode") == "main" and is_admin(uid):
        await admin_fake_otp_stop(update, context)
        return

    if text == "âš™ï¸ SETTINGS" and context.user_data.get("admin_mode") == "main" and is_admin(uid):
        await admin_fake_otp_settings(update, context)
        return

    # Required channels submenu
    if text == "âž• ADD CHANNEL" and context.user_data.get("required_channels_mode") == "main" and is_admin(uid):
        await admin_add_channel_start(update, context)
        return

    if text == "âŒ REMOVE CHANNEL" and context.user_data.get("required_channels_mode") == "main" and is_admin(uid):
        await admin_remove_channel_start(update, context)
        return

    if text == "ðŸ“‹ LIST CHANNELS" and context.user_data.get("required_channels_mode") == "main" and is_admin(uid):
        await admin_list_channels(update, context)
        return
    
    # System config submenu
    if text == "ðŸ“ˆ TODAY ALL STATUS" and context.user_data.get("system_config_mode") == "main" and is_admin(uid):
        t_n, t_o, s_n, s_o, tot_n, tot_o = get_global_system_stats()
        msg = (
            f"ðŸ“Š <b>SYSTEM STATUS</b>\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\n"
            f"âœ¨ <b>TODAY</b>\nðŸ“± NUMBERS: {t_n}\nðŸ”‘ OTPS: {t_o}\n\n"
            f"ðŸ”¥ <b>LAST 7 DAYS</b>\nðŸ“± NUMBERS: {s_n}\nðŸ”‘ OTPS: {s_o}\n\n"
            f"ðŸŒ <b>ALL TIME</b>\nðŸ“± NUMBERS: {tot_n}\nðŸ”‘ OTPS: {tot_o}"
        )
        await update.message.reply_text(msg, parse_mode="HTML")
        return
    
    if text == "ðŸ‘¤ USER STATUS CHECK" and is_admin(uid):
        context.user_data["mode"] = "input_user_id"
        await update.message.reply_text("ðŸ” ENTER TELEGRAM ID:", reply_markup=cancel_keyboard())
        return
    
    if context.user_data.get("mode") == "input_user_id" and is_admin(uid):
        target_uid = text.strip()
        if not target_uid.isdigit():
            await update.message.reply_text("âŒ INVALID ID!")
            return
        context.user_data["mode"] = None
        stats = get_user_stats(target_uid)
        msg = (
            f"ðŸ‘¤ <b>USER STATUS</b> â€” <code>{target_uid}</code>\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\n"
            f"âœ¨ TODAY: ðŸ“± {stats['today_numbers']} | ðŸ”‘ {stats['today_otps']}\n"
            f"ðŸ”¥ 7 DAYS: ðŸ“± {stats['last7d_numbers']} | ðŸ”‘ {stats['last7d_otps']}\n"
            f"ðŸŒ ALL TIME: ðŸ“± {stats['total_numbers']} | ðŸ”‘ {stats['total_otps']}"
        )
        await update.message.reply_text(
            msg, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("ðŸ“‚ CHECK ALL DATA", callback_data=f"full_logs_{target_uid}", style="primary")
            ]])
        )
        return
    
    if text == "ðŸ†” ALL USER ID" and context.user_data.get("user_management_mode") == "main" and is_admin(uid):
        users = get_all_users()
        if users:
            content = "\n".join(f"{i}. {u}" for i, u in enumerate(users, 1))
            f = io.BytesIO(content.encode()); f.name = f"ALL_USERS_{len(users)}.txt"
            await update.message.reply_document(document=f, caption=f"ðŸ‘¥ Total Users: {len(users)}", reply_markup=user_management_keyboard())
        else:
            await update.message.reply_text("No users found.", reply_markup=user_management_keyboard())
        return
    
    if text == "ðŸ’° ALL USER BALANCE" and context.user_data.get("user_management_mode") == "main" and is_admin(uid):
        user_db = load_data(USER_DATA_FILE)
        if user_db:
            total_bal = sum(v.get("balance", 0) for v in user_db.values())
            lines = [f"{i}. {uid_}: {v.get('balance', 0):.2f} BDT" for i, (uid_, v) in enumerate(user_db.items(), 1)]
            content = f"ðŸ’° TOTAL BALANCE: {total_bal:.2f} BDT\n\n" + "\n".join(lines)
            f = io.BytesIO(content.encode()); f.name = f"BALANCES_{total_bal:.0f}.txt"
            await update.message.reply_document(document=f, caption=f"ðŸ’µ Total Balance: {total_bal:.2f} BDT", reply_markup=user_management_keyboard())
        else:
            await update.message.reply_text("No data.", reply_markup=user_management_keyboard())
        return
    
    if text == "ðŸ‘¥ USER LIST (ALL)" and context.user_data.get("user_management_mode") == "main" and is_admin(uid):
        await admin_show_all_users(update, context)
        return
    
    if text == "ðŸ“œ BAN USER LIST" and is_admin(uid):
        await show_banned_users_list(update, context)
        return
    
    if text == "â›” BAN USER" and context.user_data.get("system_config_mode") == "main" and is_admin(uid):
        await admin_ban_user_start(update, context)
        return
    
    if text == "ðŸ”“ UNBAN USER" and context.user_data.get("system_config_mode") == "main" and is_admin(uid):
        await admin_unban_user_start(update, context)
        return
    
    if text == "âž• ADD BALANCE" and context.user_data.get("system_config_mode") == "main" and is_admin(uid):
        await admin_add_balance_start(update, context)
        return
    
    if text == "âž– REMOVE BALANCE" and context.user_data.get("system_config_mode") == "main" and is_admin(uid):
        await admin_remove_balance_start(update, context)
        return
    
    if text == "âš™ï¸ CHANGE MIN WITHDRAW" and context.user_data.get("system_config_mode") == "main" and is_admin(uid):
        await admin_change_min_withdraw_start(update, context)
        return
    
    if text == "ðŸ’³ TOGGLE PAYMENT METHODS" and context.user_data.get("system_config_mode") == "main" and is_admin(uid):
        await admin_toggle_payment_methods(update, context)
        return
    
    if text == "ðŸ’² CHANGE OTP PRICE" and context.user_data.get("system_config_mode") == "main" and is_admin(uid):
        await admin_change_otp_rate_start(update, context)
        return

    if text == "ðŸ”§ SET USER OTP RATE" and context.user_data.get("system_config_mode") == "main" and is_admin(uid):
        await admin_set_user_otp_rate_start(update, context)
        return

    if text == "ðŸ“‹ VIEW USER OTP RATE" and context.user_data.get("system_config_mode") == "main" and is_admin(uid):
        await admin_view_user_otp_rate_start(update, context)
        return
    
    # Broadcast
    if text == "ðŸ“¢ SEND MESSAGE TO ALL USERS" and is_admin(uid):
        context.user_data["broadcast_mode"] = True
        await update.message.reply_text(
            "ðŸ“¢ <b>ADMIN BROADCAST SYSTEM (PRO)</b>\n\n"
            "ðŸ’¬ à¦†à¦ªà¦¨à¦¿ à¦à¦–à¦¨ à¦¯à¦¾ à¦ªà¦¾à¦ à¦¾à¦¬à§‡à¦¨ (Text, Photo, Video, Document, Voice, Audio, Animation, Sticker) â€“ à¦¸à¦•à¦² à¦‡à¦‰à¦œà¦¾à¦°à§‡à¦° à¦•à¦¾à¦›à§‡ à¦ªà§à¦°à¦«à§‡à¦¶à¦¨à¦¾à¦² à¦¹à§‡à¦¡à¦¾à¦°à¦¸à¦¹ à¦šà¦²à§‡ à¦¯à¦¾à¦¬à§‡à¥¤\n\n"
            "âœ¨ à¦°à§‡à¦žà§à¦œ (à¦¯à§‡à¦®à¦¨: 237XXX) à¦¥à¦¾à¦•à¦²à§‡ à¦¤à¦¾ à¦…à¦Ÿà§‹à¦®à§‡à¦Ÿà¦¿à¦• à¦•à§à¦²à¦¿à¦•-à¦Ÿà§-à¦•à¦ªà¦¿ à¦¹à§Ÿà§‡ à¦¯à¦¾à¦¬à§‡à¥¤", 
            parse_mode="HTML", 
            reply_markup=cancel_keyboard()
        )
        return
    
    if context.user_data.get("broadcast_mode") and is_admin(uid):
        context.user_data["broadcast_mode"] = False
        user_db = load_data(USER_DATA_FILE)
        all_uids = list(user_db.keys())
        if not all_uids:
            await update.message.reply_text("âŒ à¦ªà¦¾à¦ à¦¾à¦¨à§‹à¦° à¦œà¦¨à§à¦¯ à¦•à§‹à¦¨à§‹ à¦‡à¦‰à¦œà¦¾à¦° à¦ªà¦¾à¦“à§Ÿà¦¾ à¦¯à¦¾à§Ÿà¦¨à¦¿!")
            return
        success_ids, fail_ids = [], []
        status_msg = await update.message.reply_text(f"ðŸš€ <b>à¦¬à§à¦°à¦¡à¦•à¦¾à¦¸à§à¦Ÿ à¦¶à§à¦°à§ à¦¹à§Ÿà§‡à¦›à§‡...</b>\nðŸŽ¯ à¦Ÿà¦¾à¦°à§à¦—à§‡à¦Ÿ: {len(all_uids)} à¦œà¦¨ à¦‡à¦‰à¦œà¦¾à¦°à¥¤", parse_mode="HTML")
        def format_broadcast_caption(caption_text):
            if not caption_text:
                return "<blockquote>ðŸ“¢ <b>ADMIN NOTICE :</b></blockquote>"
            formatted = re.sub(r'(\d{3,}[xX]{3,})', r'<code>\1</code>', str(caption_text))
            return f"<blockquote>ðŸ“¢ <b>ADMIN NOTICE :</b></blockquote>\n\n{formatted}"
        for user_id_str in all_uids:
            try:
                target_id = int(user_id_str)
                if update.message.text:
                    await context.bot.send_message(
                        chat_id=target_id, 
                        text=format_broadcast_caption(update.message.text), 
                        parse_mode="HTML"
                    )
                elif update.message.photo:
                    caption = format_broadcast_caption(update.message.caption) if update.message.caption else None
                    await context.bot.send_photo(
                        chat_id=target_id,
                        photo=update.message.photo[-1].file_id,
                        caption=caption,
                        parse_mode="HTML" if caption else None
                    )
                elif update.message.video:
                    caption = format_broadcast_caption(update.message.caption) if update.message.caption else None
                    await context.bot.send_video(
                        chat_id=target_id,
                        video=update.message.video.file_id,
                        caption=caption,
                        parse_mode="HTML" if caption else None
                    )
                elif update.message.document:
                    caption = format_broadcast_caption(update.message.caption) if update.message.caption else None
                    await context.bot.send_document(
                        chat_id=target_id,
                        document=update.message.document.file_id,
                        caption=caption,
                        parse_mode="HTML" if caption else None
                    )
                elif update.message.audio:
                    caption = format_broadcast_caption(update.message.caption) if update.message.caption else None
                    await context.bot.send_audio(
                        chat_id=target_id,
                        audio=update.message.audio.file_id,
                        caption=caption,
                        parse_mode="HTML" if caption else None
                    )
                elif update.message.voice:
                    caption = format_broadcast_caption(update.message.caption) if update.message.caption else None
                    await context.bot.send_voice(
                        chat_id=target_id,
                        voice=update.message.voice.file_id,
                        caption=caption,
                        parse_mode="HTML" if caption else None
                    )
                elif update.message.animation:
                    caption = format_broadcast_caption(update.message.caption) if update.message.caption else None
                    await context.bot.send_animation(
                        chat_id=target_id,
                        animation=update.message.animation.file_id,
                        caption=caption,
                        parse_mode="HTML" if caption else None
                    )
                elif update.message.sticker:
                    await context.bot.send_sticker(
                        chat_id=target_id,
                        sticker=update.message.sticker.file_id
                    )
                else:
                    try:
                        await context.bot.copy_message(
                            chat_id=target_id,
                            from_chat_id=update.message.chat_id,
                            message_id=update.message.message_id
                        )
                    except:
                        await context.bot.send_message(
                            chat_id=target_id,
                            text="ðŸ“¢ <b>ADMIN NOTICE :</b>\n\nà¦†à¦ªà¦¨à¦¾à¦° à¦œà¦¨à§à¦¯ à¦à¦•à¦Ÿà¦¿ à¦¨à¦¤à§à¦¨ à¦¬à¦¾à¦°à§à¦¤à¦¾ à¦†à¦›à§‡, à¦•à¦¿à¦¨à§à¦¤à§ à¦à¦Ÿà¦¿ à¦ªà§à¦°à¦¦à¦°à§à¦¶à¦¨ à¦•à¦°à¦¾ à¦¸à¦®à§à¦­à¦¬ à¦¹à§Ÿà¦¨à¦¿à¥¤",
                            parse_mode="HTML"
                        )
                success_ids.append(user_id_str)
            except Exception as e:
                print(f"Broadcast fail to {user_id_str}: {e}")
                fail_ids.append(user_id_str)
            await asyncio.sleep(0.05)
        report_text = (
            f"âœ… <b>ADMIN NOTICE COMPLETE !</b>\n\n"
            f"ðŸ“Š <b>BROADCAST REPORT:</b>\n\n"
            f"<blockquote>âœ… SUCCESSFULLY SENT: {len(success_ids)} USERS !</blockquote>\n"
            f"<blockquote>âŒ FAILED TO SEND: {len(fail_ids)} USERS !</blockquote>"
        )
        await status_msg.delete()
        await context.bot.send_message(chat_id=uid, text=report_text, parse_mode="HTML", reply_markup=main_keyboard(uid))
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        if success_ids:
            s_file = io.BytesIO(("\n".join(success_ids)).encode()); s_file.name = f"SUCCESS_{random_suffix}.txt"
            await context.bot.send_document(chat_id=uid, document=s_file, caption="âœ… Success User List")
        if fail_ids:
            f_file = io.BytesIO(("\n".join(fail_ids)).encode()); f_file.name = f"FAILED_{random_suffix}.txt"
            await context.bot.send_document(chat_id=uid, document=f_file, caption="âŒ Failed User List")
        return    
    await update.message.reply_text("ðŸ”¹ PLEASE USE THE BUTTONS BELOW:", reply_markup=main_keyboard(uid))

# ==================== COMMAND HANDLERS ====================
async def get1number_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    await show_app_selection(update, context)

async def searchotp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    context.user_data["mode"] = "search_otp"
    await update.message.reply_text("ðŸ” **ENTER THE NUMBER TO SEARCH OTP:**", parse_mode="Markdown")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    balance = get_user(uid)['balance']
    await update.message.reply_text(f"ðŸ’° BALANCE: `{format_balance(balance)} BDT`", parse_mode="Markdown", reply_markup=main_keyboard(uid))

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    user_data = get_user(uid)
    stats = get_user_stats(uid)
    user = update.effective_user
    profile_text = (
        f"ðŸ‘¤ **YOUR PROFILE**\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\n"
        f"ðŸ·ï¸ NAME: `{user.full_name}`\n"
        f"ðŸ†” USERNAME: @{user.username or 'No username'}\n"
        f"ðŸ—ï¸ ID: `{uid}`\n\n"
        f"ðŸ’µ BALANCE: {format_balance(user_data.get('balance', 0))} BDT\n\n"
        f"âœ¨ TODAY: ðŸ“± {stats['today_numbers']} | ðŸ”‘ {stats['today_otps']}\n"
        f"ðŸ”¥ 7 DAYS: ðŸ“± {stats['last7d_numbers']} | ðŸ”‘ {stats['last7d_otps']}\n"
        f"ðŸŒ ALL TIME: ðŸ“± {stats['total_numbers']} | ðŸ”‘ {stats['total_otps']}"
    )
    await update.message.reply_text(profile_text, parse_mode="Markdown")

async def refer_command_slash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    await refer_command(update, context)

async def leaderboard_command_slash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("ðŸš« YOU ARE BANNED ðŸš«", reply_markup=main_keyboard(uid))
        return
    await leaderboard_command(update, context)

# ==================== START & CALLBACK ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uid_str = str(uid)
    existing_data = load_data(USER_DATA_FILE)
    is_new_user = uid_str not in existing_data
    if is_new_user:
        get_user(uid)

    channels = load_required_channels()
    if channels:
        user_data = get_user(uid)
        if not user_data.get("verified", False):
            msg = "ðŸ” **à¦­à§‡à¦°à¦¿à¦«à¦¿à¦•à§‡à¦¶à¦¨ à¦ªà§à¦°à¦¯à¦¼à§‹à¦œà¦¨**\n\n"
            msg += "à¦¨à¦¿à¦šà§‡à¦° à¦ªà§à¦°à¦¤à¦¿à¦Ÿà¦¿ à¦šà§à¦¯à¦¾à¦¨à§‡à¦²/à¦—à§à¦°à§à¦ªà§‡ à¦œà§Ÿà§‡à¦¨ à¦¹à§Ÿà§‡ à¦¤à¦¾à¦°à¦ªà¦° **Verify** à¦¬à¦¾à¦Ÿà¦¨ à¦•à§à¦²à¦¿à¦• à¦•à¦°à§à¦¨:\n\n"
            keyboard_buttons = []
            for ch in channels:
                link = ch.get("link", "")
                label = ch.get("label", link)
                style = ch.get("style", "primary")
                keyboard_buttons.append([InlineKeyboardButton(label, url=link, style=style)])
            keyboard_buttons.append([InlineKeyboardButton("âœ… Verify", callback_data="verify_me", style="primary")])
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
            return

    args = context.args
    if args:
        param = args[0]
        if is_range_request(param):
            await request_queue.put({'type': 'auto_number', 'update': update, 'context': context, 'range_text': param})
            return
        elif is_referral_request(param) and is_new_user:
            try:
                referrer_id = int(param)
                if referrer_id != uid and str(referrer_id) in existing_data:
                    current_count = get_referral_count(referrer_id)
                    new_count = current_count + 1
                    update_referral_count(referrer_id, new_count)
                    await update_db_balance(referrer_id, REFERRAL_PRICE)
                    log_global_activity(referrer_id, "REFERRAL_JOINED", {"referred_user": uid})
                    try:
                        await context.bot.send_message(
                            referrer_id,
                            f"ðŸŽ‰ <b>NEW REFERRAL!</b>\n\n<blockquote>ðŸ—ï¸ ID: <code>{uid}</code>\nðŸ’° REWARD: {format_balance(REFERRAL_PRICE)} BDT\nðŸ‘¥ TOTAL REFERS: {new_count}</blockquote>",
                            parse_mode="HTML"
                        )
                    except:
                        pass
            except Exception as e:
                print(f"Referral error: {e}")
    context.user_data.clear()
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="HTML")
    await update.message.reply_text("ðŸ”¹ PLEASE USE THE BUTTONS BELOW:", reply_markup=main_keyboard(uid))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()
    
    if data == "verify_me":
        await verify_user(update, context)
        return
    
    if not is_admin(uid) and is_user_banned(uid):
        await query.edit_message_text("ðŸš« YOU ARE BANNED ðŸš«")
        return
    
    # SERVICE SELECTION
    if data.startswith("svc_"):
        service = data[4:]
        services = await fetch_services_cached()
        # ===== UPDATED: à¦à¦–à¦¨ à§ªà¦Ÿà¦¿ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦«à¦¿à¦²à§à¦Ÿà¦¾à¦° =====
        allowed = ["facebook", "instagram", "whatsapp", "telegram"]
        services = {k: v for k, v in services.items() if k in allowed}
        if service not in services:
            await query.answer("à¦à¦‡ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨à§‡ à¦‰à¦ªà¦²à¦¬à§à¦§ à¦¨à§‡à¦‡à¥¤", show_alert=True)
            return
        ranges = services[service]
        if not ranges:
            await query.answer("à¦à¦‡ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸à§‡à¦° à¦œà¦¨à§à¦¯ à¦•à§‹à¦¨à§‹ à¦°à§‡à¦žà§à¦œ à¦‰à¦ªà¦²à¦¬à§à¦§ à¦¨à§‡à¦‡à¥¤", show_alert=True)
            return
        context.user_data["la_service"] = service
        context.user_data["la_ranges"] = ranges
        keyboard = _build_countries_keyboard(ranges, service)
        await query.message.edit_text(
            f"ðŸ“¡âœ¨ {service.upper()} - AVAILABLE COUNTRIES âœ¨ðŸ“¡\n\n"
            f"<blockquote>ðŸ“± Service: <b>{html.escape(service)}</b></blockquote>\n"
            f"<blockquote>ðŸŒ à¦¹à¦Ÿ à¦¦à§‡à¦¶à¦—à§à¦²à§‹ (ðŸ”¥) à¦†à¦—à§‡ à¦¦à§‡à¦–à¦¾à¦¨à§‹ à¦¹à§Ÿà§‡à¦›à§‡:</blockquote>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return
    
    # HOT RANGE SELECTION
    if data.startswith("hot_range_"):
        parts = data.split("_")
        if len(parts) < 3:
            await query.answer("Invalid range data.", show_alert=True)
            return
        rid = parts[2]
        service = parts[3] if len(parts) > 3 else "CUSTOM"
        range_display = rid + "XXX"
        await fast_allocate_number(query, context, rid, service, range_display)
        return
    
    # CUSTOM RANGE
    if data == "custom_range":
        context.user_data["mode"] = "custom_range"
        await query.message.edit_text(
            "âš™ï¸ <b>CUSTOM RANGE</b>\n\n"
            "<blockquote>ðŸ“¶ à¦†à¦ªà¦¨à¦¾à¦° à¦•à¦¾à¦¸à§à¦Ÿà¦® range à¦Ÿà¦¾à¦‡à¦ª à¦•à¦°à§à¦¨à¥¤\n"
            "à¦‰à¦¦à¦¾à¦¹à¦°à¦£: <code>234XXX</code> à¦¬à¦¾ <code>26134</code></blockquote>\n\n"
            "<blockquote>âŒ¨ï¸ à¦¨à¦¿à¦šà§‡ range à¦²à¦¿à¦–à§‡ Send à¦•à¦°à§à¦¨:</blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("â—€ï¸ BACK", callback_data="back_services", style="danger")
            ]])
        )
        return
    
    # BACK TO SERVICES
    if data == "back_services":
        services = await fetch_services_cached()
        allowed = ["facebook", "instagram", "whatsapp", "telegram"]
        services = {k: v for k, v in services.items() if k in allowed}
        if not services:
            await query.message.edit_text("âŒ à¦•à§‹à¦¨à§‹ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦‰à¦ªà¦²à¦¬à§à¦§ à¦¨à§‡à¦‡à¥¤")
            return
        keyboard = _build_services_keyboard(services)
        await query.message.edit_text(
            "ðŸ“¡âœ¨ ð—¦ð—˜ð—Ÿð—˜ð—–ð—§ ð—¬ð—¢ð—¨ð—¥ ð—¦ð—˜ð—¥ð—©ð—œð—–ð—˜ âœ¨ðŸ“¡\n\n"
            "<blockquote>ðŸ“± à¦¨à¦¿à¦š à¦¥à§‡à¦•à§‡ à¦à¦•à¦Ÿà¦¿ <b>Service</b> à¦¸à¦¿à¦²à§‡à¦•à§à¦Ÿ à¦•à¦°à§à¦¨:</blockquote>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return
    
    # SAME RANGE (fixed)
    if data.startswith("same_range_"):
        parts = data.split("_")
        if len(parts) < 3:
            await query.answer("Invalid same range data.", show_alert=True)
            return
        rid = parts[2]
        service = parts[3] if len(parts) > 3 else "CUSTOM"
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except:
            pass
        try:
            num, country = await get_number_from_api(rid)
        except Exception as e:
            await query.message.reply_text(f"âŒ Server error: {str(e)[:100]}", reply_markup=main_keyboard(uid))
            return
        if not num:
            await query.message.reply_text(
                "âŒ <b>à¦à¦‡ à¦°à§‡à¦žà§à¦œà§‡ à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨à§‡ à¦•à§‹à¦¨à§‹ à¦¨à¦®à§à¦¬à¦° à¦¨à§‡à¦‡!</b>\n\n"
                "<blockquote>âš ï¸ à¦¦à¦¯à¦¼à¦¾ à¦•à¦°à§‡ à¦…à¦¨à§à¦¯ à¦°à§‡à¦žà§à¦œ à¦¨à¦¿à¦°à§à¦¬à¦¾à¦šà¦¨ à¦•à¦°à§à¦¨ à¦¬à¦¾ à¦ªà¦°à§‡ à¦†à¦¬à¦¾à¦° à¦šà§‡à¦·à§à¦Ÿà¦¾ à¦•à¦°à§à¦¨à¥¤</blockquote>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("â—€ï¸ BACK TO SERVICES", callback_data="back_services", style="danger")
                ]])
            )
            return
        clean_num = normalize_number(num)
        active_numbers[clean_num] = {"uid": uid, "range": rid, "timestamp": datetime.now()}
        add_number_taken(uid, 1)
        save_number_range_info(uid, clean_num, rid)
        flag, cname = get_country_info(clean_num)
        text = (
            f"âœ… <b>YOUR NEW NUMBER FROM SAME RANGE</b> âœ…\n\n"
            f"<blockquote>ðŸŒ COUNTRY: <code>{flag} {cname}</code></blockquote>\n"
            f"<blockquote>ðŸ“¶ RANGE: <code>{rid}</code></blockquote>\n"
            f"<blockquote>ðŸ“± SERVICE: <code>{service.upper()}</code></blockquote>\n"
            f"<blockquote>ðŸ“ž NUMBER: <code>{num}</code></blockquote>\n\n"
            f"<b>ðŸ“© SMS STATUS: â³ WAITING...</b>"
        )
        new_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ðŸ”„ SAME RANGE", callback_data=f"same_range_{rid}_{service}", style="success")],
            [InlineKeyboardButton("ðŸ“¢ OTP GROUP", url="https://t.me/Davil_Otp_Group", style="primary")],
            [InlineKeyboardButton("â—€ï¸ BACK", callback_data="back_to_services")]
        ])
        await query.message.reply_text(text, parse_mode="HTML", reply_markup=new_keyboard)
        return
    
    # WITHDRAW
    if data == "withdraw_start":
        balance = get_user(uid)['balance']
        config = load_system_config()
        min_with = config["min_withdraw"]
        if balance < min_with:
            await query.message.reply_text(
                f"<blockquote>ðŸ’µ BALANCE: {format_balance(balance)} BDT\nðŸ“‰ MIN WITHDRAW: {min_with} BDT</blockquote>",
                parse_mode="HTML"
            )
            return
        context.user_data["withdraw_mode"] = "select_method"
        await query.message.reply_text("ðŸ’³ SELECT YOUR PAYMENT METHOD!", reply_markup=withdraw_method_keyboard())
        return
    
    if data == "withdraw_confirm":
        await process_withdraw_confirm(update, context)
        return
    
    if data == "withdraw_cancel":
        await process_withdraw_cancel(update, context)
        return
    
    if data.startswith("admin_approve_"):
        await admin_approve_withdraw(update, context, data.replace("admin_approve_", ""))
        return
    
    if data.startswith("admin_reject_"):
        await admin_reject_withdraw(update, context, data.replace("admin_reject_", ""))
        return
    
    # BACK BUTTONS
    if data == "back_to_main":
        await query.edit_message_text("ðŸ”™ Returning to main menu...")
        await query.message.chat.send_message(
            "ðŸ”¹ PLEASE USE THE BUTTONS BELOW:",
            reply_markup=main_keyboard(uid)
        )
        context.user_data.clear()
        return

    if data == "back_to_services":
        services = await fetch_services_cached()
        allowed = ["facebook", "instagram", "whatsapp", "telegram"]
        services = {k: v for k, v in services.items() if k in allowed}
        if not services:
            await query.edit_message_text("âŒ à¦•à§‹à¦¨à§‹ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦‰à¦ªà¦²à¦¬à§à¦§ à¦¨à§‡à¦‡à¥¤")
            return
        keyboard = _build_services_keyboard(services)
        await query.edit_message_text(
            "ðŸ“¡âœ¨ ð—¦ð—˜ð—Ÿð—˜ð—–ð—§ ð—¬ð—¢ð—¨ð—¥ ð—¦ð—˜ð—¥ð—©ð—œð—–ð—˜ âœ¨ðŸ“¡\n\n"
            "<blockquote>âœ¨ à¦¨à¦¿à¦š à¦¥à§‡à¦•à§‡ à¦†à¦ªà¦¨à¦¾à¦° à¦ªà¦›à¦¨à§à¦¦à§‡à¦° <b>Service</b> à¦¨à¦¿à¦°à§à¦¬à¦¾à¦šà¦¨ à¦•à¦°à§à¦¨:</blockquote>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return
    
    # Handle toggle payment methods callback
    if data.startswith("toggle_method_"):
        await handle_toggle_method_callback(update, context)
        return
    
    if data == "back_to_admin_panel":
        await query.message.delete()
        await query.message.chat.send_message("âš™ï¸ System Configuration:", reply_markup=system_config_keyboard())
        return
    
    # COPY / MISC
    if data.startswith("copy_id_"):
        await query.answer(f"âœ… Copied ID: {data.replace('copy_id_', '')}", show_alert=True)
        return
    
    if data.startswith("copy_text_"):
        await query.answer(f"âœ… Copied: {data.replace('copy_text_', '')}", show_alert=True)
        return
    
    if data.startswith("my_ref_"):
        target_uid = data.replace("my_ref_", "")
        all_logs = load_data(ACTIVITY_LOGS_FILE)
        my_referrals = [log for log in all_logs if str(log.get('uid')) == str(target_uid) and log.get('action') == "REFERRAL_JOINED"]
        content = f"ðŸ‘¥ REFERRAL REPORT â€” {target_uid}\nâ”â”â”â”â”â”â”â”â”â”â”â”\nTOTAL: {len(my_referrals)}\n\n"
        for i, log in enumerate(my_referrals, 1):
            try:
                dt_obj = datetime.fromisoformat(log['timestamp'])
                ref_id = log.get('details', {}).get('referred_user', 'N/A')
                content += f"{i}. ID: {ref_id} | {dt_obj.strftime('%d/%m/%Y %I:%M %p')}\n"
            except:
                continue
        f = io.BytesIO(content.encode())
        f.name = f"REF_{target_uid}.txt"
        await context.bot.send_document(chat_id=uid, document=f, caption="âœ… **REFERRAL DATA**", parse_mode="Markdown")
        return
    
    if data.startswith("full_logs_"):
        target_uid = data.replace("full_logs_", "")
        stats = get_user_stats(target_uid)
        all_logs = load_data(ACTIVITY_LOGS_FILE)
        user_db = load_data(USER_DATA_FILE)
        user_info = user_db.get(str(target_uid), {})
        user_otps = [log for log in all_logs if str(log.get('uid')) == str(target_uid) and log.get('action') == "OTP_RECEIVED"]
        content = (
            f"ðŸ“Š USER DATA REPORT â€” {target_uid}\n"
            f"ðŸ’° BALANCE: {user_info.get('balance', 0):.2f} BDT\n"
            f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
            f"TODAY NUMBERS: {stats['today_numbers']}\n"
            f"TODAY OTPS: {stats['today_otps']}\n"
            f"7D NUMBERS: {stats['last7d_numbers']}\n"
            f"7D OTPS: {stats['last7d_otps']}\n"
            f"TOTAL NUMBERS: {stats['total_numbers']}\n"
            f"TOTAL OTPS: {stats['total_otps']}\n"
            f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\nOTP LOGS:\n"
        )
        for i, log in enumerate(user_otps, 1):
            try:
                dt_obj = datetime.fromisoformat(log['timestamp'])
                d = log.get('details', {})
                content += f"{i}. {dt_obj.strftime('%d/%m/%Y %I:%M %p')}\n   ðŸ“ž {d.get('number', 'N/A')}\n   ðŸ”‘ {d.get('otp', 'N/A')}\n\n"
            except:
                continue
        f = io.BytesIO(content.encode())
        f.name = f"USER_{target_uid}.txt"
        await context.bot.send_document(
            chat_id=uid, document=f,
            caption=f"âœ… <b>DATA FOR USER: <code>{target_uid}</code></b>",
            parse_mode="HTML"
        )
        return

# ==================== MAIN & POST INIT ====================
async def post_init(application):
    for _ in range(20):
        asyncio.create_task(worker())
    asyncio.create_task(monitor_loop(application))
    asyncio.create_task(fake_otp_loop(application))

# ================================================================
# ============== ðŸ”¥ à¦à¦–à¦¾à¦¨à§‡ à¦¶à§à¦§à§ main() à¦«à¦¾à¦‚à¦¶à¦¨à¦Ÿà¦¿ Webhook à¦…à¦¨à§à¦¯à¦¾à§Ÿà§€ à¦ªà¦°à¦¿à¦¬à¦°à§à¦¤à¦¨ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡ ==============
# ================================================================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).post_init(post_init).build()

    # ========== à¦¹à§à¦¯à¦¾à¦¨à§à¦¡à¦²à¦¾à¦°à¦—à§à¦²à§‹ (à¦†à¦—à§‡à¦° à¦®à¦¤à§‹à¦‡) ==========
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get1number", get1number_command))
    app.add_handler(CommandHandler("searchotp", searchotp_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("refer", refer_command_slash))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command_slash))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    # ========== à¦“à¦¯à¦¼à§‡à¦¬à¦¹à§à¦• à¦•à¦¨à¦«à¦¿à¦—à¦¾à¦°à§‡à¦¶à¦¨ ==========
    port = int(os.environ.get("PORT", 8080))
    webhook_url = os.environ.get("WEBHOOK_URL")

    # Render-à¦ RENDER_EXTERNAL_URL à¦¸à§à¦¬à¦¯à¦¼à¦‚à¦•à§à¦°à¦¿à¦¯à¦¼ à¦¸à§‡à¦Ÿ à¦¥à¦¾à¦•à§‡
    if not webhook_url:
        external_url = os.environ.get("RENDER_EXTERNAL_URL")
        if external_url:
            webhook_url = f"{external_url}/webhook"
        else:
            # à¦²à§‹à¦•à¦¾à¦² à¦¬à¦¾ à¦…à¦¨à§à¦¯ à¦•à§‹à¦¨à§‹ à¦ªà¦°à¦¿à¦¬à§‡à¦¶à§‡ à¦ªà§‹à¦²à¦¿à¦‚ à¦¬à§à¦¯à¦¾à¦•à¦†à¦ª
            print("âš ï¸ WEBHOOK_URL à¦¸à§‡à¦Ÿ à¦¨à§‡à¦‡, à¦ªà§‹à¦²à¦¿à¦‚ à¦®à§‹à¦¡à§‡ à¦šà¦²à¦›à§‡...")
            app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
            return

    print(f"ðŸš€ à¦¬à¦Ÿ à¦“à¦¯à¦¼à§‡à¦¬à¦¹à§à¦• à¦®à§‹à¦¡à§‡ à¦šà¦¾à¦²à§ à¦¹à¦šà§à¦›à§‡: {webhook_url}")
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="webhook",
        webhook_url=webhook_url,
    )

if __name__ == "__main__":
    main()
