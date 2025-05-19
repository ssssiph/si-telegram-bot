from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_connection

router = Router()

class PromoState(StatesGroup):
    waiting_for_promo_code = State()

@router.message(F.text == "🎟️ Промокоды")
async def promo_start(message: Message, state: FSMContext):
    await state.set_state(PromoState.waiting_for_promo_code)
    await message.answer("Введите промокод:")

@router.message(PromoState.waiting_for_promo_code)
async def process_promo_code(message: Message, state: FSMContext):
    code = message.text.strip()
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT reward FROM promo_codes WHERE code = %s", (code,))
            promo = await cur.fetchone()

        if promo is None:
            await message.answer("Неверный промокод. Попробуйте снова.")
            await state.clear()
            return

        reward = promo[0]

        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM promo_codes_usage WHERE tg_id = %s AND code = %s", (message.from_user.id, code))
            usage = await cur.fetchone()

        if usage is not None:
            await message.answer("Вы уже использовали данный промокод!")
            await state.clear()
            return

        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO promo_codes_usage (tg_id, code) VALUES (%s, %s)", (message.from_user.id, code))

        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET balance = balance + %s WHERE tg_id = %s", (reward, message.from_user.id))
        
        await conn.commit()
        await message.answer(f"Поздравляем! Вы получили {reward} 💎. Ваш баланс обновлён.")

    except Exception as e:
        await message.answer(f"Ошибка при обработке промокода: {e}")
    finally:
        await state.clear()
        conn.close()
