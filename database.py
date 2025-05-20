import asyncio
import inspect
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
    current_state = await state.get_state()
    if current_state == PromoActivationState.waiting_for_promo_code.state:
        print(f"[PROMO] User {message.from_user.id} уже ожидает ввод кода")
        return
    print(f"[PROMO] User {message.from_user.id} нажал '🎟️ Промокоды'")
    await state.set_state(PromoActivationState.waiting_for_promo_code)
    await message.answer("Введите промокод:")

@router.message(PromoActivationState.waiting_for_promo_code)
async def process_promo_activation(message: Message, state: FSMContext):
    if message.text == "🎟️ Промокоды":
        return

    code = message.text.strip().upper()
    user_id = message.from_user.id
    print(f"[PROMO] User {user_id} ввёл код: {code}")

    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT rank FROM users WHERE tg_id = %s", (user_id,))
            user_row = await cur.fetchone()

            if not user_row:
                await message.answer("Сначала отправьте /start.")
                await state.clear()
                return

            rank = user_row[0]
            if rank == "Гость":
                await message.answer("🚫 Промокоды недоступны для гостей.")
                await state.clear()
                return

            await cur.execute("SELECT reward FROM promo_codes WHERE code = %s", (code,))
            promo = await cur.fetchone()
            if not promo:
                await message.answer("Неверный промокод.")
                await state.clear()
                return

            reward = promo[0]

            await cur.execute("SELECT 1 FROM promo_codes_usage WHERE tg_id = %s AND code = %s", (user_id, code))
            already_used = await cur.fetchone()
            if already_used:
                await message.answer("Вы уже использовали этот промокод.")
                await state.clear()
                return

            await cur.execute("INSERT INTO promo_codes_usage (tg_id, code) VALUES (%s, %s)", (user_id, code))
            await cur.execute("UPDATE users SET balance = balance + %s WHERE tg_id = %s", (reward, user_id))
            await conn.commit()

        await message.answer(f"🎉 Промокод активирован! Получено {reward} 💎.")
        print(f"[PROMO] Промокод {code} активирован пользователем {user_id}, +{reward} 💎")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка при активации промокода: {e}")
        print("[PROMO ERROR]", e)
    finally:
        await state.clear()
        if inspect.isawaitable(safe_close(conn)):
            await safe_close(conn)
        else:
            safe_close(conn)
