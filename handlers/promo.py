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
    # Отладочный вывод при нажатии на кнопку промокодов
    print(f"[PROMO] User {message.from_user.id} нажал на кнопку '🎟️ Промокоды'")
    await state.set_state(PromoActivationState.waiting_for_promo_code)
    await message.answer("Введите промокод:")

@router.message(PromoActivationState.waiting_for_promo_code)
async def process_promo_activation(message: Message, state: FSMContext):
    # Проверяем, что обработчик вызывается
    print(f"[PROMO] Запуск process_promo_activation для пользователя {message.from_user.id}")
    
    # Приводим промокод к единому регистру, если требуется (например, верхнему)
    code = message.text.strip().upper()
    print(f"[PROMO] User {message.from_user.id} ввёл промокод: '{code}'")
    
    conn = await get_connection()
    try:
        # Поиск промокода в таблице promo_codes
        async with conn.cursor() as cur:
            await cur.execute("SELECT reward FROM promo_codes WHERE code = %s", (code,))
            row = await cur.fetchone()
        print(f"[PROMO] Полученная строка для промокода: {row}")
        
        if row is None:
            # Если промокод не найден, отправляем сообщение и завершаем FSM
            await message.answer("Неверный промокод. Попробуйте снова.")
            await state.clear()
            return
        
        reward = row[0]
        
        # Проверка, использовал ли пользователь этот промокод ранее
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM promo_codes_usage WHERE tg_id = %s AND code = %s", (message.from_user.id, code))
            usage = await cur.fetchone()
        print(f"[PROMO] Проверка использования промокода: {usage}")
        
        if usage is not None:
            await message.answer("Вы уже использовали данный промокод!")
            await state.clear()
            return
        
        # Регистрируем использование промокода и обновляем баланс пользователя
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO promo_codes_usage (tg_id, code) VALUES (%s, %s)", (message.from_user.id, code))
            await cur.execute("UPDATE users SET balance = balance + %s WHERE tg_id = %s", (reward, message.from_user.id))
        await conn.commit()
        print(f"[PROMO] Баланс обновлён для пользователя {message.from_user.id}, начислено {reward} 💎")
        await message.answer(f"Поздравляем! Вы получили {reward} 💎.")
    except Exception as e:
        print(f"[PROMO ERROR] {e}")
        await message.answer(f"Ошибка при обработке промокода: {e}")
    finally:
        await state.clear()
        await safe_close(conn)
