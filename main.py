import os
import time
import subprocess
import requests
import re
from pathlib import Path
from telegram import Bot

# ====== CONFIG ======
YOUTUBE_CHANNEL_ID = "UCxxxxxxxx"   # channel ID
CHECK_INTERVAL = 60  # seconds
COOKIES_FILE = "cookies.txt"

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # your chat or group ID

# Gofile
GOFILE_API_TOKEN = os.getenv("GOFILE_API_TOKEN")

bot = Bot(token=TELEGRAM_TOKEN)
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# ====== HELPERS ======
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

# ====== MAIN LOOP ======
if __name__ == "__main__":
    send_telegram("Bot started. Monitoring channel...")
    while True:
        try:
            if is_live(YOUTUBE_CHANNEL_ID):
                live_url = extract_live_url(YOUTUBE_CHANNEL_ID)
                if live_url:
                    send_telegram(f"Live detected! Recording: {live_url}")
                    record_stream(live_url)
                    # after recording, find latest file
                    files = sorted(DOWNLOAD_DIR.glob("*.mp4"), key=os.path.getmtime, reverse=True)
                    if files:
                        latest = files[0]
                        send_telegram(f"Recording finished: {latest.name}")
                        send_file(latest)
            else:
                print("No live stream right now.")
        except Exception as e:
            send_telegram(f"Error: {e}")
        time.sleep(CHECK_INTERVAL)
