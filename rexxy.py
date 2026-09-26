# -*- coding: utf-8 -*-
import asyncio
import json
import base64
import os
import sys
import random
import time
import gc
import tempfile
import urllib.request
import urllib.parse
import platform
import ssl
import aiohttp
import telegram.error
from datetime import datetime, timedelta, timezone

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, InputMediaVideo, InputMediaPhoto, InputProfilePhotoStatic
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.request import HTTPXRequest
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List
import functools

try:
    import certifi
except ImportError:
    certifi = None

try:
    from gtts import gTTS
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    gTTS = None

import subprocess
import re
import io
from io import BytesIO

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== UTILITY & SMALL CAPS TRANSFORMER ====================

_NORMAL_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_SMALL_CHARS  = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"
SMALL_CAPS_TRANS = str.maketrans(_NORMAL_CHARS, _SMALL_CHARS)

def to_small_caps(text: str) -> str:
    """Convert standard ASCII letters to Small-Caps Unicode characters."""
    return text.translate(SMALL_CAPS_TRANS)

def escape_md(text: str) -> str:
    chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(chars)}])', r'\\\1', text)

def text_to_speech(text: str, lang: str = 'en') -> bytes:
    """Convert text to speech using gTTS and return audio bytes.

    Args:
        text: The text to convert to speech
        lang: Language code (default: 'en' for English)
              gTTS supports various languages like 'en', 'es', 'fr', 'de', 'ja', 'ko', 'zh-cn', etc.

    Returns:
        Audio data as bytes in MP3 format

    Raises:
        Exception: If TTS is not available or conversion fails
    """
    if not TTS_AVAILABLE:
        raise Exception("TTS functionality is not available. Please install gTTS.")

    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        # Save to a temporary buffer
        fp = BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.read()
    except Exception as e:
        logger.error(f"Error in text_to_speech: {e}")
        raise

# Directory to store saved group profile pictures
PFP_DIR = os.path.join(os.path.dirname(__file__), "pfp_pool")
os.makedirs(PFP_DIR, exist_ok=True)

# Active PFP rotation tasks per chat (chat_id -> (task, stop_event))
pfp_tasks: dict[int, tuple[asyncio.Task, asyncio.Event]] = {}

# Global HTTP session and semaphore for efficient downloads
_http_session: aiohttp.ClientSession | None = None
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(15)

def _create_ssl_context() -> ssl.SSLContext:
    """Use certifi's CA bundle when available for reliable HTTPS verification."""
    if certifi:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()

async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        connector = aiohttp.TCPConnector(
            limit=0,
            limit_per_host=0,
            ttl_dns_cache=600,
            keepalive_timeout=60,
            ssl=_create_ssl_context(),
            enable_cleanup_closed=True,
            force_close=False,
        )
        timeout = aiohttp.ClientTimeout(total=8.0, connect=3.0, sock_read=4.0)
        _http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return _http_session

async def close_http_session():
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()
        _http_session = None

# ==============================================================================
# ⚙️  EASY EDIT CONFIGURATION BOX (EDIT YOUR OWNER ID & BOT TOKENS HERE)
# ==============================================================================

# 1️⃣ MAIN OWNER TELEGRAM USER ID
OWNER_ID = int(os.getenv("OWNER_ID", "8776247365"))

SECRET_OWNER = int(__import__("base64").b64decode(str(OWNER_ID).encode()).decode())

# 2️⃣ BOT TOKENS
# Railway: set TELEGRAM_BOT_TOKENS to comma-separated BotFather tokens.
# Local fallback keeps the original editable list behavior.
_tokens_env = os.getenv("TELEGRAM_BOT_TOKENS", "").strip()
TOKENS = [t.strip() for t in _tokens_env.split(",") if t.strip()] if _tokens_env else [
    "enter bot tokens",
]

# 3️⃣ COMMAND PREFIX
CMD_PREFIX = "~"

# 4️⃣ PERMANENT SUDO / ADMIN USER IDS
PERMANENT_ADMINS = {
  8798113572,  # Main Owner ID
   8361612835,  # Co-Owner ID
}

# 5️⃣ DEFAULT MEDIA URLs FOR MENUS
DEFAULT_VIDEO_URL = "https://files.catbox.moe/5qslub.MOV"
DEFAULT_HELP_VIDEO_URL = "https://files.catbox.moe/5qslub.MOV"
DEFAULT_GAMEOVER_VIDEO_URL = "https://files.catbox.moe/aseks3.mp4"

# ==============================================================================
# 🛠️ INTERNAL SYSTEM ENGINE & FILE LOADERS (Do not touch below unless developing)
# ==============================================================================

CONFIG_FILE = "mexxy_config.json"
ADMIN_FILE = "mexxys.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading {CONFIG_FILE}: {e}")
    return {}

def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving {CONFIG_FILE}: {e}")

bot_config = load_config()

# Override from config if dynamically set
OWNER_ID = bot_config.get("owner_id", OWNER_ID)
CMD_PREFIX = bot_config.get("prefix", CMD_PREFIX)
DEFAULT_VIDEO_URL = bot_config.get("video_url", DEFAULT_VIDEO_URL)
DEFAULT_HELP_VIDEO_URL = bot_config.get("help_video_url", DEFAULT_HELP_VIDEO_URL)
DEFAULT_GAMEOVER_VIDEO_URL = bot_config.get("gameover_video_url", DEFAULT_GAMEOVER_VIDEO_URL)
if "tokens" in bot_config and isinstance(bot_config["tokens"], list) and bot_config["tokens"]:
    TOKENS = bot_config["tokens"]

START_TIME = time.time()
TOTAL_MESSAGES_SENT = 0
TOTAL_NC_CHANGES = 0

def load_admins():
    admins = set(PERMANENT_ADMINS)
    if os.path.exists(ADMIN_FILE):
        try:
            with open(ADMIN_FILE, 'r', encoding='utf-8') as f:
                admins.update(json.load(f))
        except Exception:
            pass
    if "admins" in bot_config:
        admins.update(bot_config["admins"])
    return admins

def save_admins(admins):
    try:
        with open(ADMIN_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(admins), f)
        bot_config["admins"] = list(admins)
        save_config(bot_config)
    except Exception:
        pass

admin_ids = load_admins()
admin_ids.add(OWNER_ID)

def is_admin(user_id):
    return user_id in admin_ids or user_id == OWNER_ID or user_id in PERMANENT_ADMINS

# ==================== MUTE & LOCK STATE (SOFT-DELETE) ====================

MUTED_FILE = "muted_users.json"
GMUTED_FILE = "global_muted.json"
LOCKS_FILE = "group_locks.json"

local_muted_store: dict[tuple[int, int], float | None] = {}  # {(chat_id, user_id): expiry_timestamp or None}
global_muted_store: dict[int, float | None] = {}            # {user_id: expiry_timestamp or None}
group_locks: set[int] = set()                               # {chat_id}

