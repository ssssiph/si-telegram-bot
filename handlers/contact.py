from aiogram import Router, F
from aiogram.types import Message
from database import get_connection

router = Router()
waiting_for_contact = set()

@router.message(F.text == "📩 Связь")
async def contact_intro(message: Message):
    waiting_for_contact.add(message.from_user.id)
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")

@router.message()
async def receive_contact_message(message: Message):
    if message.from_user.id not in waiting_for_contact:
        return

    waiting_for_contact.remove(message.from_user.id)

    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (message.from_user.id,))
            user = await cur.fetchone()

            if not user:
                await cur.execute("""
                    INSERT INTO users (tg_id, username, full_name, `rank`, balance)
                    VALUES (%s, %s, %s, 'Гость', 0)
                """, (
                    message.from_user.id,
                    message.from_user.username or "-",
                    message.from_user.full_name or "-"
                ))

            sender_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name or "-"
            text = f"📩 <b>Новое сообщение от {sender_name}</b>\n\n{message.text}"
            await message.bot.send_message(1016554091, text)
            await message.answer("📨 Сообщение отправлено администрации.")
    finally:
        conn.close()
