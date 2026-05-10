import os
import asyncio
import threading
from flask import Flask

from pyrogram import Client, filters
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import AudioVideoPiped
from pytgcalls.types.input_stream.quality import HighQualityVideo
import yt_dlp

# ================= CONFIG =================
API_ID = int(os.getenv("33954704", "0"))
API_HASH = os.getenv("e2719a9096fb9a50dad0c550ee079f28", "")
BOT_TOKEN = os.getenv("8706187795:AAHAdPfcZWErPMDhWul_VlFknmTs-YWzDUA", "")

OWNER_ID = 8427195149  # sening TG ID

# ================= FLASK (24/7 KEEP ALIVE) =================
app_web = Flask(__name__)

@app_web.route("/")
def home():
    return "Bot is running 24/7 ⚡"

@app_web.route("/ping")
def ping():
    return "ok"

# ================= USERBOT =================
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH)
vc = PyTgCalls(userbot)

def get_stream(url):
    ydl_opts = {"format": "best"}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info["url"]

@userbot.on_message(filters.command("vplay"))
async def vplay(_, msg):
    if len(msg.command) < 2:
        return await msg.reply("❌ YouTube link yubor")

    url = msg.command[1]
    stream_url = get_stream(url)

    await vc.join_group_call(
        msg.chat.id,
        AudioVideoPiped(
            stream_url,
            video_parameters=HighQualityVideo()
        )
    )

    await msg.reply("▶️ Stream boshlandi")

@userbot.on_message(filters.command("stop"))
async def stop(_, msg):
    try:
        await vc.leave_group_call(msg.chat.id)
        await msg.reply("⏹ To‘xtatildi")
    except:
        await msg.reply("❌ Active stream yo‘q")

def run_userbot():
    userbot.start()
    vc.start()
    print("USERBOT 24/7 RUNNING")
    userbot.idle()

# ================= BOT =================
bot = Client("bot", bot_token=BOT_TOKEN)

@bot.on_message(filters.command("vplay"))
async def bot_vplay(_, msg):
    if msg.from_user.id != OWNER_ID:
        return await msg.reply("❌ Sizga ruxsat yo‘q")

    await msg.reply("▶️ Stream boshlash userbotga yuborildi")

@bot.on_message(filters.command("stop"))
async def bot_stop(_, msg):
    if msg.from_user.id != OWNER_ID:
        return await msg.reply("❌ Sizga ruxsat yo‘q")

    await msg.reply("⏹ Stop yuborildi userbotga")

def run_bot():
    bot.run()

# ================= START EVERYTHING =================
if __name__ == "__main__":
    threading.Thread(target=run_userbot).start()
    threading.Thread(target=run_bot).start()
    app_web.run(host="0.0.0.0", port=10000)
