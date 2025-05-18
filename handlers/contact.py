from aiogram import Router, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_connection

router = Router()

# Задаем ID администратора (директора)
ADMIN_ID = 1016554091

# Множество для хранения ID пользователей, ожидающих отправки сообщения администрации
waiting_for_contact = set()

# Словарь для хранения сессий ответа: key = admin_id, value = target_user_id
reply_sessions = {}

@router.message(F.text == "📩 Связь")
async def contact_intro(message: Message):
    # Не даем админу использовать эту функцию
    if message.from_user.id == ADMIN_ID:
        await message.answer("Администратор не может использовать эту функцию.")
        return
    waiting_for_contact.add(message.from_user.id)
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")
    print(f"[CONTACT] Пользователь {message.from_user.id} перешёл в режим отправки сообщения.")

@router.message()
async def receive_contact_message(message: Message):
    if message.from_user.id not in waiting_for_contact:
        return  # Если пользователь не в ожидании, выходим
    waiting_for_contact.remove(message.from_user.id)
    
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Проверяем, зарегистрирован ли пользователь; если не зарегистрирован — регистрируем
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
        
        # Создаем inline-клавиатуру с кнопкой "Ответить"
        inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Ответить", callback_data=f"reply_{message.from_user.id}")]
            ]
        )
        
        try:
            await message.bot.send_message(ADMIN_ID, text, reply_markup=inline_kb, parse_mode="HTML")
            await message.answer("📨 Сообщение отправлено администрации.")
            print(f"[CONTACT] Сообщение от {message.from_user.id} отправлено администрации.")
        except Exception as e:
            print("[CONTACT ERROR] При отправке сообщения администрации:", e)
            await message.answer("❗ Не удалось отправить сообщение администрации.")
            
    finally:
        conn.close()

@router.callback_query(lambda query: query.data is not None and query.data.startswith("reply_"))
async def admin_reply_callback(query: types.CallbackQuery):
    # Извлекаем target_user_id из callback_data, формат: reply_<tg_id>
    target_user_id_str = query.data.split("_", 1)[1]
    try:
        target_user_id = int(target_user_id_str)
    except ValueError:
        await query.answer("Ошибка: неверные данные", show_alert=True)
        return

    reply_sessions[query.from_user.id] = target_user_id
    await query.answer("Введите одно сообщение для ответа пользователю", show_alert=True)
    print(f"[REPLY] Администратор {query.from_user.id} готов ответить пользователю {target_user_id}.")

# Обработчик текста, который отправляет ответ от администрации
# Этот handler срабатывает только для администратора
@router.message(lambda message: message.from_user.id == ADMIN_ID)
async def admin_reply_handler(message: Message):
    if message.from_user.id not in reply_sessions:
        return
    target_user_id = reply_sessions.pop(message.from_user.id)
    try:
        await message.bot.send_message(
            target_user_id,
            f"📨 Ответ от администрации:\n\n{message.text}"
        )
        await message.answer("Ответ отправлен пользователю.")
        print(f"[REPLY] Ответ администратора {message.from_user.id} отправлен пользователю {target_user_id}.")
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: {e}")
        print("[REPLY ERROR]", e)