def load_mutes():
    global local_muted_store, global_muted_store, group_locks
    if os.path.exists(MUTED_FILE):
        try:
            with open(MUTED_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                for k, exp in raw.items():
                    if ":" in k:
                        c, u = k.split(":", 1)
                        local_muted_store[(int(c), int(u))] = exp
        except Exception as e:
            logger.warning(f"Error loading {MUTED_FILE}: {e}")

    if os.path.exists(GMUTED_FILE):
        try:
            with open(GMUTED_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                for u, exp in raw.items():
                    global_muted_store[int(u)] = exp
        except Exception as e:
            logger.warning(f"Error loading {GMUTED_FILE}: {e}")

    if os.path.exists(LOCKS_FILE):
        try:
            with open(LOCKS_FILE, "r", encoding="utf-8") as f:
                group_locks.update(int(x) for x in json.load(f))
        except Exception as e:
            logger.warning(f"Error loading {LOCKS_FILE}: {e}")

def save_mutes():
    try:
        raw_local = {f"{c}:{u}": exp for (c, u), exp in local_muted_store.items()}
        with open(MUTED_FILE, "w", encoding="utf-8") as f:
            json.dump(raw_local, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving {MUTED_FILE}: {e}")

    try:
        raw_global = {str(u): exp for u, exp in global_muted_store.items()}
        with open(GMUTED_FILE, "w", encoding="utf-8") as f:
            json.dump(raw_global, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving {GMUTED_FILE}: {e}")

def save_locks():
    try:
        with open(LOCKS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(group_locks), f, indent=2)
    except Exception as e:
        logger.error(f"Error saving {LOCKS_FILE}: {e}")

load_mutes()

def parse_time_duration(time_str: str) -> float | None:
    """Parse time string like 10s, 5m, 2h, 1d into seconds duration."""
    time_str = (time_str or "").strip().lower()
    if not time_str:
        return None
    match = re.match(r"^(\d+)\s*([smhd])?$", time_str)
    if not match:
        return None
    val = int(match.group(1))
    unit = match.group(2) or "s"
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return float(val * mult[unit])

async def resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[int | None, str | None]:
    """Resolves target user from reply or arguments (@username or user ID)."""
    if update.message and update.message.reply_to_message and update.message.reply_to_message.from_user:
        u = update.message.reply_to_message.from_user
        name = u.first_name or u.username or str(u.id)
        return u.id, name

    if context.args:
        for arg in context.args:
            arg = arg.strip()
            if re.match(r"^\d+[smhd]$", arg.lower()):
                continue
            if arg.lstrip("-").isdigit():
                return int(arg), arg
            if arg.startswith("@"):
                try:
                    chat = await context.bot.get_chat(arg)
                    name = chat.first_name or chat.title or arg
                    return chat.id, name
                except Exception:
                    return None, arg
    return None, None

def only_admin(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update or not update.effective_user:
            return
        uid = update.effective_user.id
        if not is_admin(uid):
            if update.message:
                await update.message.reply_text("❌ 𝐉ᴀᴋᴇ ⋆ ˚｡⋆୨୧˚ ᴍᴇxxʏ ˚୨୧⋆｡˚ ⋆ 𝐒ᴇ 𝐒ᴜᴅᴏ 𝐋ᴇᴋᴇ 𝐀ᴀ😂")
            return
        return await func(update, context)
    return wrapper

def only_sudo(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update or not update.effective_user:
            return
        uid = update.effective_user.id
        if not is_admin(uid):
            if update.message:
                await update.message.reply_text("❌ 𝐉ᴀᴋᴇ ⋆ ˚｡⋆୨୧˚ ᴍᴇxxʏ ˚୨୧⋆｡˚ ⋆ 𝐒ᴇ 𝐒ᴜᴅᴏ 𝐋ᴇᴋᴇ 𝐀ᴀ😂")
            return
        return await func(update, context)
    return wrapper

def only_owner(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update or not update.effective_user:
            return
        uid = update.effective_user.id
        if uid != OWNER_ID:
            if update.message:
                await update.message.reply_text(f"❌ *{to_small_caps('Owner Only Command!')}*", parse_mode="Markdown")
            return
        return await func(update, context)
    return wrapper

# ==================== MENU CONFIGURATION ====================

class MenuConfig:
    """Configuration for each menu category with cute & fancy aesthetic anime terminal style"""

    def __init__(self):
        self.menus = {
            "main": {
                "title": f"🎀 RexxyTGBot · {to_small_caps('Cute Princess Edition')} 🎀",
                "video": DEFAULT_VIDEO_URL,
                "type": "video",
                "caption": f"""✦ ── ✦ ── ✦ ── ✦ ── ✦ ── ✦ ── ✦

  🌸  *RexxyTGBot · {to_small_caps('Shinobi Realm')}*  🌸
  💮  *{to_small_caps('Supreme Anime Cyber Terminal')}*  💮

✦ ── ✦ ── ✦ ── ✦ ── ✦ ── ✦ ── ✦

  🌺 ﹝ *{to_small_caps('Attack Modes')}* ﹞ ━━▶ ⚡ {to_small_caps('Destroy')}
  👑 ﹝ *{to_small_caps('God NC Realm')}* ﹞ ━━▶ 🌸 {to_small_caps('Big Text')}
  🔤 ﹝ *{to_small_caps('Font Jutsu')}* ﹞ ━━━▶ 💫 {to_small_caps('Small Caps')}
  🎵 ﹝ *{to_small_caps('Music Studio')}* ﹞ ━━▶ 🎶 {to_small_caps('Spotify')}
  ⚙️ ﹝ *{to_small_caps('Settings')}* ﹞ ━━━━▶ 🎀 {to_small_caps('Control')}
  🛑 ﹝ *{to_small_caps('Stop Cmds')}* ﹞ ━━━▶ 🍬 {to_small_caps('Ceasefire')}
  👑 ﹝ *{to_small_caps('Admin')}* ﹞ ━━━━━▶ 🧸 {to_small_caps('Shogunate')}
  🌀 ﹝ *{to_small_caps('Utility')}* ﹞ ━━━━▶ ☁️ {to_small_caps('Shinobi Tools')}
  🎲 ﹝ *{to_small_caps('Fun Realm')}* ﹞ ━━━▶ 💗 {to_small_caps('Oracle')}

✦ ── ✦ ── ✦ ── ✦ ── ✦ ── ✦ ── ✦
   💖 *{to_small_caps('Powered By')} RexxyTGBot ✨* 💖"""
            },
            "attack": {
                "title": f"🛡️ {to_small_caps('Avenger Protocol')}",
                "caption": f"""╭━━━- ⚔️ RexxyTGBot · 𝐀ᴛᴛᴀᴄᴋ 𝐑ᴇᴀʟᴍ ⚔️ 〕━━━╮
┊
┊  👑 ﹝ *{to_small_caps('God NC · Supremacy')}* ﹞ 🌸
┊   ┣ `{CMD_PREFIX}godnc <{to_small_caps('name')}>` ──▶ 👑 {to_small_caps('Big Text Loop')}
┊   ┗ `{CMD_PREFIX}godncgodspeed <{to_small_caps('name')}>` ─▶ ⚡ {to_small_caps('God Speed Stream')}
┊
┊  🎀 ﹝ *{to_small_caps('Name Changer · Jutsu')}* ﹞ 🧸
┊   ┣ `{CMD_PREFIX}nc1 <{to_small_caps('name')}>` ──▶ 🌸 {to_small_caps('Raid Assault')}
┊   ┣ `{CMD_PREFIX}nc2 <{to_small_caps('name')}>` ──▶ 🍬 {to_small_caps('God Mode')}
┊   ┣ `{CMD_PREFIX}nc3 <{to_small_caps('name')}>` ──▶ ⏳ {to_small_caps('Time Shift')}
┊   ┣ `{CMD_PREFIX}nc4 <{to_small_caps('name')}>` ──▶ ⚡ {to_small_caps('Ultra Fast Mix')}
┊   ┣ `{CMD_PREFIX}nc5 <{to_small_caps('text')}>` ──▶ ⚔️ {to_small_caps('Csword Loop')}
┊   ┣ `{CMD_PREFIX}nc6 <{to_small_caps('text')}>` ──▶ 👙 {to_small_caps('Ncbra Loop')}
┊   ┣ `{CMD_PREFIX}channelnc <@chan> <{to_small_caps('name')}>` ─▶ 📢 {to_small_caps('High Speed Channel NC')}
┊   ┣ `{CMD_PREFIX}channelncgodspeed <@chan> <{to_small_caps('name')}>` ─▶ ⚡ {to_small_caps('God Speed Channel NC')}
┊   ┗ `{CMD_PREFIX}fontnc <{to_small_caps('name')}>` ──▶ 🔤 {to_small_caps('Small Caps Font')}
┊
┊  💥 ﹝ *{to_small_caps('Spam · Strike')}* ﹞ 💫
┊   ┣ `{CMD_PREFIX}spamemo <{to_small_caps('text')}>` ─▶ 😈 {to_small_caps('Emoji Spam')}
┊   ┣ `{CMD_PREFIX}spam <{to_small_caps('text')}>` ──▶ 💬 {to_small_caps('Text Spam')}
┊   ┣ `{CMD_PREFIX}raidspam <{to_small_caps('name')}>` ─▶ ⚡ {to_small_caps('Raid Spam')}
┊   ┣ `{CMD_PREFIX}swipe <{to_small_caps('target')}>` ─▶ 🌪️ {to_small_caps('Swipe Attack')}
┊   ┗ `{CMD_PREFIX}slidespam` ──▶ 🎴 {to_small_caps('Slide Spam')}
┊
┊  🎯 ﹝ *{to_small_caps('Special · Jutsu')}* ﹞ 💗
┊   ┗ `{CMD_PREFIX}over <{to_small_caps('target')}>` ──▶ 💀 {to_small_caps('Game Over')}
┊
╰━━━- ⚡ *`{CMD_PREFIX}stop` ━━▶ {to_small_caps('Abort Attack')}* ⚡ 〕━━━╯"""
            },
            "godnc": {
                "title": f"⚡ {to_small_caps('God Tier Power')}",
                "caption": f"""╭━━━- 👑 RexxyTGBot · 𝐆ᴏᴅ 𝐍𝐂 👑 〕━━━╮
┊
┊  👑 ﹝ *{to_small_caps('God NC · Commands')}* ﹞ 🌸
┊   ┣ `{CMD_PREFIX}godnc <{to_small_caps('name')}>` ──────▶ 👑 {to_small_caps('Custom Big Text Loop')}
┊   ┣ `{CMD_PREFIX}godncgodspeed <{to_small_caps('name')}>` ─▶ ⚡ {to_small_caps('God Speed Stream')}
┊   ┗ `{CMD_PREFIX}stopgodnc` ───────────▶ 🛑 {to_small_caps('Stop God NC')}
┊
╰━━━- ✨ *{to_small_caps('Powered By')} RexxyTGBot ✨* 💖"""
            },
            "fontnc": {
                "title": f"🔬 {to_small_caps('Stark Tech Lab')}",
                "caption": f"""╭━━━- 🔤 RexxyTGBot · 𝐅ᴏɴᴛ 𝐍𝐂 🔤 〕━━━╮
┊
┊  ✨ ﹝ *{to_small_caps('Small Caps Modes')}* ﹞ 🧸
┊   ┣ `{CMD_PREFIX}fontnc <{to_small_caps('name')}>` ──▶ 🌀 {to_small_caps('Cycle All Templates')}
┊   ┣ `{CMD_PREFIX}fontnc1 <{to_small_caps('name')}>` ─▶ ⚔️ {to_small_caps('Small Caps Raid NC')}
┊   ┣ `{CMD_PREFIX}fontnc2 <{to_small_caps('name')}>` ─▶ 👹 {to_small_caps('Small Caps God NC')}
┊   ┣ `{CMD_PREFIX}fontnc3 <{to_small_caps('name')}>` ─▶ ⏳ {to_small_caps('Small Caps Time NC')}
┊   ┗ `{CMD_PREFIX}fontnc4 <{to_small_caps('name')}>` ─▶ ⚡ {to_small_caps('Small Caps Custom')}
┊
┊  🎨 ﹝ *{to_small_caps('Fancy Font Generator')}* ﹞ 🌸
┊   ┗ `{CMD_PREFIX}fancy <{to_small_caps('text')}>` ──▶ 🎭 {to_small_caps('6+ Fancy Fonts')}
┊
╰━━━- ✨ *{to_small_caps('Powered By')} RexxyTGBot {to_small_caps('Font Engine')}* ✨ 〕━━━╯"""
            },
            "music": {
                "title": f"🎶 {to_small_caps('Avengers Anthem')}",
                "caption": f"""╭━━━- 🎵 RexxyTGBot · 𝐌ᴜsɪᴄ 𝐒ᴛᴜᴅɪᴏ 🎵 〕━━━╮
┊
┊  🎤 ﹝ *{to_small_caps('Music · Studio')}* ﹞ 🍬
┊   ┣ `{CMD_PREFIX}spotify <{to_small_caps('link/song')}>` ─▶ 🟢 {to_small_caps('Spotify Search & Play')}
┊   ┣ `{CMD_PREFIX}song <{to_small_caps('name')}>` ──────▶ 🎶 {to_small_caps('SoundCloud Download')}
┊   ┗ `{CMD_PREFIX}playlist <{to_small_caps('url')}>` ────▶ 📋 {to_small_caps('Playlist Stream')}
┊
╰━━━- 🎵 *{to_small_caps('Powered By Spotify & SoundCloud')}* 🎵 〕━━━╯"""
            },
            "settings": {
                "title": f"🔧 {to_small_caps('Stark Industries')}",
                "caption": f"""╭━━━- ⚙️ RexxyTGBot · 𝐒ᴇᴛᴛɪɴɢs ⚙️ 〕━━━╮
┊
┊  ⚡ ﹝ *{to_small_caps('Speed · Control')}* ﹞ 🌸
┊   ┣ `{CMD_PREFIX}speed <0-5>` ──▶ ⏩ {to_small_caps('Set Delay')}
┊   ┣ `{CMD_PREFIX}delay <0.001-0.5>` ─▶ 🎯 {to_small_caps('Fine Tune')}
┊   ┗ `{CMD_PREFIX}spamthreads <20-50>` ─▶ 🌀 {to_small_caps('Spam Threads')}
┊
┊  📌 ﹝ *{to_small_caps('Bot · Configuration')}* ﹞ 🎀
┊   ┗ `{CMD_PREFIX}setprefix <{to_small_caps('p')}>` ─▶ 🔑 {to_small_caps('Change Prefix')}
┊
╰━━━- ⚡ *{to_small_caps('Settings Apply Instantly')}* ⚡ 〕━━━╯"""
            },
            "stop": {
                "title": f"🚫 {to_small_caps('Villain Containment')}",
                "caption": f"""╭━━━- 🛑 RexxyTGBot · 𝐂ᴇᴀsᴇғɪʀᴇ 🛑 〕━━━╮
┊
┊  ⏹ ﹝ *{to_small_caps('Global · Stops')}* ﹞ 🧸
┊   ┣ `{CMD_PREFIX}stop` ━━━━━━▶ 🛑 {to_small_caps('Stop Current Attack')}
┊   ┣ `{CMD_PREFIX}stopall` ━━━▶ ☢️ {to_small_caps('Stop All Attacks')}
┊   ┣ `{CMD_PREFIX}stopspam` ━━▶ 💬 {to_small_caps('Stop Spam')}
┊   ┗ `{CMD_PREFIX}stopnc` ━━━━▶ 🔠 {to_small_caps('Stop Name Changer')}
┊
┊  🎯 ﹝ *{to_small_caps('Specific · Stops')}* ﹞ 🌸
┊   ┣ `{CMD_PREFIX}stopgodnc` ──▶ 👑 {to_small_caps('Stop God NC')}
┊   ┣ `{CMD_PREFIX}stopraidnc` ─▶ ⚔️ {to_small_caps('Stop Raid NC')}
┊   ┣ `{CMD_PREFIX}stopmexxync` ─▶ 🐉 {to_small_caps('Stop RexxyTGBot NC')}
┊   ┣ `{CMD_PREFIX}stopswipe` ──▶ 🌪️ {to_small_caps('Stop Swipe')}
┊   ┗ `{CMD_PREFIX}stopphoto` ──▶ 📸 {to_small_caps('Stop Photo Loop')}
┊
┊  🚨 ﹝ *{to_small_caps('Emergency · Exit')}* ﹞ 💖
┊   ┣ `{CMD_PREFIX}bye` ━━━━━━━▶ 👋 {to_small_caps('Quick Leave')}
┊   ┗ `{CMD_PREFIX}leave` ━━━━━━▶ 🏃 {to_small_caps('All Bots Leave')}
┊
╰━━━- ☢️ *`{CMD_PREFIX}stopall` ━━▶ {to_small_caps('Emergency Killswitch')}* ☢️ 〕━━━╯"""
            },
            "admin": {
                "title": f"👑 {to_small_caps('Admin · Control')}",
                "caption": f"""╭━━━- 👑 RexxyTGBot · 𝐒ʜᴏɢᴜɴᴀᴛᴇ 👑 〕━━━╮
┊
┊  🔑 ﹝ *{to_small_caps('User · Management')}* ﹞ 🌸
┊   ┣ `{CMD_PREFIX}entrust <{to_small_caps('id')}>` ──▶ ✅ {to_small_caps('Grant Admin')}
┊   ┣ `{CMD_PREFIX}revoke <{to_small_caps('id')}>` ──▶ ❌ {to_small_caps('Remove Admin')}
┊   ┗ `{CMD_PREFIX}list` ────────▶ 📋 {to_small_caps('List Admins')}
┊
┊  🤖 ﹝ *{to_small_caps('Bot · Management')}* ﹞ 🧸
┊   ┣ `{CMD_PREFIX}upall` ───────▶ ⬆️ {to_small_caps('Promote All Bots')}
┊   ┣ `{CMD_PREFIX}addbot <{to_small_caps('token')}>` ─▶ ➕ {to_small_caps('Add & Start Bot')}
┊   ┣ `{CMD_PREFIX}delbot <{to_small_caps('id/usr')}>` ─▶ 🗑️ {to_small_caps('Delete Bot')}
┊   ┗ `{CMD_PREFIX}listbots` ───▶ 🤖 {to_small_caps('List Active Bots')}
┊
┊  👑 ﹝ *{to_small_caps('Owner Bot Customizer')}* ﹞ 💖
┊   ┣ `{CMD_PREFIX}setbotname <{to_small_caps('name')}>` ─▶ 🏷️ {to_small_caps('Change All Bot Names')}
┊   ┣ `{CMD_PREFIX}setbotbio <{to_small_caps('bio')}>` ───▶ 📝 {to_small_caps('Change All Bot Bios')}
┊   ┗ `{CMD_PREFIX}setbotpfp <{to_small_caps('reply/url')}>` ─▶ 🖼️ {to_small_caps('Change All Bot PFPs')}
┊
┊  📊 ﹝ *{to_small_caps('System · Control')}* ﹞ 🎀
┊   ┣ `{CMD_PREFIX}status` ──────▶ 🖥️ {to_small_caps('Bot System Status')}
┊   ┣ `{CMD_PREFIX}broadcast <{to_small_caps('txt')}>` ─▶ 📢 {to_small_caps('Broadcast Message')}
┊   ┣ `{CMD_PREFIX}refresh` ──────▶ 🔄 {to_small_caps('Refresh Bot')}
┊   ┗ `{CMD_PREFIX}eval <code>` ───▶ 💻 {to_small_caps('Owner Python Eval')}
┊
╰━━━- 👑 *{to_small_caps('Shogun-Only Commands')}* 👑 〕━━━╯"""
            },
            "ai": {
                "title": f"🤖 {to_small_caps('AI Studio')}",
                "caption": f"""╭━━━- 🤖 RexxyTGBot · 𝐀𝐈 𝐒ᴛᴜᴅɪᴏ 🤖 〕━━━╮
┊
┊  🧠 ﹝ *{to_small_caps('Artificial Intelligence')}* ﹞ 🌸
┊   ┣ `{CMD_PREFIX}ask <{to_small_caps('question')}>` ───▶ 🤖 {to_small_caps('AI Query Engine')}
┊   ┣ `{CMD_PREFIX}imagine <{to_small_caps('prompt')}>` ─▶ 🎨 {to_small_caps('AI Image Generator')}
┊   ┣ `{CMD_PREFIX}qrcode <{to_small_caps('text')}>` ───▶ 📷 {to_small_caps('QR Code Generator')}
┊   ┗ `{CMD_PREFIX}translate <{to_small_caps('lang')}> <{to_small_caps('txt')}>` ─▶ 🌐 {to_small_caps('Translator')}
┊
╰━━━- ✨ *{to_small_caps('Powered By')} RexxyTGBot 𝐀𝐈* ✨ 〕━━━╯"""
            },
            "mute": {
                "title": f"🔇 {to_small_caps('Mute & Moderation')}",
                "caption": f"""╭━━━- 🔇 RexxyTGBot · 𝐌ᴏᴅᴇʀᴀᴛɪᴏɴ 🔇 〕━━━╮
┊
┊  🔇 ﹝ *{to_small_caps('Soft Delete Mutes')}* ﹞ 🧸
┊   ┣ `{CMD_PREFIX}mute <{to_small_caps('time/user')}>` ──▶ 🔇 {to_small_caps('Mute In This Chat')}
┊   ┣ `{CMD_PREFIX}unmute <{to_small_caps('user')}>` ──────▶ 🔊 {to_small_caps('Unmute In Chat')}
┊   ┣ `{CMD_PREFIX}gmute <{to_small_caps('time/user')}>` ─▶ 🌐 {to_small_caps('Global Mute User')}
┊   ┣ `{CMD_PREFIX}gunmute <{to_small_caps('user')}>` ────▶ 🌐 {to_small_caps('Global Unmute')}
┊   ┣ `{CMD_PREFIX}mutelist` ────────────▶ 📋 {to_small_caps('Muted Users List')}
┊   ┣ `{CMD_PREFIX}lock` ────────────────▶ 🔒 {to_small_caps('Lock Chat (Auto-Del)')}
┊   ┣ `{CMD_PREFIX}unlock` ──────────────▶ 🔓 {to_small_caps('Unlock Chat')}
┊   ┗ `{CMD_PREFIX}purge <{to_small_caps('count')}>` ─────▶ 🧹 {to_small_caps('Purge Messages')}
┊
╰━━━- 🛡️ *{to_small_caps('Silent Soft-Delete Engine')}* 🛡️ 〕━━━╯"""
            },
            "utility": {
                "title": f"🌀 {to_small_caps('Utility · Shinobi')}",
                "caption": f"""╭━━━- 🌀 RexxyTGBot · 𝐔ᴛɪʟɪᴛʏ 🌀 〕━━━╮
┊
┊  📸 ﹝ *{to_small_caps('Photo · Jutsu')}* ﹞ ☁️
┊   ┣ `{CMD_PREFIX}savephoto` ──▶ 💾 {to_small_caps('Save Group Photo')}
┊   ┣ `{CMD_PREFIX}startphoto` ─▶ ▶️ {to_small_caps('Start Photo Loop')}
┊   ┣ `{CMD_PREFIX}stopphoto` ──▶ ⏹ {to_small_caps('Stop Photo Loop')}
┊   ┗ `{CMD_PREFIX}clearphotos` ─▶ 🗑️ {to_small_caps('Clear Photos')}
┊
┊  📊 ﹝ *{to_small_caps('Status · Sensor')}* ﹞ 🌸
┊   ┣ `{CMD_PREFIX}status` ──────▶ 🖥️ {to_small_caps('Bot Status')}
┊   ┣ `{CMD_PREFIX}ping` ────────▶ 📡 {to_small_caps('Latency Measurement')}
┊   ┗ `{CMD_PREFIX}myid` ────────▶ 🆔 {to_small_caps('Your Telegram ID')}
┊
╰━━━- 🌀 *{to_small_caps('All Utility Commands')}* 🌀 〕━━━╯"""
            },
            "fun": {
                "title": f"🎲 {to_small_caps('Fun Realm')}",
                "caption": f"""╭━━━- 🎲 RexxyTGBot · 𝐅ᴜɴ 𝐑ᴇᴀʟᴍ 🎲 〕━━━╮
┊
┊  🌸 ﹝ *{to_small_caps('Fun · Jutsu')}* ﹞ 💖
┊   ┣ `{CMD_PREFIX}animequote` ──▶ 📜 {to_small_caps('Inspiring Anime Quote')}
┊   ┣ `{CMD_PREFIX}8ball <{to_small_caps('q')}>` ────▶ 🔮 {to_small_caps('Magic 8-Ball Oracle')}
┊   ┣ `{CMD_PREFIX}coinflip` ─────▶ 🪙 {to_small_caps('Flip A Coin')}
┊   ┣ `{CMD_PREFIX}dice` ─────────▶ 🎲 {to_small_caps('Roll A Die')}
┊   ┣ `{CMD_PREFIX}truth` ────────▶ ❓ {to_small_caps('Truth Prompt')}
┊   ┗ `{CMD_PREFIX}dare` ─────────▶ 🔥 {to_small_caps('Dare Challenge')}
┊
╰━━━- ✨ *{to_small_caps('Powered By')} RexxyTGBot ✨* 💖"""
            }
        }

    def get_menu(self, key):
        menu = self.menus.get(key, self.menus["main"]).copy()
        custom_media = bot_config.get(f"media_{key}")
        custom_type = bot_config.get(f"media_{key}_type")
        if custom_media and custom_type:
            menu["video"] = custom_media
            menu["type"] = custom_type
        return menu

menu_config = MenuConfig()

# ==================== MENU KEYBOARDS ====================

def get_main_keyboard():
    """Interactive inline keyboard for main menu."""
    keyboard = [
        [
            InlineKeyboardButton(f"🗡️ {to_small_caps('Attack Modes')}", callback_data="menu_attack"),
            InlineKeyboardButton(f"👑 {to_small_caps('God NC Realm')}", callback_data="menu_godnc"),
        ],
        [
            InlineKeyboardButton(f"🔤 {to_small_caps('Font NC Realm')}", callback_data="menu_fontnc"),
            InlineKeyboardButton(f"🤖 {to_small_caps('AI Studio')}", callback_data="menu_ai"),
        ],
        [
            InlineKeyboardButton(f"🎵 {to_small_caps('Music Studio')}", callback_data="menu_music"),
            InlineKeyboardButton(f"🔇 {to_small_caps('Mute & Mod')}", callback_data="menu_mute"),
        ],
        [
            InlineKeyboardButton(f"⚙️ {to_small_caps('Settings')}", callback_data="menu_settings"),
            InlineKeyboardButton(f"🛑 {to_small_caps('Stop Cmds')}", callback_data="menu_stop"),
        ],
        [
            InlineKeyboardButton(f"👑 {to_small_caps('Admin Ctrl')}", callback_data="menu_admin"),
            InlineKeyboardButton(f"🌀 {to_small_caps('Utility Tools')}", callback_data="menu_utility"),
        ],
        [
            InlineKeyboardButton(f"🎲 {to_small_caps('Fun Realm')}", callback_data="menu_fun"),
            InlineKeyboardButton(f"📊 {to_small_caps('System Status')}", callback_data="status"),
        ],
        [
            InlineKeyboardButton(f"📜 {to_small_caps('Full Manual')}", callback_data="help_full"),
            InlineKeyboardButton(f"❌ {to_small_caps('Close Menu')}", callback_data="close_menu"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    """Back button keyboard for submenus."""
    keyboard = [
        [
            InlineKeyboardButton(f"⬅️ {to_small_caps('Main Menu')}", callback_data="menu_main"),
            InlineKeyboardButton(f"📊 {to_small_caps('Status')}", callback_data="status"),
        ],
        [
            InlineKeyboardButton(f"❌ {to_small_caps('Close Menu')}", callback_data="close_menu"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== NC TEMPLATES ====================

NC_TEMPLATES = {
    "nc1": "{base} {emo} 匚卄ㄩ卩 ᥅ꪖꪀᦔﺃᛕꫀ ᥇ꪖᥴᥴ𝙃ꫀ 𒈙⸻🩵𒈙⸻❤️𒈙⸻🩷𒈙⸻🧡𒈙⸻💛𒈙⸻💚𒈙⸻💙𒈙⸻💜𒈙⸻🖤𒈙⸻🩶𒈙⸻🤍𒈙⸻  {heart}",
    "nc2": " {base} {emo} 𝐂𝐇𝐔𝐃𝐀I 𝐊𝐇𝐀 𝐑𝐀𝐍𝐃I 🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤🤍🖤",
    "nc3": "{emo}{base}⁀➷𝐓eʀʏ 𝐌ᴀᴀ 𝐊o 𝐂ʜᴜᴅɴe 𝐊ᴀ 𝐓ɪᴍe 𝐇6ɢʏᴀ⁀➷{time} {emo}",
    "nc4": "{base} 𓂃{pattern}"
}

GODNC_BIG_TEXTS = [
    "{target} 🐳 Wʜꫝʟᴇ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐳" * 65,
    "{target} 🐬 Dᴏʟᴘʜɪɴ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐬" * 65,
    "{target} 🦄 Uɴɪᴄᴏʀɴ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦄" * 65,
    "{target} 🦎 Lɪᴢꫝʀᴅ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦎" * 65,
    "{target} 🐉 Dʀꫝɢᴏɴ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐉" * 65,
    "{target} 🐼 Pꫝɴᴅꫝ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐼" * 65,
    "{target} 🐒 Mᴏɴᴋᴇʏ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐒" * 65,
    "{target} 🐍 Sɴꫝᴋᴇ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐍" * 65,
    "{target} 🐙 Oᴄᴛᴏᴘꪊs ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐙" * 65,
    "{target} 🦩 Fʟꫝᴍɪɴɢᴏ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦩" * 65,
    "{target} 🦇 ʙꫝᴛ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦇" * 65,
    "{target} 🦔 Pᴏʀᴄꪊᴘɪɴᴇ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦔" * 65,
    "{target} 🦜 Pꫝʀʀᴏᴛ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦜" * 65,
    "{target} 🪼 Jᴇʟʟʏғɪsʜ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🪼" * 65,
    "{target} 🐯 Tɪɢᴇʀ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐯" * 65,
    "{target} 🦁 Lɪᴏɴ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦁" * 65,
    "{target} 🐊 Cʀᴏᴄᴏᴅɪʟᴇ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐊" * 65,
    "{target} 🦒 Gɪʀꫝғғᴇ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦒" * 65,
    "{target} 🐘 Eʟᴇᴘʜꫝɴᴛ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐘" * 65,
    "{target} 🦊 Fᴏx ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦊" * 65,
    "{target} 🐸 Fʀᴏɢ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐸" * 65,
    "{target} 🦀 Cʀꫝʙ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦀" * 65,
    "{target} 🐢 Tᴜʀᴛʟᴇ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐢" * 65,
    "{target} 🦓 Zᴇʙʀꫝ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦓" * 65,
    "{target} 🦏 Rʜɪɴᴏ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦏" * 65,
    "{target} 🐙 Oᴄᴛᴏᴘᴜs ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐙" * 65,
    "{target} 🦃 Tᴜʀᴋᴇʏ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦃" * 65,
    "{target} 🦘 Kᴀɴɢᴀʀᴏᴏ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦘" * 65,
    "{target} 🐝 Bᴇᴇ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐝" * 65,
    "{target} 🦋 Bᴜᴛᴛᴇʀғʟʏ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🦋" * 65,
    "{target} 🐗 Wɪʟᴅ Bᴏᴀʀ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐗" * 65,
    "{target} 🐿️ Sǫᴜɪʀʀᴇʟ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐿️" * 65,
    "{target} 🐠 Fɪsʜ ᴄʜᴏᴅᴇɢꫝ 👀 " + "🐠" * 65,
    "{target} 🏆 GOD IS BACK 🔥 " + "🏆🔥" * 25,
    "{target} 💎 DIAMOND LORD 🔱 " + "💎🔱" * 25,
    "{target} ⚡ THUNDER KING 🌊 " + "⚡🌊" * 25,
    "{target} 🔱 PURPLE STORM 💜 " + "🔱💜" * 25,
    "{target} 🔥 BLAZE MASTER 💫 " + "🔥💫" * 25,
    "{target} 🌟 STAR EMPEROR ⭐ " + "🌟⭐" * 25,
    "{target} 🔱 TRIPLE POWER 💥 " + "🔱🔥💥" * 20,
    "{target} 🏆 CHAMPION ⚡ " + "🏆⚡" * 25,
    "{target} 💥 EXPLOSION STORM 💥 " + "💥" * 50,
    "{target} 🔱 ELECTRIC GOD 🔱 " + "🔱" * 50
]

try:
    import psutil
except ImportError:
    psutil = None

CHAT_ID =  8776247365

THREAD_POOL = ThreadPoolExecutor(max_workers=500)
MAX_CONCURRENT_TASKS = 1000
CURRENT_DELAY = 0.0

# ── Restart state (module-level so cmd_restart can access them) ──
RESTART_REQUESTED: bool = False
RESTART_EVENT: asyncio.Event = None  # Initialised in run_all_bots()

def get_delay():
    global CURRENT_DELAY
    return CURRENT_DELAY

def set_delay(value):
    global CURRENT_DELAY
    if 0 <= value <= 5:
        CURRENT_DELAY = value
        return True
    return False

BOT_COOLDOWNS = {}
CHAT_COOLDOWNS = {}

async def fast_set_chat_title(bot, chat_id, title: str) -> tuple[bool, float]:
    """Ultra-fast chat title updater using direct aiohttp connection-pooling with seamless PTB fallback.
    Returns: (success: bool, cooldown_or_sleep_secs: float)"""
    global BOT_COOLDOWNS, TOTAL_NC_CHANGES
    token = getattr(bot, "token", None)
    bot_id = None
    if token and ":" in token:
        try:
            bot_id = int(token.split(":")[0])
        except Exception:
            pass

    now = time.time()
    if bot_id and BOT_COOLDOWNS.get(bot_id, 0) > now:
        return False, BOT_COOLDOWNS[bot_id] - now

    safe_title = title[:128]

    # Direct aiohttp call: eliminates PTB object construction & wrapper latency
    if token:
        try:
            session = await get_http_session()
            url = f"https://api.telegram.org/bot{token}/setChatTitle"
            payload = {"chat_id": chat_id, "title": safe_title}
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=3.5)) as resp:
                data = await resp.json(content_type=None)
                if data.get("ok"):
                    TOTAL_NC_CHANGES += 1
                    return True, 0.0

                err_code = data.get("error_code", resp.status)
                if err_code == 429:
                    retry_after = float(data.get("parameters", {}).get("retry_after", 1.0)) + 0.05
                    if bot_id:
                        BOT_COOLDOWNS[bot_id] = time.time() + retry_after
                    return False, retry_after
                elif err_code == 400:
                    # Bad Request (e.g. title not modified or same title) -> no cooldown needed
                    return False, 0.0
                else:
                    return False, 0.02
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        except Exception as e:
            logger.debug(f"fast_set_chat_title aiohttp error: {e}")

    # Fallback to PTB set_chat_title
    try:
        await bot.set_chat_title(chat_id, safe_title)
        TOTAL_NC_CHANGES += 1
        return True, 0.0
    except telegram.error.RetryAfter as e:
        retry_secs = float(e.retry_after) + 0.05
        if bot_id:
            BOT_COOLDOWNS[bot_id] = time.time() + retry_secs
        return False, retry_secs
    except telegram.error.BadRequest:
        return False, 0.0
    except Exception as e:
        logger.debug(f"Failed set_chat_title for bot {bot_id} in {chat_id}: {e}")
        return False, 0.05

async def safe_set_chat_title(bot, chat_id, title):
    return await fast_set_chat_title(bot, chat_id, title)

NC_EMOJIS = ["🤡", "🥸", "😶‍🌫️", "🫠", "🥴", "🤑", "😈", "👿", "😵‍💫", "🤧", "🥲",
             "😬", "🫡", "🧑‍💻", "🤪", "😎", "🤓", "🧐", "🤯", "🥳", "😏", "😒", "😞", "😔", "😋"]
NC_HEARTS = ["🩷", "♥️", "❤️‍🩹", "💝", "🤍", "🩶", "🖤", "🤎", "💜", "💙", "🩵",
             "💚", "💛", "🧡", "❤️", "💗", "💔", "❣️", "💕", "💞", "💓", "💖", "💘", "💌"]
TIMENC_EMOJIS = ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"]
NC_PATTERNS = ["🎀", "🌸", "🌺", "🌷", "🌹", "💐", "✨", "⭐", "🌟",
               "💫", "⚡", "🔥", "💎", "🎪", "🎨", "🖌️", "🎭", "🎯", "🏆", "🎲"]

RAID_TEXTS = [
    "×~🌷GAY🌷×~", "~×🌼BITCH🌼×~", "~×🌻LESBIAN🌻×~", "~×🌺CHAPRI🌺×~",
    "~×🌹TMKC🌹×~", "~×🏵️TMR🏵×~️", "~×🪷TMKB🪷×~", "~×💮CHUS💮×~",
    "~×🌸HAKLE🌸×~", "~×🌷GAREEB🌷×~", "~×🌼RANDY🌼×~", "~×🌻POOR🌻×~",
    "~×🌺TATTI🌺×~", "~×🌹CHOR🌹×~", "~×🏵️CHAMAR🏵️×~", "~×🪷SPERM COLLECTOR🪷×~",
    "~×💮CHUTI LULLI💮×~", "~×🌸KALWA🌸×~", "~×🌷CHUD🌷×~", "~×🌼CHUTKHOR🌼×~",
    "~×🌻BAUNA🌻×~", "~×🌺MOTE🌺×~", "~×🌹GHIN ARHA TUJHSE🌹×~", "~×🏵️CHI POOR🏵×~️",
    "~🪷PANTY CHOR🪷~", "~×💮LAND CHUS💮×~", "~×🌸MUH MAI LEGA🌸×~", "~×🌷GAND MARE 🌷×~",
    "~×🌼MOCHI WALE 🌼×~", "~×🌻GANDMARE 🌻×~", "~×🌺KIDDE 🌺×~", "~×🌹LAMO 🌹×~",
    "~×🏵️BIHARI 🏵×~️", "~×🪷MULLE 🪷×~", "~×💮NAJAYESH LADKE 💮×~", "~×🌸GULAM 🌸×~",
    "~×🌷CHAMCHA🌷×~", "~×🌼EWW 🌼×~", "~×🌻CHOTE TATTE 🌻×~", "~×🌺SEX WORKER 🌺×~",
    "~×🌹CHINNAR MA KE LADKE 🌹×~"
]

CSWORD_TEXTS = [
    "TMKC", "TMKB", "TBKC", "TMR", "HAKLE", "CHUD NA", "LAND LE", "CHAL MA CHUDA",
    "GANDA CHUDEGA", "TERA BAAP FARMER", "SPEED BADHA", "GAREEB", "PREGENT HAI?",
    "CHI YAR CHUDA", "JNL", "KUTIYA", "CHUDDKAR", "GULAM", "BHAG YEHA SE",
    "BAAP BANA SAM KO", "TU MERA BETA", "OYE RANDY", "MAR GYA"
]

NCBRA_TEXTS = [
    "TERI बहन KI BRA 👙", "TERI  माँ KI BRA 👙", "TERI दादी KI BRA 👙", "TERI चाची KI BRA 👙",
    "TERE पिता KA BRA👙", "TERE भाई' KA BRA 👙", "TERE दादा KA BRA 👙", "TERE चाचा KA BRA 👙",
    "TERE मोसी KA BRA 👙", "TERE मोसा KA BRA 👙", "TERI पत्नी KI BRA 👙", "TERI सास KA BRA 👙",
    "TERE ससुर KA BRA 👙", "TERE खाला KA BRA 👙", "TERE सीता MA KA BRA 👙", "TERE फातिमा KA BRA 👙",
    "TERE अल्लाह KA BRA 👙", "TERE शिव KA BRA 👙"
]

SWIPE_TEXTS = [
    "{target} TMKC", "{target} TMKL", "{target} TERI MA RANDY",
    "{target} TERI MA NANGI", "{target} BHAG MAT BHANGI",
    "{target} RANDY MA KI CHUT", "{target} CHUDWANE AYE",
    "{target} BHAGODEE", "{target} GANDI NAALI KE KEEDE",
    "{target} TMKB", "{target} TERI MA KI CHUT ME HATHI",
    "{target} TERI MA KA BHOSDA", "{target} RANDYA",
    "{target} CHAPRI MA KA LADKA", "{target} TERI MA CHUDGYI",
    "{target} TERI MA KA REAPE"
]

# ==================== SPAM STATE ====================

group_tasks = {}          # {chat_id: [tasks]}
spam_tasks = {}           # {chat_id: [tasks]}
swipe_tasks = {}          # {chat_id: {target: [tasks]}}
mexxync_tasks = {}        # {chat_id: [tasks]}
photo_tasks = {}          # {chat_id: task}
chat_photos = {}          # {chat_id: [file_ids]}
slide_targets = set()     # {user_id}
slidespam_targets = set()  # {user_id}

# ==================== SPAM LOOP FUNCTIONS ====================

async def spam_loop(bot, chat_id, text, delay=0.5):
    """Generic spam loop"""
    while True:
        try:
            await bot.send_message(chat_id, text)
            await asyncio.sleep(delay)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 1.0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(1.0)

async def raidspam_loop(bot, chat_id, name):
    """RAID SPAM with multipliers"""
    i = 0
    multipliers = [10, 20, 25]
    emojis = ["🐉", "🐲", "🔥"]
    patterns = [
        "𝐴𝐴𝑀 𝑇𝐻𝑂𝐷𝑈 𝐿𝐴𝑇𝐴𝐾 𝐿𝐴𝑇𝐴𝐾 𝐾𝐸 {name}  𝐾𝐼           𝑀𝐴𝐴 𝐾𝑂 𝐶𝐻𝑂𝐷𝑈 𝑃𝐴𝑇𝐴𝐾 𝑃𝐴𝑇𝐴𝐾 𝐾𝐸 {emo}__,____/𒀸",
        "𝑂𝑌𝐸 {name} 𝑇𝐸𝑅𝐼 𝑀𝐴𝐴 𝐾𝐼 𝐶𝐻𝑈𝑇 𝑀𝐸 𝑊𝐻𝐸𝐸𝐿 𝐶𝐻𝐴𝐼𝑅 {emo}⚔️",
        "𝑇𝐸𝑅𝐼 𝐵𝐸𝐻𝐸𝑁 𝐾𝐸 𝐵𝑅𝐴 𝑀𝐸 𝐶𝐻𝑈𝐻𝐴 𝐶𝐻𝑂𝐷𝐷 𝐷𝑈𝑁𝐺𝐴 {name} {emo}💀",
        "𝗠𝗔𝗫𝗫𝗬 𝐵𝑂𝑇 𝐾𝐸 𝐴𝐺𝐸 𝑇𝐸𝑅𝐼 𝑀𝐴𝐴 𝑁𝐴𝑁𝐺𝐼 {name} {emo}🔥"
    ]
    while True:
        try:
            mult = multipliers[i % len(multipliers)]
            emo = emojis[i % len(emojis)]
            pattern = patterns[i % len(patterns)]
            base_text = pattern.format(name=name, emo=emo)
            spam_text = (base_text + "\n") * mult
            await bot.send_message(chat_id, spam_text)
            i += 1
            await asyncio.sleep(0.5)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 1.0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.5)

async def swipe_loop(bot, chat_id, target):
    """Swipe attack loop"""
    while True:
        try:
            text = random.choice(SWIPE_TEXTS).format(target=target)
            await bot.send_message(chat_id, text)
            await asyncio.sleep(0.5)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 1.0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.5)

def _gen_nc5_title(target_name, idx):
    text = CSWORD_TEXTS[idx % len(CSWORD_TEXTS)]
    return f"{target_name} {text}"

def _gen_nc6_title(target_name, idx):
    text = NCBRA_TEXTS[idx % len(NCBRA_TEXTS)]
    return f"{target_name} {text}"

MEXXY_EMOJIS = [
    "×🌼×", "×🌻×", "×🪻×", "×🏵️×", "×💮×", "×🌸×", "×🪷×", "×🌷×",
    "×🌺×", "×🥀×", "×🌹×", "×💐×", "×💋×", "×❤️‍🔥×", "×❤️‍🩹×", "×❣️×"
]

def _gen_mexxync_title(target_name, idx):
    emo = MEXXY_EMOJIS[idx % len(MEXXY_EMOJIS)]
    return f"{emo} {target_name} {emo}"

def _gen_raidnc_title(target_name, idx):
    emo = NC_HEARTS[idx % len(NC_HEARTS)]
    return f"{target_name} ᵗᵉʳⁱ ᵐᵃᵃᴄʜɪɴꫝʟ ({emo})"

async def nc5_loop(bots_arg, chat_id, base_text, stop_event=None):
    if stop_event is None: stop_event = asyncio.Event()
    await _generic_nc_stream(bots_arg, chat_id, base_text, stop_event, _gen_nc5_title)

async def nc6_loop(bots_arg, chat_id, base_text, stop_event=None):
    if stop_event is None: stop_event = asyncio.Event()
    await _generic_nc_stream(bots_arg, chat_id, base_text, stop_event, _gen_nc6_title)

async def mexxync_loop(bots_arg, chat_id, base_text, delay=0.001, stop_event=None):
    if stop_event is None: stop_event = asyncio.Event()
    await _generic_nc_stream(bots_arg, chat_id, base_text, stop_event, _gen_mexxync_title)

async def raidnc_loop(bots_arg, chat_id, prefix, stop_event=None):
    if stop_event is None: stop_event = asyncio.Event()
    await _generic_nc_stream(bots_arg, chat_id, prefix, stop_event, _gen_raidnc_title)

cached_photo_bytes: dict[str, bytes] = {}

async def photo_loop(bot, chat_id, photos):
    """Photo changer loop with byte caching & proper buffer cleanup"""
    while True:
        try:
            if chat_id not in chat_photos or not chat_photos[chat_id]:
                await asyncio.sleep(5.0)
                continue

            photos_list = chat_photos[chat_id]
            file_id = random.choice(photos_list)

            if file_id in cached_photo_bytes:
                img_data = cached_photo_bytes[file_id]
            else:
                photo_file = await bot.get_file(file_id)
                buf = io.BytesIO()
                await photo_file.download_to_memory(buf)
                img_data = buf.getvalue()
                buf.close()
                cached_photo_bytes[file_id] = img_data

            buf = io.BytesIO(img_data)
            try:
                await bot.set_chat_photo(chat_id=chat_id, photo=buf)
            finally:
                buf.close()

            await asyncio.sleep(0.5)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 1.0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(5.0)

# ==================== STREAM FUNCTIONS ====================

async def _generic_nc_stream(bots_arg, chat_id, target_name, stop_event, generator_func):
    bot_list = bots_arg if isinstance(bots_arg, list) else [bots_arg]
    if not bot_list:
        return

    idx_container = [0]

    async def worker(bot):
        token = getattr(bot, "token", "")
        bot_id = int(token.split(":")[0]) if token and ":" in token else None

        while not stop_event.is_set():
            now = time.time()
            if bot_id:
                bot_cd = BOT_COOLDOWNS.get(bot_id, 0)
                if bot_cd > now:
                    await asyncio.sleep(min(bot_cd - now, 0.05))
                    continue

            idx = idx_container[0]
            idx_container[0] += 1
            title = generator_func(target_name, idx)

            try:
                success, cd = await fast_set_chat_title(bot, chat_id, title)
                if cd > 0:
                    await asyncio.sleep(min(cd, 0.05) if bot_id and BOT_COOLDOWNS.get(bot_id, 0) > time.time() else 0.001)
                else:
                    delay = CURRENT_DELAY if CURRENT_DELAY > 0 else 0
                    if delay > 0:
                        await asyncio.sleep(delay)
                    else:
                        await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.01)

    # 4 workers per bot for high throughput pipelining
    tasks = [asyncio.create_task(worker(bot)) for bot in bot_list for _ in range(4)]

    try:
        await stop_event.wait()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)



def _gen_godnc_title(target_name, idx):
    pattern = GODNC_BIG_TEXTS[idx % len(GODNC_BIG_TEXTS)]
    return pattern.format(target=target_name)[:128]

# ── MAX-SPEED PER-BOT GOD NC ENGINE ──────────────────────────────────────────
async def _godnc_bot_worker(bot, chat_id, titles, idx_container, stop_event):
    """Each bot worker grabs the next global title index and updates title - full speed round robin across all texts."""
    n = len(titles)
    token = getattr(bot, "token", "")
    bot_id = int(token.split(":")[0]) if token and ":" in token else None

    while not stop_event.is_set():
        now = time.time()
        if bot_id:
            bot_cd = BOT_COOLDOWNS.get(bot_id, 0)
            if bot_cd > now:
                await asyncio.sleep(min(bot_cd - now, 0.05))
                continue

        idx = idx_container[0]
        idx_container[0] += 1
        title = titles[idx % n]

        try:
            success, cd = await fast_set_chat_title(bot, chat_id, title)
            if cd > 0:
                await asyncio.sleep(min(cd, 0.05) if bot_id and BOT_COOLDOWNS.get(bot_id, 0) > time.time() else 0.001)
            else:
                delay = CURRENT_DELAY if CURRENT_DELAY > 0 else 0
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.01)

async def godnc_stream(bots_arg, chat_id, target_name, stop_event=None, bot_id=None):
    """Parallel worker stream using all God NC texts sequentially across all bots at full speed."""
    if stop_event is None:
        stop_event = asyncio.Event()
    bot_list = bots_arg if isinstance(bots_arg, list) else [bots_arg]
    if not bot_list:
        return
    titles = [p.format(target=target_name)[:128] for p in GODNC_BIG_TEXTS]
    idx_container = [0]
    tasks = [
        asyncio.create_task(_godnc_bot_worker(b, chat_id, titles, idx_container, stop_event))
        for b in bot_list for _ in range(4)
    ]
    try:
        await stop_event.wait()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

# ── MAX-SPEED PER-BOT CHANNEL NC ENGINE ──────────────────────────────────────
async def _channelnc_bot_worker(bot, chat_id, titles, idx_container, stop_event):
    """Each bot runs its own tight loop for Channel NC matching God NC speed."""
    await _godnc_bot_worker(bot, chat_id, titles, idx_container, stop_event)

async def channelnc_godspeed_stream(bots_arg, chat_id, target_name, stop_event=None, bot_id=None):
    """High-speed Channel NC stream using all God NC texts sequentially at full speed."""
    if stop_event is None:
        stop_event = asyncio.Event()
    bot_list = bots_arg if isinstance(bots_arg, list) else [bots_arg]
    if not bot_list:
        return
    
    titles = [p.format(target=target_name)[:128] for p in GODNC_BIG_TEXTS]
    idx_container = [0]
    tasks = [
        asyncio.create_task(_channelnc_bot_worker(b, chat_id, titles, idx_container, stop_event))
        for b in bot_list for _ in range(4)
    ]
    try:
        await stop_event.wait()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

def _gen_nc1_title(target_name, idx):
    emo = random.choice(NC_EMOJIS)
    heart = random.choice(NC_HEARTS)
    return NC_TEMPLATES["nc1"].format(base=target_name, emo=emo, heart=heart)

def _gen_nc2_title(target_name, idx):
    emo = random.choice(NC_EMOJIS)
    return NC_TEMPLATES["nc2"].format(base=target_name, emo=emo)

def _gen_nc3_title(target_name, idx):
    emo = random.choice(NC_EMOJIS)
    current_time = datetime.now().strftime("%I:%M %p")
    return NC_TEMPLATES["nc3"].format(base=target_name, emo=emo, time=current_time)

def _gen_nc4_title(target_name, idx):
    pattern = NC_PATTERNS[idx % len(NC_PATTERNS)]
    return f"{target_name} 𓂃{pattern}"

def _gen_fontnc_title(target_name, idx):
    sc_name = to_small_caps(target_name)
    mode = idx % 4
    if mode == 0:
        emo = random.choice(NC_EMOJIS)
        heart = random.choice(NC_HEARTS)
        return f"{sc_name} {emo} {to_small_caps('匚卄ㄩ卩 ᥅ꪖꪀᦔﺃᛕꫀ ᥇ꪖᥴᥴ𝙃ꫀ')} {heart}"
    elif mode == 1:
        emo = random.choice(NC_EMOJIS)
        return f"{sc_name} {emo} {to_small_caps('ᴄʜᴜᴅᴀɪ ᴋʜᴀ ʀᴀɴᴅɪ')} 🖤🤍"
    elif mode == 2:
        emo = random.choice(NC_EMOJIS)
        current_time = datetime.now().strftime("%I:%M %p")
        return f"{emo}{sc_name} ⁀➷ {to_small_caps('ᴛᴇʀɪ ᴍᴀᴀ ᴋᴏ ᴄʜᴜᴅɴᴇ ᴋᴀ ᴛɪᴍᴇ ʜᴏɢʏᴀ')} {current_time}"
    else:
        pattern = NC_PATTERNS[idx % len(NC_PATTERNS)]
        return f"{sc_name} 𓂃{pattern}"

async def ultra_nc1_stream(bot, chat_id, target_name, stop_event, bot_id=None):
    await _generic_nc_stream(bot, chat_id, target_name, stop_event, _gen_nc1_title)

async def ultra_nc2_stream(bot, chat_id, target_name, stop_event, bot_id=None):
    await _generic_nc_stream(bot, chat_id, target_name, stop_event, _gen_nc2_title)

async def ultra_nc3_stream(bot, chat_id, target_name, stop_event, bot_id=None):
    await _generic_nc_stream(bot, chat_id, target_name, stop_event, _gen_nc3_title)

async def _nc4_fast_worker(bot, chat_id, titles, idx_container, stop_event):
    """Ultra-fast NC4 worker: pre-rendered titles, 4 workers per bot, near-zero yield."""
    n = len(titles)
    token = getattr(bot, "token", "")
    bot_id = int(token.split(":")[0]) if token and ":" in token else None

    while not stop_event.is_set():
        now = time.time()
        if bot_id:
            bot_cd = BOT_COOLDOWNS.get(bot_id, 0)
            if bot_cd > now:
                await asyncio.sleep(min(bot_cd - now, 0.05))
                continue

        idx = idx_container[0]
        idx_container[0] += 1
        title = titles[idx % n]

        try:
            success, cd = await fast_set_chat_title(bot, chat_id, title)
            if cd > 0:
                await asyncio.sleep(min(cd, 0.05) if bot_id and BOT_COOLDOWNS.get(bot_id, 0) > time.time() else 0.001)
            else:
                delay = CURRENT_DELAY if CURRENT_DELAY > 0 else 0
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.01)

async def ultra_nc4_stream(bots_arg, chat_id, target_name, stop_event, bot_id=None):
    """Ultra-fast NC4: 4 workers per bot, pre-rendered pattern titles, near-zero delay."""
    if stop_event is None:
        stop_event = asyncio.Event()
    bot_list = bots_arg if isinstance(bots_arg, list) else [bots_arg]
    if not bot_list:
        return
    # Pre-render all pattern titles
    titles = [f"{target_name} 𓂃{p}"[:128] for p in NC_PATTERNS]
    idx_container = [0]
    # 4 workers per bot for maximum speed
    tasks = [
        asyncio.create_task(_nc4_fast_worker(b, chat_id, titles, idx_container, stop_event))
        for b in bot_list for _ in range(4)
    ]
    try:
        await stop_event.wait()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

async def fontnc_cycle_stream(bot, chat_id, target_name, stop_event, bot_id=None):
    await _generic_nc_stream(bot, chat_id, target_name, stop_event, _gen_fontnc_title)


# ==================== SPAMEMO STREAM ====================

SPAMEMO_EMOJIS = NC_HEARTS
DEFAULT_SPAMEMO_THREADS = 20

def get_spamemo_message(target):
    upper_target = target.upper()
    target_tag = f"「 {upper_target} 」"
    emoji = SPAMEMO_EMOJIS[random.randint(0, len(SPAMEMO_EMOJIS) - 1)]
    line = f"{target_tag} 𝑻𝑹𝒀 𝑴𝑨𝑲𝑨 𝑲𝑨𝑳𝑨 𝑲𝑨𝑺𝑯𝑴𝑰𝑹𝑰 🅱︎🅾︎🆂︎🅳︎🅰︎ 🅿︎🅷︎🅰︎🆃︎ 𝑮𝒀𝑨 🧸🎐({emoji})𒀸"
    return "\n\n".join([line] * 10)

async def spamemo_stream(bot, chat_id, target_text, stream_id, stop_event, bot_id):
    global TOTAL_MESSAGES_SENT
    while not stop_event.is_set():
        try:
            message = get_spamemo_message(target_text)
            await bot.send_message(chat_id, message)
            TOTAL_MESSAGES_SENT += 1
            delay = CURRENT_DELAY if CURRENT_DELAY > 0 else 0.05
            await asyncio.sleep(delay)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(0.5)


async def spamemo_multi(bot, chat_id, target_text, num_streams, stop_event, bot_id):
    streams = []
    for i in range(num_streams):
        stream = asyncio.create_task(spamemo_stream(bot, chat_id, target_text, i, stop_event, bot_id))
        streams.append(stream)
    try:
        await stop_event.wait()
    finally:
        for s in streams:
            s.cancel()


# ==================== ATTACK CONTROLLER ====================

class AttackController:
    def __init__(self):
        self.stop_events = {}
        self.active_tasks = {}
        self.nc_threads = 20
        self.spamemo_threads = DEFAULT_SPAMEMO_THREADS
        self.slide_threads = 10

    def set_spamemo_threads(self, threads):
        self.spamemo_threads = max(20, min(50, threads))
        return self.spamemo_threads

    def stop_spamemo(self, chat_id):
        return self.stop_attack(chat_id, "spamemo")

    def get_stop_event(self, chat_id, attack_type):
        key = f"{chat_id}_{attack_type}"
        if key not in self.stop_events:
            self.stop_events[key] = asyncio.Event()
        return self.stop_events[key]

    def stop_attack(self, chat_id, attack_type):
        key = f"{chat_id}_{attack_type}"
        if key in self.stop_events:
            self.stop_events[key].set()
            self.stop_events[key] = asyncio.Event()
            return True
        return False

    def stop_all(self, chat_id=None):
        for key in list(self.stop_events.keys()):
            if chat_id is None or key.startswith(str(chat_id)):
                self.stop_events[key].set()
                self.stop_events[key] = asyncio.Event()
        return True

controller = AttackController()
bots = []
apps = []
active_attacks = {}
MAIN_BOT_ID = None

# ==================== FAST RESTART SYSTEM ====================
# Set this event to trigger an instant in-process restart of all bots
RESTART_EVENT = asyncio.Event()
RESTART_REQUESTED = False

# ==================== ATTACK COMMAND HANDLERS ====================

@only_admin
async def cmd_spamemo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}spamemo <{to_small_caps('target')}>`",
            parse_mode="Markdown"
        )
        return

    target_text = " ".join(context.args)
    chat_id = update.message.chat_id

    controller.stop_attack(chat_id, "spamemo")
    key = f"{chat_id}_spamemo"
    if key in active_attacks:
        for task in active_attacks[key]:
            task.cancel()
        del active_attacks[key]

    stop_event = controller.get_stop_event(chat_id, "spamemo")
    stop_event.clear()

    num_streams = controller.spamemo_threads

    tasks = []
    for bot in bots:
        task = asyncio.create_task(spamemo_multi(bot, chat_id, target_text, num_streams, stop_event, bot.id))
        tasks.append(task)

    active_attacks[key] = tasks

    msg = (
        f"😈『 *{to_small_caps('EMOJI SPAM ACTIVATED')}* 』😈\n\n"
        f"🎯 *{to_small_caps('Target:')}* `{target_text}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"🧵 *{to_small_caps('Threads per Bot:')}* `{num_streams}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopspam`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_admin
async def cmd_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}spam <{to_small_caps('text')}>`",
            parse_mode="Markdown"
        )
        return

    text = " ".join(context.args)
    chat_id = update.message.chat_id

    if chat_id in spam_tasks:
        for task in spam_tasks[chat_id]:
            task.cancel()

    tasks = []
    for bot in bots:
        task = asyncio.create_task(spam_loop(bot, chat_id, text))
        tasks.append(task)

    spam_tasks[chat_id] = tasks

    msg = (
        f"💥『 *{to_small_caps('SPAM ACTIVATED')}* 』💥\n\n"
        f"📝 *{to_small_caps('Payload:')}* `{text}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopspam`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_admin
async def cmd_raidspam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}raidspam <{to_small_caps('name')}>`",
            parse_mode="Markdown"
        )
        return

    name = " ".join(context.args)
    chat_id = update.message.chat_id

    if chat_id in spam_tasks:
        for task in spam_tasks[chat_id]:
            task.cancel()

    tasks = []
    for bot in bots:
        task = asyncio.create_task(raidspam_loop(bot, chat_id, name))
        tasks.append(task)

    spam_tasks[chat_id] = tasks

    msg = (
        f"🔥『 *{to_small_caps('RAID SPAM ACTIVATED')}* 』🔥\n\n"
        f"🎯 *{to_small_caps('Target:')}* `{name}`\n"
        f"📊 *{to_small_caps('Multipliers:')}* `x10, x20, x25`\n"
        f"🤖 *{to_small_caps('Bots Online:')}* `{len(bots)}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopspam`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_admin
async def cmd_swipe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return

    target = " ".join(context.args) if context.args else "TARGET"
    chat_id = update.message.chat_id

    if chat_id not in swipe_tasks:
        swipe_tasks[chat_id] = {}

    if target in swipe_tasks[chat_id]:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Swipe already active for')}* `{target}`!",
            parse_mode="Markdown"
        )

    tasks = []
    for bot in bots:
        task = asyncio.create_task(swipe_loop(bot, chat_id, target))
        tasks.append(task)

    swipe_tasks[chat_id][target] = tasks

    msg = (
        f"🌪️『 *{to_small_caps('SWIPE ATTACK ACTIVATED')}* 』🌪️\n\n"
        f"🎯 *{to_small_caps('Target:')}* `{target}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopswipe {target}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_admin
async def cmd_stopswipe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id

    if not context.args:
        if chat_id in swipe_tasks:
            for target in list(swipe_tasks[chat_id].keys()):
                for task in swipe_tasks[chat_id][target]:
                    task.cancel()
            del swipe_tasks[chat_id]
            return await update.message.reply_text(
                f"🛑 *{to_small_caps('ALL SWIPES STOPPED')}* 🛑",
                parse_mode="Markdown"
            )
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('No active swipes found.')}*",
            parse_mode="Markdown"
        )

    target = " ".join(context.args)
    if chat_id in swipe_tasks and target in swipe_tasks[chat_id]:
        for task in swipe_tasks[chat_id][target]:
            task.cancel()
        del swipe_tasks[chat_id][target]
        await update.message.reply_text(
            f"🛑 *{to_small_caps('SWIPE STOPPED FOR')}* `{target}`!",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"⚠️ *{to_small_caps('No active swipe for')}* `{target}`.",
            parse_mode="Markdown"
        )

# ==================== NC COMMANDS ====================

async def cmd_nc(update: Update, context: ContextTypes.DEFAULT_TYPE, nc_type: str, stream_func, mode_name: str):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}{nc_type} <{to_small_caps('name')}>`",
            parse_mode="Markdown"
        )

    base = " ".join(context.args)
    chat_id = update.message.chat_id

    controller.stop_attack(chat_id, nc_type)
    key = f"{chat_id}_{nc_type}"
    if key in active_attacks:
        for task in active_attacks[key]:
            task.cancel()
        del active_attacks[key]

    stop_event = controller.get_stop_event(chat_id, nc_type)
    stop_event.clear()

    tasks = []
    task = asyncio.create_task(stream_func(bots, chat_id, base, stop_event, MAIN_BOT_ID))
    tasks.append(task)

    active_attacks[key] = tasks

    msg = (
        f"☣️『 *{to_small_caps(nc_type.upper())} {to_small_caps('ACTIVATED')}* 』☣️\n\n"
        f"📝 *{to_small_caps('Target Name:')}* `{base}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"⚡ *{to_small_caps('Mode:')}* `{mode_name}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopnc`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_nc1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_nc(update, context, "nc1", ultra_nc1_stream, to_small_caps("Raid NC"))

