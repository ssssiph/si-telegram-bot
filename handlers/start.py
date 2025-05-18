from aiogram import Router, F
from aiogram.types import Message
from keyboards import main_menu
from database import get_connection

router = Router()

@router.message(F.text.contains("/start"))  # Гибкая проверка команды
async def start_command(message: Message):
    conn = await get_connection()
    try:
        # Проверяем, зарегистрирован ли пользователь
        user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", message.from_user.id)

        # Если пользователя нет — добавляем его
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
            user = {"rank": "Гость", "balance": 0}

        # Если это Генеральный директор, обновляем ранг
        if message.from_user.id == 1016554091:
            await conn.execute(
                "UPDATE users SET rank = 'Генеральный директор' WHERE tg_id = $1",
                message.from_user.id
            )
            user["rank"] = "Генеральный директор"

        await message.answer(f"👋 Добро пожаловать, {message.from_user.full_name or '-'}!", reply_markup=main_menu)
    finally:
        await conn.close()
