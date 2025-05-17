from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from fsm.create_event import CreateEvent
from database import get_connection

router = Router()

@router.message(CreateEvent.title)
async def get_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(CreateEvent.description)
    await message.answer("Теперь введите <b>описание</b> события:")

@router.message(CreateEvent.description)
async def get_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(CreateEvent.prize)
    await message.answer("Введите <b>приз</b> события:")

@router.message(CreateEvent.prize)
async def get_prize(message: Message, state: FSMContext):
    await state.update_data(prize=message.text)
    await state.set_state(CreateEvent.datetime)
    await message.answer("Введите <b>дату и время</b> проведения (любой текст):")

@router.message(CreateEvent.datetime)
async def get_datetime(message: Message, state: FSMContext):
    await state.update_data(datetime=message.text)
    await state.set_state(CreateEvent.media)
    await message.answer("📎 Отправьте <b>медиафайл</b> (изображение/видео) или напишите 'пропустить'")

@router.message(CreateEvent.media)
async def get_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media = None

    if message.photo:
        media = message.photo[-1].file_id
    elif message.video:
        media = message.video.file_id
    elif message.text.lower() == "пропустить":
        media = None
    else:
        return await message.answer("❗ Пришли фото/видео или напиши 'пропустить'")

    data["media"] = media

    async with await get_connection() as conn:
        await conn.execute("""
            INSERT INTO events (title, description, prize, datetime, media, creator_id)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, data["title"], data["description"], data["prize"], data["datetime"], data["media"], message.from_user.id)

    await message.answer("✅ Событие создано!")
    await state.clear()
