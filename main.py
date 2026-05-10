import os
import subprocess
import time
import threading
import telebot

# ==========================================
# TOKEN
# ==========================================
BOT_TOKEN = "8706187795:AAGujjR8Dw0ri7h_yaaXwml8dfwoGY_oLBA"

bot = telebot.TeleBot(BOT_TOKEN)

# Streamlarni saqlash
streams = {}

# ==========================================
# STREAM FUNCTION
# ==========================================
def run_stream(chat_id, youtube_url, server_url, stream_key):

    rtmp_url = f"{server_url}{stream_key}"

    while streams.get(chat_id, {}).get("active", False):

        try:
            bot.send_message(chat_id, "🔄 YouTube stream link olinmoqda...")

            # Direct video URL olish
            get_url_cmd = [
                "yt-dlp",
                "-g",
                "-f",
                "best[height<=720]",
                youtube_url
            ]

            result = subprocess.run(
                get_url_cmd,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                bot.send_message(
                    chat_id,
                    f"❌ yt-dlp xatolik:\n{result.stderr[:300]}"
                )
                time.sleep(15)
                continue

            video_url = result.stdout.strip()

            bot.send_message(chat_id, "🚀 Stream boshlandi!")

            ffmpeg_cmd = [
                "ffmpeg",
                "-re",
                "-i", video_url,

                "-c:v", "libx264",
                "-preset", "veryfast",
                "-maxrate", "2500k",
                "-bufsize", "5000k",
                "-pix_fmt", "yuv420p",
                "-g", "50",

                "-c:a", "aac",
                "-b:a", "128k",
                "-ar", "44100",

                "-f", "flv",
                rtmp_url
            ]

            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )

            streams[chat_id]["process"] = process

            process.wait()

            if streams.get(chat_id, {}).get("active", False):
                bot.send_message(
                    chat_id,
                    "⚠️ Stream uzildi.\n🔁 10 soniyadan keyin qayta ulanadi..."
                )
                time.sleep(10)

        except Exception as e:
            bot.send_message(chat_id, f"❌ Xatolik:\n{e}")
            time.sleep(10)

# ==========================================
# START
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def start(message):

    text = (
        "👋 Salom!\n\n"
        "Men YouTube videolarini Telegram Live Stream ga uzatuvchi botman.\n\n"
        "📌 Buyruqlar:\n"
        "/stream - Yangi stream boshlash\n"
        "/stop - Streamni to'xtatish\n"
        "/status - Holatni tekshirish"
    )

    bot.reply_to(message, text)

# ==========================================
# STREAM START
# ==========================================
@bot.message_handler(commands=['stream'])
def stream(message):

    msg = bot.send_message(
        message.chat.id,
        "🔗 YouTube video link yuboring:"
    )

    bot.register_next_step_handler(msg, get_youtube)

# ==========================================
# GET YOUTUBE
# ==========================================
def get_youtube(message):

    youtube_url = message.text.strip()

    msg = bot.send_message(
        message.chat.id,
        "🌐 RTMP Server URL yuboring:\n\nMasalan:\nrtmps://dc4-1.rtmp.t.me/s/"
    )

    bot.register_next_step_handler(
        msg,
        get_server,
        youtube_url
    )

# ==========================================
# GET SERVER
# ==========================================
def get_server(message, youtube_url):

    server_url = message.text.strip()

    msg = bot.send_message(
        message.chat.id,
        "🔑 Stream Key yuboring:"
    )

    bot.register_next_step_handler(
        msg,
        start_stream,
        youtube_url,
        server_url
    )

# ==========================================
# START FINAL STREAM
# ==========================================
def start_stream(message, youtube_url, server_url):

    stream_key = message.text.strip()

    chat_id = message.chat.id

    if chat_id in streams and streams[chat_id].get("active"):

        bot.send_message(
            chat_id,
            "⚠️ Sizda allaqachon stream ishlayapti."
        )

        return

    streams[chat_id] = {
        "active": True,
        "youtube": youtube_url
    }

    thread = threading.Thread(
        target=run_stream,
        args=(
            chat_id,
            youtube_url,
            server_url,
            stream_key
        )
    )

    thread.start()

# ==========================================
# STOP STREAM
# ==========================================
@bot.message_handler(commands=['stop'])
def stop(message):

    chat_id = message.chat.id

    if chat_id not in streams:

        bot.send_message(
            chat_id,
            "❌ Sizda faol stream yo'q."
        )

        return

    streams[chat_id]["active"] = False

    process = streams[chat_id].get("process")

    if process:
        process.terminate()

    bot.send_message(
        chat_id,
        "🛑 Stream to'xtatildi."
    )

# ==========================================
# STATUS
# ==========================================
@bot.message_handler(commands=['status'])
def status(message):

    chat_id = message.chat.id

    if chat_id in streams and streams[chat_id].get("active"):

        bot.send_message(
            chat_id,
            f"✅ Stream ishlayapti:\n{streams[chat_id]['youtube']}"
        )

    else:

        bot.send_message(
            chat_id,
            "❌ Hozir stream yo'q."
        )

# ==========================================
# RUN
# ==========================================
print("✅ Bot ishga tushdi...")

bot.infinity_polling(skip_pending=True)