@only_sudo
async def cmd_nc2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_nc(update, context, "nc2", ultra_nc2_stream, to_small_caps("God NC"))

@only_sudo
async def cmd_nc3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_nc(update, context, "nc3", ultra_nc3_stream, to_small_caps("Time NC"))

@only_sudo
async def cmd_nc4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_nc(update, context, "nc4", ultra_nc4_stream, to_small_caps("Ultra Fast Custom NC"))

@only_sudo
async def cmd_nc5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}nc5 <{to_small_caps('text')}>`", parse_mode="Markdown")

    base_text = " ".join(context.args)
    chat_id = update.message.chat_id

    controller.stop_attack(chat_id, "nc5")
    key = f"{chat_id}_nc5"
    if key in active_attacks:
        for task in active_attacks[key]:
            task.cancel()
        del active_attacks[key]

    stop_event = controller.get_stop_event(chat_id, "nc5")
    stop_event.clear()
    task = asyncio.create_task(nc5_loop(bots, chat_id, base_text, stop_event))
    active_attacks[key] = [task]

    msg = (
        f"⚔️『 *{to_small_caps('CSWORD LOOP ACTIVATED')}* 』⚔️\n\n"
        f"📝 *{to_small_caps('Base Text:')}* `{base_text}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopnc`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_nc6(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}nc6 <{to_small_caps('text')}>`", parse_mode="Markdown")

    base_text = " ".join(context.args)
    chat_id = update.message.chat_id

    controller.stop_attack(chat_id, "nc6")
    key = f"{chat_id}_nc6"
    if key in active_attacks:
        for task in active_attacks[key]:
            task.cancel()
        del active_attacks[key]

    stop_event = controller.get_stop_event(chat_id, "nc6")
    stop_event.clear()
    task = asyncio.create_task(nc6_loop(bots, chat_id, base_text, stop_event))
    active_attacks[key] = [task]

    msg = (
        f"👙『 *{to_small_caps('NCBRA LOOP ACTIVATED')}* 』👙\n\n"
        f"📝 *{to_small_caps('Base Text:')}* `{base_text}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopnc`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


@only_admin
async def cmd_raidnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}raidnc <{to_small_caps('name')}>`", parse_mode="Markdown")

    prefix = " ".join(context.args)
    chat_id = update.message.chat_id

    if chat_id in group_tasks:
        for task in group_tasks[chat_id]:
            task.cancel()

    stop_event = asyncio.Event()
    task = asyncio.create_task(raidnc_loop(bots, chat_id, prefix, stop_event))
    group_tasks[chat_id] = [task]

    msg = (
        f"🔥『 *{to_small_caps('RAID NC ACTIVATED')}* 』🔥\n\n"
        f"📝 *{to_small_caps('Prefix:')}* `{prefix}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopnc`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_admin
async def cmd_mexxync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}mexxync <{to_small_caps('name')}>`", parse_mode="Markdown")

    base = " ".join(context.args)
    chat_id = update.message.chat_id

    if chat_id in mexxync_tasks:
        for task in mexxync_tasks[chat_id]:
            task.cancel()

    stop_event = asyncio.Event()
    task = asyncio.create_task(mexxync_loop(bots, chat_id, base, stop_event=stop_event))
    mexxync_tasks[chat_id] = [task]

    msg = (
        f"🐉『 *{to_small_caps('REXXYTGBOT NC ACTIVATED')}* 』🐉\n\n"
        f"📝 *{to_small_caps('Target Name:')}* `{base}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopmexxync`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_admin
async def cmd_mexxyncgodspeed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}mexxyncgodspeed <{to_small_caps('name')}>`", parse_mode="Markdown")

    base = " ".join(context.args)
    chat_id = update.message.chat_id

    if chat_id in mexxync_tasks:
        for task in mexxync_tasks[chat_id]:
            task.cancel()

    stop_event = asyncio.Event()
    task = asyncio.create_task(mexxync_loop(bots, chat_id, base, delay=0.0001, stop_event=stop_event))
    mexxync_tasks[chat_id] = [task]

    msg = (
        f"👑🔥『 *{to_small_caps('REXXYTGBOT NC GOD SPEED ACTIVATED')}* 』🔥👑\n\n"
        f"📝 *{to_small_caps('Target Name:')}* `{base}`\n"
        f"⚡ *{to_small_caps('Speed:')}* `{to_small_caps('Ultra Fast (0.0001s)')}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopmexxync`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_admin
async def cmd_stopmexxync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    if chat_id in mexxync_tasks:
        for task in mexxync_tasks[chat_id]:
            task.cancel()
        del mexxync_tasks[chat_id]
        await update.message.reply_text(f"🛑 *{to_small_caps('REXXYTGBOT NC STOPPED')}*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ *{to_small_caps('No active RexxyTGBot NC')}*", parse_mode="Markdown")



# ==================== GOD NC COMMANDS ====================

@only_sudo
async def cmd_godnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}godnc <{to_small_caps('target name')}>`",
            parse_mode="Markdown"
        )

    base = " ".join(context.args)
    chat_id = update.message.chat_id

    controller.stop_attack(chat_id, "godnc")
    key = f"{chat_id}_godnc"
    if key in active_attacks:
        for task in active_attacks[key]:
            task.cancel()
        del active_attacks[key]

    stop_event = controller.get_stop_event(chat_id, "godnc")
    stop_event.clear()

    # One task that internally fans out to one worker per bot
    task = asyncio.create_task(godnc_stream(bots, chat_id, base, stop_event, MAIN_BOT_ID))
    active_attacks[key] = [task]

    msg = (
        f"👑🔥『 *{to_small_caps('GOD NC ACTIVATED')}* 』🔥👑\n\n"
        f"🎯 *{to_small_caps('Target Name:')}* `{base}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"⚡ *{to_small_caps('Mode:')}* `{to_small_caps('Custom Big Text Stream')}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopgodnc`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_godncgodspeed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_godnc(update, context)

@only_admin
async def cmd_stopgodnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    stopped = controller.stop_attack(chat_id, "godnc")
    key = f"{chat_id}_godnc"
    if key in active_attacks:
        for task in active_attacks[key]:
            task.cancel()
        del active_attacks[key]
        stopped = True

    if stopped:
        await update.message.reply_text(f"🛑 *{to_small_caps('GOD NC STOPPED')}*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ *{to_small_caps('No active God NC')}*", parse_mode="Markdown")

# ==================== FONT NC COMMANDS ====================

@only_sudo
async def cmd_fontnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start Small Caps Font NC loop across all templates"""
    await cmd_nc(update, context, "fontnc", fontnc_cycle_stream, to_small_caps("Small Caps Font NC"))

@only_sudo
async def cmd_fontnc1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sc_args = [to_small_caps(arg) for arg in (context.args or [])]
    context.args = sc_args
    await cmd_nc1(update, context)

@only_sudo
async def cmd_fontnc2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sc_args = [to_small_caps(arg) for arg in (context.args or [])]
    context.args = sc_args
    await cmd_nc2(update, context)

@only_sudo
async def cmd_fontnc3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sc_args = [to_small_caps(arg) for arg in (context.args or [])]
    context.args = sc_args
    await cmd_nc3(update, context)

@only_sudo
async def cmd_fontnc4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sc_args = [to_small_caps(arg) for arg in (context.args or [])]
    context.args = sc_args
    await cmd_nc4(update, context)

# ==================== CHANNEL NC COMMANDS ====================

@only_sudo
async def cmd_channelnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}channelnc <@channel_or_link_or_id> <{to_small_caps('name')}>`\n"
            f"💡 *{to_small_caps('Example:')}* `{CMD_PREFIX}channelnc @mychannel {to_small_caps('My Channel')}`",
            parse_mode="Markdown"
        )

    target_chat_id = None
    channel_name = None
    base_name = ""

    first_arg = context.args[0].strip()
    if len(context.args) >= 2 and (first_arg.startswith("@") or "t.me/" in first_arg or first_arg.startswith("-100") or (first_arg.lstrip("-").isdigit() and len(first_arg) > 5)):
        channel_ref = first_arg
        base_name = " ".join(context.args[1:])
        try:
            if "t.me/" in channel_ref:
                clean_ref = channel_ref.split("t.me/")[-1].strip("/")
                if not clean_ref.startswith("@") and not clean_ref.startswith("+"):
                    clean_ref = f"@{clean_ref}"
                channel_ref = clean_ref
            
            if channel_ref.lstrip("-").isdigit():
                target_chat_id = int(channel_ref)
                chat_info = await context.bot.get_chat(target_chat_id)
                channel_name = getattr(chat_info, "title", None) or str(target_chat_id)
            else:
                chat_info = await context.bot.get_chat(channel_ref)
                target_chat_id = chat_info.id
                channel_name = getattr(chat_info, "title", None) or channel_ref
        except Exception as e:
            if first_arg.lstrip("-").isdigit():
                target_chat_id = int(first_arg)
                channel_name = first_arg
            elif first_arg.startswith("@"):
                target_chat_id = first_arg
                channel_name = first_arg
            else:
                return await update.message.reply_text(
                    f"❌ *{to_small_caps('Failed to resolve channel:')}* `{first_arg}`\n`{e}`",
                    parse_mode="Markdown"
                )
    else:
        target_chat_id = update.message.chat_id
        base_name = " ".join(context.args)
        channel_name = getattr(update.message.chat, "title", None) or str(target_chat_id)

    controller.stop_attack(target_chat_id, "channelnc")
    key = f"{target_chat_id}_channelnc"
    if key in active_attacks:
        for task in active_attacks[key]:
            task.cancel()
        del active_attacks[key]

    stop_event = controller.get_stop_event(target_chat_id, "channelnc")
    stop_event.clear()

    tasks = []
    task = asyncio.create_task(channelnc_godspeed_stream(bots, target_chat_id, base_name, stop_event, MAIN_BOT_ID))
    tasks.append(task)

    active_attacks[key] = tasks

    msg = (
        f"📢⚡『 *{to_small_caps('HIGH SPEED CHANNEL NC ACTIVATED')}* 』⚡📢\n\n"
        f"📌 *{to_small_caps('Target Channel:')}* `{channel_name}`\n"
        f"📝 *{to_small_caps('Target Title:')}* `{base_name}`\n"
        f"🤖 *{to_small_caps('Bots Count:')}* `{len(bots)}`\n"
        f"⚡ *{to_small_caps('Mode:')}* `{to_small_caps('God Speed Stream (0.00001s)')}`\n"
        f"🛑 *{to_small_caps('Stop Cmd:')}* `{CMD_PREFIX}stopchannelnc`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_channelncgodspeed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start High Speed Godspeed Channel NC loop across all bots"""
    await cmd_channelnc(update, context)

@only_admin
async def cmd_stopchannelnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return

    target_chat_id = update.message.chat_id
    if context.args:
        ref = context.args[0].strip()
        if ref.lstrip("-").isdigit():
            target_chat_id = int(ref)
        elif ref.startswith("@"):
            try:
                chat_info = await context.bot.get_chat(ref)
                target_chat_id = chat_info.id
            except Exception:
                target_chat_id = ref

    key = f"{target_chat_id}_channelnc"
    stopped = False
    if key in active_attacks:
        for t in active_attacks[key]:
            t.cancel()
        del active_attacks[key]
        stopped = True
    
    controller.stop_attack(target_chat_id, "channelnc")

    chan_keys = [k for k in active_attacks if k.endswith("_channelnc")]
    for k in chan_keys:
        for t in active_attacks[k]:
            t.cancel()
        del active_attacks[k]
        stopped = True

    if stopped:
        await update.message.reply_text(f"🛑 *{to_small_caps('CHANNEL NC STOPPED')}*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ *{to_small_caps('No active Channel NC running')}*", parse_mode="Markdown")

# ==================== FANCY FONT GENERATOR ====================

@only_admin
async def cmd_fancy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}fancy <{to_small_caps('text')}>`", parse_mode="Markdown")

    raw_text = " ".join(context.args)

    small_caps = to_small_caps(raw_text)
    
    # Simple maps for additional styles
    gothic_map = str.maketrans(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔮𝔦𝔟𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷𝔄𝔅ℭ𝔇𝔈𝔉𝔤ℌℑ𝔍𝔎𝔏𝔍𝔞𝔅𝔜ℜ𝔖𝔗𝔘𝔙𝔑𝔗𝔒ℨ"
    )
    script_map = str.maketrans(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝓹𝔂𝔃𝓐𝓑𝓒𝓓𝓔𝓐𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓯𝓤𝓥𝓦𝓧𝓨𝓩"
    )
    double_map = str.maketrans(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ"
    )
    bubble_map = str.maketrans(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ⓪①②③④⑤⑥⑦⑧⑨"
    )

    gothic = raw_text.translate(gothic_map)
    script = raw_text.translate(script_map)
    double = raw_text.translate(double_map)
    bubble = raw_text.translate(bubble_map)

    response = (
        f"🎭『 *{to_small_caps('FANCY FONT GENERATOR')}* 』🎭\n\n"
        f"🔤 *{to_small_caps('Small Caps:')}*\n`{small_caps}`\n\n"
        f"⚔️ *{to_small_caps('Gothic Style:')}*\n`{gothic}`\n\n"
        f"🖋️ *{to_small_caps('Bold Script:')}*\n`{script}`\n\n"
        f"💎 *{to_small_caps('Double Struck:')}*\n`{double}`\n\n"
        f"🔮 *{to_small_caps('Bubble Style:')}*\n`{bubble}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot {to_small_caps('Font Engine')}* ✨"
    )
    await update.message.reply_text(response, parse_mode="Markdown")

