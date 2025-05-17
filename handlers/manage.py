from aiogram import Router, F
from aiogram.types import Message
from database import get_connection
from keyboards import back_menu

router = Router()

@router.message(F.text == "🛠 Управление")
async def admin_panel(message: Message):
    async with await get_connection() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", message.from_user.id)
        if user and user["rank"] == "Генеральный директор":
            await message.answer("🛠 Панель управления:\n\n1. Редактор событий\n2. Связь\n3. Пользователи", reply_markup=back_menu)
        else:
            await message.answer("⛔ Доступ разрешён только Генеральному директору.")
