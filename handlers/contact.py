from aiogram import Router, F
from aiogram.types import Message
from database import get_connection

router = Router()

waiting_for_message = set()

@router.message(F.text.strip() == "📩 Связь")
async def contact_intro(message: Message):
    waiting_for_message.add(message.from_user.id)
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")

@router.message()
async def catch_contact_message(message: Message):
    if message.from_user.id in waiting_for_message:
        waiting_for_message.remove(message.from_user.id)
        conn = await get_connection()
        try:
            user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", message.from_user.id)
            if not user:
                await conn.execute(
                    """
                    INSERT INTO users (tg_id, username, full_name, rank, balance)
                    VALUES ($1, $2, $3, 'Гость', 0)
                    """,
                    message.from_user.id,
                    message.from_user.username or "-",
                    message.from_user.full_name or "-"
                )
            director_id = 1016554091
            sender_name = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.full_name or "-")
            await message.answer("📨 Сообщение отправлено администрации.")
            text = f"📩 <b>Новое сообщение от {sender_name}</b>\n\n{message.text}"
            await message.bot.send_message(director_id, text)
        finally:
            await conn.close()
