from aiogram import Router
from aiogram.types import Message
from database import get_connection

router = Router()
waiting_for_contact = set()

@router.message(lambda message: message.text and message.text.strip() == "📩 Связь")
async def contact_intro(message: Message):
    waiting_for_contact.add(message.from_user.id)
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")

@router.message()
async def catch_contact_message(message: Message):
    if message.from_user.id in waiting_for_contact:
        waiting_for_contact.remove(message.from_user.id)
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

            sender_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name or "-"
            text = f"📩 <b>Новое сообщение от {sender_name}</b>\n\n{message.text}"
            director_id = 1016554091
            await message.bot.send_message(director_id, text)
            await message.answer("📨 Сообщение отправлено администрации.")
        finally:
            await conn.close()
