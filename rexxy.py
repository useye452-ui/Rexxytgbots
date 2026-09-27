# 𝗔𝗟𝗘𝗫_𝗕𝗔𝗔𝗣

import asyncio
import random
import json
import time
import io
import datetime
import logging
import sys

from telegram.ext import Application, MessageHandler, filters
from telegram.error import RetryAfter, TimedOut, NetworkError, BadRequest

# Suppress noisy logs, only show warnings+
logging.basicConfig(level=logging.WARNING)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("telegram").setLevel(logging.ERROR)

clock_emojis = ["🕛", "🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕜", "🕝", "🕞", "🕟", "🕠", "🕡", "🕢", "🕣", "🕤", "🕥", "🕦", "🕧"]
flower_emojis = ["🌸", "🌺", "🌻", "🌹", "🌷", "🌼", "💮", "🪷", "💐"]
animal_emojis = ["🐶", "🐱", "🐭", "🐹", "🐰", "🦊", "🐻", "🐼", "🐨", "🐯", "🦁", "🐮", "🐷", "🐸", "🐵"]
heart_emojis = ["❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "🤎", "🩷", "🩵", "🩶", "💖", "💗", "💓", "💞", "💕", "💘", "💝", "❤️‍🔥", "❤️‍🩹"]
fruit_emojis = ["🍎", "🍌", "🍉", "🍇", "🍓", "🍈", "🍒", "🍑", "🥭", "🍍", "🥥", "🥝", "🍅", "🥑", "🍏", "🍐"]
ncspam_emojis = ["❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "🤎", "🩷", "🩵", "🩶", "💖", "💗", "💓", "💞", "💕", "💘", "💝", "❤️‍🔥", "❤️‍🩹", "💔", "🫀", "💟", "🔥", "🌙", "⭐", "🌟", "💫", "✨", "🎀", "🦋"]

# ═══════════════════════════════════════
#                 CONFIG
# ═══════════════════════════════════════

BOT_TOKENS = [
"8792667118:AAG_NNL_tf86JDhc2Bc6hzqtVgAPNHHiLto",
"7774852809:AAHu6FEEejYgdQlXbmJq2kR6b2YMzoyBz-w",
"8988120622:AAGdWRLgB5ysoPh1bvM3ogPgbUTb8xMZmlE",
"8782835985:AAFiDidgR3SQ8PVrbnq0tdUXSkVJERMjB8o",
"8959207411:AAFAGWqyfE_M1XClgaSP3iPXuHHkjy6f2cc"
"8971006917:AAHCby1cyimy49D_0G7CZXusRLloHV5sLYw",
"8782835985:AAFiDidgR3SQ8PVrbnq0tdUXSkVJERMjB8o",
"8971006917:AAHCby1cyimy49D_0G7CZXusRLloHV5sLYw"
] # REPLACE WITH YOUR TOKENS

OWNER_ID = 8611807630 # YOUR CHAT ID

DELAY       = 0.0001  # NC loop delay — max speed, RetryAfter handles limit
SPAM_DELAY  = 0.0001  # Spam loop delay — ultra fast
NCSPAM_DELAY= 0.001  # Combo loop delay — fast synced
PFP_DELAY   = 0.0001  # PFP loop delay (seconds)
TIME_DELAY  = 0.1  # Time NC delay (seconds)
FLOWER_DELAY= 0.1  # Flower NC delay
ANIMAL_DELAY= 0.1  # Animal NC delay
HEART_DELAY = 0.1  # Heart NC delay
FRUIT_DELAY = 0.1  # Fruit NC delay
PREFIX      = "!"  # Bot command prefix
DEL_DELAY   = 0    # Auto-delete delay (0 = instant)

# ═══════════════════════════════════════
#               TITLE LISTS
# ═══════════════════════════════════════

nc_titles = [
   "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🧡𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒💪𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌍𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒💛𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒👏𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌎𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🩵𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒👍𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌏𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🩵𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🙌𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒☄️𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒‍💙𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒👐𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌑𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒💙𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🤲𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌒𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒💜𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🤜‍↕️𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌓‍↔️𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🤎𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🤛𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌔𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🖤𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒✊𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌔𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒❤️𝆒", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🫳𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌕𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒‍🩶𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🫴𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌖𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🤍𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🫲𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🌖𝆓",
    "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🩷𝆓", "𝘈𝘈𝘑 𝘛𝘌𝘙𝘐 𝘔𝘈 𝘒 𝘉𝘏𝘖𝘚𝘋𝘌 𝘗𝘙 𝘏𝘈𝘔𝘓𝘈 𝆒🫸𝆓",
]

toxic_titles = [
     " 𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸 ⇝ ༼ 🍓༽ ", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍈༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🫜༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍒༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍐༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥥༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍎༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🫛༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥔༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍅༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥬༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🧅༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🌶️༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🫑༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🫚༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍉༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍏༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🫘༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍑༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥝༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🌰༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍊༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥑༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥜༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍐༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🫒༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍞༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥭༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥦༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🫓༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍍༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥒༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥯༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍌༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🫐༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🧇༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍋༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍇༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍳༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🌽༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍆༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🥩༽",
    "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍋‍🟩༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍠༽", "𝐾𝐵𝐴𝐷𝐼 𝑊𝐴𝐿𝐸  ⇝ ༼ 🍟༽",
]

emoji_list = [
    "✩‧₊˚😂˖ ᡣ𐭩 ⊹", "✩‧₊˚😭˖ ᡣ𐭩 ⊹", "✩‧₊˚🤣˖ ᡣ𐭩 ⊹", "✩‧₊˚🤪˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🤗˖ ᡣ𐭩 ⊹", "✩‧₊˚🤬˖ ᡣ𐭩 ⊹", "✩‧₊˚😤˖ ᡣ𐭩 ⊹", "✩‧₊˚😒˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🙄˖ ᡣ𐭩 ⊹", "✩‧₊˚😰˖ ᡣ𐭩 ⊹", "✩‧₊˚😓˖ ᡣ𐭩 ⊹", "✩‧₊˚😲˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🤮˖ ᡣ𐭩 ⊹", "✩‧₊˚😵˖ ᡣ𐭩 ⊹", "✩‧₊˚🤧˖ ᡣ𐭩 ⊹", "✩‧₊˚😇˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🤢˖ ᡣ𐭩 ⊹", "✩‧₊˚😈˖ ᡣ𐭩 ⊹", "✩‧₊˚👻˖ ᡣ𐭩 ⊹", "✩‧₊˚😖˖ ᡣ𐭩 ⊹",
    "✩‧₊˚😣˖ ᡣ𐭩 ⊹", "✩‧₊˚😎˖ ᡣ𐭩 ⊹", "✩‧₊˚😹˖ ᡣ𐭩 ⊹", "✩‧₊˚😻˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🙈˖ ᡣ𐭩 ⊹", "✩‧₊˚🙉˖ ᡣ𐭩 ⊹", "✩‧₊˚🙊˖ ᡣ𐭩 ⊹", "✩‧₊˚❤️˖ ᡣ𐭩 ⊹",
    "✩‧₊˚💘˖ ᡣ𐭩 ⊹", "✩‧₊˚💞˖ ᡣ𐭩 ⊹", "✩‧₊˚💕˖ ᡣ𐭩 ⊹", "✩‧₊˚💖˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🖤 ᡣ𐭩 ⊹", "✩‧₊˚🩶˖ ᡣ𐭩 ⊹", "✩‧₊˚❤️‍🔥˖ ᡣ𐭩 ⊹", "✩‧₊˚❤️‍🩹˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🩵˖ ᡣ𐭩 ⊹", "✩‧₊˚🩷˖ ᡣ𐭩 ⊹", "✩‧₊˚🔥˖ ᡣ𐭩 ⊹", "✩‧₊˚🎀˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🥤˖ ᡣ𐭩 ⊹", "✩‧₊˚💀˖ ᡣ𐭩 ⊹", "✩‧₊˚💢˖ ᡣ𐭩 ⊹", "✩‧₊˚🌙˖ ᡣ𐭩 ⊹",
    "✩‧₊˚💔˖ ᡣ𐭩 ⊹", "✩‧₊˚🕊️˖ ᡣ𐭩 ⊹", "✩‧₊˚💫˖ ᡣ𐭩 ⊹", "✩‧₊˚💗˖ ᡣ𐭩 ⊹",
    "✩‧₊˚💋˖ ᡣ𐭩 ⊹", "✩‧₊˚💦˖ ᡣ𐭩 ⊹", "✩‧₊˚💐˖ ᡣ𐭩 ⊹", "✩‧₊˚🌹˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🥀˖ ᡣ𐭩 ⊹", "✩‧₊˚🌺˖ ᡣ𐭩 ⊹", "✩‧₊˚🌷˖ ᡣ𐭩 ⊹", "✩‧₊˚🌸˖ ᡣ𐭩 ⊹",
    "✩‧₊˚💮˖ ᡣ𐭩 ⊹", "✩‧₊˚🏵️˖ ᡣ𐭩 ⊹", "✩‧₊˚🌻˖ ᡣ𐭩 ⊹", "✩‧₊˚🌼˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🍂˖ ᡣ𐭩 ⊹", "✩‧₊˚🍃˖ ᡣ𐭩 ⊹", "✩‧₊˚🌊˖ ᡣ𐭩 ⊹", "✩‧₊˚❄️˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🌀˖ ᡣ𐭩 ⊹", "✩‧₊˚🌪️˖ ᡣ𐭩 ⊹", "✩‧₊˚🐕˖ ᡣ𐭩 ⊹", "✩‧₊˚🍫˖ ᡣ𐭩 ⊹",
    "✩‧₊˚🥂 ᡣ𐭩 ⊹", "✩‧₊˚🍷˖ ᡣ𐭩 ⊹", "✩‧₊˚👾˖ ᡣ𐭩 ⊹", "✩‧₊˚🎭˖ ᡣ𐭩 ⊹",
    "✩‧₊˚⚙️ ᡣ𐭩 ⊹", "✩‧₊˚⚰️˖ ᡣ𐭩 ⊹", "✩‧₊˚♥️˖ ᡣ𐭩 ⊹",
]

reply_list = [
     "पिल्ले Lᴜɴᴅ pe उछल ?🧡",
    "toxic baap hai rndyke",
    "_✍🏻 𝐘ᴇ 𝐃ᴇᴋʜ ˢᶜʳⁱᵖᵗ ˡⁱᵏʰ ʳᵃʰᵃ ʰᵘ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐁ʜᴏsᴅᴇ 𝐌ᴇɪɴ 😂😂😂",
    "Sᴜᴀʀ Tᴇʀɪ Mᴀᴀ Kɪ Cʜᴜᴛ 😌😌💤💤",
    "𝐓ᴜ 𝐈ᴅ𝐑 𝐂ᴏᴍᴇʙᴀᴄ𝐊 𝐃ᴇᴛ𝐀 𝐑ᴇ𝐇 𝐆ʏ𝐀 𝐔ᴅʜ𝐑 toxic 𝐓ᴇʀ𝐈 𝐌ᴀ𝐀 𝐂ʜᴏᴅ 𝐆ʏ𝐀 🩷🩶🩵",
    "Choding ho rhi hai teri maa ki 😬👨🏻‍💻🔥",
    "Teri Maa Ki Chut Mein Loda Daluga Beta 🥵💯",
    "🧐 Teri maa ka bh🤪sda dikh rha hai 😎",
    "😉🔥 Cya 😉🔥 re 😉 🔥 sapri 😉🔥 try 😉🔥 maa 😉🔥 tujh 😉🔥 nehlati 😉🔥 ny 😉🔥 ey 😉🔥 Cya 😉🔥",
    "Oye Madarchod Uth 😤😡🥵 Teri Maa Ka Choding Tem 😈👻🦶🏻",
    "Teri Maa Ko Football ⚽ bnake uske 𝗕𝗛😈𝗦𝗗𝗘 pe laat 🦶🏻 marunga 🤩🔥",
    "इस मंगलवार को ᴛᴇʀɪ ᴍᴀᴀ ᴋɪ ᴄʜᴜᴛ ᴋᴀ ʙʜᴀɴᴅᴀʀᴀ ʜᴏɢᴀ 😈😘👌🏻",
    "TᗴᖇI ᗰᗩᗩ Kᗩ ᗷOOᖇ ᗷᗴTᗩ 🤣🤮🔥😏🔥😂💞🌧️",
    "𝙈𝘼𝘼 𝙆𝙀 𝙇𝙊𝘿𝙀 🤮",
    "𝗣ᴇʜʟ𝗘 𝗧ᴇʀ𝗜 𝗕ᴇʜᴇ𝗡 𝗖ʜᴏᴅᴜɢ𝗔 𝗙ɪ𝗥 𝗧ᴇʀ𝗜 𝗠ᴀ𝗔 😆😂😆🔥🤢😂🤍😤",
    "ƇӇƲƤ ƬЄƦƖ Mƛƛ Ƙƛ ƁӇƠƧƊƛ ♻️",
    "𝘚𝘱𝘢𝘮𝘮𝘦𝘳 𝘣𝘢𝘯𝘦𝘨𝘢 𝘳𝘢𝘯𝘥𝘪𝘬𝘦 🤢🔥",
    "𝐀ᴊ𝐀 𝐌ᴄ 𝐁ᴀɴᴀ𝐔 𝐓ᴜᴊʜ𝐄 𝐒ᴘᴀᴍᴍᴇ𝐑 👻💥🤍😹👑",
    "𝘣𝘰𝘭 #toxic 𝘉𝘢𝘢𝘱 👑",
    "😍 Teri 😡 Randi 🤪 Maa 😤 Ko 😎 Pel 😭 Dunga 😍",
    "Idhar Aa Beta 🤪💔 Teri Maa Chodu 😂😘",
    "Oye bihari kaam pe ja 🔥⛏️🔥⛏️⛏️🔥⛏️💞💞🔥💞⛏️🔥💞⛏️⛏️",
    "Sᴄʀɪᴩᴛꜱ Kᴇɴɢ <> 𝐄 x ᴏ ʀ ᴄ ɪ ꜱ ᴛ 🌸👑 !!",
    "Teri Maa Bio Mein #Proudrandi 💔🥀 likhti hai 🤩🔥🩷",
    "Rndyk lund se utr 😩👏🏻",
    "bot by toxicmafias",
    "Tu hasta reh gya yaaro mein 😁💯💔 Teri maa chudgyi baazaro mein 😂🌹",
    "Teri Maa Chudwa denge re 🪖🔥⛏️🥴🤪💔🩷💯😁😩💞",
    "🩷 Gud ❤️ nyt 🧡 rndyk 💛 kal 🩵 Aaunga 💙 Teri 🖤 Maa 🩶 Chodne 🤍",
    "🥶 Are 😱 Mc 😩 Ye 🤔 Kaise 🤪 Kiya 😏 Teri 😎 Maa 😬 Randi 🙄 Hai 🤮 100% 😂",
    "🩷🩵🤍🩶🖤❤️💚 Ye sare dill teri maa k naam beta 😂😜🔥",
    "Hat peche hat tera exo baap aya 😂😂🥴😹🤲🏻💪🏻",
    "Leave le rndyk psnd nai aya tu meko 🤢👎🏻",
    "Teri maa chodu 💯 if yes then reply to my message 💀💀💀💪🏻🔥💯👆🏻💔😂😂💔💔💔",
    "#toxic 𝐁ᴀᴀᴘ 𝐊ᴏ 𝐃ʙᴀ ɴʜɪ 𝐏ᴀʀᴇ ᴄʏᴀ?? 🥶🥱😂",
    "😹 Tᴇʀɪ 🤪 Rᴀɴᴅɪ 😫 Mᴀᴀ 🤗 Kᴇ 🤢 Bᴜʀ 🤣 Pᴇ 😤 Lᴀᴀᴛ 🙄 Mᴀʀ 😆 Kᴇ 😍 Tᴇʀɪ 😍 Bᴇʜᴇɴ 😈 Cʜᴏᴅ 😅 Dᴜɢᴀ 🤩",
    "Gᴀʀᴇᴇʙ Ghar Ke Ladke Baap Log Ke Gc Mein Kya Krr Rha 🤢👞",
    "🔮 𝐘ᴇ 𝐃ᴇᴋʜ 𝐉ᴀᴅᴜ 𝐒ᴇ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐂ʜᴏᴅ 𝐃ɪyᴀ 😂🪄😂🪄",
    "Teri Maa Ko बाहुबली style mein chodunga 🥶💔🤪😹",
    "Tumhare Pitashree toxic x exo 💯🔥🗿🌙",
]

# ═══════════════════════════════════════
#              SUDO HELPERS
# ═══════════════════════════════════════

def load_sudo():
    try:
        with open("sudo.json", "r") as f:
            return json.load(f).get("sudo_users", [])
    except Exception:
        return []

def save_sudo(sudo_list):
    with open("sudo.json", "w") as f:
        json.dump({"sudo_users": sudo_list}, f, indent=4)

def is_sudo(user_id):
    return user_id == OWNER_ID or user_id in load_sudo()

# ═══════════════════════════════════════
#              DECORATORS
# ═══════════════════════════════════════

def only_sudo(func):
    async def wrapper(update, context):
        if not is_sudo(update.effective_user.id):
            return await update.message.reply_text("You are not sudo ❌")
        return await func(update, context)
    return wrapper

def only_owner(func):
    async def wrapper(update, context):
        if update.effective_user.id != OWNER_ID:
            return await update.message.reply_text("Only toxic Can Do This 🧃")
        return await func(update, context)
    return wrapper

# ═══════════════════════════════════════
#            TASK STORAGE
# ═══════════════════════════════════════

nc_tasks        = {}
toxic_tasks      = {}
emo_tasks       = {}
spam_tasks      = {}
reply_tasks     = {}
pfp_tasks       = {}
timenc_tasks    = {}
flower_tasks    = {}
animal_tasks    = {}
heart_tasks     = {}
fruit_tasks     = {}
ncspam_tasks    = {}
autodel_chats   = set()  # set of (bot_id, chat_id) where auto-delete is ON

def key(context, chat_id):
    return (context.bot.id, chat_id)

# ═══════════════════════════════════════
#            LOOP FUNCTIONS
# ═══════════════════════════════════════

async def nc_loop(k, prefix, context):
    while k in nc_tasks:
        try:
            await context.bot.set_chat_title(k[1], f"{prefix} {random.choice(nc_titles)}")
            await asyncio.sleep(DELAY)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(3)
        except Exception:
            await asyncio.sleep(2)

async def toxic_loop(k, prefix, context):
    while k in toxic_tasks:
        try:
            await context.bot.set_chat_title(k[1], f"{prefix} {random.choice(toxic_titles)}")
            await asyncio.sleep(DELAY)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(3)
        except Exception:
            await asyncio.sleep(2)

async def emo_loop(k, prefix, context):
    while k in emo_tasks:
        try:
            emo1 = random.choice(emoji_list)
            emo2 = random.choice(emoji_list)
            await context.bot.set_chat_title(k[1], f"{emo1} {prefix} {emo2}")
            await asyncio.sleep(DELAY)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(3)
        except Exception:
            await asyncio.sleep(2)

async def spam_loop(k, text, context):
    while k in spam_tasks:
        try:
            await context.bot.send_message(k[1], text)
            await asyncio.sleep(SPAM_DELAY)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(2)
        except Exception:
            await asyncio.sleep(1)

async def reply_loop(k, msg_id, context):
    while k in reply_tasks:
        try:
            for _ in range(15):
                if k not in reply_tasks:
                    return
                await context.bot.send_message(
                    k[1],
                    random.choice(reply_list),
                    reply_to_message_id=msg_id
                )
                await asyncio.sleep(0.2)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(2)
        except Exception:
            await asyncio.sleep(1)

async def pfp_loop(k, file_id, context):
    while k in pfp_tasks:
        try:
            tg_file = await context.bot.get_file(file_id)
            photo_bytes = io.BytesIO()
            await tg_file.download_to_memory(photo_bytes)
            photo_bytes.seek(0)
            photo_bytes.name = "pfp.jpg"
            await context.bot.set_chat_photo(k[1], photo=photo_bytes)
            await asyncio.sleep(PFP_DELAY)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(5)
        except Exception:
            await asyncio.sleep(5)

async def timenc_loop(k, prefix, context):
    while k in timenc_tasks:
        try:
            dt = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
            time_str = dt.strftime("%I:%M %p")
            emo1 = random.choice(clock_emojis)
            emo2 = random.choice(clock_emojis)
            title = f"{emo1} {prefix} {time_str} {emo2}"
            await context.bot.set_chat_title(k[1], title)
            await asyncio.sleep(TIME_DELAY)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(3)
        except Exception:
            await asyncio.sleep(2)

async def flower_loop(k, prefix, context):
    while k in flower_tasks:
        try:
            emo1 = random.choice(flower_emojis)
            emo2 = random.choice(flower_emojis)
            title = f"{emo1} {prefix} {emo2}"
            await context.bot.set_chat_title(k[1], title)
            await asyncio.sleep(FLOWER_DELAY)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(3)
        except Exception:
            await asyncio.sleep(2)

async def animal_loop(k, prefix, context):
    while k in animal_tasks:
        try:
            emo1 = random.choice(animal_emojis)
            emo2 = random.choice(animal_emojis)
            title = f"{emo1} {prefix} {emo2}"
            await context.bot.set_chat_title(k[1], title)
            await asyncio.sleep(ANIMAL_DELAY)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(3)
        except Exception:
            await asyncio.sleep(2)

async def heart_loop(k, prefix, context):
    while k in heart_tasks:
        try:
            emo1 = random.choice(heart_emojis)
            emo2 = random.choice(heart_emojis)
            title = f"{emo1} {prefix} {emo2}"
            await context.bot.set_chat_title(k[1], title)
            await asyncio.sleep(HEART_DELAY)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(3)
        except Exception:
            await asyncio.sleep(2)

async def fruit_loop(k, prefix, context):
    while k in fruit_tasks:
        try:
            emo1 = random.choice(fruit_emojis)
            emo2 = random.choice(fruit_emojis)
            title = f"{emo1} {prefix} {emo2}"
            await context.bot.set_chat_title(k[1], title)
            await asyncio.sleep(FRUIT_DELAY)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except (TimedOut, NetworkError):
            await asyncio.sleep(3)
        except Exception:
            await asyncio.sleep(2)

def make_ncspam_msgs(target):
    line1 = f"{target}   Sʟᴀᴠᴇ Tᴜ Iᴛɴᴀ Kᴀᴍᴢᴏʀ Kʏᴜ Hᴀɪ 𓍯🩷\n"
    line2 = f"{target}   घिनौने पिल्लै ,,,,,,,༈ 😩\n"
    line3 = f"{target}   ᴛᴇʀɪ ᴍᴏᴍ ɴᴏ ₁ ʜɪᴊᴅɪ 𓂃 ˖💛་༘࿐\n"
    line4 = f" {target}   Cнυρ gнιησηe тαттe ᥫ᭡😠\n"
    return [
        line1 * 22,
        line2 * 29,
        line3 * 25,
        line4 * 24,
    ]

async def ncspam_combo_loop(k, target, context):
    """Single interleaved loop: spam → NC → spam → NC... both get equal turns."""
    msgs = make_ncspam_msgs(target)
    while k in ncspam_tasks:
        # Step 1: Send spam message
        try:
            await context.bot.send_message(k[1], random.choice(msgs))
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except Exception:
            pass

        await asyncio.sleep(NCSPAM_DELAY)
        if k not in ncspam_tasks:
            break

        # Step 2: Change NC title
        try:
            emo = random.choice(ncspam_emojis)
            title = f"{target}𓂃˖˳·˖ ִֶָ ⋆{emo}͙⋆ ִֶָ˖·˳˖𓂃 ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ⋆˚{emo} ݁˖⭑"
            await context.bot.set_chat_title(k[1], title)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except Exception:
            pass

        await asyncio.sleep(NCSPAM_DELAY)
        if k not in ncspam_tasks:
            break

        # Step 3: Send another spam (different text)
        try:
            await context.bot.send_message(k[1], random.choice(msgs))
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except Exception:
            pass

        await asyncio.sleep(NCSPAM_DELAY)

# ═══════════════════════════════════════
#         NAME CHANGER COMMANDS
# ═══════════════════════════════════════

@only_sudo
async def baapnc(update, context):
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: !baapnc <prefix>")
    k = key(context, update.effective_chat.id)
    if k in nc_tasks:
        return await update.message.reply_text("🔀 NC already running in this group")
    prefix = " ".join(context.args)
    nc_tasks[k] = asyncio.create_task(nc_loop(k, prefix, context))
    await update.message.reply_text("🔁 NC Loop Started")

@only_sudo
async def dbaapnc(update, context):
    k = key(context, update.effective_chat.id)
    if k in nc_tasks:
        nc_tasks[k].cancel()
        del nc_tasks[k]
        await update.message.reply_text("🛑 NC Loop Stopped")
    else:
        await update.message.reply_text("⚠️ No NC loop running")

@only_sudo
async def toxicnc(update, context):
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: !toxicnc <prefix>")
    k = key(context, update.effective_chat.id)
    if k in toxic_tasks:
        return await update.message.reply_text("🔀 toxic NC already running")
    prefix = " ".join(context.args)
    toxic_tasks[k] = asyncio.create_task(toxic_loop(k, prefix, context))
    await update.message.reply_text("🔁 toxic NC Started")

@only_sudo
async def dtoxicnc(update, context):
    k = key(context, update.effective_chat.id)
    if k in toxic_tasks:
        toxic_tasks[k].cancel()
        del toxic_tasks[k]
        await update.message.reply_text("🛑 toxic NC Stopped")
    else:
        await update.message.reply_text("⚠️ No toxic NC running")

@only_sudo
async def anc(update, context):
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: !anc <prefix>")
    k = key(context, update.effective_chat.id)
    if k in emo_tasks:
        return await update.message.reply_text("🔀 Emoji loop already running")
    prefix = " ".join(context.args)
    emo_tasks[k] = asyncio.create_task(emo_loop(k, prefix, context))
    await update.message.reply_text("🔁 Emoji NC Started ✅")

@only_sudo
async def danc(update, context):
    k = key(context, update.effective_chat.id)
    if k in emo_tasks:
        emo_tasks[k].cancel()
        del emo_tasks[k]
        await update.message.reply_text("🛑 Emoji NC Stopped")
    else:
        await update.message.reply_text("⚠️ No emoji loop running")

@only_sudo
async def timenc(update, context):
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: !timenc <prefix>")
    k = key(context, update.effective_chat.id)
    if k in timenc_tasks:
        return await update.message.reply_text("🔀 Time NC already running in this group")
    prefix = " ".join(context.args)
    timenc_tasks[k] = asyncio.create_task(timenc_loop(k, prefix, context))
    await update.message.reply_text("🔁 Time NC Started ✅")

@only_sudo
async def dtimenc(update, context):
    k = key(context, update.effective_chat.id)
    if k in timenc_tasks:
        timenc_tasks[k].cancel()
        del timenc_tasks[k]
        await update.message.reply_text("🛑 Time NC Stopped")
    else:
        await update.message.reply_text("⚠️ No Time NC loop running")

@only_sudo
async def flowernc(update, context):
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: !flowernc <prefix>")
    k = key(context, update.effective_chat.id)
    if k in flower_tasks:
        return await update.message.reply_text("🔀 Flower NC already running in this group")
    prefix = " ".join(context.args)
    flower_tasks[k] = asyncio.create_task(flower_loop(k, prefix, context))
    await update.message.reply_text("🔁 Flower NC Started ✅")

@only_sudo
async def dflowernc(update, context):
    k = key(context, update.effective_chat.id)
    if k in flower_tasks:
        flower_tasks[k].cancel()
        del flower_tasks[k]
        await update.message.reply_text("🛑 Flower NC Stopped")
    else:
        await update.message.reply_text("⚠️ No Flower NC loop running")

@only_sudo
async def animalnc(update, context):
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: !animalnc <prefix>")
    k = key(context, update.effective_chat.id)
    if k in animal_tasks:
        return await update.message.reply_text("🔀 Animal NC already running in this group")
    prefix = " ".join(context.args)
    animal_tasks[k] = asyncio.create_task(animal_loop(k, prefix, context))
    await update.message.reply_text("🔁 Animal NC Started ✅")

@only_sudo
async def danimalnc(update, context):
    k = key(context, update.effective_chat.id)
    if k in animal_tasks:
        animal_tasks[k].cancel()
        del animal_tasks[k]
        await update.message.reply_text("🛑 Animal NC Stopped")
    else:
        await update.message.reply_text("⚠️ No Animal NC loop running")

@only_sudo
async def heartnc(update, context):
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: !heartnc <prefix>")
    k = key(context, update.effective_chat.id)
    if k in heart_tasks:
        return await update.message.reply_text("🔀 Heart NC already running in this group")
    prefix = " ".join(context.args)
    heart_tasks[k] = asyncio.create_task(heart_loop(k, prefix, context))
    await update.message.reply_text("🔁 Heart NC Started ✅")

@only_sudo
async def dheartnc(update, context):
    k = key(context, update.effective_chat.id)
    if k in heart_tasks:
        heart_tasks[k].cancel()
        del heart_tasks[k]
        await update.message.reply_text("🛑 Heart NC Stopped")
    else:
        await update.message.reply_text("⚠️ No Heart NC loop running")

@only_sudo
async def fruitnc(update, context):
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: !fruitnc <prefix>")
    k = key(context, update.effective_chat.id)
    if k in fruit_tasks:
        return await update.message.reply_text("🔀 Fruit NC already running in this group")
    prefix = " ".join(context.args)
    fruit_tasks[k] = asyncio.create_task(fruit_loop(k, prefix, context))
    await update.message.reply_text("🔁 Fruit NC Started ✅")

@only_sudo
async def dfruitnc(update, context):
    k = key(context, update.effective_chat.id)
    if k in fruit_tasks:
        fruit_tasks[k].cancel()
        del fruit_tasks[k]
        await update.message.reply_text("🛑 Fruit NC Stopped")
    else:
        await update.message.reply_text("⚠️ No Fruit NC loop running")

@only_sudo
async def ncspam(update, context):
    if not context.args:
        return await update.message.reply_text(
            "⚠️ Usage: !ncspam <name>\n"
            "Example: !ncspam Rahul"
        )
    target = " ".join(context.args)

    k = key(context, update.effective_chat.id)
    if k in ncspam_tasks:
        return await update.message.reply_text("🔀 NC+Spam combo already running in this group!")
    
    t = asyncio.create_task(ncspam_combo_loop(k, target, context))
    ncspam_tasks[k] = t
    
    await update.message.reply_text(f"🔁 NC + Spam Combo Started ✅\n🎯 Target: {target}")

@only_sudo
async def dncspam(update, context):
    k = key(context, update.effective_chat.id)
    if k in ncspam_tasks:
        ncspam_tasks[k].cancel()
        del ncspam_tasks[k]
        await update.message.reply_text("🛑 NC + Spam Combo Stopped")
    else:
        await update.message.reply_text("⚠️ No NC+Spam combo running")

# ═══════════════════════════════════════
#          AUTO DELETE COMMANDS
# ═══════════════════════════════════════

@only_sudo
async def autodel(update, context):
    k = key(context, update.effective_chat.id)
    if k in autodel_chats:
        return await update.message.reply_text("🔀 Auto-Delete already ON in this group!")
    autodel_chats.add(k)
    await update.message.reply_text("🗑️ Auto-Delete ON ✅\nDusre bots ke messages auto delete honge!")

@only_sudo
async def dautodel(update, context):
    k = key(context, update.effective_chat.id)
    if k in autodel_chats:
        autodel_chats.discard(k)
        await update.message.reply_text("🛑 Auto-Delete OFF")
    else:
        await update.message.reply_text("⚠️ Auto-Delete is not running")

@only_sudo
async def deldelay(update, context):
    global DEL_DELAY
    try:
        sec = float(context.args[0])
        if 0 <= sec <= 30:
            DEL_DELAY = sec
            await update.message.reply_text(f"⏱ Delete Delay set: {sec}s")
        else:
            await update.message.reply_text("⚠️ Range: 0 - 30")
    except Exception:
        await update.message.reply_text("⚠️ Usage: !deldelay <sec>")

@only_sudo
async def stopall(update, context):
    k = key(context, update.effective_chat.id)
    count = 0
    
    task_dicts = [
        nc_tasks, toxic_tasks, emo_tasks, timenc_tasks,
        flower_tasks, animal_tasks, heart_tasks, fruit_tasks,
        ncspam_tasks, spam_tasks, pfp_tasks, reply_tasks
    ]
    
    for d in task_dicts:
        if k in d:
            d[k].cancel()
            del d[k]
            count += 1
            
    if k in autodel_chats:
        autodel_chats.discard(k)
        count += 1
        
    if count > 0:
        await update.message.reply_text(f"🛑 ALL LOOPS STOPPED! ({count} tasks terminated in this group) ✅")
    else:
        await update.message.reply_text("⚠️ No active loops to stop in this group!")

# ═══════════════════════════════════════
#           PFP COMMANDS
# ═══════════════════════════════════════

@only_sudo
async def changepfp(update, context):
    k = key(context, update.effective_chat.id)
    if k in pfp_tasks:
        return await update.message.reply_text("🖼️ PFP loop already running! Use !dpfp to stop.")
    replied = update.message.reply_to_message
    if not replied or not replied.photo:
        return await update.message.reply_text("⚠️ Reply to a photo with !changepfp to start the loop!")
    file_id = replied.photo[-1].file_id
    pfp_tasks[k] = asyncio.create_task(pfp_loop(k, file_id, context))
    await update.message.reply_text(
        f"🔁 PFP Loop Started ✅\n"
        f"🖼️ Cycling replied photo every {PFP_DELAY}s\n"
        f"Use !dpfp to stop."
    )

@only_sudo
async def dpfp(update, context):
    k = key(context, update.effective_chat.id)
    if k in pfp_tasks:
        pfp_tasks[k].cancel()
        del pfp_tasks[k]
        await update.message.reply_text("🛑 PFP Loop Stopped")
    else:
        await update.message.reply_text("⚠️ No PFP loop running in this group")

# ═══════════════════════════════════════
#           SPAM COMMANDS
# ═══════════════════════════════════════

@only_sudo
async def spam(update, context):
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: !spam <text>")
    k = key(context, update.effective_chat.id)
    if k in spam_tasks:
        return await update.message.reply_text("🔀 Spam already running")
    spam_tasks[k] = asyncio.create_task(spam_loop(k, " ".join(context.args), context))
    await update.message.reply_text("🔁 Spam Loop Started")

@only_sudo
async def unspam(update, context):
    k = key(context, update.effective_chat.id)
    if k in spam_tasks:
        spam_tasks[k].cancel()
        del spam_tasks[k]
        await update.message.reply_text("🛑 Spam Loop Stopped")
    else:
        await update.message.reply_text("⚠️ No spam running")

# ═══════════════════════════════════════
#           REPLY COMMANDS
# ═══════════════════════════════════════

@only_sudo
async def replytoxic(update, context):
    if not update.message.reply_to_message:
        return await update.message.reply_text("⚠️ Reply to a message with !replytoxic")
    k = key(context, update.effective_chat.id)
    if k in reply_tasks:
        return await update.message.reply_text("🔀 Reply loop already running")
    msg_id = update.message.reply_to_message.message_id
    reply_tasks[k] = asyncio.create_task(reply_loop(k, msg_id, context))
    await update.message.reply_text("⚡ Reply toxic Started")

@only_sudo
async def dreply(update, context):
    k = key(context, update.effective_chat.id)
    if k in reply_tasks:
        reply_tasks[k].cancel()
        del reply_tasks[k]
        await update.message.reply_text("🛑 Reply toxic Stopped")
    else:
        await update.message.reply_text("⚠️ No reply loop running")

# ═══════════════════════════════════════
#            SUDO COMMANDS
# ═══════════════════════════════════════

@only_owner
async def addsudo(update, context):
    if not update.message.reply_to_message:
        return await update.message.reply_text("⚠️ Reply to a user with !addsudo")
    user_id = update.message.reply_to_message.from_user.id
    s = load_sudo()
    if user_id not in s:
        s.append(user_id)
        save_sudo(s)
    await update.message.reply_text("✅ Added to sudo")

@only_owner
async def remsudo(update, context):
    if not update.message.reply_to_message:
        return await update.message.reply_text("⚠️ Reply to a user with !remsudo")
    user_id = update.message.reply_to_message.from_user.id
    s = load_sudo()
    if user_id in s:
        s.remove(user_id)
        save_sudo(s)
    await update.message.reply_text("❌ Removed from sudo")

@only_owner
async def listsudo(update, context):
    s = load_sudo()
    text = "👑 SUDO USERS:\n\n" + "\n".join(map(str, s)) if s else "No sudo users"
    await update.message.reply_text(text)

# ═══════════════════════════════════════
#            UTILITY COMMANDS
# ═══════════════════════════════════════

async def ready(update, context):
    await update.message.reply_text("❤️‍🔥 █▓▒▒░░░Chudai ke liye taiyaar ab chudegi is rndykebacche ki maa░░░▒▒▓█ 💥\n\n😈 RUK RNDYKEBACHE BS TU AB...")

async def ping(update, context):
    start = time.time()
    msg = await update.message.reply_text("Pinging...")
    end = time.time()
    await msg.edit_text(f"🏓 {round((end - start) * 1000)} ms")

async def status(update, context):
    await update.message.reply_text(
        f"NC:{len(nc_tasks)} | toxic:{len(toxic_tasks)} | EMO:{len(emo_tasks)} | "
        f"SPAM:{len(spam_tasks)} | COMBO:{len(ncspam_tasks)} | PFP:{len(pfp_tasks)} | TIME:{len(timenc_tasks)} | FLOW:{len(flower_tasks)} | ANIM:{len(animal_tasks)} | HRT:{len(heart_tasks)} | FRUIT:{len(fruit_tasks)}"
    )

async def myid(update, context):
    await update.message.reply_text(f"🆔 {update.effective_user.id}")

@only_owner
async def refresh(update, context):
    await update.message.reply_text("🔄 Refreshed sudo list")

@only_sudo
async def delay(update, context):
    global DELAY
    try:
        sec = float(context.args[0])
        if 0.1 <= sec <= 20:
            DELAY = sec
            await update.message.reply_text(f"⏱ Delay set: {sec}s")
        else:
            await update.message.reply_text("⚠️ Range: 0.1 - 20")
    except Exception:
        await update.message.reply_text("⚠️ Usage: !delay <sec>")

@only_owner
async def setprefix(update, context):
    global PREFIX
    if not context.args:
        return await update.message.reply_text(f"⚠️ Current prefix: {PREFIX}\nUsage: !prefix <new_prefix>")
    PREFIX = context.args[0]
    await update.message.reply_text(f"✅ Prefix changed to: {PREFIX}")

@only_sudo
async def timedelay(update, context):
    global TIME_DELAY
    try:
        sec = float(context.args[0])
        if 0.5 <= sec <= 60:
            TIME_DELAY = sec
            await update.message.reply_text(f"⏱ Time NC Delay set: {sec}s")
        else:
            await update.message.reply_text("⚠️ Range: 0.5 - 60")
    except Exception:
        await update.message.reply_text("⚠️ Usage: !timedelay <sec>")

@only_sudo
async def flowerdelay(update, context):
    global FLOWER_DELAY
    try:
        sec = float(context.args[0])
        if 0.5 <= sec <= 60:
            FLOWER_DELAY = sec
            await update.message.reply_text(f"⏱ Flower NC Delay set: {sec}s")
        else:
            await update.message.reply_text("⚠️ Range: 0.5 - 60")
    except Exception:
        await update.message.reply_text("⚠️ Usage: !flowerdelay <sec>")

@only_sudo
async def animaldelay(update, context):
    global ANIMAL_DELAY
    try:
        sec = float(context.args[0])
        if 0.5 <= sec <= 60:
            ANIMAL_DELAY = sec
            await update.message.reply_text(f"⏱ Animal NC Delay set: {sec}s")
        else:
            await update.message.reply_text("⚠️ Range: 0.5 - 60")
    except Exception:
        await update.message.reply_text("⚠️ Usage: !animaldelay <sec>")

@only_sudo
async def heartdelay(update, context):
    global HEART_DELAY
    try:
        sec = float(context.args[0])
        if 0.5 <= sec <= 60:
            HEART_DELAY = sec
            await update.message.reply_text(f"⏱ Heart NC Delay set: {sec}s")
        else:
            await update.message.reply_text("⚠️ Range: 0.5 - 60")
    except Exception:
        await update.message.reply_text("⚠️ Usage: !heartdelay <sec>")

@only_sudo
async def ncspamdelay(update, context):
    global NCSPAM_DELAY
    try:
        sec = float(context.args[0])
        if 0.1 <= sec <= 60:
            NCSPAM_DELAY = sec
            await update.message.reply_text(f"⏱ NC-Spam Combo Delay set: {sec}s")
        else:
            await update.message.reply_text("⚠️ Range: 0.1 - 60")
    except Exception:
        await update.message.reply_text("⚠️ Usage: !ncspamdelay <sec>")

@only_sudo
async def fruitdelay(update, context):
    global FRUIT_DELAY
    try:
        sec = float(context.args[0])
        if 0.5 <= sec <= 60:
            FRUIT_DELAY = sec
            await update.message.reply_text(f"⏱ Fruit NC Delay set: {sec}s")
        else:
            await update.message.reply_text("⚠️ Range: 0.5 - 60")
    except Exception:
        await update.message.reply_text("⚠️ Usage: !fruitdelay <sec>")

# ═══════════════════════════════════════
#                 MENU
# ═══════════════════════════════════════

async def menu(update, context):
    p = PREFIX
    text = f"""
╔═════════════════════════╗
║     ❤️‍🔥 TOXIC BAAP  𝗕𝗢𝗧 𝗩𝟲 ❤️‍🔥    ║
╚═════════════════════════╝

❖ 𝗦𝘁𝗮𝘁𝘂𝘀 ➪ 🟢 𝗢𝗻𝗹𝗶𝗻𝗲
❖ 𝗢𝘄𝗻𝑲➪ @Ussekehnaistillloveher

┏━━━━━━『 🧨 𝗡𝗖 𝗦𝗘𝗖𝗧𝗜𝗢𝗡 』━━━━━━
┣ ➪ {p}baapnc <txt>  | {p}dbaapnc
┣ ➪ {p}toxicnc <txt>  | {p}dtoxicnc
┣ ➪ {p}anc <txt>     | {p}danc
┣ ➪ {p}timenc <txt>  | {p}dtimenc
┣ ➪ {p}flowernc <txt>| {p}dflowernc
┣ ➪ {p}animalnc <txt>| {p}danimalnc
┣ ➪ {p}heartnc <txt> | {p}dheartnc
┗ ➪ {p}fruitnc <txt> | {p}dfruitnc

┏━━━━『 💥 𝗔𝗧𝗧𝗔𝗖𝗞 𝗦𝗘𝗖𝗧𝗜𝗢𝗡 』━━━━
┣ ➪ {p}ncspam <name> | {p}dncspam
┣ ➪ {p}spam <txt>    | {p}unspam
┣ ➪ {p}replytoxic     | {p}dreply
┗ ➪ {p}autodel       | {p}dautodel

┏━━━━━『 ⚙️ 𝗔𝗗𝗠𝗜𝗡 𝗧𝗢𝗢𝗟𝗦 』━━━━━
┣ ➪ {p}changepfp     | {p}dpfp
┣ ➪ {p}prefix <new>  (𝗖𝗵𝗮𝗻𝗴𝗲)
┣ ➪ {p}delay <sec>   (𝗡𝗖 𝗦𝗽𝗲𝗲𝗱)
┣ ➪ {p}timedelay     (𝗧𝗶𝗺𝗲)
┣ ➪ {p}flowerdelay   (𝗙𝗹𝗼𝘄𝗲𝗿)
┣ ➪ {p}animaldelay   (𝗔𝗻𝗶𝗺𝗮𝗹)
┣ ➪ {p}heartdelay    (𝗛𝗲𝗮𝗿𝘁)
┣ ➪ {p}fruitdelay    (𝗙𝗿𝘂𝗶𝘁)
┣ ➪ {p}ncspamdelay (𝗖𝗼𝗺𝗯𝗼 𝗦𝗽𝗲𝗲𝗱)
┗ ➪ {p}deldelay      (𝗗𝗲𝗹𝗲𝘁𝗲)

┏━━━━━━『 🛡️ 𝗦𝗬𝗦𝗧𝗘𝗠 』━━━━━━━
┣ ➪ {p}addsudo   | {p}remsudo
┣ ➪ {p}listsudo  | {p}refresh
┣ ➪ {p}status    | {p}ping
┣ ➪ {p}stopall   | {p}ready
┗ ➪ {p}menu
"""
    await update.message.reply_text(text)

# ═══════════════════════════════════════
#               BOT RUNNER
# ═══════════════════════════════════════

async def run_bot(token):
    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    # Command map: "cmdname" -> handler_function
    handlers = [
        ("baapnc",        baapnc),
        ("dbaapnc",       dbaapnc),
        ("toxicnc",        toxicnc),
        ("dtoxicnc",       dtoxicnc),
        ("anc",           anc),
        ("danc",          danc),
        ("timenc",        timenc),
        ("dtimenc",       dtimenc),
        ("flowernc",      flowernc),
        ("dflowernc",     dflowernc),
        ("animalnc",      animalnc),
        ("danimalnc",     danimalnc),
        ("heartnc",       heartnc),
        ("dheartnc",      dheartnc),
        ("fruitnc",       fruitnc),
        ("dfruitnc",      dfruitnc),
        ("changepfp",     changepfp),
        ("dpfp",          dpfp),
        ("spam",          spam),
        ("unspam",        unspam),
        ("ncspam",        ncspam),
        ("dncspam",       dncspam),
        ("autodel",       autodel),
        ("dautodel",      dautodel),
        ("deldelay",      deldelay),
        ("replytoxic",     replytoxic),
        ("dreply",        dreply),
        ("delay",         delay),
        ("ncspamdelay",   ncspamdelay),
        ("timedelay",     timedelay),
        ("flowerdelay",   flowerdelay),
        ("animaldelay",   animaldelay),
        ("heartdelay",    heartdelay),
        ("fruitdelay",    fruitdelay),
        ("addsudo",       addsudo),
        ("remsudo",       remsudo),
        ("listsudo",      listsudo),
        ("ping",          ping),
        ("status",        status),
        ("ready",         ready),
        ("stopall",       stopall),
        ("myid",          myid),
        ("refresh",       refresh),
        ("menu",          menu),
        ("prefix",        setprefix),
    ]

    import re

    def make_handler(func, cmd):
        async def wrapper(update, context):
            # Parse args from message text manually
            text = update.message.text or ""
            parts = text.strip().split()
            context.args = parts[1:] if len(parts) > 1 else []
            return await func(update, context)
        return wrapper

    # Single handler that checks PREFIX dynamically
    async def dispatch(update, context):
        try:
            if not update.message:
                return
            user = update.effective_user
            chat_id = update.effective_chat.id
            bot_id = context.bot.id

            # Auto-delete: fire-and-forget delete for OTHER bots' messages
            if (bot_id, chat_id) in autodel_chats:
                if user and user.is_bot and user.id != bot_id:
                    async def delayed_del(msg, d):
                        if d > 0:
                            await asyncio.sleep(d)
                        try:
                            await msg.delete()
                        except Exception:
                            pass
                    asyncio.create_task(delayed_del(update.message, DEL_DELAY))
                    return

            text = (update.message.text or "").strip()
            if not text.startswith(PREFIX):
                return
            text_no_prefix = text[len(PREFIX):]
            cmd_part = text_no_prefix.split()[0].lower() if text_no_prefix.split() else ""
            for cmd, func in handlers:
                if cmd == cmd_part:
                    parts = text.strip().split()
                    context.args = parts[1:] if len(parts) > 1 else []
                    return await func(update, context)
        except Exception as e:
            print(f"DISPATCH ERROR: {e}")

    # Global error handler to prevent crashes
    async def error_handler(update, context):
        print(f"BOT ERROR: {context.error}")

    app.add_handler(MessageHandler(filters.TEXT, dispatch))
    app.add_error_handler(error_handler)

    print(f"✅ Bot Started: {token[:10]}...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=["message"],
        poll_interval=1.0,
        timeout=15,
    )

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        try:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception:
            pass


async def main():
    while True:
        try:
            tasks = [run_bot(token) for token in BOT_TOKENS if token.strip()]
            await asyncio.gather(*tasks)
        except Exception as e:
            print(f"❌ CRASH DETECTED: {e}")
            print("🔄 Restarting in 3 seconds...")
            await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Bot stopped by user")
    except Exception as e:
        print(f"FATAL: {e}")
