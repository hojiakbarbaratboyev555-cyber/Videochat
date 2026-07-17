import logging
import os

import asyncpg
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import Update

from fastapi import FastAPI, Request
import uvicorn

# =========================
# SOZLAMALAR
# =========================

BOT_TOKEN = "8663105105:AAETQnNHSufqKuUltEUiX9LjX1Ke-BzA7nM"
DATABASE_URL = "postgresql://hotira_user:T43Mnsk2LeOXXLvAdbEIJkxlhKCnjSOG@dpg-d9cug6r7uimc73f49o9g-a/hotira"

WEBHOOK_HOST = "https://videochat-94k9.onrender.com"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

ADMIN_GROUP_ID = -1004456580624   # Forum (mavzuli) guruh, bot admin bo'lishi shart
MAIN_GROUP_ID = -1003680334929

MAIN_TOPIC_NAME = "📢 Asosiy guruh"

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
# DATABASE (PostgreSQL)
# =========================

db_pool: asyncpg.Pool | None = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)

    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_topics (
                user_id BIGINT PRIMARY KEY,
                topic_id BIGINT UNIQUE NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                admin_msg_id BIGINT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                user_msg_id BIGINT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

async def close_db():
    if db_pool:
        await db_pool.close()

# --- messages ---

async def save_message(admin_msg_id: int, user_id: int, user_msg_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO messages (admin_msg_id, user_id, user_msg_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (admin_msg_id) DO UPDATE
            SET user_id = EXCLUDED.user_id, user_msg_id = EXCLUDED.user_msg_id
            """,
            admin_msg_id, user_id, user_msg_id
        )

async def get_message(admin_msg_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, user_msg_id FROM messages WHERE admin_msg_id = $1",
            admin_msg_id
        )
        return dict(row) if row else None

# --- user_topics ---

async def get_user_topic(user_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT topic_id FROM user_topics WHERE user_id = $1", user_id
        )
        return row["topic_id"] if row else None

async def get_topic_user(topic_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM user_topics WHERE topic_id = $1", topic_id
        )
        return row["user_id"] if row else None

async def save_user_topic(user_id: int, topic_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_topics (user_id, topic_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET topic_id = EXCLUDED.topic_id
            """,
            user_id, topic_id
        )

# --- settings (main_topic_id) ---

async def get_main_topic_id():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM settings WHERE key = 'main_topic_id'"
        )
        return int(row["value"]) if row else None

async def save_main_topic_id(topic_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES ('main_topic_id', $1)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            str(topic_id)
        )

# =========================
# YORDAMCHI FUNKSIYALAR
# =========================

# Bir vaqtda bir xil foydalanuvchi uchun ikkita topic ochilib ketmasligi uchun qulf
_topic_creation_lock = None

async def get_or_create_user_topic(user: types.User) -> int:
    global _topic_creation_lock
    if _topic_creation_lock is None:
        import asyncio
        _topic_creation_lock = asyncio.Lock()

    existing = await get_user_topic(user.id)
    if existing:
        return existing

    async with _topic_creation_lock:
        # Qulf ichida yana tekshiramiz (boshqa so'rov ulgurgan bo'lishi mumkin)
        existing = await get_user_topic(user.id)
        if existing:
            return existing

        name = user.full_name or (f"@{user.username}" if user.username else f"User {user.id}")

        topic = await bot.create_forum_topic(chat_id=ADMIN_GROUP_ID, name=name)
        topic_id = topic.message_thread_id

        await save_user_topic(user.id, topic_id)
        return topic_id

async def get_or_create_main_topic() -> int:
    existing = await get_main_topic_id()
    if existing:
        return existing

    topic = await bot.create_forum_topic(chat_id=ADMIN_GROUP_ID, name=MAIN_TOPIC_NAME)
    topic_id = topic.message_thread_id

    await save_main_topic_id(topic_id)
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

    await save_message(
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
    main_topic_id = await get_main_topic_id()

    logger.info(
        "ADMIN_HANDLER: thread_id=%s main_topic_id=%s from=%s text=%s",
        thread_id, main_topic_id, message.from_user.id if message.from_user else None, message.text
    )

    if thread_id is None:
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
    user_id = await get_topic_user(thread_id)
    logger.info("ADMIN_HANDLER: topilgan user_id=%s", user_id)

    if not user_id:
        logger.info("ADMIN_HANDLER: bu thread uchun user topilmadi")
        return

    reply_to_user_msg_id = None

    if message.reply_to_message:
        data = await get_message(message.reply_to_message.message_id)
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
    await init_db()
    await bot.set_webhook(WEBHOOK_URL)
    await get_or_create_main_topic()

@app.on_event("shutdown")
async def shutdown():
    await close_db()

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