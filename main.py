import json
import logging
import os

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import Update

from fastapi import FastAPI, Request
import uvicorn

# =========================
# SOZLAMALAR
# =========================

BOT_TOKEN = "8765242703:AAFQfTqb9G5dncCQ_SRbyRR9BGz7QX11SGA"

WEBHOOK_HOST = "https://videochat-94k9.onrender.com"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

ADMIN_GROUP_ID = -1003881398546
MAIN_GROUP_ID = -1003680334929

DB_FILE = "messages.json"

PORT = int(os.environ.get("PORT", 10000))

# =========================
# LOGGING
# =========================

logging.basicConfig(level=logging.INFO)

# =========================
# BOT
# =========================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# =========================
# DATABASE
# =========================

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_message(admin_msg_id, user_id, user_msg_id):
    data = load_db()

    data[str(admin_msg_id)] = {
        "user_id": user_id,
        "user_msg_id": user_msg_id
    }

    save_db(data)

def get_message(admin_msg_id):
    data = load_db()
    return data.get(str(admin_msg_id))

# =========================
# /start
# =========================

@dp.message(Command("start"))
async def start(message: types.Message):
    pass

# =========================
# USER -> ADMIN GROUP
# =========================

@dp.message(F.chat.type == "private")
async def user_message(message: types.Message):

    forwarded = await message.forward(ADMIN_GROUP_ID)

    save_message(
        forwarded.message_id,
        message.from_user.id,
        message.message_id
    )

# =========================
# ADMIN GROUP
# =========================

@dp.message(F.chat.id == ADMIN_GROUP_ID)
async def admin_handler(message: types.Message):

    # =====================
    # REPLY -> USER
    # =====================

    if message.reply_to_message:

        replied_msg_id = message.reply_to_message.message_id

        data = get_message(replied_msg_id)

        if not data:
            return

        user_id = data["user_id"]
        user_msg_id = data["user_msg_id"]

        if message.text:

            await bot.send_message(
                chat_id=user_id,
                text=message.text,
                reply_to_message_id=user_msg_id
            )

        elif message.photo:

            await bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=message.caption,
                reply_to_message_id=user_msg_id
            )

        elif message.video:

            await bot.send_video(
                chat_id=user_id,
                video=message.video.file_id,
                caption=message.caption,
                reply_to_message_id=user_msg_id
            )

        elif message.document:

            await bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=message.caption,
                reply_to_message_id=user_msg_id
            )

        elif message.voice:

            await bot.send_voice(
                chat_id=user_id,
                voice=message.voice.file_id,
                reply_to_message_id=user_msg_id
            )

        elif message.sticker:

            await bot.send_sticker(
                chat_id=user_id,
                sticker=message.sticker.file_id
            )

    # =====================
    # /a -> MAIN GROUP
    # =====================

    elif message.text and message.text.startswith("/a "):

        text = message.text[3:]

        if text.strip():

            await bot.send_message(
                chat_id=MAIN_GROUP_ID,
                text=text
            )

# =========================
# FASTAPI
# =========================

app = FastAPI()

@app.on_event("startup")
async def startup():
    await bot.set_webhook(WEBHOOK_URL)

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):

    data = await request.json()

    update = Update.model_validate(data)

    await dp.feed_update(bot, update)

    return {"ok": True}

@app.get("/")
async def home():
    return {"status": "running"}

# =========================
# RUN
# =========================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT
)
