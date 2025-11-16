# main.py - FINAL VERSION (v5.1 - Replit Keep Alive Edition)
# New Features:
# 1. /stats command for admins to see bot uptime and activity.
# 2. /broadcast command for admins to send messages to all users.
# 3. Integrated keep_alive for 24/7 hosting on Replit.

import os
import logging
import random
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ChatMemberHandler,
)
from telegram.error import Forbidden

# --- NEW: Import for Replit Hosting ---
from keep_alive import keep_alive

# --- 0. LOAD ENVIRONMENT SECRETS ---
load_dotenv()

# --- DEBUGGING BLOCK ---
print("--- DEBUGGING ENVIRONMENT ---")
print(f"LOADING TOKEN: {os.getenv('BOT_TOKEN')}")
print("---------------------------")

# --- 1. CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

source_channel_id_str = os.getenv("SOURCE_CHANNEL_ID", "")
try:
    SOURCE_CHANNEL_IDS = [int(channel_id.strip()) for channel_id in source_channel_id_str.split(',')]
except (ValueError, TypeError):
    logging.error("FATAL: SOURCE_CHANNEL_ID is missing or invalid in .env file.")
    exit()

admin_id_str = os.getenv("ADMIN_ID", "0")
try:
    ADMIN_IDS = [int(admin_id.strip()) for admin_id in admin_id_str.split(',')]
except (ValueError, TypeError):
    logging.error("FATAL: ADMIN_ID is missing or invalid in .env file.")
    exit()

# --- MESSAGES & SETTINGS ---
PROMOTIONAL_MESSAGES = [
    "🚀 សូមចូលរួមជាមួយបណ្តាញសង្គមរបស់យើងខ្ញុំ ដើម្បីទទួលបានព័ត៌មានថ្មីៗ និងខ្លឹមសារពិសេសៗជាច្រើនទៀត។",
    "🎉 កុំភ្លេចតាមដានពួកយើង! យើងមានព័ត៌មានអស្តារ្យជាច្រើនសម្រាប់អ្នក។ សូមអរគុណសម្រាប់ការគាំទ្រ!",
    "សួស្តី! តើអ្នកបានត្រៀមខ្លួនសម្រាប់ព័ត៌មានប្រចាំថ្ងៃហើយឬនៅ? សូមរង់ចាំតាមដានទាំងអស់គ្នា។",
]

blacklist_str = os.getenv("BLACKLIST_KEYWORDS", "")
BLACKLIST_KEYWORDS = [keyword.strip().lower() for keyword in blacklist_str.split(',') if keyword.strip()]

SETTINGS = {
    "SILENT_POST": False,
    "ANTI_BAN_DELAY": True,
    "FORWARD_FOOTER": os.getenv("FORWARD_FOOTER"),
    "WELCOME_MESSAGE": os.getenv("WELCOME_MESSAGE"),
}

# --- In-memory storage for stats and users ---
START_TIME = datetime.now()
STATS = {"ads_sent": 0, "forwards_done": 0, "welcomes_sent": 0}
USER_IDS = set()

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ADMIN FILTER ---
admin_filter = filters.User(user_id=ADMIN_IDS)

# --- BOT COMMANDS & MENUS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    USER_IDS.add(update.effective_chat.id)
    logger.info(f"New user started the bot. Total users: {len(USER_IDS)}")

    keyboard = [['🚀 Post Ad Now', 'ℹ️ Help']]
    if update.effective_user.id in ADMIN_IDS:
        keyboard.append(['⚙️ Settings', '📊 Stats'])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_html(f"Hi {update.effective_user.mention_html()}! I'm your promotion bot.", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "✅ **Auto-send Ads:** Posts a random ad every 1 hour.\n"
        "✅ **Auto-Forward:** Forwards new posts from source channels (with keyword filtering).\n"
        "✅ **Welcome Message:** Greets new users who join the channel.\n"
        "✅ **Admin Controls:** Use the keyboard for manual posts or use /settings, /stats, and /broadcast."
    )

