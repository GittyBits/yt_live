import os
import time
import subprocess
import requests
import re
from pathlib import Path
from telegram import Bot, Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

# ====== CONFIG ======
CHECK_INTERVAL = 60  # seconds
COOKIES_FILE = "cookies.txt"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GOFILE_API_TOKEN = os.getenv("GOFILE_API_TOKEN")

bot = Bot(token=TELEGRAM_TOKEN)
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

CHANNEL_FILE = Path("channel.txt")


# ====== HELPERS ======
def save_channel_id(text):
    # Handle both full link and raw ID
    if "youtube.com" in text:
        # Extract channel id from link
        if "/channel/" in text:
            cid = text.split("/channel/")[1].split("/")[0]
        elif "/@" in text:  # username URL
            # resolve username URL to channel ID
            html = requests.get(text).text
            m = re.search(r'"channelId":"(UC[0-9A-Za-z_-]{21}[AQgw])"', html)
            cid = m.group(1) if m else None
        else:
            cid = None
    else:
        cid = text  # assume raw ID
    if cid:
        CHANNEL_FILE.write_text(cid)
        return cid
    return None

def load_channel_id():
    if CHANNEL_FILE.exists():
        return CHANNEL_FILE.read_text().strip()
    return None

def is_live(channel_id):
    url = f"https://www.youtube.com/channel/{channel_id}/live"
    r = requests.get(url)
    return "isLiveNow" in r.text

def extract_live_url(channel_id):
    url = f"https://www.youtube.com/channel/{channel_id}/live"
    r = requests.get(url).text
    m = re.search(r"\"canonicalUrl\":\"(https://www\.youtube\.com/watch\?v=[^\"]+)\"", r)
    return m.group(1) if m else None

def record_stream(url):
    cmd = [
        "yt-dlp",
        "--live-from-start",
        "--no-part",
        "--restrict-filenames",
        "--remux-video", "mp4",
        "--hls-use-mpegts",
        "--concurrent-fragments", "5",
        "-f", "best",
        "-o", f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
        "--cookies", COOKIES_FILE,
        url
    ]
    subprocess.run(cmd)

def upload_gofile(filepath):
    files = {'file': open(filepath, 'rb')}
    headers = {"Authorization": f"Bearer {GOFILE_API_TOKEN}"}
    r = requests.post("https://api.gofile.io/uploadFile", files=files, headers=headers)
    return r.json()["data"]["downloadPage"]

def send_telegram(msg):
    bot.send_message(chat_id=CHAT_ID, text=msg)

def send_file(filepath):
    size = os.path.getsize(filepath)
    if size <= 2 * 1024 * 1024 * 1024:  # ≤2GB
        with open(filepath, "rb") as f:
            bot.send_document(chat_id=CHAT_ID, document=f)
    else:
        link = upload_gofile(filepath)
        send_telegram(f"File too big. Uploaded to GoFile: {link}")


# ====== TELEGRAM HANDLER ======
def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    cid = save_channel_id(text)
    if cid:
        update.message.reply_text(f"✅ Channel set to {cid}. Bot will monitor it now.")
    else:
        update.message.reply_text("❌ Could not extract channel ID. Please try again with a valid link.")


# ====== MAIN LOOP ======
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()

    send_telegram("Bot started ✅")

    while True:
        try:
            channel_id = load_channel_id()
            if not channel_id:
                send_telegram("Please send me the YouTube channel link or ID to monitor.")
                time.sleep(60)
                continue

            if is_live(channel_id):
                live_url = extract_live_url(channel_id)
                if live_url:
                    send_telegram(f"🔴 Live detected! Recording: {live_url}")
                    record_stream(live_url)
                    # after recording, find latest file
                    files = sorted(DOWNLOAD_DIR.glob("*.mp4"), key=os.path.getmtime, reverse=True)
                    if files:
                        latest = files[0]
                        send_telegram(f"✅ Recording finished: {latest.name}")
                        send_file(latest)
            else:
                print("No live stream right now.")
        except Exception as e:
            send_telegram(f"⚠️ Error: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
