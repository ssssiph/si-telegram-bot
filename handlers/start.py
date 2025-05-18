from aiogram import Router
from aiogram.types import Message
from keyboards import main_menu
from database import get_connection

router = Router()

@router.message(lambda message: message.text is not None and message.text.strip().startswith("/start"))
async def start_command(message: Message):
    print(f"[START] Получили команду от пользователя {message.from_user.id}: {message.text}")
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
            print(f"[START] Пользователь {message.from_user.id} зарегистрирован как Гость.")
        # Если это Генеральный директор (ID 1016554091), обновляем ранг
        if message.from_user.id == 1016554091:
            await conn.execute("UPDATE users SET rank = 'Генеральный директор' WHERE tg_id = $1", message.from_user.id)
            print("[START] Генеральный директор обновлён.")
        await message.answer(f"👋 Добро пожаловать, {message.from_user.full_name or '-'}!", reply_markup=main_menu)
    finally:
        await conn.close()
