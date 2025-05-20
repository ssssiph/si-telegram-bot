from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_connection, safe_close

router = Router()

class PromoActivationState(StatesGroup):
    waiting_for_promo_code = State()

@router.message(F.text == "🎟️ Промокоды")
async def promo_activation_start(message: Message, state: FSMContext):
    print(f"[PROMO] User {message.from_user.id} нажал на кнопку '🎟️ Промокоды'")
    await state.set_state(PromoActivationState.waiting_for_promo_code)
    await message.answer("Введите промокод:")

@router.message(PromoActivationState.waiting_for_promo_code)
async def process_promo_activation(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    print(f"[PROMO] User {message.from_user.id} ввёл промокод: '{code}'")
    
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT reward FROM promo_codes WHERE code = %s", (code,))
            row = await cur.fetchone()
        print(f"[PROMO] Полученная строка для промокода: {row}")
        
        if row is None:
            await message.answer("Неверный промокод. Попробуйте снова.")
            await state.clear()
            return
        
        reward = row[0]
        
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM promo_codes_usage WHERE tg_id = %s AND code = %s", (message.from_user.id, code))
            usage = await cur.fetchone()
        print(f"[PROMO] Проверка использования промокода: {usage}")
        
        if usage is not None:
            await message.answer("Вы уже использовали данный промокод!")
            await state.clear()
            return
        
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO promo_codes_usage (tg_id, code) VALUES (%s, %s)", (message.from_user.id, code))
            await cur.execute("UPDATE users SET balance = balance + %s WHERE tg_id = %s", (reward, message.from_user.id))
        await conn.commit()
        print(f"[PROMO] Баланс обновлён, начислено {reward} 💎")
        await message.answer(f"Поздравляем! Вы получили {reward} 💎.")
    except Exception as e:
        print(f"[PROMO ERROR] {e}")
        await message.answer(f"Ошибка при обработке промокода: {e}")
    finally:
        await state.clear()
        await safe_close(conn)
