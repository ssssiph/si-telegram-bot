import inspect
import aiomysql
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
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Проверка наличия промокода
            await cursor.execute("SELECT reward FROM promo_codes WHERE code = %s", (code,))
            promo = await cursor.fetchone()
            if not promo:
                await message.answer("❌ Неверный промокод.")
                await state.clear()
                return
            reward = int(promo["reward"])

            # Проверка/создание пользователя
            await cursor.execute("SELECT rank FROM users WHERE tg_id = %s", (user_id,))
            user = await cursor.fetchone()
            if not user:
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
                user_rank = user["rank"]

            # Проверка: использовал ли пользователь промокод
            await cursor.execute("SELECT 1 FROM promo_codes_usage WHERE tg_id = %s AND code = %s", (user_id, code))
            already_used = await cursor.fetchone()
            if already_used:
                await message.answer("⚠️ Вы уже использовали этот промокод.")
                await state.clear()
                return

            # Применение промокода
            await cursor.execute(
                "INSERT INTO promo_codes_usage (tg_id, code) VALUES (%s, %s)", (user_id, code)
            )
            await cursor.execute(
                "UPDATE users SET balance = balance + %s WHERE tg_id = %s", (reward, user_id)
            )
            await conn.commit()

        await message.answer(f"🎉 Промокод активирован! Вы получили {reward} 💎.")
        print(f"[PROMO] Пользователь {user_id} активировал промокод '{code}' и получил {reward} 💎")
    except aiomysql.IntegrityError as e:
        # Если промокод уже использован
        await message.answer("⚠️ Этот промокод уже был использован вами.")
        print(f"[PROMO] Ошибка IntegrityError для пользователя {user_id}: промокод уже использован")
    except Exception as e:
        await message.answer(f"❗ Ошибка при активации промокода: {e}")
        print("[PROMO ERROR]", e)
    finally:
        await state.clear()
        if inspect.isawaitable(safe_close(conn)):
            await safe_close(conn)
        else:
            safe_close(conn)
