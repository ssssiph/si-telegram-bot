from aiogram import Router, F
from aiogram.types import Message
from keyboards import back_menu
from database import get_connection

router = Router()

@router.message(F.text.contains("Управление"))
async def admin_panel(message: Message):
    print("Кнопка 'Управление' нажата")

    conn = await get_connection()
    try:
        user = await conn.fetchrow("SELECT rank FROM users WHERE tg_id = $1", message.from_user.id)
        print(f"👤 Пользователь: {user}")

        if not user or user["rank"] != "Генеральный директор":
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
        await conn.close()
