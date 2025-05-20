from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_connection, safe_close

router = Router()

class PromoState(StatesGroup):
    waiting_for_code = State()

@router.message(F.text == "🎟️ Промокоды")
async def promo_entry(message: Message, state: FSMContext):
    await message.answer("workin'")
    # Если понадобится, можно установить состояние для дальнейшей работы
    # await state.set_state(PromoState.waiting_for_code)

@router.message(F.text == "1")
async def handle_one(message: Message, state: FSMContext):
    await message.answer("2")
