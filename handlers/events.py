from aiogram import Router, F
from aiogram.types import Message
from database import get_connection

router = Router()

@router.message(F.text == "🎯 События")
async def list_events(message: Message):
    async with await get_connection() as conn:
        rows = await conn.fetch("SELECT id, title FROM events ORDER BY id DESC")
        if not rows:
            await message.answer("🎯 Пока нет активных событий.")
        else:
            text = "<b>🎯 Список событий:</b>\n\n"
            for i, row in enumerate(rows, start=1):
                text += f"{i}. {row['title']}\n"
            await message.answer(text)
