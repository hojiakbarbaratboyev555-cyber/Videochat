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

BOT_TOKEN = os.environ["8663105105:AAG9m4SAu8BJg7cByJFJHtqoVHRZQ_xr7Lw"]  # Render'da Environment Variable sifatida qo'shing

WEBHOOK_HOST = "https://videochat-94k9.onrender.com"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

ADMIN_GROUP_ID = -1004456580624   # Forum (mavzuli) guruh, bot admin bo'lishi shart
MAIN_GROUP_ID = -1003680334929

MAIN_TOPIC_NAME = "📢 Asosiy guruh"

DB_FILE = "messages.json"

PORT = int(os.environ.get("PORT", 10000))

# =========================
# LOGGING
# =========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# BOT
# =========================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# =========================
# DATABASE
# =========================
# Struktura:
# {
#   "user_topics": {"<user_id>": topic_id},
#   "topic_users": {"<topic_id>": user_id},
#   "messages": {"<admin_msg_id>": {"user_id": ..., "user_msg_id": ...}},
#   "main_topic_id": topic_id
# }

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.exception("DB o'qishda xatolik: %s", e)
            return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_message(admin_msg_id, user_id, user_msg_id):
    data = load_db()
    data.setdefault("messages", {})
    data["messages"][str(admin_msg_id)] = {
        "user_id": user_id,
        "user_msg_id": user_msg_id
    }
    save_db(data)

def get_message(admin_msg_id):
    data = load_db()
    return data.get("messages", {}).get(str(admin_msg_id))

def get_user_topic(user_id):
    data = load_db()
    return data.get("user_topics", {}).get(str(user_id))

def save_user_topic(user_id, topic_id):
    data = load_db()
    data.setdefault("user_topics", {})[str(user_id)] = topic_id
    data.setdefault("topic_users", {})[str(topic_id)] = user_id
    save_db(data)

def get_topic_user(topic_id):
    data = load_db()
    return data.get("topic_users", {}).get(str(topic_id))

def get_main_topic_id():
    data = load_db()
    return data.get("main_topic_id")

def save_main_topic_id(topic_id):
    data = load_db()
    data["main_topic_id"] = topic_id
    save_db(data)

# =========================
# YORDAMCHI FUNKSIYALAR
# =========================

async def get_or_create_user_topic(user: types.User) -> int:
    """Foydalanuvchi uchun mavzuni topadi, bo'lmasa yangi yaratadi."""
    existing = get_user_topic(user.id)
    if existing:
        return existing

    name = user.full_name or (f"@{user.username}" if user.username else f"User {user.id}")

    topic = await bot.create_forum_topic(chat_id=ADMIN_GROUP_ID, name=name)
    topic_id = topic.message_thread_id

    save_user_topic(user.id, topic_id)
    return topic_id

async def get_or_create_main_topic() -> int:
    """'Asosiy guruh' mavzusini topadi, bo'lmasa yaratadi."""
    existing = get_main_topic_id()
    if existing:
        return existing

    topic = await bot.create_forum_topic(chat_id=ADMIN_GROUP_ID, name=MAIN_TOPIC_NAME)
    topic_id = topic.message_thread_id

    save_main_topic_id(topic_id)
    return topic_id

# =========================
# /start
# =========================

@dp.message(Command("start"))
async def start(message: types.Message):
    pass

# =========================
# USER -> ADMIN GURUH (mavzuga)
# =========================

@dp.message(F.chat.type == "private")
async def user_message(message: types.Message):

    topic_id = await get_or_create_user_topic(message.from_user)

    forwarded = await message.forward(
        chat_id=ADMIN_GROUP_ID,
        message_thread_id=topic_id
    )

    save_message(
        forwarded.message_id,
        message.from_user.id,
        message.message_id
    )

# =========================
# ADMIN GURUH (mavzular ichida)
# =========================

@dp.message(F.chat.id == ADMIN_GROUP_ID)
async def admin_handler(message: types.Message):

    thread_id = message.message_thread_id
    main_topic_id = get_main_topic_id()

    logger.info(
        "ADMIN_HANDLER: thread_id=%s main_topic_id=%s from=%s text=%s",
        thread_id, main_topic_id, message.from_user.id if message.from_user else None, message.text
    )

    if thread_id is None:
        # Umumiy (General) bo'limga yozilgan xabarlarni e'tiborsiz qoldiramiz
        logger.info("ADMIN_HANDLER: thread_id yo'q, chiqib ketyapmiz")
        return

    # =====================
    # "Asosiy guruh" mavzusi -> MAIN_GROUP_ID
    # =====================
    if main_topic_id and thread_id == main_topic_id:
        try:
            await message.copy_to(chat_id=MAIN_GROUP_ID)
            logger.info("ADMIN_HANDLER: MAIN_GROUP_ID ga yuborildi")
        except Exception as e:
            logger.exception("MAIN_GROUP_ID ga yuborishda xatolik: %s", e)
        return

    # =====================
    # Foydalanuvchi mavzusi -> foydalanuvchiga
    # =====================
    user_id = get_topic_user(thread_id)
    logger.info("ADMIN_HANDLER: topilgan user_id=%s", user_id)

    if not user_id:
        logger.info("ADMIN_HANDLER: bu thread uchun user topilmadi")
        return

    reply_to_user_msg_id = None

    if message.reply_to_message:
        data = get_message(message.reply_to_message.message_id)
        logger.info("ADMIN_HANDLER: reply_to_message_id=%s -> data=%s",
                     message.reply_to_message.message_id, data)
        if data:
            reply_to_user_msg_id = data["user_msg_id"]

    try:
        await message.copy_to(
            chat_id=user_id,
            reply_to_message_id=reply_to_user_msg_id
        )
        logger.info("ADMIN_HANDLER: foydalanuvchiga (%s) yuborildi", user_id)
    except Exception as e:
        logger.exception("Foydalanuvchiga yuborishda xatolik: %s", e)

# =========================
# FASTAPI
# =========================

app = FastAPI()

@app.on_event("startup")
async def startup():
    await bot.set_webhook(WEBHOOK_URL)

    try:
        await get_or_create_main_topic()
    except Exception as e:
        logger.error(
            "Asosiy guruh mavzusini yaratib bo'lmadi. "
            "ADMIN_GROUP_ID to'g'riligini, guruhda Topics yoqilganligini "
            "va bot admin/'Manage Topics' huquqiga egaligini tekshiring. Xato: %s",
            e
        )

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
