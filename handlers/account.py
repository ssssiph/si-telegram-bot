from aiogram import Router
from aiogram.types import Message
from database import get_connection

router = Router()

@router.message(lambda message: message.text is not None and message.text.strip() == "👤 Аккаунт")
async def account_info(message: Message):
    print(f"[ACCOUNT] Получили команду от пользователя {message.from_user.id}: {message.text}")
    conn = await get_connection()
    try:
        user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", message.from_user.id)
        if not user:
            await message.answer("❗ Пользователь не найден. Пожалуйста, отправьте /start для регистрации.")
            print(f"[ACCOUNT] Пользователь {message.from_user.id} не зарегистрирован!")
            return
        await message.answer(
            f"<b>🧾 Ваш аккаунт:</b>\n"
            f"ID: <code>{user['tg_id']}</code>\n"
            f"Имя: {user['full_name']}\n"
            f"Юзернейм: {user['username']}\n"
            f"Ранг: {user['rank']}\n"
            f"💎 Баланс: {user['balance']}"
        )
        print(f"[ACCOUNT] Информация для пользователя {message.from_user.id} отправлена.")
    finally:
        await conn.close()