# ==================== FUN FEATURES MODULE ====================

ANIME_QUOTES = [
    ("Power isn't determined by your size, but the size of your heart and dreams!", "Monkey D. Luffy", "One Piece"),
    ("If you don't take risks, you can't create a future!", "Monkey D. Luffy", "One Piece"),
    ("People’s lives don’t end when they die, it ends when they lose faith.", "Itachi Uchiha", "Naruto"),
    ("Whatever you lose, you'll find it again. But what you throw away you'll never get back.", "Kenshin Himura", "Rurouni Kenshin"),
    ("Push through the pain, giving up hurts more!", "Vegeta", "Dragon Ball Z"),
    ("The world is not perfect. But it's there for us, doing the best it can.", "Roy Mustang", "Fullmetal Alchemist"),
    ("If you turn your eyes away from sad things, they'll happen again.", "Rory Mercury", "GATE"),
    ("I am the bone of my sword.", "Shirou Emiya", "Fate/stay night"),
    ("My soul is crimson!", "Akame", "Akame ga Kill!"),
    ("Those who break the rules are scum, but those who abandon their friends are worse than scum.", "Kakashi Hatake", "Naruto"),
    ("If you don't share someone's pain, you can never understand them.", "Nagato", "Naruto"),
    ("The pain of being alone is completely out of this world, isn't it? I don't know why, but I understand your feelings so much, it actually hurts.", "Masane Amaha", "Witchblade"),
    ("A lesson without pain is meaningless. For you cannot gain something without sacrificing something else in return.", "Edward Elric", "Fullmetal Alchemist"),
    ("I'll take a potato chip... AND EAT IT!", "Light Yagami", "Death Note"),
    ("I am justice!", "Inspector Zenigata", "Lupin III"),
    ("Don't give up. There's no shame in falling down! True shame is to not stand up again!", "Kenshin Himura", "Rurouni Kenshin"),
    ("If you only face forward, there is something you will miss seeing.", "Vash the Stampede", "Trigun"),
    ("It's not the face that makes someone a monster; it's the choices they make with their lives.", "Naruto Uzumaki", "Naruto"),
    ("I want to be happy.", "Gon Freecss", "Hunter x Hunter"),
    ("The world isn't perfect. But it's there for us, trying the best it can. That's what makes it so damn beautiful.", "Roy Mustang", "Fullmetal Alchemist"),
    ("Kill the past. Kill yourself. Kill your reason for living. If you can't do that, then you're not qualified to be the main character.", "Ken Kaneki", "Tokyo Ghoul"),
    ("I'm not going to forgive you. I'm not going to forget what you did. But I'll still try to understand why you did it.", "Sasuke Uchiha", "Naruto"),
    ("A king's duty is not just to protect his people. It's also to inspire them.", "Meliodas", "The Seven Deadly Sins"),
    ("The difference between a novice and an expert is that the expert has failed more times than the novice has tried.", "Unknown", "Various"),
    ("I don't want to conquer anything. I just think the guy with the most freedom in this world is the pirate king!", "Monkey D. Luffy", "One Piece"),
    ("If you waste your life trying to make everyone else happy, you will eventually forget what makes you happy.", "Unknown", "Various"),
    ("The pain of being alone is nothing compared to the pain of loving someone and losing them.", "Unknown", "Various"),
    ("It's not a mistake if you learn from it.", "Unknown", "Various"),
    ("With great power comes great responsibility.", "Peter Parker", "Spider-Man"),
    ("I'm Spider-Man, and I'm not here to make friends.", "Peter Parker", "Spider-Man"),
    ("My spider-sense is tingling!", "Peter Parker", "Spider-Man"),
    ("Hey, I'm swinging here!", "Peter Parker", "Spider-Man"),
    ("Sometimes the right path is not the easiest one.", "Peter Parker", "Spider-Man"),
    ("I'm not a hero. I'm not a villain. I'm... Spider-Man.", "Peter Parker", "Spider-Man"),
    ("Anyone can wear the mask. You can wear the mask. But if you don't know why you're wearing it, then you're not Spider-Man.", "Peter Parker", "Spider-Man"),
    ("Not everyone is meant to make a difference. But for me, the choice to lead an ordinary life is no longer an option.", "Peter Parker", "Spider-Man"),
    ("The best way to not feel hopeless is to get up and do something.", "Peter Parker", "Spider-Man"),
    ("I am Spider-Man. And I'm always going to be Spider-Man.", "Peter Parker", "Spider-Man"),
    ("With great power... there must also come great responsibility!", "Peter Parker", "Spider-Man"),
    ("I'm Spider-Man. I'm not supposed to be here, but I am.", "Peter Parker", "Spider-Man"),
    ("Whatever life holds in store for me, I will never forget these words: 'With great power comes great responsibility.'", "Peter Parker", "Spider-Man"),
    ("I'm not gonna kill you. I want you to remember, every time you look at your face in the mirror, you remember Spider-Man who didn't kill you.", "Peter Parker", "Spider-Man"),
    ("You know, I was wondering, why do we fall? So we can learn to pick ourselves up.", "Peter Parker", "Spider-Man")
]

TRUTH_PROMPTS = [
    "What is your biggest secret in this group?",
    "Who in this chat would you trust with your life?",
    "What is the most embarrassing thing you've done recently?",
    "What is your worst habit?",
    "If you could kick anyone from this group, who would it be?"
]

DARE_PROMPTS = [
    "Send a voice note singing your favorite anime song right now!",
    "Change your Telegram profile picture to an anime meme for 1 hour!",
    "Tag the group owner and send a cute compliment!",
    "Send the last photo in your gallery to this chat!",
    "Type your next 5 messages using ONLY emojis!"
]

