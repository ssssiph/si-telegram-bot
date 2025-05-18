from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardRemove

class EventCreation(StatesGroup):
    title = State()
    description = State()
    prize = State()
    datetime = State()
    media = State()

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
    await message.answer("🖼 Пришлите изображение/видео (или напишите «-» если нет):")
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
                data['title'],
                data['description'],
                data['prize'],
                data['datetime'],
                media,
                message.from_user.id
            ))
        await message.answer("✅ Событие сохранено!", reply_markup=back_menu)
    finally:
        conn.close()
    await state.clear()
