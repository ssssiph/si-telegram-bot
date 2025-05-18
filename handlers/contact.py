from aiogram import Router, F
from aiogram.types import Message
from database import get_connection

router = Router()

@router.message(F.text.strip() == "📩 Связь")
async def contact_intro(message: Message):
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")

@router.message()
async def catch_contact_message(message: Message):
    if message.text and message.text.strip() != "/start":
        async with await get_connection() as conn:
            sender = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", message.from_user.id)
            if not sender:
                await conn.execute(
                    "INSERT INTO users (tg_id, username, full_name) VALUES ($1, $2, $3)",
                    message.from_user.id,
                    message.from_user.username or "",
                    message.from_user.full_name or ""
                )

            await message.answer("📨 Сообщение отправлено администрации.")

            director_id = 1016554091
            sender_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
            text = f"📩 <b>Новое сообщение от {sender_name}</b>\n\n{message.text}"

            await message.bot.send_message(director_id, text)
