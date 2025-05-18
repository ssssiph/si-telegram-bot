from aiogram import Router, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_connection

router = Router()

# ID администратора (тот, кто имеет право отвечать)
ADMIN_ID = 1016554091

# Новый state для ожидания ответа на конкретное обращение
class ContactReplyState(StatesGroup):
    waiting_for_reply = State()

# Обработчик кнопки, которая будет вызываться администратором для показа списка обращений.
# ОБРАТИТЕ ВНИМАНИЕ: эта кнопка (в административном меню) теперь называется "Связь"
@router.message(lambda message: message.text is not None and message.text.strip() == "Связь")
async def admin_contacts_list(message: Message, state: FSMContext):
    # Проверяем, что пользователь – администратор (ранг "Генеральный директор")
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `rank` FROM users WHERE tg_id = %s", (message.from_user.id,))
            result = await cur.fetchone()
            if not result:
                await message.answer("❗ Пользователь не найден. Отправьте /start для регистрации.")
                return
            rank = result[0]
        if rank != "Генеральный директор":
            await message.answer("Отказано в доступе.")
            return

        # Получаем номер страницы из состояния или устанавливаем по умолчанию 1
        page = 1
        data = await state.get_data()
        if "contacts_page" in data:
            page = data["contacts_page"]

        contacts_per_page = 9  # показываем 9 запросов на странице
        offset = (page - 1) * contacts_per_page

        conn2 = await get_connection()
        async with conn2.cursor(dictionary=True) as cur:
            await cur.execute("SELECT * FROM contacts WHERE answered = FALSE ORDER BY created_at DESC LIMIT %s OFFSET %s", (contacts_per_page, offset))
            contacts = await cur.fetchall()
        await conn2.close()

        if not contacts:
            await message.answer("Нет новых обращений.")
            return

        # Строим inline-клавиатуру: по одной кнопке на запрос
        kb_buttons = []
        for contact in contacts:
            # Формат кнопки: "<имя пользователя> (<юзернейм> или '-' если его нет | айди обращения)"
            user_display = contact['full_name'] if contact['full_name'] and contact['full_name'].strip() else "-"
            username_display = f"@{contact['username']}" if contact['username'] and contact['username'].strip() else "-"
            button_text = f"{user_display} ({username_display} | {contact['id']})"
            callback_data = f"contact_reply:{contact['id']}"
            kb_buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
        # Если на этой странице ровно contacts_per_page, добавляем кнопку "Следующая страница"
        if len(contacts) == contacts_per_page:
            kb_buttons.append([InlineKeyboardButton(text="Следующая страница", callback_data="contacts_page:next")])
        
        inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
        await message.answer("Обращения пользователей:", reply_markup=inline_kb)
    except Exception as e:
        await message.answer(f"Ошибка при получении обращений: <code>{e}</code>")
    finally:
        conn.close()

# Обработчик для навигации между страницами обращений
@router.callback_query(lambda query: query.data and query.data.startswith("contacts_page:"))
async def contacts_page_callback(query: types.CallbackQuery, state: FSMContext):
    direction = query.data.split(":", 1)[1]
    data = await state.get_data()
    page = data.get("contacts_page", 1)
    if direction == "next":
        page += 1
    else:
        page = max(1, page - 1)
    await state.update_data(contacts_page=page)
    # Обновляем сообщение со списком обращений
    await query.message.edit_reply_markup()  # удалим старые кнопки
    await admin_contacts_list(query.message, state)
    await query.answer()

# Обработчик для нажатия на кнопку конкретного обращения
@router.callback_query(lambda query: query.data and query.data.startswith("contact_reply:"))
async def contact_reply_callback(query: types.CallbackQuery, state: FSMContext):
    contact_id_str = query.data.split(":", 1)[1]
    try:
        contact_id = int(contact_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    # Сохраняем ID обращения для дальнейшего ответа
    await state.update_data(contact_reply_id=contact_id)
    await query.message.answer("Введите ответ для данного обращения:")
    await ContactReplyState.waiting_for_reply.set()
    await query.answer("Ожидается ваш ответ.")

# Обработчик, получающий ответ администратора на конкретное обращение
@router.message(ContactReplyState.waiting_for_reply)
async def process_contact_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    if "contact_reply_id" not in data:
        await message.answer("Ошибка: не найдено обращение для ответа.")
        await state.clear()
        return
    contact_id = data["contact_reply_id"]
    conn = await get_connection()
    try:
        async with conn.cursor(dictionary=True) as cur:
            await cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
            contact = await cur.fetchone()
            if not contact:
                await message.answer("Обращение не найдено.")
                await state.clear()
                return
            # Помечаем обращение как отвеченное
            await cur.execute("UPDATE contacts SET answered = TRUE WHERE id = %s", (contact_id,))
        target_user_id = contact['tg_id']
        # Отправляем ответ пользователю. Предполагается, что ответ – текстовое сообщение
        await message.bot.send_message(target_user_id, f"📨 Ответ от администрации:\n\n{message.text}")
        await message.answer("Ответ отправлен пользователю.")
        print(f"[ADMIN REPLY] Ответ на обращение {contact_id} отправлен пользователю {target_user_id}.")
    except Exception as e:
        await message.answer(f"Ошибка отправки ответа: <code>{e}</code>")
        print("[ADMIN REPLY ERROR]", e)
    finally:
        await state.clear()
        await conn.close()
