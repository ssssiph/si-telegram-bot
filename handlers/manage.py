from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_connection

router = Router()

@router.message(lambda message: message.text is not None and message.text.strip() in ["⚙️ Управление", "Управление"])
async def admin_panel(message: Message):
    # Отладочный вывод
    print(f"[MANAGE] Triggered by user {message.from_user.id} with text: '{message.text.strip()}'")
    
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `rank` FROM users WHERE tg_id = %s", (message.from_user.id,))
            result = await cur.fetchone()
            if not result:
                await message.answer("❗ Пользователь не найден. Отправьте /start для регистрации.")
                print(f"[MANAGE] Пользователь {message.from_user.id} не найден в базе.")
                return
            user_rank = result[0]
            print(f"[MANAGE] User rank for {message.from_user.id}: {user_rank}")
        
        if user_rank != "Генеральный директор":
            await message.answer("Отказано в доступе.")
            print(f"[MANAGE] Отказано в доступе пользователю {message.from_user.id} с рангом {user_rank}.")
            return

        # Для администратора (Генеральный директор) создаем inline-клавиатуру с URL-кнопкой
        inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Перейти", url="https://example.com")]]
        )
        # Отправляем сообщение с текстом "Тестик" и прикреплённой кнопкой
        await message.answer("Тестик", reply_markup=inline_kb)
        print(f"[MANAGE] Сообщение с текстом 'Тестик' отправлено пользователю {message.from_user.id}.")
    except Exception as e:
        await message.answer(f"Ошибка в админке:\n<code>{e}</code>")
        print("[MANAGE ERROR]", e)
    finally:
        conn.close()
