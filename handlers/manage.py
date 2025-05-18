import re
from aiogram import Router, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiomysql import DictCursor  # используем DictCursor вместо dictionary=True
from database import get_connection

router = Router()
ADMIN_ID = 1016554091  # ID администратора

# ---------------------------------------------
# Обработчик для кнопки "⚙️ Управление" из главного меню
# ---------------------------------------------
@router.message(lambda message: message.text is not None and message.text.strip() == "⚙️ Управление")
async def admin_panel(message: Message, state: FSMContext):
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `rank` FROM users WHERE tg_id = %s", (message.from_user.id,))
            result = await cur.fetchone()
            if not result:
                await message.answer("❗ Пользователь не найден. Отправьте /start для регистрации.")
                return
            user_rank = result[0]
        if user_rank != "Генеральный директор":
            await message.answer("Отказано в доступе.")
            return
        # Формируем inline‑клавиатуру для админпанели – одна кнопка "Связь"
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Связь", callback_data="admin_contacts_list")]
        ])
        await message.answer("Тестик", reply_markup=inline_kb)
    except Exception as e:
        await message.answer(f"Ошибка в админке:\n<code>{e}</code>")
    finally:
        if conn:
            await conn.close()

# Вспомогательная функция для извлечения списка обращений и отправки его администратору
async def send_contacts_list_to_admin(dest_message: Message, state: FSMContext):
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("contacts_page", 1)
        contacts_per_page = 9
        offset = (page - 1) * contacts_per_page

        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM contacts WHERE answered = FALSE ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (contacts_per_page, offset)
            )
            contacts = await cur.fetchall()
        if not contacts:
            await dest_message.answer("Нет новых обращений.")
            return

        buttons = []
        for contact in contacts:
            full_name = (contact.get("full_name") or "-").strip()
            username = f"@{contact.get('username')}" if contact.get("username") and contact.get("username").strip() else "-"
            contact_id = contact.get("id")
            # Форматируем дату из created_at; если она уже строка, можно вывести как есть
            created_at = contact.get("created_at")
            # Для простоты выводим дату как str; при необходимости можно использовать datetime.strftime
            date_str = str(created_at) if created_at else ""
            # Добавляем дату после скобок
            button_text = f"{full_name} ({username} | {contact_id}) {date_str}"
            callback_data = f"contact_reply:{contact_id}"
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        if len(contacts) == contacts_per_page:
            buttons.append([InlineKeyboardButton(text="Следующая страница", callback_data="contacts_page:next")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await dest_message.answer("Список обращений:", reply_markup=kb)
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении обращений: <code>{e}</code>")
    finally:
        if conn:
            await conn.close()

# -------------------------------------------------
# Callback для отображения списка обращений после нажатия "Связь" (из админпанели)
# -------------------------------------------------
@router.callback_query(lambda query: query.data == "admin_contacts_list")
async def admin_contacts_list_callback(query: types.CallbackQuery, state: FSMContext):
    # Сразу обновляем список обращений
    await send_contacts_list_to_admin(query.message, state)
    await query.answer()

# -------------------------------------------------
# Callback для навигации по страницам списка обращений
# -------------------------------------------------
@router.callback_query(lambda q: q.data and q.data.startswith("contacts_page:"))
async def contacts_page_nav(query: types.CallbackQuery, state: FSMContext):
    direction = query.data.split(":", 1)[1]
    data = await state.get_data()
    page = data.get("contacts_page", 1)
    if direction == "next":
        page += 1
    else:
        page = max(1, page - 1)
    await state.update_data(contacts_page=page)
    await send_contacts_list_to_admin(query.message, state)
    await query.answer()

# -------------------------------------------------
# Callback при выборе конкретного обращения
# -------------------------------------------------
@router.callback_query(lambda q: q.data and q.data.startswith("contact_reply:"))
async def contact_reply_select(query: types.CallbackQuery, state: FSMContext):
    contact_id_str = query.data.split(":", 1)[1]
    try:
        contact_id = int(contact_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await state.update_data(contact_reply_id=contact_id)
    await query.message.answer("Введите ответ для данного обращения:")
    await query.answer("Ожидается ваш ответ.")

# -------------------------------------------------
# Обработчик для ответа администрации на выбранное обращение
# -------------------------------------------------
@router.message(lambda m: m.from_user.id == ADMIN_ID)
async def process_contact_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    if "contact_reply_id" not in data or not data["contact_reply_id"]:
        return  # Если обращение не выбрано, игнорируем сообщение
    contact_id = data["contact_reply_id"]
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE contacts SET answered = TRUE WHERE id = %s", (contact_id,))
            await conn.commit()
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
            contact = await cur.fetchone()
        if not contact:
            await message.answer("Обращение не найдено.")
            # Не очищаем состояние, чтобы список оставался видимым, можно затем обновить его
            return
        target_user_id = contact.get("tg_id")
        await message.bot.send_message(target_user_id, f"📨 Ответ от администрации:\n\n{message.text}")
        await message.answer("Ответ отправлен пользователю.")
        print(f"[ADMIN REPLY] Ответ на обращение {contact_id} отправлен пользователю {target_user_id}.")
        # После ответа обновляем список обращений, чтобы ответанное обращение исчезло
        await send_contacts_list_to_admin(message, state)
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: <code>{e}</code>")
    finally:
        # Очищаем только ключ обработки ответа, сохраняя данные о текущей странице
        current_state = await state.get_data()
        new_state = {}
        if "contacts_page" in current_state:
            new_state["contacts_page"] = current_state["contacts_page"]
        await state.set_data(new_state)
        if conn:
            await conn.close()
