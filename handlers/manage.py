from aiogram import Router, F
from aiogram.types import Message
from keyboards import back_menu
from fsm.create_event import CreateEvent
from database import get_connection

router = Router()

@router.message(F.text.strip() == "🛠 Управление")
async def admin_panel(message: Message):
    conn = await get_connection()
    try:
        user = await conn.fetchrow("SELECT rank FROM users WHERE tg_id = $1", message.from_user.id)
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

@router.message(F.text.strip() == "1")
async def start_event_creation(message: Message):
    conn = await get_connection()
    try:
        user = await conn.fetchrow("SELECT rank FROM users WHERE tg_id = $1", message.from_user.id)
        if not user or user["rank"] != "Генеральный директор":
            await message.answer("❌ У вас нет доступа к созданию событий.")
            return

        await message.answer("Введите <b>название</b> события:")
        await message.answer("📝 Введите <b>описание</b> события:")
        await message.answer("🏆 Введите <b>приз</b>:")
        await message.answer("📅 Введите <b>дату и время</b>:")
        await message.answer("📎 Отправьте <b>медиафайл</b> (изображение/видео) или напишите 'пропустить'.")
        
        await message.answer("✅ Событие успешно создано!")
    finally:
        await conn.close()

@router.message(F.text.strip() == "0")
async def go_back(message: Message):
    await message.answer("🔙 Возвращение в главное меню")
