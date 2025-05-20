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
    await state.set_state(PromoActivationState.waiting_for_promo_code)
    await message.answer("Введите промокод:")

@router.message(PromoActivationState.waiting_for_promo_code)
async def process_promo_activation(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    user_id = message.from_user.id
    conn = await get_connection()
    try:
        async with conn.cursor() as cursor:
            # Проверка наличия промокода
            await cursor.execute("SELECT reward FROM promo_codes WHERE code = %s", (code,))
            promo_row = await cursor.fetchone()
            if not promo_row:
                await message.answer("❌ Неверный промокод.")
                return
            reward = int(promo_row[0])

        # Проверка наличия пользователя и регистрация при необходимости
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT `rank` FROM users WHERE tg_id = %s", (user_id,))
            user_row = await cursor.fetchone()
            if not user_row:
                await cursor.execute("""
                    INSERT INTO users (tg_id, username, full_name, `rank`, balance)
                    VALUES (%s, %s, %s, 'Гость', 0)
                """, (
                    user_id,
                    message.from_user.username or "-",
                    message.from_user.full_name or "-"
                ))
                user_rank = "Гость"
            else:
                user_rank = user_row[0]

        # Генеральный директор может использовать промокоды многократно
        if user_rank != "Генеральный директор":
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1 FROM promo_codes_usage WHERE tg_id = %s AND code = %s", (user_id, code))
                already_used = await cursor.fetchone()
                if already_used:
                    await message.answer("⚠️ Вы уже использовали этот промокод.")
                    return

        # Применение промокода
        async with conn.cursor() as cursor:
            # Фиксируем использование, только если не директор
            if user_rank != "Генеральный директор":
                await cursor.execute(
                    "INSERT INTO promo_codes_usage (tg_id, code) VALUES (%s, %s)", (user_id, code)
                )
            await cursor.execute(
                "UPDATE users SET balance = balance + %s WHERE tg_id = %s", (reward, user_id)
            )
        await conn.commit()

        await message.answer(f"🎉 Промокод активирован! Вы получили {reward} 💎.")
        print(f"[PROMO] {user_rank} {user_id} активировал промокод '{code}' на {reward} 💎.")
    except Exception as e:
        print("[PROMO ERROR]", e)
        await message.answer(f"Ошибка при обработке промокода: {e}")
    finally:
        await state.clear()
        if inspect.isawaitable(safe_close(conn)):
            await safe_close(conn)
        else:
            safe_close(conn)
