from aiogram import Router, F
from aiogram.types import Message
from database import get_connection

router = Router()

@router.message(F.text.strip() == "🎯 События")
async def show_events(message: Message):
    conn = await get_connection()
    try:
        events = await conn.fetch("SELECT * FROM events ORDER BY id DESC")
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
            if event["media"]:
                await message.answer_photo(photo=event["media"], caption=text)
            else:
                await message.answer(text)
    finally:
        await conn.close()
