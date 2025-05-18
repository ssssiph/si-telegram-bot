from aiogram import Router, F
from aiogram.types import Message
from database import get_connection

router = Router()

@router.message(F.text == "👤 Аккаунт")
async def account_info(message: Message):
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (message.from_user.id,))
            user = await cur.fetchone()

            if not user:
                await cur.execute("""
                    INSERT INTO users (tg_id, username, full_name, `rank`, balance)
                    VALUES (%s, %s, %s, 'Гость', 0)
                """, (
                    message.from_user.id,
                    message.from_user.username or "-",
                    message.from_user.full_name or "-"
                ))
                await cur.execute("SELECT * FROM users WHERE tg_id = %s", (message.from_user.id,))
                user = await cur.fetchone()

            tg_id, username, full_name, rank, balance, *_ = user

            await message.answer(
                f"<b>🧾 Ваш аккаунт:</b>\n"
                f"ID: <code>{tg_id}</code>\n"
                f"Имя: {full_name}\n"
                f"Юзернейм: {username}\n"
                f"Ранг: {rank}\n"
                f"💎 Баланс: {balance}"
            )
    finally:
        conn.close()
