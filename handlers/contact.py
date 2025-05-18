import re
from aiogram import Router, F, types
from aiogram.types import Message
from database import get_connection

router = Router()

# Задаем ID администратора (директора)
ADMIN_ID = 1016554091

# Пользователь нажимает кнопку «📩 Связь» – получает приглашение отправить сообщение (функция доступна только обычным пользователям)
@router.message(F.text == "📩 Связь")
async def contact_intro(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Администратор не может использовать эту функцию.")
        return
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")
    print(f"[CONTACT] Пользователь {message.from_user.id} начал контакт.")

# При обычном сообщении от пользователя (не являющемся reply) – обработка отправки администрации
@router.message()
async def receive_contact_message(message: Message):
    # Если сообщение является reply или отправлено администратором – пропускаем
    if message.from_user.id == ADMIN_ID or message.reply_to_message is not None:
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Проверка регистрации пользователя; если нет – регистрируем
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
        sender_name = (f"@{message.from_user.username}"
                       if message.from_user.username
                       else (message.from_user.full_name or "-"))
        # Формируем текст с маркером (UID) – этот маркер будет нужен для извлечения ID целевого пользователя
        text = (
            f"📩 <b>Новое сообщение от {sender_name}</b>\n\n"
            f"{message.text}\n\n"
            f"<code>UID:{message.from_user.id}</code>"
        )
        
        # Отправляем сообщение администрации (без inline-клавиатуры)
        sent_msg = await message.bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        await message.answer("📨 Сообщение отправлено администрации.")
        print(f"[CONTACT] Сообщение от {message.from_user.id} отправлено администрации (msg id: {sent_msg.message_id}).")
    except Exception as e:
        print("[CONTACT ERROR] При отправке сообщения администрации:", e)
        await message.answer("❗ Не удалось отправить сообщение администрации.")
    finally:
        conn.close()

# Обработчик для ответа администратора.
# Срабатывает, если администратор (ADMIN_ID) отвечает в режиме reply (то есть, есть поле reply_to_message)
@router.message(lambda message: message.from_user.id == ADMIN_ID and message.reply_to_message is not None)
async def admin_reply_handler(message: Message):
    # Попытка извлечь текст исходного сообщения. Если оно текстовое – берём message.reply_to_message.text,
    # иначе, если, например, сообщение с фото, можно попробовать message.reply_to_message.caption
    reply_content = message.reply_to_message.text or message.reply_to_message.caption
    if not reply_content:
        await message.answer("Невозможно определить получателя ответа (текст недоступен).")
        return

    # Ищем маркер вида "UID:<число>" в тексте исходного сообщения
    match = re.search(r"UID:(\d+)", reply_content)
    if not match:
        await message.answer("Не удалось извлечь ID пользователя из исходного сообщения. Проверьте, что оно содержит маркер <code>UID:...</code>.")
        return

    target_user_id = int(match.group(1))
    try:
        # Используем copy_message для пересылки ответа (любой тип – текст, фото, голос и т.д.)
        await message.bot.copy_message(
            chat_id=target_user_id,
            from_chat_id=ADMIN_ID,
            message_id=message.message_id
        )
        await message.answer("Ответ отправлен пользователю.")
        print(f"[REPLY] Ответ администратора от {message.from_user.id} отправлен пользователю {target_user_id}.")
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: {e}")
        print("[REPLY ERROR]", e)
