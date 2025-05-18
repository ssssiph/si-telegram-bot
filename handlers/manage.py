from aiogram import Router, F
from aiogram.types import Message
from keyboards import back_menu
from database import get_connection

router = Router()

@router.message(F.text == "🛠 Управление")
async def admin_panel(message: Message):
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT rank FROM users WHERE tg_id = %s", (message.from_user.id,))
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
                rank = 'Гость'
            else:
                rank = result[0]

            if rank != "Генеральный директор":
                await message.answer("❌ У вас нет доступа к управлению.")
                return

            await message.answer(
                "🛠 Панель управления:\n\n"
                "1️⃣ Создать событие\n"
                "2️⃣ Редактировать/Удалить событие\n"
                "3️⃣ Управление пользователями\n"
                "0️⃣ Назад",
                reply_markup=back_menu
            )
    finally:
        conn.close()
