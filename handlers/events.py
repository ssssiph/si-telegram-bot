import aiomysql
from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from database import get_connection

router = Router()

async def safe_close(conn):
    if conn:
        try:
            ret = conn.close()
            if ret is not None and hasattr(ret, '__await__'):
                await ret
        except Exception as ex:
            print("safe_close error:", ex)

async def ensure_published_column(conn):
    async with conn.cursor() as cur:
        await cur.execute("SHOW COLUMNS FROM events LIKE 'published'")
        col = await cur.fetchone()
        if not col:
            print("[DB] Столбец 'published' не найден. Добавляем его ...")
            await cur.execute("ALTER TABLE events ADD COLUMN published TEXT DEFAULT '{}'")
            await conn.commit()
            print("[DB] Столбец 'published' успешно добавлен.")

@router.message(F.text == "🎯 События")
async def show_events(message: Message):
    conn = await get_connection()
    try:
        await ensure_published_column(conn)
        
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM events ORDER BY id DESC")
            events = await cur.fetchall()

            if not events:
                await message.answer("❗ Нет активных событий.")
                return

            for event in events:
                text = (
                    f"📢 <b>{event['title']}</b>\n\n"
                    f"{event['description']}\n\n"
                    f"🏆 Приз: {event['prize']}\n"
                    f"📅 Дата: {event['datetime']}"
                )
                if event.get('media'):
                    await message.answer_photo(photo=event['media'], caption=text)
                else:
                    await message.answer(text)
    finally:
        conn.close()
