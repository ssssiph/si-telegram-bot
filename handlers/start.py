from aiogram import Router, F
from aiogram.types import Message
from keyboards import main_menu
from database import get_connection

router = Router()

@router.message(F.text == "/start")
async def start_command(message: Message):
    async with await get_connection() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", message.from_user.id)
        if not user:
            await conn.execute(
                "INSERT INTO users (tg_id, username, full_name, rank, balance) VALUES ($1, $2, $3, 'Гость', 0)",
                message.from_user.id,
                message.from_user.username or "",
                message.from_user.full_name or ""
            )

        if message.from_user.id == 1016554091:
            await conn.execute(
                "UPDATE users SET rank = 'Генеральный директор' WHERE tg_id = $1",
                message.from_user.id
            )

    await message.answer("Добро пожаловать в Siph Industry!", reply_markup=main_menu)
