import aiomysql
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards import back_menu
from database import get_connection

router = Router()

class EventCreation(StatesGroup):
    title = State()
    description = State()
    prize = State()
    datetime = State()
    media = State()

@router.message(F.text == "🛠 Управление")
async def admin_panel(message: Message):
    try:
        conn = await get_connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT `rank` FROM users WHERE tg_id = %s", (message.from_user.id,))
            result = await cur.fetchone()

            if not result:
                await cur.execute("""
                    INSERT INTO users (tg_id, username, full_name, `rank`, balance)
                    VALUES (%s, %s, %s, 'Генеральный директор', 0)
                """, (
                    message.from_user.id,
                    message.from_user.username or "-",
                    message.from_user.full_name or "-"
                ))
                rank = 'Генеральный директор'
            else:
                rank = result[0]

        # 🔍 Всегда выводим ранг
        await message.answer(f"🔍 Ваш ранг: <b>{rank}</b>")

        # 🛡 Проверка прав
        if rank != "Генеральный директор":
            await message.answer("❌ У вас нет доступа к управлению.")
            return

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
        try:
            conn.close()
        except:
            pass
