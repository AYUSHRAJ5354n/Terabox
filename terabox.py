from aria2p import API as Aria2API, Client as Aria2Client
import asyncio
from dotenv import load_dotenv
from datetime import datetime
import os
import logging
import math
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait
import time
import urllib.parse
from urllib.parse import urlparse, parse_qs
from flask import Flask, render_template
from threading import Thread

load_dotenv('config.env', override=True)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(name)s - %(levelname)s] %(message)s - %(filename)s:%(lineno)d"
)

logger = logging.getLogger(__name__)

logging.getLogger("pyrogram.session").setLevel(logging.ERROR)
logging.getLogger("pyrogram.connection").setLevel(logging.ERROR)
logging.getLogger("pyrogram.dispatcher").setLevel(logging.ERROR)

aria2 = Aria2API(
    Aria2Client(
        host="http://localhost",
        port=6800,
        secret=""
    )
)
options = {
    "max-tries": "50",
    "retry-wait": "3",
    "continue": "true",
    "allow-overwrite": "true",
    "min-split-size": "4M",
    "split": "10"
}
aria2.set_global_options(options)

API_ID = os.environ.get('TELEGRAM_API', '')
API_HASH = os.environ.get('TELEGRAM_HASH', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
DUMP_CHAT_ID = int(os.environ.get('DUMP_CHAT_ID', '0'))
FSUB_ID = int(os.environ.get('FSUB_ID', '0'))
USER_SESSION_STRING = os.environ.get('USER_SESSION_STRING', '')

app = Client("jetbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user = None
SPLIT_SIZE = 2093796556
if USER_SESSION_STRING:
    user = Client("jetu", api_id=API_ID, api_hash=API_HASH, session_string=USER_SESSION_STRING)
    SPLIT_SIZE = 4241280205

VALID_DOMAINS = [
    'terabox.com', 'nephobox.com', '4funbox.com', 'mirrobox.com',
    'momerybox.com', 'teraboxapp.com', '1024tera.com',
    'terabox.app', 'gibibox.com', 'goaibox.com', 'terasharelink.com',
    'teraboxlink.com', 'terafileshare.com'
]

# Store active downloads so we can stop them
active_downloads = {}

def is_valid_url(url):
    parsed_url = urlparse(url)
    return any(parsed_url.netloc.endswith(domain) for domain in VALID_DOMAINS)

def extract_filename(url: str) -> str:
    try:
        qs = parse_qs(urlparse(url).query)
        if "fin" in qs:
            return urllib.parse.unquote(qs["fin"][0])
    except Exception:
        pass
    return None

def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"

async def is_user_member(client, user_id):
    try:
        member = await client.get_chat_member(FSUB_ID, user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    join_button = InlineKeyboardButton("ᴊᴏɪɴ ❤️🚀", url="https://t.me/jetmirror")
    stop_button = InlineKeyboardButton("🛑 Stop Download", callback_data="stop_download")
    reply_markup = InlineKeyboardMarkup([[join_button], [stop_button]])
    await message.reply_text("Welcome! Send me a Terabox link to download.", reply_markup=reply_markup)

@app.on_callback_query(filters.regex("stop_download"))
async def stop_download_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id in active_downloads:
        gid = active_downloads[user_id]
        try:
            aria2.remove([aria2.get_download(gid)], force=True, files=True)
            await callback_query.message.edit_text("🛑 Download stopped.")
            del active_downloads[user_id]
        except Exception as e:
            await callback_query.message.edit_text(f"❌ Failed to stop: {e}")
    else:
        await callback_query.message.edit_text("No active download found.")

@app.on_message(filters.text)
async def handle_message(client: Client, message: Message):
    if message.text.startswith('/'):
        return

    user_id = message.from_user.id
    if not await is_user_member(client, user_id):
        await message.reply_text("You must join the channel to use me.")
        return

    url = None
    for word in message.text.split():
        if is_valid_url(word):
            url = word
            break
    if not url:
        await message.reply_text("Please provide a valid Terabox link.")
        return

    filename = extract_filename(url)
    if not filename:
        filename = "file_from_terabox.mp4"

    encoded_url = urllib.parse.quote(url)
    final_url = f"https://terabox-url-fixer.amir470517.workers.dev/?url={encoded_url}"

    download = aria2.add_uris([final_url])
    active_downloads[user_id] = download.gid

    status_message = await message.reply_text(f"📥 Starting download: `{filename}`")

    start_time = datetime.now()
    while not download.is_complete and not download.is_removed:
        await asyncio.sleep(5)  # update every 5 seconds
        download.update()
        progress = download.progress
        elapsed_time = datetime.now() - start_time
        status_text = (
            f"📥 **Downloading**\n\n"
            f"File: `{filename}`\n"
            f"Progress: {progress:.2f}%\n"
            f"Done: {format_size(download.completed_length)} / {format_size(download.total_length)}\n"
            f"Speed: {format_size(download.download_speed)}/s\n"
            f"Elapsed: {elapsed_time.seconds // 60}m {elapsed_time.seconds % 60}s"
        )
        try:
            await status_message.edit_text(status_text)
        except FloodWait as e:
            await asyncio.sleep(e.value)

    if download.is_removed:
        return

    file_path = download.files[0].path
    # Ensure correct filename
    if not file_path.endswith(filename):
        new_path = os.path.join(os.path.dirname(file_path), filename)
        os.rename(file_path, new_path)
        file_path = new_path

    await status_message.edit_text(f"✅ Download complete. Uploading `{filename}`...")

    await client.send_video(
        message.chat.id,
        video=file_path,
        caption=f"✨ {filename}\n👤 By: {message.from_user.mention}"
    )

    del active_downloads[user_id]
    os.remove(file_path)

# Flask server for keepalive
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return render_template("index.html")

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

def keep_alive():
    Thread(target=run_flask).start()

if __name__ == "__main__":
    keep_alive()
    if user:
        Thread(target=lambda: asyncio.run(user.start())).start()
    app.run()
