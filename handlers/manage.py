import aiomysql
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards import back_menu
from database import get_connection

router = Router()

class EventCreation(StatesGroup):
    title = State()
    description = State()
    prize = State()
    datetime = State()
    media = State()

# 🛠 Главная панель управления
@router.message(F.text == "🛠 Управление")
async def admin_panel(message: Message):
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `rank` FROM users WHERE tg_id = %s", (message.from_user.id,))
            result = await cur.fetchone()

            if not result:
                await cur.execute("""
                    INSERT INTO users (tg_id, username, full_name, `rank`, balance)
                    VALUES (%s, %s, %s, 'Генеральный директор', 0)
                """, (
                    message.from_user.id,
                    message.from_user.username or "-",
                    message.from_user.full_name or "-"
                ))
                rank = 'Генеральный директор'
            else:
                rank = result[0]

            # 🔎 Покажем ранг в чате (отладка)
            await message.answer(f"🔍 Ваш ранг: <b>{rank}</b>")

            # 🛡 Проверка прав
            if rank != "Генеральный директор":
                await message.answer("❌ У вас нет доступа к управлению.")
                return

            # ✅ Меню управления
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


# 📋 Создание события
@router.message(F.text == "1️⃣")
async def create_event_start(message: Message, state: FSMContext):
    await message.answer("✍️ Введите <b>название</b> события:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EventCreation.title)

@router.message(EventCreation.title)
async def set_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("📝 Теперь введите <b>описание</b> события:")
    await state.set_state(EventCreation.description)

@router.message(EventCreation.description)
async def set_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("🏆 Укажите <b>приз</b> события:")
    await state.set_state(EventCreation.prize)

@router.message(EventCreation.prize)
async def set_prize(message: Message, state: FSMContext):
    await state.update_data(prize=message.text)
    await message.answer("📅 Введите <b>дату и время</b> события:")
    await state.set_state(EventCreation.datetime)

@router.message(EventCreation.datetime)
async def set_datetime(message: Message, state: FSMContext):
    await state.update_data(datetime=message.text)
    await message.answer("🖼 Пришлите изображение/видео или отправьте «-», если не нужно:")
    await state.set_state(EventCreation.media)

@router.message(EventCreation.media)
async def finish_event(message: Message, state: FSMContext):
    data = await state.get_data()
    media = None
    if message.photo:
        media = message.photo[-1].file_id
    elif message.video:
        media = message.video.file_id
    elif message.text.strip() != "-":
        media = message.text.strip()

    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO events (title, description, prize, datetime, media, creator_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                data["title"],
                data["description"],
                data["prize"],
                data["datetime"],
                media,
                message.from_user.id
            ))
        await message.answer("✅ Событие успешно создано и сохранено!", reply_markup=back_menu)
    finally:
        conn.close()
    await state.clear()
