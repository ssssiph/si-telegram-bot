from aiogram import Router, F, types
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_connection

router = Router()

ADMIN_ID = 1016554091  # ID администрации

# Определяем группу состояний для контакта
class ContactState(StatesGroup):
    waiting_for_message = State()

# При нажатии кнопки «📩 Связь» переводим пользователя в состояние ожидания
@router.message(F.text == "📩 Связь")
async def contact_intro(message: Message, state: FSMContext):
    # Администратор не может использовать эту функцию
    if message.from_user.id == ADMIN_ID:
        await message.answer("Администратор не может использовать эту функцию.")
        return
    await state.set_state(ContactState.waiting_for_message)
    await message.answer("✉️ Напиши сообщение, которое ты хочешь отправить администрации.")
    print(f"[CONTACT] Пользователь {message.from_user.id} перешёл в режим отправки сообщения.")

# Обработчик срабатывает, когда пользователь находится в состоянии ContactState.waiting_for_message
@router.message(ContactState.waiting_for_message)
async def receive_contact_message(message: Message, state: FSMContext):
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Проверяем, зарегистрирован ли пользователь; если не найден — регистрируем его
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (message.from_user.id,))
            user = await cur.fetchone()
            if not user:
                await cur.execute(
                    "INSERT INTO users (tg_id, username, full_name, `rank`, balance) VALUES (%s, %s, %s, 'Гость', 0)",
                    (message.from_user.id, message.from_user.username or "-", message.from_user.full_name or "-")
                )
        sender_name = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.full_name or "-")
        # Формируем текст с маркером, позволяющим идентифицировать отправителя
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
        await state.clear()
        if conn is not None:
            await conn.close()
