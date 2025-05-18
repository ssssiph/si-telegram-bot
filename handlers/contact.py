from aiogram import Router, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_connection

router = Router()

waiting_for_contact = set()

reply_sessions = {}

@router.message(F.text == "📩 Связь")
async def contact_intro(message: Message):
    waiting_for_contact.add(message.from_user.id)
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")

@router.message()
async def receive_contact_message(message: Message):
    if message.from_user.id not in waiting_for_contact:
        return
    waiting_for_contact.remove(message.from_user.id)
    
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
            sender_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name or "-"
            text = f"📩 <b>Новое сообщение от {sender_name}</b>\n\n{message.text}"
            
            inline_kb = InlineKeyboardMarkup(row_width=1)
            inline_kb.add(InlineKeyboardButton(text="Ответить", callback_data=f"reply_{message.from_user.id}"))
            
            await message.bot.send_message(1016554091, text, reply_markup=inline_kb)
            await message.answer("📨 Сообщение отправлено администрации.")
    finally:
        conn.close()

@router.callback_query(lambda query: query.data is not None and query.data.startswith("reply_"))
async def admin_reply_callback(query: types.CallbackQuery):
    target_user_id_str = query.data.split("_", 1)[1]
    try:
        target_user_id = int(target_user_id_str)
    except ValueError:
        await query.answer("Ошибка: неверные данные", show_alert=True)
        return
    
    reply_sessions[query.from_user.id] = target_user_id
    await query.answer("Введите одно сообщение для ответа пользователю", show_alert=True)

@router.message()
async def admin_reply_handler(message: Message):
    if message.from_user.id not in reply_sessions:
        return
    target_user_id = reply_sessions.pop(message.from_user.id)
    try:
        await message.bot.send_message(target_user_id, f"📨 Ответ от администрации:\n\n{message.text}")
        await message.answer("Ответ отправлен пользователю.")
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: {e}")