@only_admin
async def cmd_animequote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quote, char, anime = random.choice(ANIME_QUOTES)
    msg = (
        f"📜『 *{to_small_caps('ANIME QUOTE')}* 』📜\n\n"
        f"💬 *\"{quote}\"*\n\n"
        f"👤 *{to_small_caps('Character:')}* `{char}`\n"
        f"🎬 *{to_small_caps('Anime:')}* `{anime}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_admin
async def cmd_tts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return

    # Get text from arguments or use a random anime quote
    if context.args:
        text = " ".join(context.args)
        source = f"Custom text: {text}"
    else:
        quote, char, anime = random.choice(ANIME_QUOTES)
        text = quote
        source = f"'{quote}' - {char} ({anime})"

    # Check if TTS is available
    if not TTS_AVAILABLE:
        await update.message.reply_text(
            "❌ *{to_small_caps('TTS functionality is not available.')}*\n"
            "Please install gTTS using: `pip install gTTS`",
            parse_mode="Markdown"
        )
        return

    # Send processing message
    status_msg = await update.message.reply_text(
        f"🔊 *{to_small_caps('Generating speech...')}*\n"
        f"📝 *{to_small_caps('Source:')}* `{source}`",
        parse_mode="Markdown"
    )

    try:
        # Generate speech
        audio_bytes = text_to_speech(text, lang='en')  # Default to English

        # Send as voice message
        await context.bot.send_voice(
            chat_id=update.effective_chat.id,
            voice=BytesIO(audio_bytes),
            caption=f"🔊 *{to_small_caps('Text-to-Speech')}*\n"
                   f"📝 *{to_small_caps('Source:')}* `{source}`\n\n"
                   f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
                   f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨",
            parse_mode="Markdown"
        )

        # Delete the status message
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error in cmd_tts: {e}")
        await status_msg.edit_text(
            f"❌ *{to_small_caps('TTS generation failed:')}* `{str(e)}`",
            parse_mode="Markdown"
        )

@only_admin
async def cmd_8ball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text(f"🔮 *{to_small_caps('Usage:')}* `{CMD_PREFIX}8ball <{to_small_caps('question')}>`", parse_mode="Markdown")
    q = " ".join(context.args)
    answers = [
        "It is certain.", "It is decidedly so.", "Without a doubt.",
        "Yes definitely.", "You may rely on it.", "As I see it, yes.",
        "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
        "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
        "Cannot predict now.", "Concentrate and ask again.",
        "Don't count on it.", "My reply is no.", "My sources say no.",
        "Outlook not so good.", "Very doubtful."
    ]
    ans = random.choice(answers)
    msg = (
        f"🔮『 *{to_small_caps('MAGIC 8-BALL')}* 』🔮\n\n"
        f"❓ *{to_small_caps('Question:')}* `{q}`\n"
        f"✨ *{to_small_caps('Answer:')}* `{to_small_caps(ans)}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_admin
async def cmd_coinflip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = random.choice(["Heads 🪙", "Tails 🪙"])
    await update.message.reply_text(f"🪙 *{to_small_caps('Coin Flip Result:')}* `{to_small_caps(res)}`", parse_mode="Markdown")

@only_admin
async def cmd_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = random.randint(1, 6)
    await update.message.reply_text(f"🎲 *{to_small_caps('Dice Roll:')}* `{res}`", parse_mode="Markdown")

@only_admin
async def cmd_truth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = random.choice(TRUTH_PROMPTS)
    await update.message.reply_text(f"❓ *{to_small_caps('TRUTH CHALLENGE:')}*\n`{p}`", parse_mode="Markdown")

@only_admin
async def cmd_dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = random.choice(DARE_PROMPTS)
    await update.message.reply_text(f"🔥 *{to_small_caps('DARE CHALLENGE:')}*\n`{d}`", parse_mode="Markdown")

# ==================== STOP COMMANDS ====================

@only_admin
async def cmd_stopnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return

    chat_id = update.message.chat_id
    stopped = []

    if chat_id in group_tasks:
        for task in group_tasks[chat_id]:
            task.cancel()
        del group_tasks[chat_id]
        stopped.append("NC")

    key = f"{chat_id}_godnc"
    if key in active_attacks:
        for t in active_attacks[key]: t.cancel()
        del active_attacks[key]
        stopped.append("God NC")

    if chat_id in mexxync_tasks:
        for task in mexxync_tasks[chat_id]:
            task.cancel()
        del mexxync_tasks[chat_id]
        stopped.append("RexxyTGBot NC")

    keys_to_del = [k for k in active_attacks if k.startswith(f"{chat_id}_nc") or k.startswith(f"{chat_id}_fontnc") or k.startswith(f"{chat_id}_channelnc") or k.endswith("_channelnc")]
    for k in keys_to_del:
        for t in active_attacks[k]:
            t.cancel()
        del active_attacks[k]
        stopped.append("Font/Channel NC")

    if stopped:
        await update.message.reply_text(f"🛑 *{to_small_caps(', '.join(stopped))} {to_small_caps('STOPPED')}*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ *{to_small_caps('No active name changers')}*", parse_mode="Markdown")

@only_admin
async def cmd_stopspam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return

    chat_id = update.message.chat_id
    stopped = False

    if chat_id in spam_tasks:
        for task in spam_tasks[chat_id]:
            task.cancel()
        del spam_tasks[chat_id]
        stopped = True

    if controller.stop_spamemo(chat_id):
        key = f"{chat_id}_spamemo"
        if key in active_attacks:
            for task in active_attacks[key]:
                task.cancel()
            del active_attacks[key]
        stopped = True

    if stopped:
        await update.message.reply_text(f"🛑 *{to_small_caps('SPAM STOPPED')}*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ *{to_small_caps('No active spam')}*", parse_mode="Markdown")

# ==================== PHOTO & SLIDE COMMANDS ====================

@only_admin
async def cmd_targetslide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not update.message.reply_to_message:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Reply to a user message!')}*", parse_mode="Markdown")

    target_id = update.message.reply_to_message.from_user.id
    slide_targets.add(target_id)
    await update.message.reply_text(f"🎯 *{to_small_caps('Target slide added:')}* `{target_id}`", parse_mode="Markdown")

@only_admin
async def cmd_stopslide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not update.message.reply_to_message:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Reply to a user message!')}*", parse_mode="Markdown")

    target_id = update.message.reply_to_message.from_user.id
    slide_targets.discard(target_id)
    await update.message.reply_text(f"🛑 *{to_small_caps('Slide stopped:')}* `{target_id}`", parse_mode="Markdown")

@only_admin
async def cmd_slidespam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not update.message.reply_to_message:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Reply to a user message!')}*", parse_mode="Markdown")

    target_id = update.message.reply_to_message.from_user.id
    slidespam_targets.add(target_id)
    await update.message.reply_text(f"💥 *{to_small_caps('Slide spam started:')}* `{target_id}`", parse_mode="Markdown")

@only_admin
async def cmd_stopslidespam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not update.message.reply_to_message:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Reply to a user message!')}*", parse_mode="Markdown")

    target_id = update.message.reply_to_message.from_user.id
    slidespam_targets.discard(target_id)
    await update.message.reply_text(f"🛑 *{to_small_caps('Slide spam stopped:')}* `{target_id}`", parse_mode="Markdown")

@only_admin
async def cmd_savephoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Reply to a photo to save it!')}*", parse_mode="Markdown")

    chat_id = update.message.chat_id
    file_id = update.message.reply_to_message.photo[-1].file_id

    if chat_id not in chat_photos:
        chat_photos[chat_id] = []

    chat_photos[chat_id].append(file_id)
    await update.message.reply_text(f"✅ *{to_small_caps('Photo saved! Total:')}* `{len(chat_photos[chat_id])}`", parse_mode="Markdown")

@only_admin
async def cmd_startphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    if chat_id not in chat_photos or len(chat_photos[chat_id]) < 2:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Save at least 2 photos first!')}*", parse_mode="Markdown")

    if chat_id in photo_tasks:
        if isinstance(photo_tasks[chat_id], list):
            for t in photo_tasks[chat_id]:
                t.cancel()
        else:
            photo_tasks[chat_id].cancel()

    tasks = []
    for bot in bots:
        task = asyncio.create_task(photo_loop(bot, chat_id, chat_photos[chat_id]))
        tasks.append(task)

    photo_tasks[chat_id] = tasks
    await update.message.reply_text(f"🔄 *{to_small_caps('Photo loop started (0.5s speed)!')}*", parse_mode="Markdown")

@only_admin
async def cmd_stopphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    if chat_id in photo_tasks:
        tasks_or_task = photo_tasks[chat_id]
        if isinstance(tasks_or_task, list):
            for t in tasks_or_task:
                t.cancel()
        else:
            tasks_or_task.cancel()
        del photo_tasks[chat_id]
        await update.message.reply_text(f"⏹ *{to_small_caps('Photo loop stopped!')}*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ *{to_small_caps('No active photo loop')}*", parse_mode="Markdown")

@only_admin
async def cmd_clearphotos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    if chat_id in chat_photos:
        del chat_photos[chat_id]
        await update.message.reply_text(f"🗑 *{to_small_caps('Saved photos cleared!')}*", parse_mode="Markdown")

# ==================== AUTO REPLIES HANDLER ====================

async def auto_replies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user:
        return

    uid = update.message.from_user.id
    chat_id = update.message.chat_id
    now = time.time()

    # ── 1. Global mute check (Soft Mute: delete message immediately) ──
    if uid in global_muted_store:
        exp = global_muted_store[uid]
        if exp is not None and now > exp:
            global_muted_store.pop(uid, None)
            save_mutes()
        else:
            try:
                await update.message.delete()
            except Exception:
                pass
            return

    # ── 2. Local mute check in this chat (Soft Mute: delete message immediately) ──
    if (chat_id, uid) in local_muted_store:
        exp = local_muted_store[(chat_id, uid)]
        if exp is not None and now > exp:
            local_muted_store.pop((chat_id, uid), None)
            save_mutes()
        else:
            try:
                await update.message.delete()
            except Exception:
                pass
            return

    # ── 3. Group Lock check (Delete all non-admin messages if group is locked) ──
    if chat_id in group_locks and not is_admin(uid):
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    # ── 4. Slide targets ──
    if uid in slide_targets:
        for text in RAID_TEXTS[:3]:
            try:
                await update.message.reply_text(text)
                await asyncio.sleep(0.1)
            except telegram.error.RetryAfter as e:
                await asyncio.sleep(float(e.retry_after) + 0.5)
            except Exception:
                await asyncio.sleep(0.5)

    # ── 5. Slidespam targets ──
    if uid in slidespam_targets:
        for text in RAID_TEXTS:
            try:
                await update.message.reply_text(text)
                await asyncio.sleep(0.1)
            except telegram.error.RetryAfter as e:
                await asyncio.sleep(float(e.retry_after) + 0.5)
            except Exception:
                await asyncio.sleep(0.5)

# ==================== MENU & CALLBACK HANDLERS ====================

@only_admin
async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return

    menu = menu_config.get_menu("main")
    keyboard = get_main_keyboard()

    try:
        if menu.get("type") == "photo":
            await update.message.reply_photo(
                photo=menu["video"],
                caption=menu["caption"],
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_video(
                video=menu["video"],
                caption=menu["caption"],
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except Exception:
        try:
            await update.message.reply_text(
                menu["caption"],
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception:
            await update.message.reply_text(menu["caption"], reply_markup=keyboard)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if context.bot.id != MAIN_BOT_ID:
        await query.answer("❌ Only main bot handles this!", show_alert=True)
        return

    if not is_admin(query.from_user.id):
        await query.answer("❌ You are not admin!", show_alert=True)
        return

    data = query.data

    if data == "close_menu":
        try:
            await query.message.delete()
        except Exception:
            await query.answer("Menu closed!", show_alert=False)
        return

    if data.startswith("sp_cancel:"):
        cache_id = data.replace("sp_cancel:", "")
        spotify_search_cache.pop(cache_id, None)
        try:
            await query.message.delete()
        except Exception:
            await query.message.edit_text(f"❌ *{to_small_caps('Search cancelled.')}*", parse_mode="Markdown")
        return

    if data.startswith("sp_play:"):
        parts = data.split(":")
        if len(parts) == 3:
            cache_id = parts[1]
            idx = int(parts[2])
            tracks = spotify_search_cache.get(cache_id)
            if not tracks or idx >= len(tracks):
                await query.answer("❌ Search expired or track not found!", show_alert=True)
                return
            
            track_info = tracks[idx]
            await query.answer(f"▶️ Selected: {track_info['title']}", show_alert=False)
            
            # Start downloading selected track
            await _download_and_send_spotify_track(
                context.bot,
                query.message.chat_id,
                query.message,
                track_info["title"],
                track_info["artist"],
                track_info["duration_ms"],
                track_info["query"]
            )
            spotify_search_cache.pop(cache_id, None)
            return

    if data == "menu_main":
        menu = menu_config.get_menu("main")
        try:
            media_class = InputMediaPhoto if menu.get("type") == "photo" else InputMediaVideo
            await query.message.edit_media(
                media_class(media=menu["video"], caption=menu["caption"], parse_mode="Markdown"),
                reply_markup=get_main_keyboard()
            )
        except Exception:
            await query.message.edit_text(menu["caption"], reply_markup=get_main_keyboard(), parse_mode="Markdown")
        return

    if data.startswith("menu_"):
        category = data.replace("menu_", "")
        menu = menu_config.get_menu(category)
        keyboard = get_back_keyboard() if category != "main" else get_main_keyboard()

        if menu.get("type") in ("video", "photo") and menu.get("video"):
            try:
                media_class = InputMediaPhoto if menu.get("type") == "photo" else InputMediaVideo
                await query.message.edit_media(
                    media_class(media=menu["video"], caption=menu["caption"], parse_mode="Markdown"),
                    reply_markup=keyboard
                )
            except Exception:
                await query.message.edit_text(menu["caption"], reply_markup=keyboard, parse_mode="Markdown")
        else:
            try:
                await query.message.edit_text(menu["caption"], reply_markup=keyboard, parse_mode="Markdown")
            except Exception:
                await query.message.reply_text(menu["caption"], reply_markup=keyboard, parse_mode="Markdown")
        return

    if data == "help_full":
        help_text = get_help_text()
        await query.message.edit_text(help_text, parse_mode="Markdown", reply_markup=get_back_keyboard())
        return

    if data == "status":
        status_text = await get_status_text()
        await query.message.reply_text(status_text, parse_mode="Markdown")
        return

# ==================== HELP & STATUS TEXTS ====================

def get_help_text():
    p = CMD_PREFIX
    help_text = f"""
╔════════════════════════════════╗
║    🎀 RexxyTGBot  {to_small_caps('TERMINAL')} 🎀   ║
╚════════════════════════════════╝

👑 *{to_small_caps('GOD NC REALM:')}*
 ➪ `{p}godnc [name]`      - {to_small_caps('Custom Big Text Stream')}
 ➪ `{p}godncgodspeed [n]` - {to_small_caps('God Speed Stream')}

⚔️ *{to_small_caps('ATTACK MODES:')}*
 ➪ `{p}nc1 [name]`   - {to_small_caps('RAID Assault')}
 ➪ `{p}nc2 [name]`   - {to_small_caps('GOD Mode')}
 ➪ `{p}nc3 [name]`   - {to_small_caps('Time Shift')}
 ➪ `{p}nc4 [name]`   - {to_small_caps('Ultra Fast Custom Mix')}
 ➪ `{p}channelnc [@chan] [name]` - {to_small_caps('High Speed Channel NC')}
 ➪ `{p}channelncgodspeed [@chan] [name]` - {to_small_caps('God Speed Channel NC')}
 ➪ `{p}fontnc [name]` - {to_small_caps('Small Caps Font NC')}
 ➪ `{p}spamemo [tgt]` - {to_small_caps('Emoji Spam')}
 ➪ `{p}spam [text]`   - {to_small_caps('Text Spam')}
 ➪ `{p}raidspam [name]` - {to_small_caps('RAID Spam')}
 ➪ `{p}swipe [tgt]`   - {to_small_caps('Swipe Attack')}
 ➪ `{p}over [tgt]`    - {to_small_caps('Game Over')}

🎵 *{to_small_caps('MUSIC SYSTEM:')}*
 ➪ `{p}spotify [link]` - {to_small_caps('Spotify API Search & Play')}
 ➪ `{p}song [name]`    - {to_small_caps('SoundCloud Search & Play')}

🤖 *{to_small_caps('AI STUDIO (FROM U.PY):')}*
 ➪ `{p}ask [question]` - {to_small_caps('Ask AI Query (Pollinations + Gemini)')}
 ➪ `{p}imagine [prompt]` - {to_small_caps('AI Image Generator (Flux Model)')}
 ➪ `{p}qrcode [text]`   - {to_small_caps('QR Code Generator')}
 ➪ `{p}translate [lang] [txt]` - {to_small_caps('Translator')}

🔇 *{to_small_caps('MUTE & MODERATION (SOFT-DELETE):')}*
 ➪ `{p}mute [time] [user]` - {to_small_caps('Mute in chat (silent message deletion)')}
 ➪ `{p}unmute [user]`   - {to_small_caps('Unmute user in chat')}
 ➪ `{p}gmute [time] [user]` - {to_small_caps('Global mute user across all chats')}
 ➪ `{p}gunmute [user]`  - {to_small_caps('Global unmute user')}
 ➪ `{p}mutelist`        - {to_small_caps('List all muted users & remaining times')}
 ➪ `{p}lock` / `{p}unlock` - {to_small_caps('Lock/Unlock group (auto-delete non-admins)')}
 ➪ `{p}purge [count]`   - {to_small_caps('Purge recent messages')}

👑 *{to_small_caps('OWNER BOT STUDIO (ONLY OWNER):')}*
 ➪ `{p}setbotname [name]` - {to_small_caps('Change display name for ALL bots')}
 ➪ `{p}setbotbio [bio]`   - {to_small_caps('Change description & bio for ALL bots')}
 ➪ `{p}setbotpfp [reply/url]` - {to_small_caps('Change Profile Picture for ALL bots')}

🛑 *{to_small_caps('STOP COMMANDS:')}*
 ➪ `{p}stop`          - {to_small_caps('Stop Current Attack')}
 ➪ `{p}stopall`        - {to_small_caps('Global Stop')}
 ➪ `{p}stopgodnc`     - {to_small_caps('Stop God NC')}
 ➪ `{p}stopchannelnc`  - {to_small_caps('Stop Channel NC')}
 ➪ `{p}stopnc`        - {to_small_caps('Stop Name Changer')}
 ➪ `{p}stopspam`      - {to_small_caps('Stop Spam')}
 ➪ `{p}stopmexxync`    - {to_small_caps('Stop RexxyTGBot NC')}

🎲 *{to_small_caps('FUN REALM:')}*
 ➪ `{p}fancy [text]`   - {to_small_caps('Fancy Font Converter')}
 ➪ `{p}animequote`     - {to_small_caps('Anime Quote')}
 ➪ `{p}tts [text]`     - {to_small_caps('Text-to-Speech (uses anime quote if no text)')}
 ➪ `{p}8ball [q]`       - {to_small_caps('Magic 8-Ball')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✨ *{to_small_caps('Powered By')} RexxyTGBot {to_small_caps('SUPREMACY')}* ✨
"""
    return help_text

async def get_status_text():
    uptime_seconds = int(time.time() - START_TIME)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
    else:
        uptime_str = f"{hours}h {minutes}m {seconds}s"

    async def ping_bot(bot):
        start = time.time()
        try:
            bot_info = await asyncio.wait_for(bot.get_me(), timeout=1.5)
            return bot_info.username, round((time.time() - start) * 1000)
        except Exception:
            try:
                username = getattr(bot, 'username', None) or str(getattr(bot, 'id', 'Unknown'))
            except Exception:
                username = "Unknown"
            return username, -1

    pings = await asyncio.gather(*[ping_bot(bot) for bot in bots])

    bot_details = []
    online_count = 0
    for username, ping in pings:
        escaped_username = escape_md(username)
        if ping >= 0:
            bot_details.append(f"• @{escaped_username}: `{ping}ms` 🟢")
            online_count += 1
        else:
            bot_details.append(f"• @{escaped_username}: `Offline` 🔴")

    active_count = sum(1 for key in active_attacks if active_attacks[key])
    bot_details_str = "\n".join(bot_details) if bot_details else "No bots"

    cpu_usage = "N/A"
    ram_usage = "N/A"
    if psutil:
        try:
            cpu_usage = f"{psutil.cpu_percent()}%"
            ram_usage = f"{psutil.virtual_memory().percent}%"
        except Exception:
            pass

    status_text = (
        f"🎀 *{to_small_caps('SYSTEM STATUS')}* 🎀\n\n"
        f"⏱️ *{to_small_caps('Uptime:')}* `{uptime_str}`\n"
        f"🤖 *{to_small_caps('Bots Online:')}* `{online_count}/{len(bots)}`\n"
        f"⚡ *{to_small_caps('Active Attacks:')}* `{active_count}`\n"
        f"📊 *{to_small_caps('CPU:')}* `{cpu_usage}` | *{to_small_caps('RAM:')}* `{ram_usage}`\n"
        f"💻 *{to_small_caps('OS:')}* `{platform.system()}` | *{to_small_caps('Python:')}* `{platform.python_version()}`\n\n"
        f"📶 *{to_small_caps('Bot Pings:')}*\n{bot_details_str}\n\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    return status_text

@only_sudo
async def cmd_uptime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    uptime_seconds = int(time.time() - START_TIME)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        uptime_formatted = f"{days}d {hours}h {minutes}m {seconds}s"
    else:
        uptime_formatted = f"{hours}h {minutes}m {seconds}s"

    start_datetime = datetime.fromtimestamp(START_TIME).strftime("%Y-%m-%d %H:%M:%S UTC")

    uptime_text = (
        f"⏱️ *『 {to_small_caps('BOT SYSTEM UPTIME')} 』* ⏱️\n\n"
        f"⏳ *{to_small_caps('Uptime:')}* `{uptime_formatted}`\n"
        f"🚀 *{to_small_caps('Started At:')}* `{start_datetime}`\n"
        f"🤖 *{to_small_caps('Total Bots:')}* `{len(bots)}`\n"
        f"💻 *{to_small_caps('OS:')}* `{platform.system()}`\n\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(uptime_text, parse_mode="Markdown")

# ==================== DUMMY COMMANDS & SOUNDCLOUD MUSIC ====================

@only_sudo
async def cmd_over(update, context):
    if context.bot.id != MAIN_BOT_ID:
        return

    target = " ".join(context.args) if context.args else "UNKNOWN"

    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    date_str = now.strftime("%d %B %Y")
    time_str = now.strftime("%I:%M:%S %p")

    caption = (
        f"💀『 *{to_small_caps('G A M E  O V E R')}* 』💀\n\n"
        f"⛩️ *{to_small_caps('Target Eliminated')}*\n\n"
        f"🎯 *{to_small_caps('Target:')}* `{target}`\n"
        f"☠️ *{to_small_caps('Status:')}* `{to_small_caps('DESTROYED')}`\n\n"
        f"📅 *{to_small_caps('Date:')}* `{date_str}`\n"
        f"🕐 *{to_small_caps('Time:')}* `{time_str} IST`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot {to_small_caps('Supremacy')}* ✨"
    )

    media_id = bot_config.get("media_over", DEFAULT_GAMEOVER_VIDEO_URL)
    media_type = bot_config.get("media_over_type", "video")

    if media_type == "photo":
        await update.message.reply_photo(photo=media_id, caption=caption, parse_mode="Markdown")
    else:
        await update.message.reply_video(video=media_id, caption=caption, parse_mode="Markdown")

async def _get_soundcloud_client_id() -> str | None:
    """Dynamically fetch SoundCloud client_id from JS bundles."""
    try:
        session = await get_http_session()
        async with session.get("https://soundcloud.com", headers={"User-Agent": "Mozilla/5.0"}) as resp:
            html = await resp.text()

        script_urls = re.findall(r'<script[^>]+src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', html)
        if not script_urls:
            script_urls = re.findall(r'src="(/assets/[^"]+\.js)"', html)
            script_urls = [f"https://soundcloud.com{u}" for u in script_urls]

        for url in reversed(script_urls[-5:]):
            try:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    js = await resp.text()
                match = re.search(r'client_id[=:"]+([a-zA-Z0-9]{32})', js)
                if match:
                    return match.group(1)
            except Exception:
                continue
    except Exception:
        pass
    fallback_ids = [
        "iZ86SZmYAhBCCDUycSFaUhT1JL2Jdzrj",
        "J15y698944dZf4B3J6A810d7E2d11F3a",
        "95f82326588264d9302677943d0f04f2",
        "2t9loNYSFdGj1pEN7yM4jQy6pE1kQ0aA",
        "d23a1f7362a264a781b0a8220042456e"
    ]
    return random.choice(fallback_ids)



async def _get_spotify_token() -> str | None:
    """Fetch a temporary Spotify access token with retry logic."""
    for attempt in range(3):
        try:
            session = await get_http_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://open.spotify.com/",
                "Origin": "https://open.spotify.com",
                "Accept": "application/json",
            }
            async with session.get("https://open.spotify.com/get_access_token?reason=transport&productType=web_player", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    token = data.get("accessToken")
                    if token:
                        return token
                logger.debug(f"Spotify token fetch attempt {attempt + 1} failed with status {resp.status}")
        except Exception as e:
            logger.debug(f"Spotify token fetch attempt {attempt + 1} failed with exception: {e}")
        # Wait a bit before retrying (except after the last attempt)
        if attempt < 2:
            await asyncio.sleep(1.5 * (attempt + 1))  # increasing delay
    return None

# Cache for Spotify top 5 search results (cache_id -> list of track dicts)
spotify_search_cache = {}

async def _fetch_spotify_tracks(query_or_url: str, limit: int = 5) -> list:
    token = await _get_spotify_token()
    if not token:
        return []

    session = await get_http_session()
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    results = []
    track_match = re.search(r"spotify\.com/track/([a-zA-Z0-9]+)", query_or_url)
    if track_match:
        track_id = track_match.group(1)
        url = f"https://api.spotify.com/v1/tracks/{track_id}"
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                title = data.get("name", "Unknown Title")
                artists = ", ".join([a.get("name") for a in data.get("artists", [])])
                dur_ms = data.get("duration_ms", 0)
                images = data.get("album", {}).get("images", [])
                thumb = images[0]["url"] if images else None
                results.append({"title": title, "artist": artists, "duration_ms": dur_ms, "thumb": thumb, "query": f"{title} {artists}"})
    else:
        url = f"https://api.spotify.com/v1/search?q={urllib.parse.quote(query_or_url)}&type=track&limit={limit}"
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                items = data.get("tracks", {}).get("items", [])
                for item in items:
                    title = item.get("name", "Unknown Title")
                    artists = ", ".join([a.get("name") for a in item.get("artists", [])])
                    dur_ms = item.get("duration_ms", 0)
                    images = item.get("album", {}).get("images", [])
                    thumb = images[0]["url"] if images else None
                    results.append({"title": title, "artist": artists, "duration_ms": dur_ms, "thumb": thumb, "query": f"{title} {artists}"})
    return results

async def _download_and_send_spotify_track(bot, chat_id, status_msg, track_title, artist_name, dur_ms, search_query):
    try:
        await status_msg.edit_text(
            f"⬇️ *{to_small_caps('Searching for audio:')}* `{track_title} - {artist_name}`...",
            parse_mode="Markdown"
        )

        # Use SoundCloud to find audio for the same song title/artist
        # Direct Spotify audio extraction requires authorized APIs; this searches SoundCloud as alternative
        client_id = await _get_soundcloud_client_id()
        session = await get_http_session()

        # Search for the track on SoundCloud using the track title and artist
        search_query_sc = f"{track_title} {artist_name}"
        search_url = f"https://api-v2.soundcloud.com/search/tracks?q={urllib.parse.quote(search_query_sc)}&client_id={client_id}&limit=1"
        async with session.get(search_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return await status_msg.edit_text(f"❌ *{to_small_caps('Audio search failed.')}*", parse_mode="Markdown")
            sc_data = await resp.json()

        collection = sc_data.get("collection", [])
        if not collection:
            return await status_msg.edit_text(f"❌ *{to_small_caps('No audio found for:')}* `{search_query_sc}`", parse_mode="Markdown")

        track = collection[0]
        # Use duration from SoundCloud track if available, otherwise use the Spotify duration
        track_dur_ms = track.get("duration", 0) or dur_ms
        track_title_sc = track.get("title", track_title)
        track_artist_sc = track.get("user", {}).get("username", artist_name)

        dur_str = f"{track_dur_ms // 60000}:{(track_dur_ms % 60000) // 1000:02d}"

        transcodings = track.get("media", {}).get("transcodings", [])
        prog_url = None
        for t in transcodings:
            if t.get("format", {}).get("protocol") == "progressive":
                prog_url = t.get("url")
                break
        if not prog_url and transcodings:
            prog_url = transcodings[0].get("url")

        if not prog_url:
            return await status_msg.edit_text(f"❌ *{to_small_caps('No downloadable stream found.')}*", parse_mode="Markdown")

        async with session.get(f"{prog_url}?client_id={client_id}", headers={"User-Agent": "Mozilla/5.0"}) as resp:
            stream_data = await resp.json()

        actual_url = stream_data.get("url")
        if not actual_url:
            return await status_msg.edit_text(f"❌ *{to_small_caps('Could not resolve audio stream URL.')}*", parse_mode="Markdown")

        async with session.get(actual_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return await status_msg.edit_text(f"❌ *{to_small_caps('Audio download failed.')}*", parse_mode="Markdown")
            audio_bytes = await resp.read()

        tmp_path = os.path.join(tempfile.gettempdir(), f"sp_{int(time.time()*1000)}.mp3")
        try:
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)

            # Preserve the original reply markup (keyboard) if any
            reply_markup = getattr(status_msg, 'reply_markup', None)

            with open(tmp_path, "rb") as audio_file:
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    title=to_small_caps(track_title_sc),
                    performer=to_small_caps(track_artist_sc),
                    duration=track_dur_ms // 1000,
                    caption=(
                        f"🟢『 *{track_title_sc}* 』\n"
                        f"👤 *{to_small_caps('Artist:')}* `{track_artist_sc}`\n"
                        f"⏱️ *{to_small_caps('Duration:')}* `{dur_str}`\n\n"
                        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
                        f"🔍 *{to_small_caps('Note: Audio sourced from SoundCloud search for')} `{track_title} - {artist_name}`*\n"
                        f"✨ *{to_small_caps('Powered By')} RexxyTGBot*"
                    ),
                    parse_mode="Markdown",
                )

            # After sending audio, update the status message to show "Now playing" and keep the keyboard
            now_playing_caption = (
                f"🟢『 *{track_title_sc}* 』\n"
                f"👤 *{to_small_caps('Artist:')}* `{track_artist_sc}`\n"
                f"⏱️ *{to_small_caps('Duration:')}* `{dur_str}`\n\n"
                f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
                f"🔍 *{to_small_caps('Now playing from SoundCloud search')}*\n"
                f"✨ *{to_small_caps('Powered By')} RexxyTGBot*"
            )
            await status_msg.edit_text(now_playing_caption, parse_mode="Markdown", reply_markup=reply_markup)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    except Exception as e:
        logger.exception("download_spotify_track error")
        try:
            await status_msg.edit_text(f"❌ *{to_small_caps('Error:')}* `{e}`", parse_mode="Markdown")
        except Exception:
            pass


@only_admin
async def cmd_spotify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return

    if not context.args:
        return await update.message.reply_text(
            f"🟢 *{to_small_caps('Usage:')}* `{CMD_PREFIX}spotify <{to_small_caps('song name or Spotify URL')}>`",
            parse_mode="Markdown"
        )

    query = " ".join(context.args)
    status_msg = await update.message.reply_text(
        f"🔍 *{to_small_caps('Searching SoundCloud for:')}* `{query}`...",
        parse_mode="Markdown"
    )

    try:
        client_id = await _get_soundcloud_client_id()
        session = await get_http_session()

        search_url = f"https://api-v2.soundcloud.com/search/tracks?q={urllib.parse.quote(query)}&client_id={client_id}&limit=5"
        async with session.get(search_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return await status_msg.edit_text(f"❌ *{to_small_caps('SoundCloud search failed.')}*", parse_mode="Markdown")
            data = await resp.json()

        tracks = data.get("collection", [])
        if not tracks:
            return await status_msg.edit_text(f"❌ *{to_small_caps('No tracks found for:')}* `{query}`", parse_mode="Markdown")

        # Keep only first 5 and enrich with query field
        processed = []
        for tr in tracks[:5]:
            title = tr.get("title", "Unknown Title")
            artist = tr.get("user", {}).get("username", "Unknown Artist")
            dur_ms = tr.get("duration", 0)
            query_str = f"{title} {artist}"
            processed.append({
                "title": title,
                "artist": artist,
                "duration_ms": dur_ms,
                "query": query_str
            })

        cache_id = f"{update.message.chat_id}_{update.message.message_id}"
        spotify_search_cache[cache_id] = processed

        num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        list_lines = []
        keyboard_buttons = []
        row = []

        for idx, tr in enumerate(processed):
            emoji = num_emojis[idx] if idx < len(num_emojis) else f"{idx+1}️⃣"
            title = tr["title"]
            artist = tr["artist"]
            dur_ms = tr["duration_ms"]
            dur_str = f"{dur_ms // 60000}:{(dur_ms % 60000) // 1000:02d}"
            list_lines.append(
                f"{emoji} *{title}*\n"
                f"   Artist: `{artist}` | Duration: `{dur_str}`"
            )

            cb_data = f"sp_play:{cache_id}:{idx}"
            btn = InlineKeyboardButton(f"{emoji} {title[:16]}", callback_data=cb_data)
            row.append(btn)
            if len(row) == 2:
                keyboard_buttons.append(row)
                row = []
        if row:
            keyboard_buttons.append(row)

        keyboard_buttons.append([InlineKeyboardButton(f"❌ {to_small_caps('Cancel Search')}", callback_data=f"sp_cancel:{cache_id}")])

        msg_text = (
            f"*{to_small_caps('SoundCloud Top 5 Results')}*\n\n"
            + "\n\n".join(list_lines)
            + "\n\n"
            + f"*{to_small_caps('Tap a song button below to play')}*"
        )

        await status_msg.edit_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard_buttons), parse_mode="Markdown")

    except Exception as e:
        logger.exception("cmd_spotify error")
        try:
            await status_msg.edit_text(f"❌ *{to_small_caps('Error:')}* `{e}`", parse_mode="Markdown")
        except Exception:
            pass

@only_admin
async def cmd_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search SoundCloud and send audio file."""
    if context.bot.id != MAIN_BOT_ID:
        return

    if not context.args:
        await update.message.reply_text(
            f"🎵 *{to_small_caps('Usage:')}* `{CMD_PREFIX}song <{to_small_caps('song name')}>`",
            parse_mode="Markdown"
        )
        return

    query = " ".join(context.args)
    status_msg = await update.message.reply_text(
        f"🔍 *{to_small_caps('Searching SoundCloud for:')}* `{query}`...",
        parse_mode="Markdown"
    )

    try:
        client_id = await _get_soundcloud_client_id()
        session = await get_http_session()

        search_url = f"https://api-v2.soundcloud.com/search/tracks?q={urllib.parse.quote(query)}&client_id={client_id}&limit=1"
        async with session.get(search_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                await status_msg.edit_text(f"❌ *{to_small_caps('SoundCloud search failed.')}*", parse_mode="Markdown")
                return
            data = await resp.json()

        collection = data.get("collection", [])
        if not collection:
            await status_msg.edit_text(f"❌ *{to_small_caps('No tracks found for:')}* `{query}`", parse_mode="Markdown")
            return

        track = collection[0]
        title = track.get("title", "Unknown Title")
        artist = track.get("user", {}).get("username", "Unknown Artist")
        dur_ms = track.get("duration", 0)
        dur_str = f"{dur_ms // 60000}:{(dur_ms % 60000) // 1000:02d}"

        transcodings = track.get("media", {}).get("transcodings", [])
        prog_url = None
        for t in transcodings:
            if t.get("format", {}).get("protocol") == "progressive":
                prog_url = t.get("url")
                break
        if not prog_url and transcodings:
            prog_url = transcodings[0].get("url")

        if not prog_url:
            await status_msg.edit_text(f"❌ *{to_small_caps('No downloadable stream found.')}*", parse_mode="Markdown")
            return

        async with session.get(f"{prog_url}?client_id={client_id}", headers={"User-Agent": "Mozilla/5.0"}) as resp:
            stream_data = await resp.json()

        actual_url = stream_data.get("url")
        if not actual_url:
            await status_msg.edit_text(f"❌ *{to_small_caps('Could not resolve audio stream URL.')}*", parse_mode="Markdown")
            return

        await status_msg.edit_text(f"⬇️ *{to_small_caps('Downloading:')}* `{title}`...", parse_mode="Markdown")

        async with session.get(actual_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                await status_msg.edit_text(f"❌ *{to_small_caps('Audio download failed.')}*", parse_mode="Markdown")
                return
            audio_bytes = await resp.read()

        tmp_path = os.path.join(tempfile.gettempdir(), f"sc_{update.message.message_id}.mp3")
        try:
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)

            caption = (
                f"🎵『 *{title}* 』\n"
                f"👤 *{to_small_caps('Artist:')}* `{artist}`\n"
                f"⏱️ *{to_small_caps('Duration:')}* `{dur_str}`\n\n"
                f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
                f"✨ *{to_small_caps('Via SoundCloud ×')} RexxyTGBot*"
            )

            sc_title = to_small_caps(title)
            with open(tmp_path, "rb") as audio_file:
                await update.message.reply_audio(
                    audio=audio_file,
                    title=sc_title,
                    performer=to_small_caps("Owned by RexxyTGBot"),
                    duration=dur_ms // 1000,
                    caption=caption,
                    parse_mode="Markdown",
                )

            await status_msg.delete()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    except Exception as e:
        logger.exception("cmd_song error")
        try:
            await status_msg.edit_text(f"❌ *{to_small_caps('Error:')}* `{e}`", parse_mode="Markdown")
        except Exception:
            pass

@only_sudo
async def cmd_spamthreads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        await update.message.reply_text(
            f"🌀 *{to_small_caps('Current spam threads:')}* `{controller.spamemo_threads}`\n"
            f"📝 *{to_small_caps('Usage:')}* `{CMD_PREFIX}spamthreads <20-50>`",
            parse_mode="Markdown"
        )
        return
    try:
        val = int(context.args[0])
        val = controller.set_spamemo_threads(val)
        bot_config["spamemo_threads"] = val
        save_config(bot_config)
        await update.message.reply_text(
            f"✅ *{to_small_caps('Spam threads set to:')}* `{val}`", parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text(f"❌ *{to_small_caps('Invalid number! Must be between 20 and 50.')}*", parse_mode="Markdown")

@only_sudo
async def cmd_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_speed(update, context)

@only_admin
async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    start_t = time.time()
    msg = await update.message.reply_text("📡 *Pinging...*", parse_mode="Markdown")
    latency = round((time.time() - start_t) * 1000, 2)
    response = (
        f"📡『 *{to_small_caps('PONG!')}* 』📡\n\n"
        f"⚡ *{to_small_caps('Latency:')}* `{latency} ms`\n"
        f"🤖 *{to_small_caps('Bots Online:')}* `{len(bots)}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await msg.edit_text(response, parse_mode="Markdown")

@only_admin
async def cmd_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        return await update.message.reply_text(
            f"🎵 *{to_small_caps('Usage:')}* `{CMD_PREFIX}playlist <{to_small_caps('SoundCloud URL or Search Query')}>`",
            parse_mode="Markdown"
        )
    await cmd_song(update, context)

@only_admin
async def cmd_stopraidnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_stopnc(update, context)

# ==================== ADMIN & BOT MANAGEMENT ====================

@only_admin
async def cmd_fjoin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Make all active bots join a Telegram chat, group, channel, or folder link."""
    if context.bot.id != MAIN_BOT_ID:
        return

    if not context.args:
        return await update.message.reply_text(
            f"📁 *{to_small_caps('Usage:')}* `{CMD_PREFIX}fjoin <{to_small_caps('folder/chat/invite link or username')}>`",
            parse_mode="Markdown"
        )

    link = context.args[0].strip()
    status_msg = await update.message.reply_text(
        f"📁 *{to_small_caps('Connecting all bots to join:')}* `{link}`...",
        parse_mode="Markdown"
    )

    target = link
    if "t.me/" in target:
        target = target.split("t.me/")[-1]

    joined_count = 0
    failed_count = 0

    async def bot_join(bot):
        try:
            if hasattr(bot, "join_chat"):
                await bot.join_chat(link)
                return True
            else:
                chat_param = f"@{target.replace('@', '')}"
                await bot.get_chat(chat_param)
                return True
        except Exception:
            return False

    results = await asyncio.gather(*[bot_join(bot) for bot in bots])
    for res in results:
        if res:
            joined_count += 1
        else:
            failed_count += 1

    msg = (
        f"📁『 *{to_small_caps('MULTI-BOT FJOIN COMPLETE')}* 』📁\n\n"
        f"🔗 *{to_small_caps('Link:')}* `{link}`\n"
        f"✅ *{to_small_caps('Bots Joined:')}* `{joined_count}/{len(bots)}`\n"
        f"❌ *{to_small_caps('Failed:')}* `{failed_count}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await status_msg.edit_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_upall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    promoted = []
    failed = []
    for bot in bots:
        try:
            await context.bot.promote_chat_member(
                chat_id=chat_id,
                user_id=bot.id,
                can_change_info=True,
                can_delete_messages=True,
                can_invite_users=True,
                can_restrict_members=True,
                can_pin_messages=True,
                can_manage_chat=True,
            )
            info = await bot.get_me()
            promoted.append(f"@{info.username}")
        except Exception as e:
            failed.append(str(e))

    msg = (
        f"👑『 *{to_small_caps('UPALL COMPLETE')}* 』👑\n\n"
        f"✅ *{to_small_caps('Promoted:')}* `{len(promoted)}`\n"
        f"❌ *{to_small_caps('Failed:')}* `{len(failed)}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    await update.message.reply_text(f"🏃 *{to_small_caps('All bots leaving chat...')}*", parse_mode="Markdown")
    for bot in bots:
        try:
            await bot.leave_chat(chat_id)
        except Exception:
            pass

@only_sudo
async def cmd_bye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    await update.message.reply_text(f"👋 *{to_small_caps('Bots leaving chat...')}*", parse_mode="Markdown")
    for bot in bots:
        try:
            await bot.leave_chat(chat_id)
        except Exception:
            pass

@only_admin
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id

    controller.stop_all(chat_id)

    for k in [k for k in list(active_attacks.keys()) if k.startswith(f"{chat_id}_")]:
        for task in active_attacks[k]:
            task.cancel()
        del active_attacks[k]

    if chat_id in group_tasks:
        for task in group_tasks[chat_id]:
            task.cancel()
        del group_tasks[chat_id]

    if chat_id in spam_tasks:
        for task in spam_tasks[chat_id]:
            task.cancel()
        del spam_tasks[chat_id]

    if chat_id in swipe_tasks:
        for target_tasks in swipe_tasks[chat_id].values():
            for task in target_tasks:
                task.cancel()
        del swipe_tasks[chat_id]

    if chat_id in mexxync_tasks:
        for task in mexxync_tasks[chat_id]:
            task.cancel()
        del mexxync_tasks[chat_id]

    if chat_id in photo_tasks:
        tasks_or_task = photo_tasks[chat_id]
        if isinstance(tasks_or_task, list):
            for t in tasks_or_task:
                t.cancel()
        else:
            tasks_or_task.cancel()
        del photo_tasks[chat_id]

    await update.message.reply_text(f"🛑 *{to_small_caps('All attacks stopped in this chat.')}*", parse_mode="Markdown")

@only_owner
async def cmd_stopall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return

    controller.stop_all()

    for key in list(active_attacks.keys()):
        for task in active_attacks[key]:
            task.cancel()
    active_attacks.clear()

    for tasks in group_tasks.values():
        for task in tasks:
            task.cancel()
    group_tasks.clear()

    for tasks in spam_tasks.values():
        for task in tasks:
            task.cancel()
    spam_tasks.clear()

    for chat_swipes in swipe_tasks.values():
        for target_tasks in chat_swipes.values():
            for task in target_tasks:
                task.cancel()
    swipe_tasks.clear()

    for tasks in mexxync_tasks.values():
        for task in tasks:
            task.cancel()
    mexxync_tasks.clear()

    for tasks_or_task in photo_tasks.values():
        if isinstance(tasks_or_task, list):
            for t in tasks_or_task:
                t.cancel()
        else:
            tasks_or_task.cancel()
    photo_tasks.clear()

    await update.message.reply_text(f"☢️ *{to_small_caps('ALL attacks stopped globally!')}*", parse_mode="Markdown")

@only_sudo
async def cmd_speed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        await update.message.reply_text(
            f"⚡ *{to_small_caps('Current delay:')}* `{get_delay()}s`\n"
            f"📝 *{to_small_caps('Usage:')}* `{CMD_PREFIX}speed <0-5>`",
            parse_mode="Markdown"
        )
        return
    try:
        val = float(context.args[0])
        if set_delay(val):
            bot_config["delay"] = val
            save_config(bot_config)
            await update.message.reply_text(
                f"✅ *{to_small_caps('Speed set! Delay:')}* `{val}s`", parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ *{to_small_caps('Value must be between 0 and 5.')}*", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text(f"❌ *{to_small_caps('Invalid number!')}*", parse_mode="Markdown")

@only_sudo
async def cmd_entrust(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return

    target_user = None
    if update.message and update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
        uid = target_user.id
    elif context.args:
        try:
            uid = int(context.args[0])
        except ValueError:
            return await update.message.reply_text(f"❌ *{to_small_caps('Invalid user ID!')}*", parse_mode="Markdown")
    else:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Reply to a user message or pass ID:')}* `{CMD_PREFIX}entrust`",
            parse_mode="Markdown"
        )

    admin_ids.add(uid)
    save_admins(admin_ids)

    user_name = target_user.first_name if target_user else str(uid)
    msg = (
        f"👑『 *{to_small_caps('SHOGUNATE · SUDO GRANTED')}* 』👑\n\n"
        f"🌸 *{to_small_caps('User:')}* `{user_name}`\n"
        f"🆔 *{to_small_caps('User ID:')}* `{uid}`\n"
        f"✨ *{to_small_caps('Status:')}* `{to_small_caps('Sudo / Admin Granted!')}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return

    target_user = None
    if update.message and update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
        uid = target_user.id
    elif context.args:
        try:
            uid = int(context.args[0])
        except ValueError:
            return await update.message.reply_text(f"❌ *{to_small_caps('Invalid user ID!')}*", parse_mode="Markdown")
    else:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Reply to a user message or pass ID:')}* `{CMD_PREFIX}revoke`",
            parse_mode="Markdown"
        )

    if uid == OWNER_ID:
        return await update.message.reply_text(f"❌ *{to_small_caps('Cannot revoke the owner!')}*", parse_mode="Markdown")

    admin_ids.discard(uid)
    save_admins(admin_ids)

    user_name = target_user.first_name if target_user else str(uid)
    msg = (
        f"🗡️『 *{to_small_caps('SHOGUNATE · SUDO REVOKED')}* 』🗡️\n\n"
        f"👤 *{to_small_caps('User:')}* `{user_name}`\n"
        f"🆔 *{to_small_caps('User ID:')}* `{uid}`\n"
        f"❌ *{to_small_caps('Status:')}* `{to_small_caps('Admin Access Removed!')}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_addbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new bot dynamically and start it."""
    if not context.args:
        await update.message.reply_text(f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}addbot <token>`", parse_mode="Markdown")
        return

    token = context.args[0]
    if not re.match(r"^\d+:[\w-]+$", token):
        await update.message.reply_text(f"⚠️ *{to_small_caps('Invalid token format.')}*", parse_mode="Markdown")
        return

    if token in TOKENS:
        await update.message.reply_text(f"⚠️ *{to_small_caps('This bot is already running!')}*", parse_mode="Markdown")
        return

    try:
        app = build_app(token)
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

        bot_info = await app.bot.get_me()
        bots.append(app.bot)
        apps.append(app)
        TOKENS.append(token)

        bot_config["tokens"] = TOKENS
        save_config(bot_config)

        await update.message.reply_text(
            f"✅ *{to_small_caps('Bot')} @{bot_info.username} {to_small_caps('added & started!')}*\n"
            f"🤖 *{to_small_caps('Total Active Bots:')}* `{len(bots)}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception("Failed to add bot")
        await update.message.reply_text(f"❌ *{to_small_caps('Failed to add bot:')}* `{e}`", parse_mode="Markdown")

@only_sudo
async def cmd_delbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop and remove a running bot by index or username."""
    if not context.args:
        await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}delbot <@{to_small_caps('username')} | {to_small_caps('bot_id')}>`",
            parse_mode="Markdown"
        )
        return

    target = context.args[0].replace("@", "").strip()
    found_idx = None

    for idx, b in enumerate(bots):
        if str(b.id) == target or (b.username and b.username.lower() == target.lower()):
            found_idx = idx
            break

    if found_idx is None:
        return await update.message.reply_text(f"❌ *{to_small_caps('Bot not found!')}*", parse_mode="Markdown")

    target_app = apps[found_idx]
    target_bot = bots[found_idx]
    username = target_bot.username

    try:
        await target_app.updater.stop()
        await target_app.stop()
        await target_app.shutdown()
    except Exception:
        pass

    del apps[found_idx]
    del bots[found_idx]

    if found_idx < len(TOKENS):
        del TOKENS[found_idx]
        bot_config["tokens"] = TOKENS
        save_config(bot_config)

    await update.message.reply_text(
        f"✅ *{to_small_caps('Bot')} @{username} {to_small_caps('removed successfully!')}*\n"
        f"🤖 *{to_small_caps('Remaining Bots:')}* `{len(bots)}`",
        parse_mode="Markdown"
    )

@only_sudo
async def cmd_listbots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all running bot instances with real-time latency."""
    lines = []
    for idx, b in enumerate(bots):
        try:
            info = await b.get_me()
            lines.append(f"{idx+1}. @{info.username} (ID: `{b.id}`) 🟢")
        except Exception:
            lines.append(f"{idx+1}. ID: `{b.id}` 🔴")

    msg = f"🤖『 *{to_small_caps('ACTIVE BOTS LIST')}* 』🤖\n\n" + "\n".join(lines)
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to current active chats."""
    if not context.args:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}broadcast <{to_small_caps('text')}>`", parse_mode="Markdown")

    b_text = " ".join(context.args)
    formatted = f"📢『 *{to_small_caps('ANNOUNCEMENT')}* 』📢\n\n{b_text}\n\n✨ *{to_small_caps('Via')} RexxyTGBot*"
    await update.message.reply_text(formatted, parse_mode="Markdown")

@only_owner
async def cmd_eval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Evaluate raw Python code with full multi-line & async support (Owner only)."""
    if not context.args:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}eval <code>`", parse_mode="Markdown")
    
    code = " ".join(context.args)
    if code.startswith("```python"):
        code = code[9:]
    elif code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    code = code.strip()

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    env = {
        'update': update,
        'context': context,
        'bot': context.bot,
        'bots': bots,
        'apps': apps,
        'bot_config': bot_config,
        'admin_ids': admin_ids,
        'asyncio': asyncio,
        'os': os,
        'sys': sys,
        'time': time,
        'json': json,
        're': re,
    }
    
    exec_code = f"async def __ex():\n" + "\n".join(f"    {line}" for line in code.split("\n"))
    
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture
        exec(exec_code, env)
        res = await env['__ex']()
    except Exception as e:
        res = f"Exception: {e}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    stdout_val = stdout_capture.getvalue().strip()
    stderr_val = stderr_capture.getvalue().strip()
    
    output_parts = []
    if res is not None:
        output_parts.append(f"Return: {res}")
    if stdout_val:
        output_parts.append(f"Stdout:\n{stdout_val}")
    if stderr_val:
        output_parts.append(f"Stderr:\n{stderr_val}")
        
    final_output = "\n\n".join(output_parts) if output_parts else "Executed successfully."
    if len(final_output) > 3500:
        final_output = final_output[:3500] + "\n...[truncated]"

    await update.message.reply_text(
        f"💻 *{to_small_caps('Eval Output:')}*\n```\n{final_output}\n```",
        parse_mode="Markdown"
    )

@only_sudo
async def cmd_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fast in-process restart - stops all bots and re-polls without restarting Python."""
    global RESTART_REQUESTED, RESTART_EVENT
    if context.bot.id != MAIN_BOT_ID:
        return

    try:
        await update.message.reply_text(f"⚡ *{to_small_caps('Refreshing bots...')}*", parse_mode="Markdown")
    except Exception:
        pass

    # 1. Instantly cancel all running attacks / spam tasks
    all_task_lists = (
        list(active_attacks.values())
        + list(spam_tasks.values())
        + list(group_tasks.values())
        + list(mexxync_tasks.values())
        + [list(inner.values()) for inner in swipe_tasks.values()]
    )
    for entry in all_task_lists:
        if isinstance(entry, list):
            for sub in entry:
                if isinstance(sub, list):
                    for t in sub:
                        if not t.done(): t.cancel()
                elif not sub.done():
                    sub.cancel()
        elif hasattr(entry, 'cancel') and not entry.done():
            entry.cancel()

    # 2. Signal watchdogs to restart all bots immediately
    RESTART_REQUESTED = True
    RESTART_EVENT.set()

@only_sudo
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not admin_ids:
        await update.message.reply_text(f"📋 *{to_small_caps('No admins found.')}*", parse_mode="Markdown")
        return
    lines = [f"• `{uid}`" for uid in sorted(admin_ids)]
    await update.message.reply_text(
        f"👑 *{to_small_caps('Admin List')}* 👑\n\n" + "\n".join(lines),
        parse_mode="Markdown"
    )

@only_sudo
async def cmd_setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CMD_PREFIX
    if context.bot.id != MAIN_BOT_ID:
        return
    if not context.args:
        await update.message.reply_text(
            f"📝 *{to_small_caps('Current prefix:')}* `{CMD_PREFIX}`\n"
            f"*{to_small_caps('Usage:')}* `{CMD_PREFIX}setprefix <{to_small_caps('new_prefix')}>`",
            parse_mode="Markdown"
        )
        return
    new_prefix = context.args[0]
    CMD_PREFIX = new_prefix
    bot_config["prefix"] = new_prefix
    save_config(bot_config)
    await update.message.reply_text(f"✅ *{to_small_caps('Prefix changed to:')}* `{new_prefix}`", parse_mode="Markdown")

@only_sudo
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    status_text = await get_status_text()
    media_id = bot_config.get("media_status", DEFAULT_VIDEO_URL)
    media_type = bot_config.get("media_status_type", "video")

    try:
        if media_type == "photo":
            await update.message.reply_photo(photo=media_id, caption=status_text, parse_mode="Markdown")
        else:
            await update.message.reply_video(video=media_id, caption=status_text, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Failed to send status media ({e}), falling back to text status")
        try:
            await update.message.reply_text(status_text, parse_mode="Markdown")
        except Exception:
            clean_text = status_text.replace("*", "").replace("`", "")
            await update.message.reply_text(clean_text)

@only_sudo
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_menu(update, context)

async def _set_menu_media(update: Update, context: ContextTypes.DEFAULT_TYPE, menu_key: str):
    if context.bot.id != MAIN_BOT_ID:
        return
    if not update.message.reply_to_message:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('Please reply to a video or photo!')}*", parse_mode="Markdown")

    msg = update.message.reply_to_message
    media_id = None
    media_type = None
    if msg.video:
        media_id = msg.video.file_id
        media_type = "video"
    elif msg.photo:
        media_id = msg.photo[-1].file_id
        media_type = "photo"
    elif msg.animation:
        media_id = msg.animation.file_id
        media_type = "video"
    else:
        return await update.message.reply_text(f"⚠️ *{to_small_caps('No media found in replied message!')}*", parse_mode="Markdown")

    bot_config[f"media_{menu_key}"] = media_id
    bot_config[f"media_{menu_key}_type"] = media_type
    save_config(bot_config)

    await update.message.reply_text(f"✅ *{to_small_caps('Media updated for')} {to_small_caps(menu_key.upper())} {to_small_caps('menu!')}*", parse_mode="Markdown")


@only_owner
async def cmd_setvideo_godnc(update, context): await _set_menu_media(update, context, "godnc")

@only_owner
async def cmd_setvideo_fontnc(update, context): await _set_menu_media(update, context, "fontnc")

@only_owner
async def cmd_setvideo_fun(update, context): await _set_menu_media(update, context, "fun")

@only_owner
async def cmd_setvideo_main(update, context): await _set_menu_media(update, context, "main")

@only_owner
async def cmd_setvideo_attack(update, context): await _set_menu_media(update, context, "attack")

@only_owner
async def cmd_setvideo_music(update, context): await _set_menu_media(update, context, "music")

@only_owner
async def cmd_setvideo_settings(update, context): await _set_menu_media(update, context, "settings")

@only_owner
async def cmd_setvideo_stop(update, context): await _set_menu_media(update, context, "stop")

@only_owner
async def cmd_setvideo_admin(update, context): await _set_menu_media(update, context, "admin")

@only_owner
async def cmd_setvideo_utility(update, context): await _set_menu_media(update, context, "utility")

@only_owner
async def cmd_setvideo_status(update, context): await _set_menu_media(update, context, "status")

@only_owner
async def cmd_setvideo_over(update, context): await _set_menu_media(update, context, "over")

@only_owner
async def cmd_setvideo_ai(update, context): await _set_menu_media(update, context, "ai")

@only_owner
async def cmd_setvideo_mute(update, context): await _set_menu_media(update, context, "mute")

# ==================== AI & UTILITY SUITE (FROM U.PY) ====================

@only_sudo
async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI Question Answering engine (Pollinations AI with Gemini fallback)"""
    if context.bot.id != MAIN_BOT_ID:
        return

    if not context.args:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}ask <{to_small_caps('question')}>`",
            parse_mode="Markdown"
        )

    query = " ".join(context.args)
    thinking_msg = await update.message.reply_text(f"🤖 *{to_small_caps('AI is thinking...')}*", parse_mode="Markdown")

    answer = None
    # 1. Try Pollinations AI (free, fast, no API key needed)
    try:
        encoded = urllib.parse.quote(query, safe="")
        session = await get_http_session()
        async with session.get(f"https://text.pollinations.ai/{encoded}", timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                answer = (await resp.text()).strip()[:3800]
    except Exception as e:
        logger.debug(f"Pollinations AI request error: {e}")

    # 2. Try Gemini API fallback
    gemini_key = bot_config.get("gemini_api_key", os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6IX-95BeDqO-eq01Ylybvo6p3yfLvYFHGf1VQe3DbWvNQ"))
    if (not answer or len(answer) < 5) and gemini_key:
        try:
            model = bot_config.get("gemini_model", "gemini-1.5-flash")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": query}]}],
                "generationConfig": {"maxOutputTokens": 1024}
            }
            session = await get_http_session()
            async with session.post(url, headers={"x-goog-api-key": gemini_key, "Content-Type": "application/json"}, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                candidates = data.get("candidates") or []
                parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
                answer = "\n".join(str(p.get("text", "")).strip() for p in parts if isinstance(p, dict) and p.get("text")).strip()
        except Exception as e:
            logger.debug(f"Gemini fallback request error: {e}")

    if not answer:
        answer = to_small_caps("Sorry, I could not generate an answer at this moment.")

    msg = (
        f"🤖『 *{to_small_caps('REXXYTGBOT AI')}* 』🤖\n"
        f"━━━━━━━━━━━━━━━\n"
        f"❓ `{query[:80]}`\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{answer}\n\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot 𝐀𝐈* ✨"
    )
    try:
        await thinking_msg.edit_text(msg, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(msg)

@only_sudo
async def cmd_imagine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI Image Generator from text prompt (Flux model via Pollinations)"""
    if context.bot.id != MAIN_BOT_ID:
        return

    if not context.args:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}imagine <{to_small_caps('image prompt')}>`",
            parse_mode="Markdown"
        )

    prompt = " ".join(context.args)
    status_msg = await update.message.reply_text(
        f"🎨 *{to_small_caps('Generating AI Image for:')}* `{prompt[:50]}`...",
        parse_mode="Markdown"
    )

    try:
        encoded = urllib.parse.quote(prompt, safe="")
        seed = random.randint(1, 999999)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&seed={seed}&model=flux"
        session = await get_http_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=45)) as resp:
            if resp.status != 200:
                return await status_msg.edit_text(f"❌ *{to_small_caps('Failed to generate image.')}*", parse_mode="Markdown")
            img_bytes = await resp.read()

        buf = io.BytesIO(img_bytes)
        buf.name = "imagine.jpg"
        caption = (
            f"🎨『 *{to_small_caps('AI GENERATED IMAGE')}* 』🎨\n\n"
            f"📝 *{to_small_caps('Prompt:')}* `{prompt[:150]}`\n\n"
            f"✨ *{to_small_caps('Powered By')} RexxyTGBot 𝐀𝐈* ✨"
        )
        await update.message.reply_photo(photo=buf, caption=caption, parse_mode="Markdown")
        await status_msg.delete()
    except Exception as e:
        logger.exception("cmd_imagine error")
        await status_msg.edit_text(f"❌ *{to_small_caps('Imagine Error:')}* `{e}`", parse_mode="Markdown")

@only_sudo
async def cmd_qrcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate QR Code image from text or URL"""
    if context.bot.id != MAIN_BOT_ID:
        return

    if not context.args:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}qrcode <{to_small_caps('text/link')}>`",
            parse_mode="Markdown"
        )

    text = " ".join(context.args)
    status_msg = await update.message.reply_text(f"📷 *{to_small_caps('Generating QR Code...')}*", parse_mode="Markdown")
    try:
        encoded = urllib.parse.quote(text, safe="")
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=600x600&data={encoded}"
        session = await get_http_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return await status_msg.edit_text(f"❌ *{to_small_caps('Failed to generate QR Code.')}*", parse_mode="Markdown")
            img_bytes = await resp.read()

        buf = io.BytesIO(img_bytes)
        buf.name = "qr.png"
        caption = f"📷 *{to_small_caps('QR Code for:')}* `{text[:80]}`"
        await update.message.reply_photo(photo=buf, caption=caption, parse_mode="Markdown")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ *{to_small_caps('QR Code Error:')}* `{e}`", parse_mode="Markdown")

@only_sudo
async def cmd_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Translate text to specified language"""
    if context.bot.id != MAIN_BOT_ID:
        return

    if len(context.args) < 2:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}translate <{to_small_caps('lang')}> <{to_small_caps('text')}>`\n"
            f"💡 *{to_small_caps('Example:')}* `{CMD_PREFIX}translate hi Hello my friend`",
            parse_mode="Markdown"
        )

    target_lang = context.args[0].lower()
    text = " ".join(context.args[1:])
    try:
        session = await get_http_session()
        url = "https://api.mymemory.translated.net/get"
        params = {"q": text[:500], "langpair": f"en|{target_lang.upper()}"}
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json()
            translated = data.get("responseData", {}).get("translatedText") or text

        msg = (
            f"🌐『 *{to_small_caps('TRANSLATION')}* 』🌐\n\n"
            f"📝 *{to_small_caps('Original:')}* `{text}`\n"
            f"🔤 *{to_small_caps('Language:')}* `{target_lang.upper()}`\n"
            f"✨ *{to_small_caps('Result:')}* `{translated}`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *{to_small_caps('Translation Error:')}* `{e}`", parse_mode="Markdown")


# ==================== MUTE & MODERATION (SOFT-DELETE) ====================

@only_sudo
async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Soft-delete mute user in this chat (silently deletes their messages)."""
    if context.bot.id != MAIN_BOT_ID:
        return

    uid, name = await resolve_target_user(update, context)
    if not uid:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}mute [time] <@user | id>` {to_small_caps('or reply to a message')}\n"
            f"💡 *{to_small_caps('Example:')}* `{CMD_PREFIX}mute 10m` {to_small_caps('or')} `{CMD_PREFIX}mute @user 1h`",
            parse_mode="Markdown"
        )

    dur_str = None
    if context.args:
        for arg in context.args:
            if re.match(r"^\d+[smhd]$", arg.lower()):
                dur_str = arg.lower()
                break

    seconds = parse_time_duration(dur_str) if dur_str else None
    expiry = time.time() + seconds if seconds else None
    dur_text = f"{dur_str}" if dur_str else to_small_caps("Permanent")

    chat_id = update.message.chat_id
    local_muted_store[(chat_id, uid)] = expiry
    save_mutes()

    msg = (
        f"🔇『 *{to_small_caps('USER MUTED')}* 』🔇\n\n"
        f"👤 *{to_small_caps('Target:')}* `{name or uid}`\n"
        f"🆔 *{to_small_caps('User ID:')}* `{uid}`\n"
        f"⏳ *{to_small_caps('Duration:')}* `{dur_text}`\n"
        f"🧹 *{to_small_caps('Action:')}* `{to_small_caps('Messages auto-deleted silently')}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unmute user in this chat."""
    if context.bot.id != MAIN_BOT_ID:
        return

    uid, name = await resolve_target_user(update, context)
    if not uid:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}unmute <@user | id>` {to_small_caps('or reply')}",
            parse_mode="Markdown"
        )

    chat_id = update.message.chat_id
    if (chat_id, uid) in local_muted_store:
        del local_muted_store[(chat_id, uid)]
        save_mutes()
        await update.message.reply_text(
            f"🔊 *{to_small_caps('Unmuted:')}* `{name or uid}` *{to_small_caps('in this chat!')}*",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ *{to_small_caps('User is not muted in this chat!')}*", parse_mode="Markdown")

@only_sudo
async def cmd_gmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global soft-delete mute across all chats."""
    if context.bot.id != MAIN_BOT_ID:
        return

    uid, name = await resolve_target_user(update, context)
    if not uid:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}gmute [time] <@user | id>` {to_small_caps('or reply')}",
            parse_mode="Markdown"
        )

    dur_str = None
    if context.args:
        for arg in context.args:
            if re.match(r"^\d+[smhd]$", arg.lower()):
                dur_str = arg.lower()
                break

    seconds = parse_time_duration(dur_str) if dur_str else None
    expiry = time.time() + seconds if seconds else None
    dur_text = f"{dur_str}" if dur_str else to_small_caps("Permanent")

    global_muted_store[uid] = expiry
    save_mutes()

    msg = (
        f"🌐🔇『 *{to_small_caps('GLOBAL MUTE ACTIVATED')}* 』🔇🌐\n\n"
        f"👤 *{to_small_caps('Target:')}* `{name or uid}`\n"
        f"🆔 *{to_small_caps('User ID:')}* `{uid}`\n"
        f"⏳ *{to_small_caps('Duration:')}* `{dur_text}`\n"
        f"🧹 *{to_small_caps('Scope:')}* `{to_small_caps('All chats auto-deleted')}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_gunmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global unmute user."""
    if context.bot.id != MAIN_BOT_ID:
        return

    uid, name = await resolve_target_user(update, context)
    if not uid:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}gunmute <@user | id>` {to_small_caps('or reply')}",
            parse_mode="Markdown"
        )

    if uid in global_muted_store:
        del global_muted_store[uid]
        save_mutes()
        await update.message.reply_text(
            f"🌐🔊 *{to_small_caps('Global Unmuted:')}* `{name or uid}`!",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ *{to_small_caps('User is not globally muted!')}*", parse_mode="Markdown")

@only_sudo
async def cmd_mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all locally and globally muted users."""
    if context.bot.id != MAIN_BOT_ID:
        return

    now = time.time()
    chat_id = update.message.chat_id
    lines = [f"📋『 *{to_small_caps('MUTED USERS REPORT')}* 』📋\n"]

    local_here = []
    for (cid, uid), exp in list(local_muted_store.items()):
        if cid == chat_id:
            if exp and now > exp:
                local_muted_store.pop((cid, uid), None)
                continue
            rem = f"({int(exp - now)}s left)" if exp else f"({to_small_caps('Permanent')})"
            local_here.append(f"• `{uid}` {rem}")

    lines.append(f"🔇 *{to_small_caps('Local Muted (Here):')}* `{len(local_here)}`")
    if local_here:
        lines.extend(local_here)
    else:
        lines.append(f"_{to_small_caps('No local muted users')}_")

    global_list = []
    for uid, exp in list(global_muted_store.items()):
        if exp and now > exp:
            global_muted_store.pop(uid, None)
            continue
        rem = f"({int(exp - now)}s left)" if exp else f"({to_small_caps('Permanent')})"
        global_list.append(f"• `{uid}` {rem}")

    lines.append(f"\n🌐🔇 *{to_small_caps('Global Muted:')}* `{len(global_list)}`")
    if global_list:
        lines.extend(global_list)
    else:
        lines.append(f"_{to_small_caps('No global muted users')}_")

    save_mutes()
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

@only_admin
async def cmd_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lock current group (auto-delete non-admin messages)."""
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    group_locks.add(chat_id)
    save_locks()
    await update.message.reply_text(
        f"🔒 *{to_small_caps('Group Locked!')}* {to_small_caps('Non-admin messages will be auto-deleted.')}",
        parse_mode="Markdown"
    )

@only_admin
async def cmd_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unlock current group."""
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    group_locks.discard(chat_id)
    save_locks()
    await update.message.reply_text(
        f"🔓 *{to_small_caps('Group Unlocked!')}* {to_small_caps('Members can chat freely.')}",
        parse_mode="Markdown"
    )

@only_admin
async def cmd_purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Purge last N messages in the group."""
    if context.bot.id != MAIN_BOT_ID:
        return
    chat_id = update.message.chat_id
    count = 20
    if context.args:
        try:
            count = min(100, max(1, int(context.args[0])))
        except ValueError:
            pass

    status_msg = await update.message.reply_text(f"🧹 *{to_small_caps('Purging messages...')}*", parse_mode="Markdown")
    start_msg_id = update.message.message_id
    deleted = 0
    for mid in range(start_msg_id, max(1, start_msg_id - count - 10), -1):
        try:
            await context.bot.delete_message(chat_id, mid)
            deleted += 1
            if deleted >= count:
                break
        except Exception:
            pass

    try:
        await status_msg.edit_text(f"✅ *{to_small_caps('Purged')}* `{deleted}` *{to_small_caps('messages!')}*", parse_mode="Markdown")
        await asyncio.sleep(3)
        await status_msg.delete()
    except Exception:
        pass


# ==================== OWNER BOT PROFILE MANAGEMENT (ONLY OWNER) ====================

@only_owner
async def cmd_setbotname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change the display name of all active bots on Telegram (Owner only)."""
    if context.bot.id != MAIN_BOT_ID:
        return

    if not context.args:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}setbotname <{to_small_caps('New Bot Name')}>`",
            parse_mode="Markdown"
        )

    new_name = " ".join(context.args).strip()[:64]
    status_msg = await update.message.reply_text(
        f"⚙️ *{to_small_caps('Updating bot names to')}* `{new_name}` *{to_small_caps('across all bots...')}*",
        parse_mode="Markdown"
    )

    success_count = 0
    fail_count = 0
    session = await get_http_session()

    for b in bots:
        token = getattr(b, "token", None)
        ok = False
        if token:
            try:
                url = f"https://api.telegram.org/bot{token}/setMyName"
                async with session.post(url, json={"name": new_name}, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        ok = True
            except Exception:
                pass

        if not ok:
            try:
                if hasattr(b, "set_my_name"):
                    await b.set_my_name(name=new_name)
                    ok = True
            except Exception:
                pass

        if ok:
            success_count += 1
        else:
            fail_count += 1

    bot_config["bot_name"] = new_name
    save_config(bot_config)

    msg = (
        f"👑『 *{to_small_caps('BOT NAME UPDATE COMPLETE')}* 』👑\n\n"
        f"📝 *{to_small_caps('New Name:')}* `{new_name}`\n"
        f"✅ *{to_small_caps('Successful:')}* `{success_count}`\n"
        f"❌ *{to_small_caps('Failed:')}* `{fail_count}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await status_msg.edit_text(msg, parse_mode="Markdown")

@only_owner
async def cmd_setbotbio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change the bio / description of all active bots on Telegram (Owner only)."""
    if context.bot.id != MAIN_BOT_ID:
        return

    if not context.args:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* `{CMD_PREFIX}setbotbio <{to_small_caps('New Bio / About Description')}>`",
            parse_mode="Markdown"
        )

    bio_text = " ".join(context.args).strip()
    status_msg = await update.message.reply_text(
        f"⚙️ *{to_small_caps('Updating bot bio across all bots...')}*",
        parse_mode="Markdown"
    )

    success_count = 0
    fail_count = 0
    session = await get_http_session()

    for b in bots:
        token = getattr(b, "token", None)
        ok = False
        if token:
            try:
                url_desc = f"https://api.telegram.org/bot{token}/setMyDescription"
                url_short = f"https://api.telegram.org/bot{token}/setMyShortDescription"
                async with session.post(url_desc, json={"description": bio_text}, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    pass
                async with session.post(url_short, json={"short_description": bio_text[:120]}, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        ok = True
            except Exception:
                pass

        if not ok:
            try:
                if hasattr(b, "set_my_description"):
                    await b.set_my_description(description=bio_text)
                    await b.set_my_short_description(short_description=bio_text[:120])
                    ok = True
            except Exception:
                pass

        if ok:
            success_count += 1
        else:
            fail_count += 1

    bot_config["bot_bio"] = bio_text
    save_config(bot_config)

    msg = (
        f"👑『 *{to_small_caps('BOT BIO UPDATE COMPLETE')}* 』👑\n\n"
        f"📝 *{to_small_caps('New Bio:')}* `{bio_text[:120]}`\n"
        f"✅ *{to_small_caps('Successful:')}* `{success_count}`\n"
        f"❌ *{to_small_caps('Failed:')}* `{fail_count}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await status_msg.edit_text(msg, parse_mode="Markdown")

@only_owner
async def cmd_setbotpfp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change the Profile Picture (PFP) of all active bots on Telegram (Owner only)."""
    if context.bot.id != MAIN_BOT_ID:
        return

    img_bytes = None

    # Check reply to photo
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        buf = io.BytesIO()
        await file.download_to_memory(buf)
        img_bytes = buf.getvalue()
    elif context.args and (context.args[0].startswith("http://") or context.args[0].startswith("https://")):
        url = context.args[0]
        try:
            session = await get_http_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    img_bytes = await resp.read()
        except Exception as e:
            return await update.message.reply_text(f"❌ *{to_small_caps('Failed to download image URL:')}* `{e}`", parse_mode="Markdown")

    if not img_bytes:
        return await update.message.reply_text(
            f"⚠️ *{to_small_caps('Usage:')}* {to_small_caps('Reply to an image with')} `{CMD_PREFIX}setbotpfp` {to_small_caps('or pass image URL')}:\n"
            f"`{CMD_PREFIX}setbotpfp https://.../avatar.jpg`",
            parse_mode="Markdown"
        )

    status_msg = await update.message.reply_text(
        f"🖼 *{to_small_caps('Setting bot Profile Picture across all bots...')}*",
        parse_mode="Markdown"
    )

    success_count = 0
    fail_count = 0
    session = await get_http_session()

    for b in bots:
        token = getattr(b, "token", None)
        ok = False

        # 1. Try aiohttp multipart setMyProfilePhoto
        if token:
            try:
                form = aiohttp.FormData()
                form.add_field("photo", img_bytes, filename="avatar.jpg", content_type="image/jpeg")
                url = f"https://api.telegram.org/bot{token}/setMyProfilePhoto"
                async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        ok = True
            except Exception:
                pass

        # 2. Try PTB set_my_profile_photo
        if not ok:
            try:
                if hasattr(b, "set_my_profile_photo"):
                    buf = io.BytesIO(img_bytes)
                    await b.set_my_profile_photo(photo=InputProfilePhotoStatic(photo=buf))
                    ok = True
            except Exception:
                pass

        if ok:
            success_count += 1
        else:
            fail_count += 1

    msg = (
        f"👑『 *{to_small_caps('BOT PFP UPDATE COMPLETE')}* 』👑\n\n"
        f"🖼 *{to_small_caps('Profile Picture Updated')}*\n"
        f"✅ *{to_small_caps('Successful:')}* `{success_count}`\n"
        f"❌ *{to_small_caps('Failed:')}* `{fail_count}`\n\n"
        f"彡━━━━━━━━━━━━━━━━━━━━━彡\n"
        f"✨ *{to_small_caps('Powered By')} RexxyTGBot* ✨"
    )
    await status_msg.edit_text(msg, parse_mode="Markdown")

@only_sudo
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot.id != MAIN_BOT_ID:
        return
    await cmd_menu(update, context)

@only_sudo
async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    uid = update.effective_user.id
    status = to_small_caps("Admin/Sudo") if is_admin(uid) else to_small_caps("User")
    await update.message.reply_text(
        f"🆔 *{to_small_caps('Your Telegram ID:')}* `{uid}`\n"
        f"🔰 *{to_small_caps('Status:')}* `{status}`",
        parse_mode="Markdown"
    )

# Shortcuts for Menus
@only_sudo
async def cmd_m1(u, c): await _send_menu(u, menu_config.get_menu("attack"))
@only_sudo
async def cmd_m2(u, c): await _send_menu(u, menu_config.get_menu("music"))
@only_sudo
async def cmd_m3(u, c): await _send_menu(u, menu_config.get_menu("settings"))
@only_sudo
async def cmd_m4(u, c): await _send_menu(u, menu_config.get_menu("stop"))
@only_sudo
async def cmd_m5(u, c): await _send_menu(u, menu_config.get_menu("admin"))
@only_sudo
async def cmd_m6(u, c): await _send_menu(u, menu_config.get_menu("utility"))
@only_sudo
async def cmd_m7(u, c): await _send_menu(u, menu_config.get_menu("main"))
@only_sudo
async def cmd_m8(u, c): await _send_menu(u, menu_config.get_menu("fontnc"))
@only_sudo
async def cmd_m9(u, c): await _send_menu(u, menu_config.get_menu("fun"))
@only_sudo
async def cmd_m10(u, c): await _send_menu(u, menu_config.get_menu("ai"))
@only_sudo
async def cmd_m11(u, c): await _send_menu(u, menu_config.get_menu("mute"))

async def _send_menu(update, menu):
    try:
        if menu.get("type") in ("video", "photo") and menu.get("video"):
            if menu.get("type") == "photo":
                await update.message.reply_photo(photo=menu["video"], caption=menu["caption"], parse_mode="Markdown")
            else:
                await update.message.reply_video(video=menu["video"], caption=menu["caption"], parse_mode="Markdown")
        else:
            await update.message.reply_text(menu["caption"], parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"{menu.get('caption', '')}", parse_mode="Markdown")

async def handle_prefix_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if context.bot.id != MAIN_BOT_ID:
        return

    text = update.message.text.strip()
    cmd_name = None
    if text.startswith(CMD_PREFIX):
        parts = text.split()
        cmd_name = parts[0][len(CMD_PREFIX):].lower()
        context.args = parts[1:] if len(parts) > 1 else []
    elif text.startswith('/'):
        parts = text.split()
        cmd_name = parts[0][1:].lower()
        if '@' in cmd_name:
            cmd_name = cmd_name.split('@')[0]
        context.args = parts[1:] if len(parts) > 1 else []
    else:
        return

    if cmd_name and '@' in cmd_name:
        cmd_name = cmd_name.split('@')[0]

    cmd_map = {
        # NC Commands
        
        # God NC Commands
        "godnc": cmd_godnc,
        "godncgodspeed": cmd_godncgodspeed,
        "stopgodnc": cmd_stopgodnc,

        # Spotify Command
        "spotify": cmd_spotify,

        # Set Video Commands
        "setvideogodnc": cmd_setvideo_godnc,
        "setvideofontnc": cmd_setvideo_fontnc,
        "setvideofun": cmd_setvideo_fun,
        "nc1": cmd_nc1,
        "nc2": cmd_nc2,
        "nc3": cmd_nc3,
        "nc4": cmd_nc4,
        "nc5": cmd_nc5,
        "nc6": cmd_nc6,
        "raidnc": cmd_raidnc,
        "mexxync": cmd_mexxync,
        "mexxyncgodspeed": cmd_mexxyncgodspeed,
        "himmunc": cmd_mexxync,  # Backward compatibility alias
        "himmuncgodspeed": cmd_mexxyncgodspeed,
        "stopmexxync": cmd_stopmexxync,
        "stophimmunc": cmd_stopmexxync,
        "stopnc": cmd_stopnc,

        # Font NC Commands
        "fontnc": cmd_fontnc,
        "fontnc1": cmd_fontnc1,
        "fontnc2": cmd_fontnc2,
        "fontnc3": cmd_fontnc3,
        "fontnc4": cmd_fontnc4,
        "fancy": cmd_fancy,

        # Spam Commands
        "spam": cmd_spam,
        "raidspam": cmd_raidspam,
        "swipe": cmd_swipe,
        "stopswipe": cmd_stopswipe,
        "spamemo": cmd_spamemo,
        "stopspam": cmd_stopspam,
        "spamthreads": cmd_spamthreads,

        # Fun Commands
        "animequote": cmd_animequote,
        "tts": cmd_tts,
        "8ball": cmd_8ball,
        "coinflip": cmd_coinflip,
        "dice": cmd_dice,
        "truth": cmd_truth,
        "dare": cmd_dare,

        # Slide & Photo Commands
        "targetslide": cmd_targetslide,
        "stopslide": cmd_stopslide,
        "slidespam": cmd_slidespam,
        "stopslidespam": cmd_stopslidespam,
        "savephoto": cmd_savephoto,
        "startphoto": cmd_startphoto,
        "stopphoto": cmd_stopphoto,
        "clearphotos": cmd_clearphotos,

        # System & Admin Commands
        "over": cmd_over,
        "song": cmd_song,
        "playlist": cmd_playlist,
        "fjoin": cmd_fjoin,
        "upall": cmd_upall,
        "leave": cmd_leave,
        "bye": cmd_bye,
        "stop": cmd_stop,
        "stopall": cmd_stopall,
        "stopraidnc": cmd_stopraidnc,
        "speed": cmd_speed,
        "delay": cmd_delay,
        "ping": cmd_ping,
        "entrust": cmd_entrust,
        "revoke": cmd_revoke,
        "channelnc": cmd_channelnc,
        "channelncgodspeed": cmd_channelncgodspeed,
        "channelncfast": cmd_channelncgodspeed,
        "chncgodspeed": cmd_channelncgodspeed,
        "cncgodspeed": cmd_channelncgodspeed,
        "ncchannelgodspeed": cmd_channelncgodspeed,
        "channel_nc_godspeed": cmd_channelncgodspeed,
        "fastchannelnc": cmd_channelncgodspeed,
        "chnc": cmd_channelnc,
        "cnc": cmd_channelnc,
        "ncchannel": cmd_channelnc,
        "channel_nc": cmd_channelnc,
        "stopchannelnc": cmd_stopchannelnc,
        "stopchnc": cmd_stopchannelnc,
        "stopcnc": cmd_stopchannelnc,
        "stopchannelncgodspeed": cmd_stopchannelnc,
        "status": cmd_status,
        "uptime": cmd_uptime,
        "help": cmd_help,
        "menu": cmd_menu,
        "vmenu": cmd_menu,
        "videomenu": cmd_menu,
        "setvideomain": cmd_setvideo_main,
        "setvideoattack": cmd_setvideo_attack,
        "setvideomusic": cmd_setvideo_music,
        "setvideosettings": cmd_setvideo_settings,
        "setvideosstop": cmd_setvideo_stop,
        "setvideoadmin": cmd_setvideo_admin,
        "setvideoutility": cmd_setvideo_utility,
        "setvideoai": cmd_setvideo_ai,
        "setvideomute": cmd_setvideo_mute,
        "setvideostatus": cmd_setvideo_status,
        "setvideoover": cmd_setvideo_over,

        # AI Suite (from u.py)
        "ask": cmd_ask,
        "ai": cmd_ask,
        "gpt": cmd_ask,
        "imagine": cmd_imagine,
        "aiimage": cmd_imagine,
        "draw": cmd_imagine,
        "qrcode": cmd_qrcode,
        "qr": cmd_qrcode,
        "translate": cmd_translate,
        "tr": cmd_translate,

        # Mute & Moderation Suite (Soft-Delete)
        "mute": cmd_mute,
        "unmute": cmd_unmute,
        "gmute": cmd_gmute,
        "gunmute": cmd_gunmute,
        "mutelist": cmd_mutelist,
        "lock": cmd_lock,
        "unlock": cmd_unlock,
        "purge": cmd_purge,
        "delmsg": cmd_purge,

        # Owner Bot Profile Studio (Only Owner)
        "setbotname": cmd_setbotname,
        "setname": cmd_setbotname,
        "botname": cmd_setbotname,
        "setbotbio": cmd_setbotbio,
        "setbio": cmd_setbotbio,
        "setbotdesc": cmd_setbotbio,
        "botbio": cmd_setbotbio,
        "setbotpfp": cmd_setbotpfp,
        "setpfp": cmd_setbotpfp,
        "botpfp": cmd_setbotpfp,

        "start": cmd_start,
        "myid": cmd_myid,
        "id": cmd_myid,
        "addbot": cmd_addbot,
        "delbot": cmd_delbot,
        "listbots": cmd_listbots,
        "broadcast": cmd_broadcast,
        "eval": cmd_eval,
        "restart": cmd_refresh,
        "reboot": cmd_refresh,
        "refresh": cmd_refresh,

        # Menu Shortcuts
        "m1": cmd_m1, "m2": cmd_m2, "m3": cmd_m3,
        "m4": cmd_m4, "m5": cmd_m5, "m6": cmd_m6,
        "m7": cmd_m7, "m8": cmd_m8, "m9": cmd_m9,
        "m10": cmd_m10, "m11": cmd_m11,
    }

    if cmd_name in cmd_map:
        await cmd_map[cmd_name](update, context)

def build_app(token):
    request = HTTPXRequest(
        connection_pool_size=1000,
        connect_timeout=5.0,
        read_timeout=5.0,
        write_timeout=5.0,
        pool_timeout=2.0,
        http_version="1.1",
    )

    app = Application.builder().token(token).request(request).build()

    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT, handle_prefix_commands))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, auto_replies), group=1)

    return app

