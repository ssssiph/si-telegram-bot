from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_connection, safe_close

router = Router()

class PromoState(StatesGroup):
    waiting_for_code = State()
    test_state = State()  # Состояние для тестирования

@router.message(F.text == "🎟️ Промокоды")
async def promo_entry(message: Message, state: FSMContext):
    # Устанавливаем специальное состояние для теста
    await state.set_state(PromoState.test_state)
    await message.answer("workin'")

@router.message(PromoState.test_state, F.text == "1")
async def handle_one(message: Message, state: FSMContext):
    await message.answer("2")
    # Сбрасываем состояние, чтобы наше тестовое условие не мешало другим обработчикам
    await state.clear()