async def manual_post_ad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("✅ Roger that! Sending a promotional ad now...")
    context.job_queue.run_once(send_promotional_post_job, 1)

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    silent_status = "✅ ON" if SETTINGS["SILENT_POST"] else "❌ OFF"
    keyboard = [[InlineKeyboardButton(f"Silent Posts: {silent_status}", callback_data="toggle_silent_post")], [InlineKeyboardButton("Close", callback_data="close_settings")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ **Bot Settings**", reply_markup=reply_markup, parse_mode='Markdown')

async def settings_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "toggle_silent_post":
        SETTINGS["SILENT_POST"] = not SETTINGS["SILENT_POST"]
        logger.info(f"Admin {query.from_user.id} toggled Silent Posts to {SETTINGS['SILENT_POST']}")
        silent_status = "✅ ON" if SETTINGS["SILENT_POST"] else "❌ OFF"
        keyboard = [[InlineKeyboardButton(f"Silent Posts: {silent_status}", callback_data="toggle_silent_post")], [InlineKeyboardButton("Close", callback_data="close_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="⚙️ **Bot Settings**", reply_markup=reply_markup, parse_mode='Markdown')
    elif query.data == "close_settings":
        await query.edit_message_text(text="Settings menu closed.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uptime = datetime.now() - START_TIME
    uptime_str = str(timedelta(seconds=int(uptime.total_seconds())))

    stats_text = (
        f"📊 **Bot Statistics**\n\n"
        f"🕒 **Uptime:** {uptime_str}\n"
        f"🚀 **Promotional Ads Sent:** {STATS['ads_sent']}\n"
        f"➡️ **Messages Forwarded:** {STATS['forwards_done']}\n"
        f"👋 **New Members Greeted:** {STATS['welcomes_sent']}\n"
        f"👥 **Unique Users (for broadcast):** {len(USER_IDS)}"
    )
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_to_broadcast = " ".join(context.args)
    if not message_to_broadcast:
        await update.message.reply_text("⚠️ Please provide a message to broadcast. \nUsage: `/broadcast Your message here`")
        return

    await update.message.reply_text(f"📢 Starting broadcast to {len(USER_IDS)} users... Please wait.")
    
    success_count = 0
    failed_count = 0
    for user_id in USER_IDS:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_to_broadcast)
            success_count += 1
            await asyncio.sleep(0.1)
        except Forbidden:
            logger.warning(f"Broadcast failed for user {user_id}: User blocked the bot.")
            failed_count += 1
        except Exception as e:
            logger.error(f"Broadcast failed for user {user_id}: {e}")
            failed_count += 1

    await update.message.reply_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"Sent successfully to: **{success_count}** users.\n"
        f"Failed to send to: **{failed_count}** users (they may have blocked the bot)."
    , parse_mode='Markdown')

# --- CORE FUNCTIONS ---
async def send_promotional_post_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    if SETTINGS["ANTI_BAN_DELAY"]: await asyncio.sleep(random.uniform(1, 5))
    message_to_send = random.choice(PROMOTIONAL_MESSAGES)
    keyboard = [[InlineKeyboardButton("👤 Admin", url="https://t.me/foryou_know001"), InlineKeyboardButton("📢 Channel", url="https://t.me/foryou_know001")], [InlineKeyboardButton("👥 Group", url="https://t.me/night_press24h"), InlineKeyboardButton("👍 Facebook", url="https://www.facebook.com/Kobsarinews")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=message_to_send, reply_markup=reply_markup, disable_notification=SETTINGS["SILENT_POST"])
        STATS['ads_sent'] += 1
        logger.info(f"Successfully sent ad to channel {CHANNEL_ID}")
    except Exception as e:
        logger.error(f"Failed to send ad to {CHANNEL_ID}: {e}")

async def news_forwarder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    message_content = (message.text or message.caption or "").lower()
    if any(keyword in message_content for keyword in BLACKLIST_KEYWORDS):
        logger.info(f"Blocked message from {message.chat_id} due to blacklisted keyword.")
        return

    try:
        footer = SETTINGS.get("FORWARD_FOOTER")
        if not footer:
            await message.forward(chat_id=CHANNEL_ID)
        else:
            new_caption = f"{(message.caption or '')}\n\n{footer}" if not message.text else None
            new_text = f"{message.text}\n\n{footer}" if message.text else None
            if new_text: await context.bot.send_message(chat_id=CHANNEL_ID, text=new_text, parse_mode='HTML')
            else: await message.copy(chat_id=CHANNEL_ID, caption=new_caption, parse_mode='HTML')
        
        STATS['forwards_done'] += 1
        logger.info(f"Processed message from {message.chat_id}")
    except Exception as e:
        logger.error(f"Failed to process message: {e}")

async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.delete_message(chat_id=context.job.chat_id, message_id=context.job.data['message_id'])

async def greet_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_template = SETTINGS.get("WELCOME_MESSAGE")
    if not welcome_template: return

    new_member = update.chat_member.new_chat_member.user
    message_text = welcome_template.format(username=new_member.mention_html(), chat_title=update.chat.title)
    
    sent_message = await context.bot.send_message(chat_id=CHANNEL_ID, text=message_text, parse_mode='HTML')
    context.job_queue.run_once(delete_message_job, 90, data={'message_id': sent_message.message_id}, chat_id=CHANNEL_ID)
    STATS['welcomes_sent'] += 1
    
    try: await context.bot.delete_message(chat_id=CHANNEL_ID, message_id=update.effective_message.message_id)
    except Exception as e: logger.warning(f"Could not delete 'join' service message: {e}")

# --- MAIN FUNCTION ---
def main() -> None:
    if not all([BOT_TOKEN, CHANNEL_ID, SOURCE_CHANNEL_IDS, ADMIN_IDS]):
        logger.error("FATAL: One or more required variables are missing from .env file. Exiting.")
        return

    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Admin-only handlers
    application.add_handler(CommandHandler("settings", settings_menu, filters=admin_filter))
    application.add_handler(CommandHandler("stats", stats_command, filters=admin_filter))
    application.add_handler(CommandHandler("broadcast", broadcast_command, filters=admin_filter))
    application.add_handler(MessageHandler(filters.Regex('^🚀 Post Ad Now$') & admin_filter, manual_post_ad))
    application.add_handler(MessageHandler(filters.Regex('^⚙️ Settings$') & admin_filter, settings_menu))
    application.add_handler(MessageHandler(filters.Regex('^📊 Stats$') & admin_filter, stats_command))
    application.add_handler(CallbackQueryHandler(settings_button_handler))

    # Core functionality handlers
    application.add_handler(MessageHandler(filters.Chat(chat_id=SOURCE_CHANNEL_IDS) & (~filters.COMMAND), news_forwarder))
    application.add_handler(ChatMemberHandler(greet_new_members, chat_member_types=ChatMemberHandler.CHAT_MEMBER))

    # Scheduled jobs
    application.job_queue.run_repeating(send_promotional_post_job, interval=3600, first=10)
    
    # Logging startup info
    logger.info(f"Bot started successfully. Admin IDs: {ADMIN_IDS}")
    logger.info(f"Forwarding from Source Channel IDs: {SOURCE_CHANNEL_IDS}")
    if SETTINGS["FORWARD_FOOTER"]: logger.info(f"Using custom footer: {SETTINGS['FORWARD_FOOTER']}")
    if SETTINGS["WELCOME_MESSAGE"]: logger.info("Welcome message feature is ENABLED.")
    if BLACKLIST_KEYWORDS: logger.info(f"BLACKLIST active. Keywords: {BLACKLIST_KEYWORDS}")

    application.run_polling()

if __name__ == '__main__':
    # --- NEW: Call keep_alive before starting the bot ---
    keep_alive()
    main()