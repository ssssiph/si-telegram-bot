from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from keyboards import back_menu
from fsm.create_event import CreateEvent

router = Router()

@router.message(F.text.strip() == "🛠 Управление")
async def admin_panel(message: Message, state: FSMContext):
    await message.answer(
        "🛠 Панель управления:\n\n1. Создать событие",
        reply_markup=back_menu
    )

@router.message(F.text.strip() == "1")
async def start_event_creation(message: Message, state: FSMContext):
    await state.set_state(CreateEvent.title)
    await message.answer("Введите <b>название</b> события:")
