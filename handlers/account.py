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

            username = message.from_user.username or "-"
            full_name = message.from_user.full_name or "-"

            if not user:
                await cur.execute("""
                    INSERT INTO users (tg_id, username, full_name, `rank`, balance)
                    VALUES (%s, %s, %s, 'Гость', 0)
                """, (message.from_user.id, username, full_name))
                await cur.execute("SELECT * FROM users WHERE tg_id = %s", (message.from_user.id,))
                user = await cur.fetchone()
            else:
                await cur.execute("""
                    UPDATE users SET username = %s, full_name = %s WHERE tg_id = %s
                """, (username, full_name, message.from_user.id))
                await conn.commit()
                user = (message.from_user.id, username, full_name, user[3], user[4])

            tg_id, username, full_name, rank, balance = user[:5]

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
