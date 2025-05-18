import os
from aiogram import Router, F, types
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_connection

router = Router()
ADMIN_ID = 1016554091  # ID администрации

# Группа состояний для обращения
class ContactState(StatesGroup):
    waiting_for_message = State()

@router.message(F.text == "📩 Связь")
async def contact_intro(message: Message, state: FSMContext):
    # Администратор не может отправлять обращения
    if message.from_user.id == ADMIN_ID:
        await message.answer("Администратор не может использовать эту функцию.")
        return
    await state.set_state(ContactState.waiting_for_message)
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")
    print(f"[CONTACT] Пользователь {message.from_user.id} перешёл в режим отправки сообщения.")

@router.message(ContactState.waiting_for_message)
async def receive_contact_message(message: Message, state: FSMContext):
    conn = await get_connection()
    try:
        # Регистрируем пользователя, если его нет в базе
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (message.from_user.id,))
            user = await cur.fetchone()
            if not user:
                await cur.execute(
                    "INSERT INTO users (tg_id, username, full_name, `rank`, balance) VALUES (%s, %s, %s, 'Гость', 0)",
                    (message.from_user.id,
                     message.from_user.username or "-",
                     message.from_user.full_name or "-")
                )
        # Определяем, что именно отправил пользователь
        if message.content_type == 'text':
            content = message.text
            admin_forward = False
        elif message.content_type in ['photo', 'video', 'voice', 'audio', 'document']:
            # Если есть caption – используем его, иначе вставляем имя типа сообщения
            content = message.caption if message.caption else f"<{message.content_type}>"
            admin_forward = True
        else:
            content = f"<{message.content_type}>"
            admin_forward = False

        sender_name = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.full_name or "-")
        
        # Формируем текст уведомления для администрации (с UID)
        text = (f"📩 <b>Новое сообщение от {sender_name}</b>\n\n"
                f"{content}\n\n"
                f"<code>UID:{message.from_user.id}</code>")

        # Сохраняем обращение в таблицу contacts
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO contacts (tg_id, username, full_name, message, answered) VALUES (%s, %s, %s, %s, FALSE)",
                (message.from_user.id,
                 message.from_user.username or "-",
                 message.from_user.full_name or "-",
                 content)
            )
        await conn.commit()

        # Отправляем обращение администрации:
        # Если сообщение содержит медиа – пересылаем оригинальное сообщение,
        # иначе – отправляем текстовое уведомление
        if admin_forward:
            forwarded = await message.bot.copy_message(
                chat_id=ADMIN_ID,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
        else:
            forwarded = await message.bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        await message.answer("📨 Сообщение отправлено администрации.")
        print(f"[CONTACT] Сообщение от {message.from_user.id} отправлено администрации (msg id: {forwarded.message_id}).")
    except Exception as e:
        print("[CONTACT ERROR]", e)
        await message.answer("❗ Не удалось отправить сообщение администрации.")
    finally:
        await state.clear()
        if conn:
            await conn.close()
