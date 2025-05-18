import re
from aiogram import Router, F, types
from aiogram.types import Message
from database import get_connection

router = Router()

# Укажите ID администратора
ADMIN_ID = 1016554091

@router.message(F.text == "📩 Связь")
async def contact_intro(message: Message):
    # Запрещаем администратору пользоваться этой функцией
    if message.from_user.id == ADMIN_ID:
        await message.answer("Администратор не может использовать эту функцию.")
        return
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")
    print(f"[CONTACT] Пользователь {message.from_user.id} начал контакт.")

@router.message()
async def receive_contact_message(message: Message):
    # Этот handler срабатывает для обычных сообщений, не являющихся reply, от НЕ администратора
    if message.from_user.id == ADMIN_ID or message.reply_to_message is not None:
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Регистрируем пользователя, если он не найден
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (message.from_user.id,))
            user = await cur.fetchone()
            if not user:
                await cur.execute(
                    "INSERT INTO users (tg_id, username, full_name, `rank`, balance) VALUES (%s, %s, %s, 'Гость', 0)",
                    (message.from_user.id, message.from_user.username or "-", message.from_user.full_name or "-")
                )
        sender_name = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.full_name or "-")
        # Формируем сообщение, дописывая скрытый маркер с ID пользователя
        text = (
            f"📩 <b>Новое сообщение от {sender_name}</b>\n\n"
            f"{message.text}\n\n"
            f"<code>UID:{message.from_user.id}</code>"
        )
        sent_msg = await message.bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        await message.answer("📨 Сообщение отправлено администрации.")
        print(f"[CONTACT] Сообщение от {message.from_user.id} отправлено администрации (msg id: {sent_msg.message_id}).")
    except Exception as e:
        print("[CONTACT ERROR]", e)
        await message.answer("❗ Не удалось отправить сообщение администрации.")
    finally:
        conn.close()

# Handler, который срабатывает, когда администратор отвечает (reply) на сообщение с маркером
@router.message(lambda m: m.from_user.id == ADMIN_ID and m.reply_to_message is not None)
async def admin_reply_handler(message: Message):
    # Отладочный вывод: печатаем содержание сообщения, на которое администратор отвечает
    reply_message = message.reply_to_message
    print("[DEBUG] admin_reply_handler triggered.")
    print("[DEBUG] Replied message text:", reply_message.text)
    print("[DEBUG] Replied message caption:", reply_message.caption)
    
    # Извлекаем содержимое исходного сообщения (текст или caption)
    content = reply_message.text or reply_message.caption
    if not content:
        await message.answer("Невозможно определить получателя ответа (нет текста/описания).")
        return

    # Ищем маркер вида "UID:<число>" в содержимом
    match = re.search(r"UID:(\d+)", content)
    if not match:
        await message.answer("Не удалось извлечь ID пользователя. Убедитесь, что исходное сообщение содержит маркер <code>UID:...</code>.")
        return
    target_user_id = int(match.group(1))
    print(f"[DEBUG] Извлечён target_user_id: {target_user_id}")

    # Если ответ администртора является текстовым, используем send_message, иначе пытаемся использовать copy_message
    if message.text:
        try:
            await message.bot.send_message(target_user_id, f"📨 Ответ от администрации:\n\n{message.text}")
            print(f"[REPLY] Текстовый ответ от {message.from_user.id} отправлен пользователю {target_user_id}.")
        except Exception as e:
            await message.answer(f"Ошибка при отправке текста: {e}")
            print("[REPLY ERROR]", e)
    else:
        try:
            await message.bot.copy_message(chat_id=target_user_id, from_chat_id=ADMIN_ID, message_id=message.message_id)
            print(f"[REPLY] Ответ (copy_message) от {message.from_user.id} отправлен пользователю {target_user_id}.")
        except Exception as e:
            await message.answer(f"Ошибка при копировании сообщения: {e}")
            print("[REPLY ERROR]", e)
    await message.answer("Ответ отправлен пользователю.")