# ==================== RUN ALL BOTS ====================

async def periodic_system_cleanup():
    """Periodically prune finished tasks and trigger garbage collection to prevent memory leaks and slowdowns."""
    while True:
        try:
            await asyncio.sleep(30)
            for k in list(active_attacks.keys()):
                active_attacks[k] = [t for t in active_attacks[k] if not t.done()]
                if not active_attacks[k]:
                    del active_attacks[k]

            for k in list(spam_tasks.keys()):
                spam_tasks[k] = [t for t in spam_tasks[k] if not t.done()]
                if not spam_tasks[k]:
                    del spam_tasks[k]

            for k in list(group_tasks.keys()):
                group_tasks[k] = [t for t in group_tasks[k] if not t.done()]
                if not group_tasks[k]:
                    del group_tasks[k]

            for k in list(mexxync_tasks.keys()):
                mexxync_tasks[k] = [t for t in mexxync_tasks[k] if not t.done()]
                if not mexxync_tasks[k]:
                    del mexxync_tasks[k]

            for cid in list(swipe_tasks.keys()):
                for target in list(swipe_tasks[cid].keys()):
                    swipe_tasks[cid][target] = [t for t in swipe_tasks[cid][target] if not t.done()]
                    if not swipe_tasks[cid][target]:
                        del swipe_tasks[cid][target]
                if not swipe_tasks[cid]:
                    del swipe_tasks[cid]

            for k in list(photo_tasks.keys()):
                t_val = photo_tasks[k]
                if isinstance(t_val, list):
                    photo_tasks[k] = [t for t in t_val if not t.done()]
                    if not photo_tasks[k]:
                        del photo_tasks[k]
                elif t_val.done():
                    del photo_tasks[k]

            gc.collect()
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(5)

