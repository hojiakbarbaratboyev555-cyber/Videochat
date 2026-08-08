import logging
import os

import asyncpg
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import Update, ChatJoinRequest, ChatMemberUpdated

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

# /link buyrug'ini yuborganda BARCHA foydalanuvchilarning ma'lumotini
# ko'ra oladigan super-admin(lar)
SUPER_ADMIN_IDS = {8638979973}

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
        # --- /link funksiyasi uchun jadvallar ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS invite_links (
                user_id BIGINT PRIMARY KEY,
                invite_link TEXT UNIQUE NOT NULL,
                full_name TEXT,
                username TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS join_requests (
                id SERIAL PRIMARY KEY,
                link_owner_id BIGINT NOT NULL,
                requester_id BIGINT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (link_owner_id, requester_id)
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

# --- invite_links / join_requests ---

async def get_user_invite_link(user_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT invite_link FROM invite_links WHERE user_id = $1", user_id
        )
        return row["invite_link"] if row else None

async def save_user_invite_link(user_id: int, invite_link: str, full_name: str, username: str | None):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO invite_links (user_id, invite_link, full_name, username)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE
            SET full_name = EXCLUDED.full_name, username = EXCLUDED.username
            """,
            user_id, invite_link, full_name, username
        )

async def get_link_owner(invite_link: str):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM invite_links WHERE invite_link = $1", invite_link
        )
        return row["user_id"] if row else None

async def add_join_request(link_owner_id: int, requester_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO join_requests (link_owner_id, requester_id, status)
            VALUES ($1, $2, 'pending')
            ON CONFLICT (link_owner_id, requester_id) DO UPDATE SET status = 'pending'
            """,
            link_owner_id, requester_id
        )

async def mark_join_request_approved(requester_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE join_requests SET status = 'approved'
            WHERE requester_id = $1 AND status = 'pending'
            """,
            requester_id
        )

async def get_link_stats(link_owner_id: int):
    async with db_pool.acquire() as conn:
        approved = await conn.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE link_owner_id = $1 AND status = 'approved'",
            link_owner_id
        )
        pending = await conn.fetchval(
            "SELECT COUNT(*) FROM join_requests WHERE link_owner_id = $1 AND status = 'pending'",
            link_owner_id
        )
        return approved, pending

async def get_all_invite_links():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, invite_link, full_name, username FROM invite_links ORDER BY created_at"
        )
        return [dict(row) for row in rows]

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
# /link — shaxsiy taklif havolasi
# =========================

_link_creation_lock = None

def _format_link_info(user_id: int, full_name: str | None, username: str | None,
                       invite_link: str, approved: int, pending: int) -> str:
    username_text = f"@{username}" if username else "yo'q"
    return (
        f"👤 Ism: {full_name or '-'}\n"
        f"🔹 Username: {username_text}\n"
        f"🆔 ID: {user_id}\n\n"
        f"🔗 Link: {invite_link}\n"
        f"✅ Qo'shilganlar: {approved} ta\n"
        f"⏳ Qo'shilishi kutilayotganlar: {pending} ta"
    )

@dp.message(Command("link"), F.chat.type == "private")
async def link_command(message: types.Message):
    global _link_creation_lock
    if _link_creation_lock is None:
        import asyncio
        _link_creation_lock = asyncio.Lock()

    user = message.from_user

    # --- Super-admin: barcha foydalanuvchilarning ma'lumotini ko'rsatish ---
    if user.id in SUPER_ADMIN_IDS:
        all_links = await get_all_invite_links()

        if not all_links:
            await message.answer("Hozircha hech kim /link buyrug'idan foydalanmagan.")
            return

        for row in all_links:
            approved, pending = await get_link_stats(row["user_id"])
            text = _format_link_info(
                row["user_id"], row["full_name"], row["username"],
                row["invite_link"], approved, pending
            )
            await message.answer(text)
        return

    invite_link = await get_user_invite_link(user.id)

    if not invite_link:
        async with _link_creation_lock:
            # qulf ichida qayta tekshiramiz
            invite_link = await get_user_invite_link(user.id)
            if not invite_link:
                try:
                    link_obj = await bot.create_chat_invite_link(
                        chat_id=MAIN_GROUP_ID,
                        name=(user.full_name or str(user.id))[:32],
                        creates_join_request=True,
                    )
                    invite_link = link_obj.invite_link
                    await save_user_invite_link(
                        user.id, invite_link, user.full_name, user.username
                    )
                except Exception as e:
                    logger.exception("Invite link yaratishda xatolik: %s", e)
                    await message.answer(
                        "Havola yaratishda xatolik yuz berdi. Botga guruhda "
                        "\"Foydalanuvchi qo'shish\" huquqi berilganini tekshiring."
                    )
                    return

    approved, pending = await get_link_stats(user.id)
    text = _format_link_info(
        user.id, user.full_name, user.username, invite_link, approved, pending
    )
    await message.answer(text)

# =========================
# Havola orqali qo'shilish so'rovi
# =========================

@dp.chat_join_request()
async def on_join_request(request: ChatJoinRequest):
    if request.chat.id != MAIN_GROUP_ID:
        return
    if not request.invite_link:
        return

    owner_id = await get_link_owner(request.invite_link.invite_link)
    if not owner_id:
        return

    await add_join_request(owner_id, request.from_user.id)
    logger.info(
        "JOIN_REQUEST: owner=%s requester=%s", owner_id, request.from_user.id
    )

# =========================
# Admin so'rovni tasdiqlagach — a'zo bo'lib qo'shilganda
# =========================

@dp.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated):
    if event.chat.id != MAIN_GROUP_ID:
        return

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    if new_status == "member" and old_status != "member":
        await mark_join_request_approved(event.new_chat_member.user.id)
        logger.info(
            "CHAT_MEMBER: user=%s guruhga qo'shildi (tasdiqlandi)",
            event.new_chat_member.user.id
        )

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
    await bot.set_webhook(
        WEBHOOK_URL,
        allowed_updates=[
            "message",
            "chat_join_request",
            "chat_member",
        ],
    )
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
