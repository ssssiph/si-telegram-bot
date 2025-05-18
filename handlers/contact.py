import re
from aiogram import Router, F, types
from aiogram.types import Message
from database import get_connection

router = Router()

# ID администратора (директора)
ADMIN_ID = 1016554091

@router.message(F.text == "📩 Связь")
async def contact_intro(message: Message):
    # Администратор не может использовать эту функцию
    if message.from_user.id == ADMIN_ID:
        await message.answer("Администратор не может использовать эту функцию.")
        return
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")
    print(f"[CONTACT] Пользователь {message.from_user.id} начал контакт.")

@router.message()
async def receive_contact_message(message: Message):
    # Этот handler срабатывает, если сообщение НЕ является reply и не от администратора
    if message.from_user.id == ADMIN_ID or message.reply_to_message is not None:
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Проверяем, зарегистрирован ли пользователь, если нет — регистрируем
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (message.from_user.id,))
            user = await cur.fetchone()
            if not user:
                await cur.execute(
                    """INSERT INTO users (tg_id, username, full_name, `rank`, balance)
                    VALUES (%s, %s, %s, 'Гость', 0)""",
                    (message.from_user.id,
                     message.from_user.username or "-",
                     message.from_user.full_name or "-")
                )
        # Формируем имя отправителя
        sender_name = (f"@{message.from_user.username}"
                       if message.from_user.username
                       else (message.from_user.full_name or "-"))
        # Добавляем маркер с ID пользователя (он будет виден в виде моноширинного текста)
        text = (f"📩 <b>Новое сообщение от {sender_name}</b>\n\n"
                f"{message.text}\n\n"
                f"<code>UID:{message.from_user.id}</code>")
        sent_msg = await message.bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        await message.answer("📨 Сообщение отправлено администрации.")
        print(f"[CONTACT] Сообщение от {message.from_user.id} отправлено администрации (msg id {sent_msg.message_id}).")
    except Exception as e:
        print("[CONTACT ERROR]", e)
        await message.answer("❗ Не удалось отправить сообщение администрации.")
    finally:
        conn.close()

@router.message(lambda m: m.from_user.id == ADMIN_ID and m.reply_to_message is not None)
async def admin_reply_handler(message: Message):
    """
    Этот handler срабатывает, когда администратор отвечает (reply) на сообщение,
    содержащее маркер с ID пользователя. Извлекаем ID и пересылаем ответ.
    """
    if not message.reply_to_message.text:
        await message.answer("Невозможно определить получателя ответа.")
        return

    # Ищем маркер вида "UID:<число>" в тексте сообщения, отправленного администрации
    match = re.search(r"UID:(\d+)", message.reply_to_message.text)
    if not match:
        await message.answer("Не удалось извлечь ID пользователя из сообщения.")
        return

    target_user_id = int(match.group(1))
    try:
        # Используем copy_message для пересылки ответа администратора, независимо от типа (текст, фото и т.д.)
        await message.bot.copy_message(
            chat_id=target_user_id,
            from_chat_id=ADMIN_ID,
            message_id=message.message_id
        )
        await message.answer("Ответ отправлен пользователю.")
        print(f"[REPLY] Ответ администратора {message.from_user.id} отправлен пользователю {target_user_id}.")
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: {e}")
        print("[REPLY ERROR]", e)
