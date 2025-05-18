import os
import json
import re
from aiogram import Router, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State  # для aiogram v3.x
from aiomysql import DictCursor  # для получения результатов в виде словаря
from database import get_connection

router = Router()
ADMIN_ID = 1016554094  # Замените на актуальный ID администратора

# Получаем список каналов для публикации событий из env, например: "-1001234567890,-1009876543210"
channels_raw = os.getenv("CHANNEL_IDS", "")
CHANNEL_IDS = [int(ch.strip()) for ch in channels_raw.split(",") if ch.strip()]

# Функция для безопасного закрытия подключения
async def safe_close(conn):
    if conn:
        try:
            ret = conn.close()
            if ret is not None and hasattr(ret, '__await__'):
                await ret
        except Exception as ex:
            print("safe_close error:", ex)
            pass

# ================================  
#          ГЛАВНАЯ АДМИН-ПАНЕЛЬ  
# ================================  

@router.message(lambda message: message.text and message.text.strip() == "⚙️ Управление")
async def admin_panel(message: Message, state: FSMContext):
    print("[Admin Panel] Запуск главного раздела для", message.from_user.id)
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
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Обращения", callback_data="admin_contacts_list")],
            [InlineKeyboardButton(text="События", callback_data="admin_events_list")],
            [InlineKeyboardButton(text="Пользователи", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="Объявления", callback_data="admin_broadcast")]
        ])
        await message.answer("Панель управления. Выберите раздел:", reply_markup=kb)
        print("[Admin Panel] Панель выведена")
    except Exception as e:
        await message.answer(f"Ошибка в админке:\n<code>{e}</code>")
        print("[Admin Panel ERROR]", e)
    finally:
        await safe_close(conn)

# ================================  
#          РАЗДЕЛ "ОБРАЩЕНИЯ"  
# ================================  

