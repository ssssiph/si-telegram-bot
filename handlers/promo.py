#promo.py
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
    print(f"[PROMO] User {message.from_user.id} ввёл код: {code}")

    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Проверка, существует ли такой промокод
            await cur.execute("SELECT reward FROM promo_codes WHERE code = %s", (code,))
            promo_row = await cur.fetchone()
            if not promo_row:
                await message.answer("❌ Неверный промокод.")
                await state.clear()
                return

            reward = promo_row[0]

            # Проверка, использовал ли уже
            await cur.execute("SELECT 1 FROM promo_codes_usage WHERE tg_id = %s AND code = %s", (message.from_user.id, code))
            already_used = await cur.fetchone()
            if already_used:
                await message.answer("⚠️ Вы уже использовали этот промокод.")
                await state.clear()
                return

            # Если пользователя нет — создаём его как гостя
            await cur.execute("SELECT 1 FROM users WHERE tg_id = %s", (message.from_user.id,))
            exists = await cur.fetchone()
            if not exists:
                await cur.execute(
                    "INSERT INTO users (tg_id, username, full_name, rank, balance) VALUES (%s, %s, %s, 'Гость', 0)",
                    (message.from_user.id, message.from_user.username or "-", message.from_user.full_name or "-")
                )

            # Сохраняем использование и обновляем баланс
            await cur.execute("INSERT INTO promo_codes_usage (tg_id, code) VALUES (%s, %s)", (message.from_user.id, code))
            await cur.execute("UPDATE users SET balance = balance + %s WHERE tg_id = %s", (reward, message.from_user.id))
            await conn.commit()

            await message.answer(f"🎉 Промокод активирован! Вам начислено {reward} 💎.")
            print(f"[PROMO] Промокод {code} активирован для {message.from_user.id}")
    except Exception as e:
        print(f"[PROMO ERROR] {e}")
        await message.answer(f"⚠️ Ошибка при активации промокода: {e}")
    finally:
        await state.clear()
        await safe_close(conn)
