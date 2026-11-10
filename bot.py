from __future__ import annotations

import html
import json
import logging
import os
import re
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

# ════════════════════════════════════════════════════════════
# 🔧 CONFIGURATION  —  EDIT THESE VALUES
# ════════════════════════════════════════════════════════════
TOKEN        = ""  # Set TOKEN in Render Environment Variables
ADMIN_ID     = ""  # Set ADMIN_ID in Render Environment Variables
BOT_USERNAME = "Test1hostbot"
PORT         = 8080
# ════════════════════════════════════════════════════════════

TOKEN = (os.getenv("TOKEN") or TOKEN).strip()
ADMIN_ID = (os.getenv("ADMIN_ID") or ADMIN_ID).strip()
BOT_USERNAME = (os.getenv("BOT_USERNAME") or BOT_USERNAME).strip().lstrip("@")
PORT = int(os.getenv("PORT", str(PORT)))

ADMIN_IDS: set[int] = set()
for _x in ADMIN_ID.split(","):
    _x = _x.strip()
    if _x.lstrip("-").isdigit():
        ADMIN_IDS.add(int(_x))

LOG = logging.getLogger("streamly")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
TIKWM_ENDPOINT = "https://www.tikwm.com/api/"
SNAPTIK_ENDPOINT = "https://snaptik.app/abc2.php"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MAX_MEDIA_BYTES = 48 * 1024 * 1024
MAX_VIDEO_SECONDS = 30 * 60

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "streamly_data.json")

LANG: dict[int, str] = {}
STATE: dict[int, dict[str, Any]] = {}
USERS: dict[int, dict[str, Any]] = {}
BANNED: dict[int, dict[str, Any]] = {}
ADMIN_FLOW: dict[int, dict[str, Any]] = {}
ADMIN_VIEW: dict[int, dict[str, Any]] = {}
OWNER_CONTACT_URL = ""
TOTAL_DOWNLOADS = 0
START_TIME = time.time()
STATE_LOCK = threading.RLock()
EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="streamly")
SHUTDOWN = threading.Event()
BOT_PHOTO_CACHE: str | None = None


def log(msg, *args): LOG.info(msg, *args)
def escape(v): return html.escape(str(v), quote=False)


def save_data():
    data = {
        "owner_link": OWNER_CONTACT_URL,
        "users": {str(k): v for k, v in USERS.items()},
        "banned": {str(k): v for k, v in BANNED.items()},
        "downloads": TOTAL_DOWNLOADS,
    }
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        log("Save failed: %s", e)


