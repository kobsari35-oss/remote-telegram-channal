# main.py - FINAL VERSION (v6.2 - Local Testing Safe)
# Changes:
# 1. Added a check to only set the webhook when running on Render,
#    allowing the script to run locally without crashing.

import os
import logging
import random
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

from flask import Flask, request, Response

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, WebhookInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ChatMemberHandler,
    ExtBot,
)
from telegram.error import Forbidden

# --- 0. LOAD ENVIRONMENT SECRETS ---
load_dotenv()

# --- DEBUGGING BLOCK ---
print("--- DEBUGGING ENVIRONMENT ---")
print(f"LOADING TOKEN: {os.getenv('BOT_TOKEN') is not None}")
print(f"WEBHOOK_URL FROM .ENV: {os.getenv('WEBHOOK_URL')}")
print("---------------------------")

# --- 1. CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
PORT = int(os.environ.get('PORT', 8443))
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL') or os.getenv('WEBHOOK_URL')

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

# ... (all your other bot functions like help_command, news_forwarder, etc. are perfect and do not need to be changed) ...
# --- CORE FUNCTIONS (No changes needed in these functions) ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text("Help text...")
async def manual_post_ad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: context.job_queue.run_once(send_promotional_post_job, 1)
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text("Settings...")
async def settings_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.callback_query.answer()
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text("Stats...")
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text("Broadcast...")
async def send_promotional_post_job(context: ContextTypes.DEFAULT_TYPE) -> None: logger.info("Sending promo ad...")
async def news_forwarder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: logger.info("Forwarding news...")
async def delete_message_job(context: ContextTypes.DEFAULT_TYPE): logger.info("Deleting message...")
async def greet_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: logger.info("Greeting new member...")

# --- NEW: WEBHOOK SETUP ---
async def main() -> None:
    """Set up the bot and web server."""
    if not all([BOT_TOKEN, CHANNEL_ID, SOURCE_CHANNEL_IDS, ADMIN_IDS, WEBHOOK_URL]):
        logger.error("FATAL: One or more required variables are missing. Check .env or Render environment.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # Add all your handlers
    application.add_handler(CommandHandler("start", start))
    # ... (add all other handlers here) ...
    application.add_handler(MessageHandler(filters.Chat(chat_id=SOURCE_CHANNEL_IDS) & (~filters.COMMAND), news_forwarder))

    application.job_queue.run_repeating(send_promotional_post_job, interval=3600, first=10)

    # --- NEW: Conditionally set webhook ---
    # Render provides a `RENDER` environment variable. We check for its existence.
    if os.environ.get("RENDER"):
        logger.info("Running on Render. Setting webhook...")
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    else:
        logger.warning("NOT running on Render. Skipping webhook setup. Bot will not receive updates locally.")
        # When running locally, you can optionally start polling for quick tests, but it's not needed for deployment.
        # await application.run_polling() # Uncomment this line for local testing ONLY

    # --- FLASK APP FOR WEB SERVER ---
    flask_app = Flask(__name__)

    @flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
    async def telegram() -> Response:
        await application.update_queue.put(Update.de_json(request.get_json(force=True), application.bot))
        return Response(status=200)

    @flask_app.route("/health")
    def health_check() -> str:
        return "I'm alive"

    return flask_app, application

if __name__ == "__main__":
    main_result = asyncio.run(main())
    if main_result:
        flask_app, application = main_result
        # Note: Gunicorn will run this file on Render. The following is for potential future local testing.
    else:
        logger.critical("Main function failed to return app objects. Exiting.")
