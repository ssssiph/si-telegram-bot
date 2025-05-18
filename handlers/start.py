from aiogram import Router, F
from aiogram.types import Message
from keyboards import main_menu
from database import get_connection

router = Router()

@router.message(F.text.startswith("/start"))
async def start_command(message: Message):
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (message.from_user.id,))
            result = await cur.fetchone()

            if not result:
                await cur.execute("""
                    INSERT INTO users (tg_id, username, full_name, rank, balance)
                    VALUES (%s, %s, %s, 'Гость', 0)
                """, (
                    message.from_user.id,
                    message.from_user.username or "-",
                    message.from_user.full_name or "-"
                ))

            if message.from_user.id == 1016554091:
                await cur.execute("UPDATE users SET rank = 'Генеральный директор' WHERE tg_id = %s", (message.from_user.id,))

        await message.answer("👋 Добро пожаловать в Siph Industry!", reply_markup=main_menu)
    finally:
        conn.close()