async def send_contacts_list_to_admin(dest_message: Message, state: FSMContext):
    print("[Обращения] Получение списка обращений")
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
            button_text = f"{full_name} ({username} | {contact_id}) {date_str}"
            callback_data = f"contact_reply:{contact_id}"
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        if len(contacts) == contacts_per_page:
            buttons.append([InlineKeyboardButton(text="Следующая страница", callback_data="contacts_page:next")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await dest_message.answer("Список обращений:", reply_markup=kb)
        print("[Обращения] Список отправлен")
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении обращений: <code>{e}</code>")
        print("[Обращения ERROR]", e)
    finally:
        await safe_close(conn)

@router.callback_query(lambda query: query.data == "admin_contacts_list")
async def admin_contacts_list_callback(query: types.CallbackQuery, state: FSMContext):
    print("[Обращения] Нажата кнопка 'Обращения'")
    await send_contacts_list_to_admin(query.message, state)
    await query.answer()

@router.callback_query(lambda q: q.data and q.data.startswith("contacts_page:"))
async def contacts_page_nav(query: types.CallbackQuery, state: FSMContext):
    direction = query.data.split(":", 1)[1]
    data = await state.get_data()
    page = data.get("contacts_page", 1)
    print(f"[Обращения] Навигация по страницам, текущая страница {page}, направление: {direction}")
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
    print(f"[Обращения] Выбрано обращение {contact_id} для ответа")
    await query.message.answer("Введите ответ для данного обращения:")
    await query.answer("Ожидается ваш ответ.")

@router.message(lambda m: m.from_user.id == ADMIN_ID)
async def process_contact_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    if "contact_reply_id" not in data or not data["contact_reply_id"]:
        print("[Обращения] Нет выбранного обращения для ответа")
        return
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
        if not target_user_id:
            await message.answer("Ошибка: у обращения отсутствует tg_id.")
            return
        print(f"[Обращения] Отправка ответа пользователю {target_user_id}")
        if message.content_type == 'text':
            await message.bot.send_message(target_user_id, f"📨 Ответ от администрации:\n\n{message.text}")
        else:
            await message.bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
        await message.answer("Ответ отправлен пользователю.")
        await send_contacts_list_to_admin(message, state)
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: <code>{e}</code>")
        print("[Обращения ERROR при ответе]", e)
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

# FSM для создания события
class EventCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_datetime = State()
    waiting_for_description = State()
    waiting_for_prize = State()

@router.callback_query(lambda q: q.data == "event_create")
async def event_create_callback(query: types.CallbackQuery, state: FSMContext):
    print("[События] Начало создания события")
    await query.message.answer("Введите название события:")
    await EventCreation.waiting_for_title.set()
    await query.answer()

@router.message(EventCreation.waiting_for_title)
async def process_event_title(message: Message, state: FSMContext):
    await state.update_data(event_title=message.text)
    await message.answer("Введите дату и время события:")
    await EventCreation.next()
    print("[События] Получено название:", message.text)

@router.message(EventCreation.waiting_for_datetime)
async def process_event_datetime(message: Message, state: FSMContext):
    await state.update_data(event_datetime=message.text)
    await message.answer("Введите описание события:")
    await EventCreation.next()
    print("[События] Получена дата и время:", message.text)

@router.message(EventCreation.waiting_for_description)
async def process_event_description(message: Message, state: FSMContext):
    await state.update_data(event_description=message.text)
    await message.answer("Введите приз (или оставьте пустым):")
    await EventCreation.next()
    print("[События] Получено описание:", message.text)

@router.message(EventCreation.waiting_for_prize)
async def process_event_prize(message: Message, state: FSMContext):
    prize = message.text if message.text else ""
    data = await state.get_data()
    title = data.get("event_title")
    datetime_str = data.get("event_datetime")
    description = data.get("event_description")
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Предполагается, что в таблице events есть колонка published (TEXT)
            await cur.execute(
                "INSERT INTO events (title, description, prize, datetime, media, creator_id, published) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (title, description, prize, datetime_str, "", message.from_user.id, "{}")
            )
            await conn.commit()
            event_id = cur.lastrowid
        await message.answer(f"Событие создано с ID: {event_id}. Теперь выберите действие:",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text="Опубликовать событие", callback_data=f"event_publish:{event_id}")],
                                 [InlineKeyboardButton(text="Редактировать событие", callback_data=f"event_edit:{event_id}")],
                                 [InlineKeyboardButton(text="Удалить событие", callback_data=f"event_delete:{event_id}")],
                                 [InlineKeyboardButton(text="Назад", callback_data="admin_events_list")]
                             ]))
        print("[События] Событие создано с ID:", event_id)
    except Exception as e:
        await message.answer(f"Ошибка при создании события: <code>{e}</code>")
        print("[События ERROR при создании]", e)
    finally:
        await state.clear()
        await safe_close(conn)

@router.callback_query(lambda q: q.data == "admin_events_list")
async def admin_events_list_callback(query: types.CallbackQuery, state: FSMContext):
    await send_events_list_to_admin(query.message, state)
    await query.answer()

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
        print("[События] Список событий отправлен")
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении событий: <code>{e}</code>")
        print("[События ERROR при получении]", e)
    finally:
        await safe_close(conn)

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

