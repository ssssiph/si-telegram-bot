from aiogram import Router, F, types
from aiogram.types import Message
from database import get_connection

router = Router()

# Задаем ID администратора (директора)
ADMIN_ID = 1016554091

# Множество для хранения ID пользователей, ожидающих отправки сообщения администрации
waiting_for_contact = set()

# Словарь для хранения соответствий:
# key = message_id (сообщения, отправленного администрации ботом)
# value = target_user_id (пользователь, от которого пришло сообщение)
contact_mapping = {}

@router.message(F.text == "📩 Связь")
async def contact_intro(message: Message):
    # Функция недоступна для администратора
    if message.from_user.id == ADMIN_ID:
        await message.answer("Администратор не может использовать эту функцию.")
        return
    waiting_for_contact.add(message.from_user.id)
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")
    print(f"[CONTACT] Пользователь {message.from_user.id} перешёл в режим отправки сообщения.")

@router.message()
async def receive_contact_message(message: Message):
    if message.from_user.id not in waiting_for_contact:
        return  # Если пользователь не ожидает отправки сообщения – выходим
    waiting_for_contact.remove(message.from_user.id)
    
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Проверяем, зарегистрирован ли пользователь; если нет – регистрируем
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
        text = f"📩 <b>Новое сообщение от {sender_name}</b>\n\n{message.text}"
        
        # Отправляем сообщение администрации и сохраняем его ID
        sent_msg = await message.bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        contact_mapping[sent_msg.message_id] = message.from_user.id
        
        await message.answer("📨 Сообщение отправлено администрации.")
        print(f"[CONTACT] Сообщение от {message.from_user.id} отправлено администрации (admin_msg_id={sent_msg.message_id}).")
    except Exception as e:
        print("[CONTACT ERROR] При отправке сообщения администрации:", e)
        await message.answer("❗ Не удалось отправить сообщение администрации.")
    finally:
        conn.close()

# Обработчик для ответа администратора
# Срабатывает, если сообщение от администратора является ответом (reply) на одно из пересланных сообщений
@router.message(lambda message: message.from_user.id == ADMIN_ID and message.reply_to_message is not None)
async def admin_reply_handler(message: Message):
    replied_msg_id = message.reply_to_message.message_id  # ID сообщения, на которое ответил администратор
    if replied_msg_id not in contact_mapping:
        await message.answer("Не найдена сессия для ответа на это сообщение.")
        return
    target_user_id = contact_mapping.pop(replied_msg_id)
    try:
        # Пересылаем ответ администратора (любого типа сообщения) исходному пользователю
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
