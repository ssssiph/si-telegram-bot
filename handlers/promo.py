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
    await state.set_state(PromoState.waiting_for_code)
    await message.answer("🔑 Введите промокод:")

@router.message(PromoState.waiting_for_code)
async def promo_process(message: Message, state: FSMContext):
    code = message.text.strip().upper()  # Приводим код к единому регистру
    user_id = message.from_user.id
    conn = await get_connection()

    try:
        async with conn.cursor() as cur:
            # Проверка существования промокода
            await cur.execute("SELECT reward FROM promo_codes WHERE code = %s", (code,))
            promo = await cur.fetchone()
            if not promo:
                await message.answer("❌ Неверный или несуществующий промокод.")
                return
            reward = promo[0]

            # Проверка: использовал ли уже пользователь этот промокод
            await cur.execute("SELECT 1 FROM promo_codes_usage WHERE tg_id = %s AND code = %s", (user_id, code))
            used = await cur.fetchone()
            if used:
                await message.answer("⚠️ Этот промокод уже был использован вами.")
                return

            # Регистрируем пользователя, если он отсутствует в таблице users
            await cur.execute("SELECT 1 FROM users WHERE tg_id = %s", (user_id,))
            exists = await cur.fetchone()
            if not exists:
                await cur.execute(
                    "INSERT INTO users (tg_id, username, full_name, rank, balance) VALUES (%s, %s, %s, 'Гость', 0)",
                    (user_id, message.from_user.username or "-", message.from_user.full_name or "-")
                )

            # Регистрируем использование промокода и обновляем баланс пользователя
            await cur.execute("INSERT INTO promo_codes_usage (tg_id, code) VALUES (%s, %s)", (user_id, code))
            await cur.execute("UPDATE users SET balance = balance + %s WHERE tg_id = %s", (reward, user_id))
            await conn.commit()

            await message.answer(f"🎉 Промокод успешно активирован! Вы получили {reward} 💎.")
    except Exception as e:
        print(f"[PROMO ERROR] {e}")
        await message.answer("🚫 Ошибка при активации промокода.")
    finally:
        await state.clear()
        close_result = safe_close(conn)
        if hasattr(close_result, '__await__'):
            await close_result