@router.callback_query(lambda q: q.data and q.data.startswith("event_publish:"))
async def event_publish_callback(query: types.CallbackQuery, state: FSMContext):
    event_id_str = query.data.split(":", 1)[1]
    try:
        event_id = int(event_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
            event = await cur.fetchone()
        if not event:
            await query.message.answer("Событие не найдено.")
            return
        publish_text = (
            f"📢 Событие!\n\nНазвание: {event.get('title')}\nДата и время: {event.get('datetime')}\n"
            f"Описание: {event.get('description')}\nПриз: {event.get('prize')}"
        )
        published = {}  # маппинг: channel_id -> message_id
        for ch in CHANNEL_IDS:
            try:
                sent = await query.bot.send_message(ch, publish_text)
                published[str(ch)] = sent.message_id
            except Exception as pub_e:
                print(f"[События] Ошибка публикации в канале {ch}: {pub_e}")
        async with conn.cursor() as cur:
            await cur.execute("UPDATE events SET published = %s WHERE id = %s", (json.dumps(published), event_id))
            await conn.commit()
        await query.message.answer("Событие опубликовано во всех каналах.")
        print(f"[События] Событие {event_id} опубликовано:", published)
    except Exception as e:
        await query.message.answer(f"Ошибка при публикации события: <code>{e}</code>")
        print("[События ERROR при публикации]", e)
    finally:
        await safe_close(conn)
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

@router.callback_query(lambda q: q.data and q.data.startswith("event_delete:"))
async def event_delete_callback(query: types.CallbackQuery, state: FSMContext):
    event_id_str = query.data.split(":", 1)[1]
    try:
        event_id = int(event_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM events WHERE id = %s", (event_id,))
            await conn.commit()
        await query.message.answer("Событие удалено.")
        print(f"[События] Событие {event_id} удалено")
    except Exception as e:
        await query.message.answer(f"Ошибка при удалении события: <code>{e}</code>")
        print("[События ERROR при удалении]", e)
    finally:
        await safe_close(conn)
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
        print("[Пользователи] Список пользователей отправлен")
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении пользователей: <code>{e}</code>")
        print("[Пользователи ERROR]", e)
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
        print(f"[Пользователи] Открыто управление для пользователя {user_id}")
        await query.answer()
    except Exception as e:
        await query.message.answer(f"Ошибка при получении данных пользователя: <code>{e}</code>")
        print("[Пользователи ERROR при управлении]", e)
    finally:
        await safe_close(conn)

# Состояния для изменения баланса (алмазики)
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
    print(f"[Пользователи] Запрошено изменение баланса для {user_id}, действие {action}")
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
        if action == "give":
            notification = f"Вам было выдано {value} 💎."
        else:
            notification = f"У вас было снято {value} 💎."
        await message.bot.send_message(user_id, notification)
        await message.answer("Баланс обновлен.")
        print(f"[Пользователи] Баланс изменен для {user_id}: {action} {value}")
    except Exception as e:
        await message.answer(f"Ошибка при изменении баланса: <code>{e}</code>")
        print("[Пользователи ERROR при балансе]", e)
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
        print(f"[Пользователи] Статус блокировки изменен для {user_id} на {new_block}")
        await query.answer()
        await send_users_list_to_admin(query.message, state)
    except Exception as e:
        await query.message.answer(f"Ошибка при изменении статуса: <code>{e}</code>")
        print("[Пользователи ERROR при блокировке]", e)
    finally:
        await safe_close(conn)

# ================================  
#         РАЗДЕЛ "ОБЪЯВЛЕНИЯ"  
# ================================  

class BroadcastState(StatesGroup):
    waiting_for_broadcast_text = State()

@router.callback_query(lambda q: q.data == "admin_broadcast")
async def broadcast_callback(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("Введите текст объявления для рассылки всем пользователям:")
    await BroadcastState.waiting_for_broadcast_text.set()
    print("[Объявления] Начало рассылки объявления")
    await query.answer()

@router.message(BroadcastState.waiting_for_broadcast_text)
async def process_broadcast(message: Message, state: FSMContext):
    announcement = message.text
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT tg_id FROM users")
            users = await cur.fetchall()
        count = 0
        for user in users:
            tg_id = user.get("tg_id")
            try:
                await message.bot.send_message(tg_id, f"📣 Объявление:\n\n{announcement}")
                count += 1
            except Exception as e:
                print(f"[Объявления] Ошибка отправки объявления пользователю {tg_id}: {e}")
        await message.answer(f"Объявление отправлено {count} пользователям.")
        print(f"[Объявления] Рассказано {count} пользователям")
    except Exception as e:
        await message.answer(f"Ошибка при рассылке объявления: <code>{e}</code>")
        print("[Объявления ERROR]", e)
    finally:
        await state.clear()
        await safe_close(conn)
