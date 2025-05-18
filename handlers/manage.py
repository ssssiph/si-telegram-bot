import re
from aiogram import Router, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiomysql import DictCursor  # Для получения результатов в виде словаря
from database import get_connection

router = Router()
ADMIN_ID = 1016554094  # Замените на ваш актуальный ID администратора (например, Генеральный директор)

# Функция для безопасного закрытия подключения
async def safe_close(conn):
    if conn:
        ret = conn.close()
        if ret is not None and hasattr(ret, '__await__'):
            await ret

# ================================  
#         ГЛАВНАЯ АДМИН-ПАНЕЛЬ  
# ================================  

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
        # Inline‑клавиатура для выбора раздела:
        # «Обращения», «События», «Пользователи»
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Обращения", callback_data="admin_contacts_list")],
            [InlineKeyboardButton(text="События", callback_data="admin_events_list")],
            [InlineKeyboardButton(text="Пользователи", callback_data="admin_users_list")]
        ])
        await message.answer("Панель управления. Выберите раздел:", reply_markup=inline_kb)
    except Exception as e:
        await message.answer(f"Ошибка в админке:\n<code>{e}</code>")
    finally:
        await safe_close(conn)

# ================================  
#          РАЗДЕЛ "ОБРАЩЕНИЯ"  
# ================================  

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
            created_at = contact.get("created_at")
            date_str = str(created_at) if created_at else ""
            # Формируем кнопку: "Имя (Юзернейм | ID) <Дата>"
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
        await safe_close(conn)

@router.callback_query(lambda query: query.data == "admin_contacts_list")
async def admin_contacts_list_callback(query: types.CallbackQuery, state: FSMContext):
    await send_contacts_list_to_admin(query.message, state)
    await query.answer()

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

@router.message(lambda m: m.from_user.id == ADMIN_ID)
async def process_contact_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    if "contact_reply_id" not in data or not data["contact_reply_id"]:
        return  # Если обращение не выбрано – игнорируем сообщение.
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
            await state.clear()
            return
        target_user_id = contact.get("tg_id")
        if message.content_type == 'text':
            await message.bot.send_message(target_user_id, f"📨 Ответ от администрации:\n\n{message.text}")
        else:
            await message.bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
        await message.answer("Ответ отправлен пользователю.")
        # После ответа обновляем список обращений, чтобы ответанное обращение исчезло
        await send_contacts_list_to_admin(message, state)
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: <code>{e}</code>")
    finally:
        current_state = await state.get_data()
        new_state = {}
        if "contacts_page" in current_state:
            new_state["contacts_page"] = current_state["contacts_page"]
        await state.set_data(new_state)
        await safe_close(conn)

# ================================  
#          РАЗДЕЛ "СОБЫТИЯ"  
# ================================  