def load_data():
    global OWNER_CONTACT_URL, TOTAL_DOWNLOADS
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return
    except Exception as e:
        log("Load failed: %s", e)
        return
    OWNER_CONTACT_URL = data.get("owner_link", "") or ""
    TOTAL_DOWNLOADS = int(data.get("downloads", 0))
    for k, v in data.get("users", {}).items():
        try: USERS[int(k)] = v
        except ValueError: pass
    for k, v in data.get("banned", {}).items():
        try: BANNED[int(k)] = v
        except ValueError: pass


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------
TR: dict[str, dict[str, str]] = {
    "en": {
        "welcome_title": "✨ <b>WELCOME TO STREAMLY</b> ✨",
        "name": "👤 <b>Name:</b>", "user_id": "🆔 <b>User ID:</b>",
        "bot_username": "🤖 <b>Bot:</b>",
        "features_title": "🌟 <b>FEATURES</b>",
        "features": ("├ ⚡ Instant downloads\n├ 🎬 HD video • no watermark\n"
                     "├ 🎵 MP3 audio extraction\n├ 🌐 Bangla & English\n└ 🆓 100% free forever"),
        "start_hint": "👇 <i>Use the buttons below to begin</i>",

        # main reply buttons
        "btn_download": "⬇️ DOWNLOAD TIKTOK VIDEO",
        "btn_how":      "📖 HOW TO USE",
        "btn_language": "🌐 LANGUAGE",
        "btn_owner":    "👑 CONTACT OWNER",

        # sub reply buttons
        "btn_video":   "🎬 VIDEO",
        "btn_music":   "🎵 MUSIC",
        "btn_back":    "🔙 BACK",
        "btn_english": "🇬🇧 ENGLISH",
        "btn_bangla":  "🇧🇩 বাংলা",

        # admin reply buttons
        "btn_users":     "👥 USER MANAGEMENT",
        "btn_stats":     "📊 STATS",
        "btn_broadcast": "📢 BROADCAST",
        "btn_ownerlink": "🔗 OWNER LINK",
        "btn_ban":       "🚫 BAN USER",
        "btn_unban":     "✅ UNBAN USER",
        "btn_prev":      "⬅️ PREV",
        "btn_next":      "NEXT ➡️",

        "send_link": (
            "🔗 <b>SEND ME A TIKTOK LINK</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Paste any public TikTok video URL below.\n\n"
            "<i>Example:</i>\n<code>https://www.tiktok.com/@user/video/123456</code>"
        ),
        "invalid_link": "❌ <b>INVALID TIKTOK LINK</b>\n\nPlease send a valid public TikTok video URL.",
        "choose_format": ("🎯 <b>WHAT DO YOU WANT?</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                          "🎬 <b>VIDEO</b> — full video, no watermark\n"
                          "🎵 <b>MUSIC</b> — audio only"),
        "processing": "⚡ <b>PROCESSING...</b>\n\n<i>Fetching your media, please wait...</i>",
        "download_failed": "❌ <b>DOWNLOAD FAILED</b>\n\nThe video may be private or unavailable.\nTry another link.",
        "too_big": "❌ <b>FILE TOO LARGE</b>\n\nExceeds Telegram's 50 MB bot limit.",
        "success": "✅ <b>DONE! YOUR FILE IS READY</b>\n\n<i>Choose another action below.</i>",
        "language_changed": "✅ <b>LANGUAGE SET TO ENGLISH</b>\n\n<i>Menu updated below.</i>",
        "choose_language": "🌐 <b>CHOOSE YOUR LANGUAGE</b>\n\n<i>Tap a button below.</i>",
        "menu": "🏠 <b>MAIN MENU</b>\n\n<i>Use the buttons below to continue.</i>",

        "how_to_use": (
            "📖 <b>HOW TO USE STREAMLY</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ Tap <b>DOWNLOAD TIKTOK VIDEO</b>\n"
            "2️⃣ Paste any public TikTok video URL\n"
            "3️⃣ Choose <b>VIDEO</b> or <b>MUSIC</b>\n"
            "4️⃣ File arrives in a few seconds — done!\n\n"
            "💡 <b>TIPS</b>\n"
            "├ ✅ Only public videos work\n"
            "├ ✅ No watermarks, no hashtags\n"
            "├ ✅ MP4 & MP3 supported\n"
            "├ ❌ Private / age-restricted videos are skipped\n"
            "└ 🌐 Change language anytime"
        ),

        "owner_info": (
            "👑 <b>CONTACT OWNER</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Reach out for support, feature requests, or any questions.\n\n"
            "👇 Tap the button below to contact the owner."
        ),
        "owner_no_link": "⚠️ <i>Owner contact has not been configured yet.</i>",

        "admin_panel": ("🛠 <b>ADMIN PANEL</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                        "Manage users, view stats, broadcast, and configure."),
        "admin_only": "⛔ <i>Admin only.</i>",
        "users_header": "👥 <b>USER MANAGEMENT</b>",
        "users_empty": "No users yet.",
        "user_details": (
            "👤 <b>USER DETAILS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "📛 <b>Name:</b> {name}\n🔗 <b>Username:</b> {username}\n"
            "🆔 <b>User ID:</b> <code>{uid}</code>\n📅 <b>Joined:</b> {joined}\n"
            "🚦 <b>Status:</b> {status}\n📥 <b>Downloads:</b> {downloads}"
        ),
        "ask_ban_reason": ("📝 <b>BAN USER</b>\n\n"
                           "Send the <b>reason</b> for banning <b>{name}</b> (<code>{uid}</code>).\n\n"
                           "<i>Tap BACK to cancel.</i>"),
        "ask_ban_url": ("🔗 <b>BAN USER</b>\n\n"
                        "Now send the <b>admin contact URL</b> the user can reach\n"
                        "(e.g. <code>https://t.me/youradmin</code>).\n\n"
                        "<i>Tap BACK to cancel.</i>"),
        "ban_done": "✅ <b>USER BANNED</b>\n\n<b>{name}</b> (<code>{uid}</code>) has been banned and notified.",
        "unban_done": "✅ <b>USER UNBANNED</b>\n\n<code>{uid}</code> is active again.",
        "ban_notify": (
            "🚫 <b>YOU HAVE BEEN BANNED</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "📝 <b>Reason:</b>\n{reason}\n\n"
            "<i>If you believe this is a mistake, contact the admin below.</i>\n\n📞 {url}"
        ),
        "stats": (
            "📊 <b>BOT STATISTICS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "🤖 <b>Bot:</b> @{bot}\n👥 <b>Total users:</b> {total}\n"
            "✅ <b>Active users:</b> {active}\n🚫 <b>Banned users:</b> {banned}\n"
            "📥 <b>Total downloads:</b> {downloads}\n⏱ <b>Uptime:</b> {uptime}\n"
            "🟢 <b>Status:</b> Online"
        ),
        "broadcast_ask": ("📢 <b>BROADCAST</b>\n\n"
                          "Send the message you want to broadcast to all active users.\n\n"
                          "<i>Tap BACK to cancel.</i>"),
        "broadcast_done": "✅ <b>BROADCAST SENT</b>\n\nDelivered: {ok}\nFailed: {fail}",
        "ownerlink_ask": ("🔗 <b>OWNER CONTACT LINK</b>\n\n"
                          "Current: {current}\n\n"
                          "Send the new contact URL (e.g. <code>https://t.me/youradmin</code>).\n\n"
                          "<i>Tap BACK to cancel.</i>"),
        "ownerlink_saved": "✅ <b>OWNER LINK SAVED</b>\n\nNew: {url}",
        "cancel_flow": "❌ <i>Cancelled.</i>",
        "admin_extra": "\n\n🛠 <i>You are admin — use /admin to open the admin panel.</i>",
    },
    "bn": {
        "welcome_title": "✨ <b>STREAMLY-তে স্বাগতম</b> ✨",
        "name": "👤 <b>নাম:</b>", "user_id": "🆔 <b>ইউজার আইডি:</b>",
        "bot_username": "🤖 <b>বট:</b>",
        "features_title": "🌟 <b>ফিচারসমূহ</b>",
        "features": ("├ ⚡ দ্রুত ডাউনলোড\n├ 🎬 HD ভিডিও • ওয়াটারমার্ক ছাড়া\n"
                     "├ 🎵 MP3 অডিও\n├ 🌐 বাংলা ও ইংরেজি\n└ 🆓 চিরকাল ফ্রি"),
        "start_hint": "👇 <i>শুরু করতে নিচের বাটনগুলো ব্যবহার করুন</i>",

        "btn_download": "⬇️ টিকটক ভিডিও ডাউনলোড",
        "btn_how":      "📖 কীভাবে ব্যবহার করবেন",
        "btn_language": "🌐 ভাষা",
        "btn_owner":    "👑 যোগাযোগ করুন",

        "btn_video":   "🎬 ভিডিও",
        "btn_music":   "🎵 মিউজিক",
        "btn_back":    "🔙 পিছনে",
        "btn_english": "🇬🇧 ENGLISH",
        "btn_bangla":  "🇧🇩 বাংলা",

        "btn_users":     "👥 ইউজার ম্যানেজমেন্ট",
        "btn_stats":     "📊 স্ট্যাটস",
        "btn_broadcast": "📢 ব্রডকাস্ট",
        "btn_ownerlink": "🔗 মালিকের লিংক",
        "btn_ban":       "🚫 ব্যান করুন",
        "btn_unban":     "✅ আনব্যান করুন",
        "btn_prev":      "⬅️ আগে",
        "btn_next":      "পরে ➡️",

        "send_link": (
            "🔗 <b>টিকটক লিংক পাঠান</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "যেকোনো পাবলিক টিকটক ভিডিওর লিংক নিচে পেস্ট করুন।\n\n"
            "<i>উদাহরণ:</i>\n<code>https://www.tiktok.com/@user/video/123456</code>"
        ),
        "invalid_link": "❌ <b>অবৈধ টিকটক লিংক</b>\n\nঅনুগ্রহ করে একটি বৈধ পাবলিক টিকটক URL পাঠান।",
        "choose_format": ("🎯 <b>আপনি কী চান?</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                          "🎬 <b>ভিডিও</b> — ওয়াটারমার্ক ছাড়া সম্পূর্ণ ভিডিও\n"
                          "🎵 <b>মিউজিক</b> — শুধু অডিও"),
        "processing": "⚡ <b>প্রসেস হচ্ছে...</b>\n\n<i>মিডিয়া আনা হচ্ছে, অপেক্ষা করুন...</i>",
        "download_failed": "❌ <b>ডাউনলোড ব্যর্থ</b>\n\nভিডিওটি প্রাইভেট বা আনএভেইলেবল হতে পারে।\nঅন্য লিংক দিন।",
        "too_big": "❌ <b>ফাইল বড় হয়ে গেছে</b>\n\nTelegram-এর 50 MB লিমিট ছাড়িয়ে গেছে।",
        "success": "✅ <b>সম্পন্ন! আপনার ফাইল তৈরি</b>\n\n<i>নিচ থেকে আরেকটি অপশন বেছে নিন।</i>",
        "language_changed": "✅ <b>ভাষা বাংলায় সেট হয়েছে</b>\n\n<i>মেনু নিচে আপডেট হয়েছে।</i>",
        "choose_language": "🌐 <b>আপনার ভাষা বেছে নিন</b>\n\n<i>নিচের বাটনে চাপ দিন।</i>",
        "menu": "🏠 <b>মেইন মেনু</b>\n\n<i>চালিয়ে যেতে নিচের বাটনগুলো ব্যবহার করুন।</i>",

        "how_to_use": (
            "📖 <b>STREAMLY কীভাবে ব্যবহার করবেন</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ <b>টিকটক ভিডিও ডাউনলোড</b> চাপুন\n"
            "2️⃣ যেকোনো পাবলিক টিকটক ভিডিওর লিংক পেস্ট করুন\n"
            "3️⃣ <b>ভিডিও</b> বা <b>মিউজিক</b> বেছে নিন\n"
            "4️⃣ কয়েক সেকেন্ডেই ফাইল চলে আসবে!\n\n"
            "💡 <b>টিপস</b>\n"
            "├ ✅ শুধু পাবলিক ভিডিও কাজ করে\n"
            "├ ✅ ওয়াটারমার্ক বা হ্যাশট্যাগ নেই\n"
            "├ ✅ MP4 ও MP3 দুটোই সাপোর্টেড\n"
            "├ ❌ প্রাইভেট / বয়স-নিষিদ্ধ ভিডিও বাদ যাবে\n"
            "└ 🌐 যেকোনো সময় ভাষা বদলাতে পারবেন"
        ),

        "owner_info": (
            "👑 <b>মালিকের সাথে যোগাযোগ</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "সাপোর্ট, ফিচার রিকোয়েস্ট বা যেকোনো প্রশ্নে যোগাযোগ করুন।\n\n"
            "👇 মালিকের সাথে যোগাযোগ করতে নিচের বাটনে চাপ দিন।"
        ),
        "owner_no_link": "⚠️ <i>মালিকের কন্টাক্ট এখনো সেট করা হয়নি।</i>",

        "admin_panel": ("🛠 <b>অ্যাডমিন প্যানেল</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                        "ইউজার ম্যানেজ, স্ট্যাটস, ব্রডকাস্ট এবং কনফিগার।"),
        "admin_only": "⛔ <i>শুধুমাত্র অ্যাডমিন।</i>",
        "users_header": "👥 <b>ইউজার ম্যানেজমেন্ট</b>",
        "users_empty": "এখনো কোনো ইউজার নেই।",
        "user_details": (
            "👤 <b>ইউজার ডিটেইলস</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "📛 <b>নাম:</b> {name}\n🔗 <b>ইউজারনেম:</b> {username}\n"
            "🆔 <b>ইউজার আইডি:</b> <code>{uid}</code>\n📅 <b>জয়েন:</b> {joined}\n"
            "🚦 <b>স্ট্যাটাস:</b> {status}\n📥 <b>ডাউনলোড:</b> {downloads}"
        ),
        "ask_ban_reason": ("📝 <b>ইউজার ব্যান</b>\n\n"
                           "<b>{name}</b> (<code>{uid}</code>) কে ব্যান করার <b>কারণ</b> লিখে পাঠান।\n\n"
                           "<i>বাতিল করতে BACK চাপুন।</i>"),
        "ask_ban_url": ("🔗 <b>ইউজার ব্যান</b>\n\n"
                        "এখন <b>অ্যাডমিন কন্টাক্ট URL</b> পাঠান\n"
                        "(যেমন <code>https://t.me/youradmin</code>)।\n\n"
                        "<i>বাতিল করতে BACK চাপুন।</i>"),
        "ban_done": "✅ <b>ইউজার ব্যান হয়েছে</b>\n\n<b>{name}</b> (<code>{uid}</code>) ব্যান + নোটিফাই সম্পন্ন।",
        "unban_done": "✅ <b>ইউজার আনব্যান হয়েছে</b>\n\n<code>{uid}</code> আবার সক্রিয়।",
        "ban_notify": (
            "🚫 <b>আপনাকে ব্যান করা হয়েছে</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "📝 <b>কারণ:</b>\n{reason}\n\n"
            "<i>ভুল মনে হলে নিচের অ্যাডমিনের সাথে যোগাযোগ করুন।</i>\n\n📞 {url}"
        ),
        "stats": (
            "📊 <b>বট স্ট্যাটিসটিক্স</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "🤖 <b>বট:</b> @{bot}\n👥 <b>মোট ইউজার:</b> {total}\n"
            "✅ <b>সক্রিয়:</b> {active}\n🚫 <b>ব্যান:</b> {banned}\n"
            "📥 <b>ডাউনলোড:</b> {downloads}\n⏱ <b>আপটাইম:</b> {uptime}\n"
            "🟢 <b>স্ট্যাটাস:</b> অনলাইন"
        ),
        "broadcast_ask": ("📢 <b>ব্রডকাস্ট</b>\n\n"
                          "সব সক্রিয় ইউজারকে যে মেসেজ পাঠাতে চান সেটি লিখে পাঠান।\n\n"
                          "<i>বাতিল করতে BACK চাপুন।</i>"),
        "broadcast_done": "✅ <b>ব্রডকাস্ট সম্পন্ন</b>\n\nসফল: {ok}\nব্যর্থ: {fail}",
        "ownerlink_ask": ("🔗 <b>মালিকের কন্টাক্ট লিংক</b>\n\n"
                          "বর্তমান: {current}\n\n"
                          "নতুন URL পাঠান (যেমন <code>https://t.me/youradmin</code>)।\n\n"
                          "<i>বাতিল করতে BACK চাপুন।</i>"),
        "ownerlink_saved": "✅ <b>মালিকের লিংক সেভ হয়েছে</b>\n\nনতুন: {url}",
        "cancel_flow": "❌ <i>বাতিল হয়েছে।</i>",
        "admin_extra": "\n\n🛠 <i>আপনি অ্যাডমিন — /admin দিয়ে অ্যাডমিন প্যানেল খুলুন।</i>",
    },
}


def get_lang(chat_id): return LANG.get(chat_id, "en")
def tr(chat_id, key): return TR[get_lang(chat_id)][key]


def match_reply_button(text: str) -> str | None:
    """Return action key for the reply button text, across all languages."""
    mapping = {
        "btn_download": "download", "btn_how": "how",
        "btn_language": "language", "btn_owner": "owner",
        "btn_video": "video", "btn_music": "music", "btn_back": "back",
        "btn_english": "en", "btn_bangla": "bn",
        "btn_users": "admin_users", "btn_stats": "admin_stats",
        "btn_broadcast": "admin_broadcast", "btn_ownerlink": "admin_ownerlink",
        "btn_ban": "admin_ban", "btn_unban": "admin_unban",
        "btn_prev": "admin_prev", "btn_next": "admin_next",
    }
    for lang in TR:
        for key, action in mapping.items():
            if text == TR[lang][key]:
                return action
    return None


# ---------------------------------------------------------------------------
# HTTP / Telegram helpers
# ---------------------------------------------------------------------------
def http_request(url, *, method="GET", payload=None, headers=None, timeout=35, max_bytes=3*1024*1024):
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers: hdrs.update(headers)
    request = Request(url, data=payload, headers=hdrs, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            chunks, total = [], 0
            while total < max_bytes:
                chunk = response.read(min(64 * 1024, max_bytes - total))
                if not chunk: break
                chunks.append(chunk); total += len(chunk)
            return response.status, dict(response.headers.items()), b"".join(chunks)
    except HTTPError as error:
        body = error.read(1024)
        raise RuntimeError(f"HTTP {error.code}: {body.decode(errors='replace')[:180]}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"Unreachable: {error}") from error


def json_request(url, *, method="GET", data=None, headers=None, timeout=35):
    body = json.dumps(data).encode() if data is not None else None
    hdrs = {"Content-Type": "application/json"} if data is not None else {}
    if headers: hdrs.update(headers)
    _, _, raw = http_request(url, method=method, payload=body, headers=hdrs, timeout=timeout)
    try: return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error: raise RuntimeError("Invalid JSON") from error


def telegram_call(method, data=None):
    if not TOKEN: raise RuntimeError("TOKEN missing")
    payload = (data or {}).copy()
    status, _, raw = http_request(
        f"{TELEGRAM_API}/{method}", method="POST",
        payload=urlencode(payload).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=45, max_bytes=4*1024*1024)
    if status >= 400: raise RuntimeError(f"Telegram HTTP {status}")
    try: result = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error: raise RuntimeError("Telegram invalid JSON") from error
    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram request failed"))
    return result.get("result")


def send_message(chat_id, text, **extra):
    return telegram_call("sendMessage",
        {"chat_id": str(chat_id), "text": text, "parse_mode": "HTML", **extra})


def send_chat_action(chat_id, action="typing"):
    try: telegram_call("sendChatAction", {"chat_id": str(chat_id), "action": action})
    except Exception: pass


# ---------------------------------------------------------------------------
# Reply keyboards
# ---------------------------------------------------------------------------
def _button_style(button_text: str) -> str:
    """Choose a native Telegram Bot API 9.4 color for each reply button."""
    action = match_reply_button(button_text)
    styles = {
        "download": "success",
        "how": "primary",
        "language": "danger",
        "owner": "success",
        "video": "success",
        "music": "primary",
        "back": "danger",
        "en": "primary",
        "bn": "success",
        "admin_users": "primary",
        "admin_stats": "danger",
        "admin_broadcast": "success",
        "admin_ownerlink": "primary",
        "admin_ban": "danger",
        "admin_unban": "success",
        "admin_prev": "primary",
        "admin_next": "primary",
    }
    return styles.get(action, "primary")


def _reply_kb(rows, persistent=True):
    keyboard = [[{"text": t, "style": _button_style(t)} for t in row] for row in rows]
    return json.dumps({
        "keyboard": keyboard,
        "resize_keyboard": True,
        "is_persistent": persistent,
    }, ensure_ascii=False)


def owner_inline_kb(chat_id):
    """A URL button must be inline; keep the existing reply keyboard unchanged."""
    return json.dumps({
        "inline_keyboard": [[{
            "text": tr(chat_id, "btn_owner"),
            "url": OWNER_CONTACT_URL,
            "style": "success",
        }]]
    }, ensure_ascii=False)


def main_reply_kb(chat_id):
    return _reply_kb([
        [tr(chat_id, "btn_download")],
        [tr(chat_id, "btn_how"), tr(chat_id, "btn_language")],
        [tr(chat_id, "btn_owner")],
    ])


def back_only_reply_kb(chat_id):
    return _reply_kb([[tr(chat_id, "btn_back")]])


def format_reply_kb(chat_id):
    return _reply_kb([
        [tr(chat_id, "btn_video"), tr(chat_id, "btn_music")],
        [tr(chat_id, "btn_back")],
    ])


def language_reply_kb(chat_id):
    return _reply_kb([
        [tr(chat_id, "btn_english"), tr(chat_id, "btn_bangla")],
        [tr(chat_id, "btn_back")],
    ])


def admin_reply_kb(chat_id):
    return _reply_kb([
        [tr(chat_id, "btn_users"), tr(chat_id, "btn_stats")],
        [tr(chat_id, "btn_broadcast"), tr(chat_id, "btn_ownerlink")],
        [tr(chat_id, "btn_back")],
    ])


def user_list_reply_kb(chat_id, count: int, page: int, pages: int):
    """Build a numbered reply keyboard for user management page."""
    rows = []
    # up to 5 numbered buttons per row
    nums = [str(i + 1) for i in range(count)]
    if nums:
        rows.append(nums)
    # pagination row
    nav = []
    if page > 0: nav.append(tr(chat_id, "btn_prev"))
    if page < pages - 1: nav.append(tr(chat_id, "btn_next"))
    if nav: rows.append(nav)
    rows.append([tr(chat_id, "btn_back")])
    return _reply_kb(rows)


def user_detail_reply_kb(chat_id, uid: int):
    if uid in BANNED:
        action = tr(chat_id, "btn_unban")
    else:
        action = tr(chat_id, "btn_ban")
    return _reply_kb([[action], [tr(chat_id, "btn_back")]])


# ---------------------------------------------------------------------------
# Bot photo
# ---------------------------------------------------------------------------
def get_bot_photo():
    global BOT_PHOTO_CACHE
    if BOT_PHOTO_CACHE: return BOT_PHOTO_CACHE
    try:
        me = telegram_call("getMe")
        bot_id = me.get("id")
        if not bot_id: return None
        photos = telegram_call("getUserProfilePhotos", {"user_id": str(bot_id), "limit": "1"})
        if photos and photos.get("total_count", 0) > 0:
            BOT_PHOTO_CACHE = photos["photos"][0][-1]["file_id"]
    except Exception as error:
        log("Bot photo fetch failed: %s", error)
    return BOT_PHOTO_CACHE


# ---------------------------------------------------------------------------
# TikTok resolver
# ---------------------------------------------------------------------------
def normalize_url(value):
    candidate = value.strip()
    if not re.match(r"^https?://", candidate, flags=re.IGNORECASE):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname: return None
    if len(candidate) > 2048: return None
    return candidate


TIKTOK_DOMAINS = ("tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com")


def is_tiktok_url(url):
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return any(host == d or host.endswith(f".{d}") for d in TIKTOK_DOMAINS)


def _remote_url(v):
    return v if isinstance(v, str) and v.startswith(("http://", "https://")) else None


def _media_links(value):
    videos, audios = [], []
    if isinstance(value, dict):
        for key, nested in value.items():
            hint = key.lower()
            url = _remote_url(nested)
            if url:
                if any(w in hint for w in ("music", "audio", "mp3", "sound")):
                    audios.append(url)
                elif any(w in hint for w in ("play", "video", "mp4", "download", "hd", "url")) \
                        and not any(w in hint for w in ("cover", "avatar", "image", "thumb")):
                    videos.append(url)
            v2, a2 = _media_links(nested); videos.extend(v2); audios.extend(a2)
    elif isinstance(value, list):
        for nested in value:
            v2, a2 = _media_links(nested); videos.extend(v2); audios.extend(a2)
    return list(dict.fromkeys(videos)), list(dict.fromkeys(audios))


def _resolve_tikwm(source_url):
    endpoint = f"{TIKWM_ENDPOINT}?{urlencode({'url': source_url, 'hd': '1'})}"
    response = json_request(endpoint, timeout=45)
    if not isinstance(response, dict) or response.get("code") not in {0, "0", None}:
        msg = response.get("msg") if isinstance(response, dict) else ""
        raise RuntimeError(str(msg or "TikWM failed"))
    data = response.get("data")
    if not isinstance(data, dict): raise RuntimeError("TikWM no data")
    duration = int(data.get("duration") or 0)
    if duration > MAX_VIDEO_SECONDS:
        raise RuntimeError(f"Video is {duration // 60} min. Limit is {MAX_VIDEO_SECONDS // 60} min.")
    video_urls, audio_urls = _media_links(data)
    preferred_video = [_remote_url(data.get(k)) for k in ("hdplay", "play", "wmplay") if _remote_url(data.get(k))]
    preferred_audio = [_remote_url(data.get(k)) for k in ("music", "music_url", "mp3", "audio") if _remote_url(data.get(k))]
    videos = list(dict.fromkeys(preferred_video + video_urls))
    audios = list(dict.fromkeys(preferred_audio + audio_urls))
    if not videos: raise RuntimeError("No video URL")
    size_hint = 0
    for key in ("hd_size", "size", "wm_size"):
        try: size_hint = max(size_hint, int(data.get(key) or 0))
        except (TypeError, ValueError): pass
    return {"title": str(data.get("title") or "TikTok media"),
            "video_url": videos[0], "audio_url": audios[0] if audios else "", "size": size_hint}


def _resolve_snaptik(source_url):
    body = urlencode({"url": source_url}).encode()
    _, _, raw = http_request(SNAPTIK_ENDPOINT, method="POST", payload=body,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "Referer": "https://snaptik.app/"},
        timeout=45, max_bytes=4 * 1024 * 1024)
    try: response = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error: raise RuntimeError("SnapTik invalid JSON") from error
    if isinstance(response, dict) and response.get("success") is False:
        raise RuntimeError("SnapTik failed")
    videos, audios = _media_links(response)
    if not videos: raise RuntimeError("No video URL")
    title = "TikTok media"
    if isinstance(response, dict):
        title = str(response.get("title") or (response.get("data") or {}).get("title") or title)
    return {"title": title, "video_url": videos[0], "audio_url": audios[0] if audios else "", "size": 0}


def resolve_tiktok(source_url):
    last = None
    for resolver in (_resolve_tikwm, _resolve_snaptik):
        try: return resolver(source_url)
        except Exception as error: last = error
    raise RuntimeError(f"Resolve failed: {last}")


# ---------------------------------------------------------------------------
# Welcome
# ---------------------------------------------------------------------------
def welcome_text(chat_id, first_name, user_id):
    bot_line = f"{tr(chat_id, 'bot_username')} @{escape(BOT_USERNAME)}" if BOT_USERNAME else ""
    lines = [
        tr(chat_id, "welcome_title"), "",
        f"{tr(chat_id, 'name')} {escape(first_name or '—')}",
        f"{tr(chat_id, 'user_id')} <code>{user_id}</code>",
    ]
    if bot_line: lines.append(bot_line)
    lines += ["", "━━━━━━━━━━━━━━━━━━", "", tr(chat_id, "features_title"),
              tr(chat_id, "features"), "", "━━━━━━━━━━━━━━━━━━", "", tr(chat_id, "start_hint")]
    return "\n".join(lines)


def send_welcome(chat_id, first_name, user_id):
    caption = welcome_text(chat_id, first_name, user_id)
    kb = main_reply_kb(chat_id)
    photo = get_bot_photo()
    if photo:
        try:
            telegram_call("sendPhoto", {"chat_id": str(chat_id), "photo": photo,
                                        "caption": caption, "parse_mode": "HTML",
                                        "reply_markup": kb})
            return
        except Exception as error:
            log("sendPhoto failed: %s — falling back", error)
    send_message(chat_id, caption, reply_markup=kb)


# ---------------------------------------------------------------------------
# FAST download (no animation delay)
# ---------------------------------------------------------------------------
def _run_download(chat_id, url, kind):
    global TOTAL_DOWNLOADS
    status = None
    try:
        send_chat_action(chat_id, "upload_video" if kind == "video" else "upload_audio")
        status = send_message(chat_id, tr(chat_id, "processing"))

        info = resolve_tiktok(url)
        if kind == "music":
            media_url = info.get("audio_url")
            if not media_url: raise RuntimeError("No audio available")
            send_chat_action(chat_id, "upload_audio")
            telegram_call("sendAudio", {"chat_id": str(chat_id), "audio": media_url})
        else:
            media_url = info.get("video_url")
            if not media_url: raise RuntimeError("No video available")
            if info.get("size", 0) > MAX_MEDIA_BYTES:
                try:
                    telegram_call("editMessageText", {
                        "chat_id": str(chat_id),
                        "message_id": str(status["message_id"]),
                        "text": tr(chat_id, "too_big"), "parse_mode": "HTML",
                        "reply_markup": main_reply_kb(chat_id),
                    })
                except Exception: pass
                return
            send_chat_action(chat_id, "upload_video")
            telegram_call("sendVideo", {"chat_id": str(chat_id),
                                        "video": media_url, "supports_streaming": "true"})

        try:
            telegram_call("deleteMessage",
                          {"chat_id": str(chat_id), "message_id": str(status["message_id"])})
        except Exception: pass

        with STATE_LOCK:
            TOTAL_DOWNLOADS += 1
            if chat_id in USERS:
                USERS[chat_id]["downloads"] = USERS[chat_id].get("downloads", 0) + 1
        save_data()
        send_message(chat_id, tr(chat_id, "success"), reply_markup=main_reply_kb(chat_id))
    except Exception as error:
        log("Download failed for %s: %s", chat_id, error)
        if status:
            try:
                telegram_call("editMessageText", {
                    "chat_id": str(chat_id),
                    "message_id": str(status["message_id"]),
                    "text": tr(chat_id, "download_failed"), "parse_mode": "HTML",
                    "reply_markup": main_reply_kb(chat_id),
                })
            except Exception:
                send_message(chat_id, tr(chat_id, "download_failed"),
                             reply_markup=main_reply_kb(chat_id))
        else:
            send_message(chat_id, tr(chat_id, "download_failed"),
                         reply_markup=main_reply_kb(chat_id))
    finally:
        with STATE_LOCK:
            STATE[chat_id] = {"mode": "menu"}


def start_download(chat_id, url, kind):
    EXECUTOR.submit(_run_download, chat_id, url, kind)


# ---------------------------------------------------------------------------
# Ban notify
# ---------------------------------------------------------------------------
def notify_ban(user_id, reason, contact_url):
    text = tr(user_id, "ban_notify").format(reason=escape(reason),
                                            url=escape(contact_url or "—"))
    try: send_message(user_id, text)
    except Exception as error: log("Ban notify failed for %s: %s", user_id, error)


# ---------------------------------------------------------------------------
# User tracking / formatting
# ---------------------------------------------------------------------------
def track_user(message):
    frm = message.get("from") or {}
    uid = frm.get("id")
    if uid is None: return
    with STATE_LOCK:
        if uid in USERS:
            USERS[uid]["first_name"] = frm.get("first_name") or USERS[uid].get("first_name")
            USERS[uid]["username"] = frm.get("username") or USERS[uid].get("username")
        else:
            USERS[uid] = {"id": uid, "first_name": frm.get("first_name") or "",
                          "username": frm.get("username") or "",
                          "joined": int(time.time()), "downloads": 0}
            save_data()


def fmt_uptime(seconds):
    h, rem = divmod(seconds, 3600); m, s = divmod(rem, 60)
    if h: return f"{h}h {m}m"
    if m: return f"{m}m {s}s"
    return f"{s}s"


def fmt_date(ts):
    try: return time.strftime("%Y-%m-%d", time.gmtime(ts))
    except Exception: return "—"


# ---------------------------------------------------------------------------
# Admin panel helpers
# ---------------------------------------------------------------------------
def show_admin_panel(chat_id):
    ADMIN_VIEW.pop(chat_id, None)
    send_message(chat_id, tr(chat_id, "admin_panel"), reply_markup=admin_reply_kb(chat_id))


def show_users_page(chat_id, page: int = 0):
    per_page = 5
    user_list = sorted(USERS.values(), key=lambda u: u.get("joined", 0), reverse=True)
    total = len(user_list)
    if total == 0:
        ADMIN_VIEW.pop(chat_id, None)
        send_message(chat_id, tr(chat_id, "users_empty"), reply_markup=admin_reply_kb(chat_id))
        return
    pages = (total + per_page - 1) // per_page
    page = max(0, min(page, pages - 1))
    chunk = user_list[page*per_page:(page+1)*per_page]
    ADMIN_VIEW[chat_id] = {"page": page, "list": user_list, "pages": pages}

    lines = [tr(chat_id, "users_header"),
             f"━━━━━━━━━━━━━━━━━━",
             f"📄 <b>Page {page+1} / {pages}</b>  •  👥 Total: <b>{total}</b>",
             ""]
    for i, u in enumerate(chunk, start=1):
        uid = u["id"]
        icon = "🚫" if uid in BANNED else "✅"
        uname = f"@{u['username']}" if u.get("username") else "—"
        lines.append(
            f"<b>{i}.</b> {icon} {escape(u.get('first_name') or 'User')} "
            f"(<code>{uid}</code>)\n    {escape(uname)}"
        )
    lines += ["", "👇 <i>Tap a number below to view user details.</i>"]
    send_message(chat_id, "\n".join(lines),
                 reply_markup=user_list_reply_kb(chat_id, len(chunk), page, pages))


def show_user_detail(chat_id, uid: int):
    u = USERS.get(uid)
    if not u:
        send_message(chat_id, tr(chat_id, "users_empty"), reply_markup=admin_reply_kb(chat_id))
        return
    status = "🚫 Banned" if uid in BANNED else "✅ Active"
    username = f"@{u.get('username')}" if u.get("username") else "—"
    text = tr(chat_id, "user_details").format(
        name=escape(u.get("first_name") or "—"),
        username=escape(username), uid=uid,
        joined=fmt_date(u.get("joined", 0)), status=status,
        downloads=u.get("downloads", 0))
    if uid in BANNED:
        text += f"\n\n📝 <b>Ban reason:</b> {escape(BANNED[uid].get('reason',''))}"
    ADMIN_VIEW[chat_id] = ADMIN_VIEW.get(chat_id, {}) | {"selected_uid": uid}
    send_message(chat_id, text, reply_markup=user_detail_reply_kb(chat_id, uid))


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------
def process_message(message):
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None: return
    text = (message.get("text") or "").strip()
    frm = message.get("from") or {}
    first_name = frm.get("first_name") or ""
    user_id = frm.get("id", chat_id)
    if not text: return

    is_admin = user_id in ADMIN_IDS

    # Banned user check
    if user_id in BANNED and not is_admin:
        ban = BANNED[user_id]
        notify_ban(user_id, ban.get("reason", ""), ban.get("contact_url", ""))
        return

    track_user(message)

    # --- Admin flow (highest priority) ---
    if is_admin and user_id in ADMIN_FLOW:
        flow = ADMIN_FLOW[user_id]
        # Allow BACK to cancel
        if match_reply_button(text) == "back":
            del ADMIN_FLOW[user_id]
            send_message(chat_id, tr(chat_id, "cancel_flow"))
            show_admin_panel(chat_id)
            return
        action = flow.get("action")
        if action == "ban_reason":
            ADMIN_FLOW[user_id] = {"action": "ban_url",
                                   "target": flow["target"], "reason": text}
            send_message(chat_id, tr(chat_id, "ask_ban_url"),
                         reply_markup=back_only_reply_kb(chat_id))
            return
        if action == "ban_url":
            target, reason = flow["target"], flow.get("reason", "")
            url = text.strip()
            if not re.match(r"^https?://", url):
                send_message(chat_id, "❌ Invalid URL. Send again (must start with https://)",
                             reply_markup=back_only_reply_kb(chat_id))
                return
            with STATE_LOCK:
                BANNED[target] = {"reason": reason, "contact_url": url,
                                  "banned_at": int(time.time())}
            del ADMIN_FLOW[user_id]
            save_data()
            notify_ban(target, reason, url)
            name = USERS.get(target, {}).get("first_name", "User")
            send_message(chat_id,
                         tr(chat_id, "ban_done").format(name=escape(name), uid=target))
            show_admin_panel(chat_id)
            return
        if action == "broadcast":
            del ADMIN_FLOW[user_id]
            ok = fail = 0
            for uid in list(USERS.keys()):
                if uid in BANNED: continue
                try: send_message(uid, text); ok += 1
                except Exception: fail += 1
                time.sleep(0.05)
            send_message(chat_id, tr(chat_id, "broadcast_done").format(ok=ok, fail=fail))
            show_admin_panel(chat_id)
            return
        if action == "ownerlink":
            url = text.strip()
            if not re.match(r"^https?://", url):
                send_message(chat_id, "❌ Invalid URL. Send again (must start with https://)",
                             reply_markup=back_only_reply_kb(chat_id))
                return
            global OWNER_CONTACT_URL
            OWNER_CONTACT_URL = url
            del ADMIN_FLOW[user_id]
            save_data()
            send_message(chat_id, tr(chat_id, "ownerlink_saved").format(url=escape(url)))
            show_admin_panel(chat_id)
            return

    # --- /start ---
    if text == "/start":
        with STATE_LOCK:
            STATE[chat_id] = {"mode": "menu"}
        ADMIN_VIEW.pop(chat_id, None)
        ADMIN_FLOW.pop(user_id, None) if is_admin else None
        send_welcome(chat_id, first_name, user_id)
        return

    # --- /admin ---
    if text == "/admin":
        if not is_admin:
            send_message(chat_id, tr(chat_id, "admin_only"),
                         reply_markup=main_reply_kb(chat_id))
            return
        show_admin_panel(chat_id)
        return

    # --- Reply buttons ---
    action = match_reply_button(text)

    if action == "back":
        with STATE_LOCK:
            STATE[chat_id] = {"mode": "menu"}
        # If admin was in user view, go back to user list page
        if is_admin and chat_id in ADMIN_VIEW and "list" in ADMIN_VIEW[chat_id]:
            view = ADMIN_VIEW[chat_id]
            if "selected_uid" in view:
                # was viewing a user, go back to list
                view.pop("selected_uid", None)
                show_users_page(chat_id, view.get("page", 0))
                return
        send_message(chat_id, tr(chat_id, "menu"), reply_markup=main_reply_kb(chat_id))
        return

    if action == "download":
        with STATE_LOCK:
            STATE[chat_id] = {"mode": "awaiting_url"}
        send_message(chat_id, tr(chat_id, "send_link"),
                     reply_markup=back_only_reply_kb(chat_id))
        return

    if action == "how":
        with STATE_LOCK:
            STATE[chat_id] = {"mode": "menu"}
        send_message(chat_id, tr(chat_id, "how_to_use"),
                     reply_markup=main_reply_kb(chat_id))
        return

    if action == "language":
        with STATE_LOCK:
            STATE[chat_id] = {"mode": "awaiting_language"}
        send_message(chat_id, tr(chat_id, "choose_language"),
                     reply_markup=language_reply_kb(chat_id))
        return

    if action == "owner":
        with STATE_LOCK:
            STATE[chat_id] = {"mode": "menu"}
        if OWNER_CONTACT_URL:
            text_owner = tr(chat_id, "owner_info")
            if is_admin:
                text_owner += tr(chat_id, "admin_extra")
            send_message(chat_id, text_owner,
                         reply_markup=owner_inline_kb(chat_id))
        else:
            text_owner = tr(chat_id, "owner_no_link")
            if is_admin:
                text_owner += tr(chat_id, "admin_extra")
            send_message(chat_id, text_owner, reply_markup=main_reply_kb(chat_id))
        return

    if action in ("en", "bn"):
        LANG[chat_id] = action
        with STATE_LOCK:
            STATE[chat_id] = {"mode": "menu"}
        send_message(chat_id, tr(chat_id, "language_changed"),
                     reply_markup=main_reply_kb(chat_id))
        return

    if action in ("video", "music"):
        with STATE_LOCK:
            item = STATE.get(chat_id, {})
            if item.get("mode") == "awaiting_format":
                url = item.get("url", "")
                STATE[chat_id] = {"mode": "menu"}
            else:
                url = ""
        if url:
            start_download(chat_id, url, action)
        else:
            send_message(chat_id, tr(chat_id, "menu"),
                         reply_markup=main_reply_kb(chat_id))
        return

    # --- Admin buttons ---
    if action == "admin_users" and is_admin:
        show_users_page(chat_id, 0); return

    if action == "admin_stats" and is_admin:
        total = len(USERS); banned = len(BANNED); active = total - banned
        uptime = fmt_uptime(int(time.time() - START_TIME))
        text_stats = tr(chat_id, "stats").format(
            bot=BOT_USERNAME or "—", total=total, active=active,
            banned=banned, downloads=TOTAL_DOWNLOADS, uptime=uptime)
        send_message(chat_id, text_stats, reply_markup=admin_reply_kb(chat_id))
        return

    if action == "admin_broadcast" and is_admin:
        ADMIN_FLOW[user_id] = {"action": "broadcast"}
        send_message(chat_id, tr(chat_id, "broadcast_ask"),
                     reply_markup=back_only_reply_kb(chat_id))
        return

    if action == "admin_ownerlink" and is_admin:
        ADMIN_FLOW[user_id] = {"action": "ownerlink"}
        current = OWNER_CONTACT_URL or "—"
        send_message(chat_id, tr(chat_id, "ownerlink_ask").format(current=escape(current)),
                     reply_markup=back_only_reply_kb(chat_id))
        return

    # numbered user buttons
    if is_admin and chat_id in ADMIN_VIEW and text.isdigit():
        view = ADMIN_VIEW[chat_id]
        idx = int(text) - 1
        page = view.get("page", 0)
        user_list = view.get("list", [])
        actual_idx = page * 5 + idx
        if 0 <= actual_idx < len(user_list):
            show_user_detail(chat_id, user_list[actual_idx]["id"])
            return

    if action == "admin_prev" and is_admin:
        view = ADMIN_VIEW.get(chat_id, {})
        show_users_page(chat_id, view.get("page", 0) - 1); return

    if action == "admin_next" and is_admin:
        view = ADMIN_VIEW.get(chat_id, {})
        show_users_page(chat_id, view.get("page", 0) + 1); return

    if action in ("admin_ban", "admin_unban") and is_admin:
        view = ADMIN_VIEW.get(chat_id, {})
        uid = view.get("selected_uid")
        if not uid:
            send_message(chat_id, tr(chat_id, "menu"),
                         reply_markup=main_reply_kb(chat_id)); return
        if action == "admin_unban":
            with STATE_LOCK: BANNED.pop(uid, None)
            save_data()
            try:
                send_message(uid, "✅ <b>You have been unbanned. Welcome back!</b>",
                             reply_markup=main_reply_kb(uid))
            except Exception: pass
            send_message(chat_id, tr(chat_id, "unban_done").format(uid=uid))
            show_users_page(chat_id, view.get("page", 0))
        else:  # admin_ban
            if uid in ADMIN_IDS:
                send_message(chat_id, "⛔ Cannot ban an admin.",
                             reply_markup=admin_reply_kb(chat_id)); return
            ADMIN_FLOW[user_id] = {"action": "ban_reason", "target": uid}
            u = USERS.get(uid, {})
            send_message(chat_id, tr(chat_id, "ask_ban_reason").format(
                name=escape(u.get("first_name") or "User"), uid=uid),
                reply_markup=back_only_reply_kb(chat_id))
        return

    # --- Awaiting URL ---
    with STATE_LOCK:
        current = STATE.get(chat_id, {"mode": "menu"}).copy()

    if current.get("mode") == "awaiting_url":
        url = normalize_url(text)
        if not url or not is_tiktok_url(url):
            send_message(chat_id, tr(chat_id, "invalid_link"),
                         reply_markup=back_only_reply_kb(chat_id))
            return
        with STATE_LOCK:
            STATE[chat_id] = {"mode": "awaiting_format", "url": url}
        send_message(chat_id, tr(chat_id, "choose_format"),
                     reply_markup=format_reply_kb(chat_id))
        return

    # --- Fallback ---
    send_message(chat_id, tr(chat_id, "menu"), reply_markup=main_reply_kb(chat_id))


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------
def polling_loop():
    offset = 0
    backoff = 2
    while not SHUTDOWN.is_set():
        try:
            updates = telegram_call("getUpdates", {
                "offset": str(offset), "timeout": "25",
                "allowed_updates": json.dumps(["message"]),
            })
            backoff = 2
            for update in updates or []:
                offset = max(offset, int(update.get("update_id", 0)) + 1)
                try:
                    if update.get("message"):
                        process_message(update["message"])
                except Exception:
                    LOG.exception("Update handling failed")
        except Exception as error:
            log("Polling error: %s", error)
            SHUTDOWN.wait(backoff)
            backoff = min(backoff * 2, 30)


# ---------------------------------------------------------------------------
# Health server
# ---------------------------------------------------------------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/healthz", "/health"}:
            self.send_response(404); self.end_headers(); return
        payload = json.dumps({"ok": True, "service": "streamly",
                              "users": len(USERS), "banned": len(BANNED),
                              "downloads": TOTAL_DOWNLOADS}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers(); self.wfile.write(payload)
    def log_message(self, format, *args): return


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_health_server():
    for port in (PORT, PORT + 1, PORT + 2, PORT + 10):
        try:
            server = ReusableThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
        except OSError as error:
            log("Port %s unavailable (%s)", port, error); continue
        threading.Thread(target=server.serve_forever,
                         name="health-server", daemon=True).start()
        log("Health server listening on 0.0.0.0:%s", port)
        return server
    log("Health server disabled — bot will run without it.")
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def shutdown_handler(_signum, _frame):
    log("Shutdown signal received"); SHUTDOWN.set()


def main():
    if not TOKEN or TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("❌ TOKEN is missing. Edit the TOKEN line at the top of the file.")
    if not ADMIN_IDS:
        log("⚠️  ADMIN_ID is not set. Nobody can access the admin panel.")

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    load_data()
    health_server = start_health_server()

    try:
        telegram_call("deleteWebhook", {"drop_pending_updates": "false"})
        me = telegram_call("getMe")
        log("Bot connected as @%s", me.get("username", "unknown"))
        log("Admins: %s", ADMIN_IDS or "none")
        log("Owner link: %s", OWNER_CONTACT_URL or "not set (use /admin → OWNER LINK)")
        threading.Thread(target=polling_loop, name="telegram-polling",
                         daemon=True).start()
        while not SHUTDOWN.wait(1):
            pass
    finally:
        SHUTDOWN.set(); save_data()
        if health_server is not None:
            try: health_server.shutdown()
            except Exception: pass
        EXECUTOR.shutdown(wait=False, cancel_futures=True)
        log("Streamly stopped")


if __name__ == "__main__":
    main()