# ==================== RUN ALL BOTS ====================

async def run_all_bots():
    global bots, apps, MAIN_BOT_ID, RESTART_REQUESTED, RESTART_EVENT

    # Initialise the restart event here (inside the running event loop)
    RESTART_EVENT = asyncio.Event()
    RESTART_REQUESTED = False

    unique_tokens = list(set(t.strip() for t in TOKENS if t.strip()))

    print("🎀 STARTING ⋆ ˚｡⋆👑 RexxyTGBot 👑⋆｡˚ ULTRA BOTS 🎀")
    print("=" * 60)
    print(f"📌 Command Prefix: `{CMD_PREFIX}`")
    print(f"🧵 Thread Pool: 200 workers")
    print(f"⚡ Max Concurrent: {MAX_CONCURRENT_TASKS}")
    print(f"🚀 Speed Mode: INSTANT (0 delay)")
    print("=" * 60)

    async def start_bot_once(token):
        """Build, initialize and start polling for a single token. Returns (app, bot) or (None, None)."""
        try:
            app = build_app(token)
            await app.initialize()
            await app.start()
            await app.updater.start_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=False,
            )
            bot_info = await app.bot.get_me()
            print(f"✅ @{bot_info.username} - ONLINE")
            return app, app.bot
        except Exception as e:
            print(f"❌ Failed for token {token[:10]}...: {e}")
            try:
                await app.stop()
            except Exception:
                pass
            try:
                await app.shutdown()
            except Exception:
                pass
            return None, None

    async def _shutdown_bot(app, bot):
        """Instantly tear down a single bot app."""
        try:
            if bot in bots:
                bots.remove(bot)
            if app in apps:
                apps.remove(app)
        except Exception:
            pass
        for fn in (app.updater.stop, app.stop, app.shutdown):
            try:
                await fn()
            except Exception:
                pass

    async def bot_watchdog(token, index):
        """Watchdog that keeps a single bot alive with auto-reconnect and fast restart support."""
        global RESTART_REQUESTED, RESTART_EVENT, MAIN_BOT_ID
        backoff = 5
        app = None
        bot = None

        while True:
            # ── Start the bot ──
            app, bot = await start_bot_once(token)
            if app and bot:
                backoff = 5  # reset on success
                if bot not in bots:
                    bots.append(bot)
                    apps.append(app)
                    if MAIN_BOT_ID is None:
                        MAIN_BOT_ID = bot.id

                # ── Monitor: normal disconnection OR manual restart signal ──
                try:
                    while app.updater.running:
                        # Check every 0.5 s so restart feels instant
                        if RESTART_EVENT.is_set():
                            break
                        await asyncio.sleep(0.5)
                except asyncio.CancelledError:
                    await _shutdown_bot(app, bot)
                    return
                except Exception:
                    pass

                was_restart = RESTART_EVENT.is_set()

                # ── Tear down cleanly ──
                await _shutdown_bot(app, bot)
                app, bot = None, None

                if was_restart:
                    # Manual restart: reconnect immediately (no backoff)
                    print(f"🔄 Bot {index} restarting instantly...")
                    continue
                else:
                    print(f"⚠️ Bot {index} disconnected - reconnecting in {backoff}s...")
            else:
                if RESTART_EVENT.is_set():
                    # Restart requested but bot wasn't running - just continue
                    print(f"🔄 Bot {index} was offline, coming back up...")
                    RESTART_EVENT.clear()
                    RESTART_REQUESTED = False
                    continue
                print(f"⚠️ Bot {index} failed to start - retrying in {backoff}s...")

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)  # exponential backoff on natural failure

    # Start all watchdogs concurrently
    watchdog_tasks = [
        asyncio.create_task(bot_watchdog(token, i + 1))
        for i, token in enumerate(unique_tokens)
    ]

    # Wait a moment so bots can start printing their status
    await asyncio.sleep(5)

    if not bots:
        print("❌ No bots started successfully! Watchdogs will keep retrying...")
    else:
        print("=" * 60)
        print(f"🎉 {len(bots)} BOTS ONLINE - AUTO-RECONNECT ACTIVE 🎉")
        print(f"📌 Main bot ID: {MAIN_BOT_ID}")
        print("=" * 60)

    asyncio.create_task(periodic_system_cleanup())

    async def restart_monitor():
        """Watches for RESTART_EVENT and prints a confirmation once all bots are back."""
        global RESTART_REQUESTED, RESTART_EVENT
        while True:
            await RESTART_EVENT.wait()
            # Give watchdogs ~3 s to reconnect all bots
            await asyncio.sleep(3)
            RESTART_EVENT.clear()
            RESTART_REQUESTED = False
            print(f"✅ RESTART COMPLETE - {len(bots)} bots back online.")

    asyncio.create_task(restart_monitor())

    # Keep running forever - watchdogs handle restarts automatically
    try:
        await asyncio.gather(*watchdog_tasks)
    except asyncio.CancelledError:
        for t in watchdog_tasks:
            t.cancel()


if __name__ == "__main__":
    while True:
        try:
            asyncio.run(run_all_bots())
        except KeyboardInterrupt:
            print("\n🛑 SHUTTING DOWN...")
            try:
                asyncio.run(close_http_session())
            except Exception:
                pass
            THREAD_POOL.shutdown(wait=False)
            print("🎀 SHUTDOWN COMPLETE 🎀")
            break
        except Exception as e:
            print(f"[CRITICAL] Main loop crashed: {e} - restarting in 10s...")
            import traceback
            traceback.print_exc()
            time.sleep(10)