async def send_events_list_to_admin(dest_message: Message, state: FSMContext):
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("events_page", 1)
        events_per_page = 9
        offset = (page - 1) * events_per_page
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM events ORDER BY datetime DESC LIMIT %s OFFSET %s",
                (events_per_page, offset)
            )
            events = await cur.fetchall()
        buttons = []
        # Кнопка для создания нового события
        buttons.append([InlineKeyboardButton(text="Создать событие", callback_data="event_create")])
        if events:
            for event in events:
                title = event.get("title") or "-"
                datetime_str = event.get("datetime") or "-"
                event_id = event.get("id")
                button_text = f"{title} | {datetime_str}"
                callback_data = f"event_edit:{event_id}"
                buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
            if len(events) == events_per_page:
                buttons.append([InlineKeyboardButton(text="Следующая страница", callback_data="events_page:next")])
        else:
            buttons.append([InlineKeyboardButton(text="Нет событий", callback_data="none")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await dest_message.answer("События:", reply_markup=kb)
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении событий: <code>{e}</code>")
    finally:
        await safe_close(conn)

@router.callback_query(lambda q: q.data == "admin_events_list")
async def admin_events_list_callback(query: types.CallbackQuery, state: FSMContext):
    await send_events_list_to_admin(query.message, state)
    await query.answer()

@router.callback_query(lambda q: q.data and q.data.startswith("events_page:"))
async def events_page_nav(query: types.CallbackQuery, state: FSMContext):
    direction = query.data.split(":", 1)[1]
    data = await state.get_data()
    page = data.get("events_page", 1)
    if direction == "next":
        page += 1
    else:
        page = max(1, page - 1)
    await state.update_data(events_page=page)
    await send_events_list_to_admin(query.message, state)
    await query.answer()

@router.callback_query(lambda q: q.data and q.data.startswith("event_edit:"))
async def event_edit_callback(query: types.CallbackQuery, state: FSMContext):
    event_id_str = query.data.split(":", 1)[1]
    try:
        event_id = int(event_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await query.message.answer(f"Редактирование события {event_id} не реализовано.")
    await query.answer()

@router.callback_query(lambda q: q.data == "event_create")
async def event_create_callback(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("Создание события не реализовано.")
    await query.answer()

# ================================  
#         РАЗДЕЛ "ПОЛЬЗОВАТЕЛИ"  
# ================================  

async def send_users_list_to_admin(dest_message: Message, state: FSMContext):
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("users_page", 1)
        users_per_page = 9
        offset = (page - 1) * users_per_page
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM users ORDER BY tg_id LIMIT %s OFFSET %s",
                (users_per_page, offset)
            )
            users = await cur.fetchall()
        if not users:
            await dest_message.answer("Нет зарегистрированных пользователей.")
            return
        buttons = []
        for user in users:
            full_name = (user.get("full_name") or "-").strip()
            username = f"@{user.get('username')}" if user.get("username") and user.get("username").strip() else "-"
            tg_id = user.get("tg_id")
            prefix = "❌" if user.get("blocked") else ""
            button_text = f"{prefix}{full_name} ({username} | {tg_id})"
            callback_data = f"user_manage:{tg_id}"
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        if len(users) == users_per_page:
            buttons.append([InlineKeyboardButton(text="Следующая страница", callback_data="users_page:next")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await dest_message.answer("Пользователи:", reply_markup=kb)
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении пользователей: <code>{e}</code>")
    finally:
        await safe_close(conn)

@router.callback_query(lambda q: q.data == "admin_users_list")
async def admin_users_list_callback(query: types.CallbackQuery, state: FSMContext):
    await send_users_list_to_admin(query.message, state)
    await query.answer()

@router.callback_query(lambda q: q.data and q.data.startswith("users_page:"))
async def users_page_nav(query: types.CallbackQuery, state: FSMContext):
    direction = query.data.split(":", 1)[1]
    data = await state.get_data()
    page = data.get("users_page", 1)
    if direction == "next":
        page += 1
    else:
        page = max(1, page - 1)
    await state.update_data(users_page=page)
    await send_users_list_to_admin(query.message, state)
    await query.answer()

@router.callback_query(lambda q: q.data and q.data.startswith("user_manage:"))
async def user_manage_callback(query: types.CallbackQuery, state: FSMContext):
    user_id_str = query.data.split(":", 1)[1]
    try:
        user_id = int(user_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await state.update_data(manage_user_id=user_id)
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (user_id,))
            user = await cur.fetchone()
        if not user:
            await query.message.answer("Пользователь не найден.")
            return
        options = []
        options.append(InlineKeyboardButton(text="Выдать алмазики", callback_data=f"user_diamond:{user_id}:give"))
        options.append(InlineKeyboardButton(text="Забрать алмазики", callback_data=f"user_diamond:{user_id}:take"))
        if user.get("blocked"):
            options.append(InlineKeyboardButton(text="Разблокировать", callback_data=f"user_toggle:{user_id}"))
        else:
            options.append(InlineKeyboardButton(text="Блокировать", callback_data=f"user_toggle:{user_id}"))
        options.append(InlineKeyboardButton(text="Назад", callback_data="admin_users_list"))
        kb = InlineKeyboardMarkup(inline_keyboard=[options])
        await query.message.answer("Управление пользователем:", reply_markup=kb)
        await query.answer()
    except Exception as e:
        await query.message.answer(f"Ошибка при получении данных пользователя: <code>{e}</code>")
    finally:
        await safe_close(conn)

from aiogram.fsm.state import StatesGroup, State
class UserDiamondState(StatesGroup):
    waiting_for_diamond_value = State()

@router.callback_query(lambda q: q.data and q.data.startswith("user_diamond:"))
async def user_diamond_callback(query: types.CallbackQuery, state: FSMContext):
    parts = query.data.split(":")
    try:
        user_id = int(parts[1])
        action = parts[2]  # "give" или "take"
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await state.update_data(manage_user_id=user_id, diamond_action=action)
    await query.message.answer("Введите количество алмазиков:")
    await UserDiamondState.waiting_for_diamond_value.set()
    await query.answer()

@router.message(UserDiamondState.waiting_for_diamond_value)
async def process_diamond_change(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("manage_user_id")
    action = data.get("diamond_action")
    try:
        value = int(message.text)
    except ValueError:
        await message.answer("Введите числовое значение.")
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            if action == "give":
                await cur.execute("UPDATE users SET balance = balance + %s WHERE tg_id = %s", (value, user_id))
            else:
                await cur.execute("UPDATE users SET balance = GREATEST(balance - %s, 0) WHERE tg_id = %s", (value, user_id))
            await conn.commit()
        # Уведомление пользователя о изменении баланса:
        if action == "give":
            notification = f"Вам было выдано {value} 💎."
        else:
            notification = f"У вас было снято {value} 💎."
        await message.bot.send_message(user_id, notification)
        await message.answer("Баланс обновлен.")
    except Exception as e:
        await message.answer(f"Ошибка при изменении баланса: <code>{e}</code>")
    finally:
        await state.clear()
        await safe_close(conn)
        await send_users_list_to_admin(message, state)

@router.callback_query(lambda q: q.data and q.data.startswith("user_toggle:"))
async def user_toggle_callback(query: types.CallbackQuery, state: FSMContext):
    user_id_str = query.data.split(":", 1)[1]
    try:
        user_id = int(user_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT blocked FROM users WHERE tg_id = %s", (user_id,))
            result = await cur.fetchone()
            if not result:
                await query.message.answer("Пользователь не найден.")
                return
            current_block = result[0]
            new_block = not current_block
            await cur.execute("UPDATE users SET blocked = %s WHERE tg_id = %s", (new_block, user_id))
            await conn.commit()
        await query.message.answer("Статус блокировки обновлен.")
        await query.answer()
        await send_users_list_to_admin(query.message, state)
    except Exception as e:
        await query.message.answer(f"Ошибка при изменении статуса: <code>{e}</code>")
    finally:
        await safe_close(conn)
