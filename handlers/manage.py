from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_connection

router = Router()

@router.message(lambda message: message.text is not None and message.text.strip() == "⚙️ Управление")
async def admin_panel(message: Message):
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Проверяем наличие пользователя в базе
            await cur.execute("SELECT `rank` FROM users WHERE tg_id = %s", (message.from_user.id,))
            result = await cur.fetchone()
            if not result:
                await message.answer("❗ Пользователь не найден. Отправьте /start для регистрации.")
                return
            rank = result[0]
        # Если ранг не соответствует, выдаём отказ
        if rank != "Генеральный директор":
            await message.answer("Отказано в доступе.")
            return

        # Для пользователей с рангом "Генеральный директор" отправляем сообщение с inline URL‑кнопкой
        inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Перейти", url="https://example.com")]
            ]
        )
        await message.answer("Тестик", reply_markup=inline_kb)
    except Exception as e:
        await message.answer(f"Ошибка в админке:\n<code>{e}</code>")
    finally:
        conn.close()
