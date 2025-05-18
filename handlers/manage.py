import aiomysql
from aiogram import Router
from aiogram.types import Message
from keyboards import back_menu
from database import get_connection

router = Router()

@router.message(lambda message: message.text is not None and message.text.strip() == "🛠 Управление")
async def admin_panel(message: Message):
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Проверяем, существует ли пользователь
            await cur.execute("SELECT `rank` FROM users WHERE tg_id = %s", (message.from_user.id,))
            result = await cur.fetchone()

            if not result:
                # Если пользователь не найден, регистрируем его как Гость (если не админ)
                if message.from_user.id == 1016554091:
                    new_rank = 'Генеральный директор'
                else:
                    new_rank = 'Гость'
                await cur.execute("""
                    INSERT INTO users (tg_id, username, full_name, `rank`, balance)
                    VALUES (%s, %s, %s, %s, 0)
                """, (
                    message.from_user.id,
                    message.from_user.username or "-",
                    message.from_user.full_name or "-",
                    new_rank
                ))
                rank = new_rank
            else:
                rank = result[0]

        # Выводим полученный ранг
        await message.answer(f"🔍 Ваш ранг: <b>{rank}</b>")

        # Если ранг не "Генеральный директор" - доступ закрыт
        if rank != "Генеральный директор":
            await message.answer("❌ У вас нет доступа к управлению.")
            return

        # Если доступ имеется – выводим панель управления
        await message.answer(
            "🛠 Панель управления:\n\n"
            "1️⃣ Создать событие\n"
            "2️⃣ Редактировать/Удалить событие\n"
            "3️⃣ Управление пользователями\n"
            "0️⃣ Назад",
            reply_markup=back_menu
        )

    except Exception as e:
        await message.answer(f"❗ Произошла ошибка в админке:\n<code>{e}</code>")
        print("[MANAGE ERROR]", e)
    finally:
        conn.close()
