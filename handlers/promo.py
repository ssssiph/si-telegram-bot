import asyncio
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
    # При нажатии на кнопку промокодов устанавливаем состояние
    print(f"[PROMO] User {message.from_user.id} нажал на кнопку '🎟️ Промокоды'")
    await state.set_state(PromoActivationState.waiting_for_promo_code)
    await message.answer("Введите промокод:")

@router.message(PromoActivationState.waiting_for_promo_code)
async def process_promo_activation(message: Message, state: FSMContext):
    # Приводим промокод к верхнему регистру (если база содержит коды в верхнем регистре)
    code = message.text.strip().upper()
    print(f"[PROMO] Запуск process_promo_activation для пользователя {message.from_user.id}")
    print(f"[PROMO] User {message.from_user.id} ввёл промокод: '{code}'")
    
    conn = await get_connection()
    try:
        # Проверяем наличие указанного промокода в таблице promo_codes
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT reward FROM promo_codes WHERE code = %s", (code,)
            )
            promo_row = await cursor.fetchone()
        print(f"[PROMO] Результат запроса промокода: {promo_row}")
        
        if promo_row is None:
            # Если промокод не найден
            await message.answer("Неверный промокод. Попробуйте снова.")
            await state.clear()
            return
        
        reward = promo_row[0]
        
        # Проверяем, не использовал ли уже пользователь этот промокод
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT 1 FROM promo_codes_usage WHERE tg_id = %s AND code = %s",
                (message.from_user.id, code)
            )
            usage_exists = await cursor.fetchone()
        print(f"[PROMO] Проверка использования промокода: {usage_exists}")
        
        if usage_exists is not None:
            await message.answer("Вы уже использовали данный промокод!")
            await state.clear()
            return
        
        # Регистрируем использование промокода и обновляем баланс пользователя
        async with conn.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO promo_codes_usage (tg_id, code) VALUES (%s, %s)",
                (message.from_user.id, code)
            )
            await cursor.execute(
                "UPDATE users SET balance = balance + %s WHERE tg_id = %s",
                (reward, message.from_user.id)
            )
        await conn.commit()
        print(f"[PROMO] Промокод активирован для пользователя {message.from_user.id}, начислено {reward} 💎")
        await message.answer(f"Поздравляем! Вы получили {reward} 💎.")
    except Exception as e:
        print(f"[PROMO ERROR] Ошибка при обработке промокода: {e}")
        await message.answer(f"Ошибка при обработке промокода: {e}")
    finally:
        await state.clear()
        await safe_close(conn)
