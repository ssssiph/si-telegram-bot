import os
import json
from aiogram import Router, types, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State    # для aiogram v3.x
from aiomysql import DictCursor                    # для работы с запросами в виде словаря
from database import get_connection

router = Router()
# Задайте действительный ID администратора
ADMIN_ID = 1016554091  
# Для каналов chat_id обычно отрицательный.
PUBLISH_CHANNEL_ID = -1002292957980

async def safe_close(conn):
    if conn:
        try:
            ret = conn.close()
            if ret is not None and hasattr(ret, '__await__'):
                await ret
        except Exception as ex:
            print("safe_close error:", ex)

# =============================================================================
# Helper: проверка, заблокирован ли пользователь
# =============================================================================
async def is_user_blocked(user_id: int) -> bool:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT blocked FROM users WHERE tg_id = %s", (user_id,))
            result = await cur.fetchone()
            return bool(result[0]) if result is not None else False
    except Exception as e:
        print("Error in is_user_blocked:", e)
        return False
    finally:
        await safe_close(conn)

# =============================================================================
# FSM для ответов на обращения
# =============================================================================
class ContactReplyState(StatesGroup):
    waiting_for_reply = State()

# =============================================================================
# FSM для создания событий
# =============================================================================
class EventCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_datetime = State()
    waiting_for_description = State()
    waiting_for_prize = State()
    waiting_for_media = State()

# =============================================================================
# FSM для редактирования событий
# =============================================================================
class EventEditState(StatesGroup):
    waiting_for_edit_details = State()

# =============================================================================
# FSM для редактирования пользователей (смена ранга)
# =============================================================================
class UserEditState(StatesGroup):
    waiting_for_new_rank = State()

# =============================================================================
# FSM для операций с алмазиками
# =============================================================================
class DiamondsState(StatesGroup):
    waiting_for_amount = State()

# =============================================================================
# Обработка входящих сообщений от пользователей (обращения)
# =============================================================================
@router.message(lambda m: m.chat.type == "private" and m.from_user.id != ADMIN_ID)
async def handle_incoming_contact(m: Message, state: FSMContext):
    # Если уже активен FSM, пропускаем
    if await state.get_state() is not None:
        return
    # Блокированные пользователи, или пользователи с рангом "Гость", не могут взаимодействовать
    if await is_user_blocked(m.from_user.id):
        await m.answer("🚫 Отказано в доступе.")
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT rank FROM users WHERE tg_id = %s", (m.from_user.id,))
            result = await cur.fetchone()
        if result is None or result[0] == "Гость":
            await m.answer("🚫 Отказано в доступе.")
            return

        sender_info = f"{m.from_user.full_name} (@{m.from_user.username})" if m.from_user.username else m.from_user.full_name
        if m.content_type == "text":
            content = m.text
        else:
            content = f"[Медиа: {m.content_type}]\nОтправитель: {sender_info}"
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO contacts (tg_id, full_name, username, message, answered) VALUES (%s, %s, %s, %s, %s)",
                (m.from_user.id, m.from_user.full_name, m.from_user.username, content, False)
            )
            await conn.commit()
        await m.answer("Ваше обращение принято.")
    except Exception as e:
        await m.answer("Ошибка при отправке обращения.")
        print("Error in handle_incoming_contact:", e)
    finally:
        conn.close()

# =============================================================================
# Главная админ-панель
# =============================================================================
@router.message(lambda message: message.text and message.text.strip().lower() == "⚙️ управление")
async def admin_panel(message: Message, state: FSMContext):
    await state.clear()
    print("[Admin] Запуск панели для", message.from_user.id)
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT rank FROM users WHERE tg_id = %s", (message.from_user.id,))
            result = await cur.fetchone()
            if not result:
                await message.answer("❗ Пользователь не найден. Используйте /start для регистрации.")
                return
            user_rank = result[0]
        if user_rank != "Генеральный директор":
            await message.answer("Отказано в доступе.")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Обращения", callback_data="admin_contacts_list")],
            [InlineKeyboardButton(text="📅 События", callback_data="admin_events_list")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_list")]
        ])
        await message.answer("Панель управления. Выберите раздел:", reply_markup=kb)
        print("[Admin] Меню выведено")
    except Exception as e:
        await message.answer(f"Ошибка в админ-панели:\n<code>{e}</code>")
        print("[Admin ERROR]", e)
    finally:
        await safe_close(conn)

# =============================================================================
# Раздел "Обращения"
# =============================================================================
async def send_contacts_list_to_admin(dest_message: Message, state: FSMContext):
    print("[Contacts] Запрос списка обращений")
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("contacts_page", 1)
        per_page = 9
        offset = (page - 1) * per_page
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM contacts WHERE answered = FALSE ORDER BY created_at DESC LIMIT %s OFFSET %s", (per_page, offset))
            contacts = await cur.fetchall()
        if not contacts:
            await dest_message.answer("Нет новых обращений.")
            return
        buttons = []
        for contact in contacts:
            cid = contact.get("id")
            full_name = contact.get("full_name") or "-"
            username = contact.get("username") or "-"
            created_at = contact.get("created_at")
            date_str = str(created_at) if created_at else ""
            btn_text = f"{full_name} (@{username} | {cid}) {date_str}"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"contact_reply:{cid}")])
        if len(contacts) == per_page:
            buttons.append([InlineKeyboardButton(text="➡️ Следующая страница", callback_data="contacts_page:next")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await dest_message.answer("Обращения:", reply_markup=kb)
        print("[Contacts] Список обращений отправлен")
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении обращений: <code>{e}</code>")
        print("[Contacts ERROR]", e)
    finally:
        await safe_close(conn)

@router.callback_query(lambda q: q.data == "admin_contacts_list")
async def admin_contacts_list_callback(query: types.CallbackQuery, state: FSMContext):
    await send_contacts_list_to_admin(query.message, state)
    await query.answer()

@router.callback_query(lambda q: q.data and q.data.startswith("contacts_page:"))
async def contacts_page_nav(query: types.CallbackQuery, state: FSMContext):
    direction = query.data.split(":", 1)[1]
    data = await state.get_data()
    page = data.get("contacts_page", 1)
    page = page + 1 if direction == "next" else max(1, page - 1)
    await state.update_data(contacts_page=page)
    await send_contacts_list_to_admin(query.message, state)
    await query.answer()

# При нажатии на кнопку ответа выводим исходное обращение
@router.callback_query(lambda q: q.data and q.data.startswith("contact_reply:"))
async def contact_reply_select(query: types.CallbackQuery, state: FSMContext):
    cid_str = query.data.split(":", 1)[1]
    try:
        cid = int(cid_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await state.update_data(contact_reply_id=cid)
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM contacts WHERE id = %s", (cid,))
            contact = await cur.fetchone()
        if contact:
            original_text = contact.get("message") or "Нет текста обращения."
            await query.message.answer(f"📨 Исходное обращение:\n\n{original_text}\n\nВведите ваш ответ:")
        else:
            await query.message.answer("Обращение не найдено.")
    except Exception as e:
        await query.message.answer(f"Ошибка при получении обращения: <code>{e}</code>")
        print("[Contacts ERROR]", e)
    finally:
        await safe_close(conn)
    await state.set_state(ContactReplyState.waiting_for_reply)
    await query.answer("Ожидается ваш ответ.")

@router.message(ContactReplyState.waiting_for_reply)
async def process_contact_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    cid = data.get("contact_reply_id")
    if not cid:
        await message.answer("Ошибка: обращение не выбрано.")
        await state.clear()
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE contacts SET answered = TRUE WHERE id = %s", (cid,))
            await conn.commit()
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM contacts WHERE id = %s", (cid,))
            contact = await cur.fetchone()
        if not contact:
            await message.answer("Обращение не найдено.")
            await state.clear()
            return
        target_id = contact.get("tg_id")
        if not target_id:
            await message.answer("Ошибка: отсутствует tg_id.")
            await state.clear()
            return
        original_text = contact.get("message") or "Нет текста обращения."
        author_info = f"{contact.get('full_name','-')}" + (f" (@{contact.get('username','-')})" if contact.get("username") else "")
        header = f"Ваше обращение от {author_info}:\n\n{original_text}\n\nОтвет от администрации:"
        if message.content_type == "text":
            await message.bot.send_message(target_id, header + "\n\n" + message.text)
        else:
            await message.bot.send_message(target_id, header + "\n\nОтвет ниже:")
            await message.bot.copy_message(
                chat_id=target_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
        await message.answer("Ответ отправлен пользователю.")
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: <code>{e}</code>")
        print("[Contacts ERROR при ответе]", e)
    finally:
        await state.clear()
        await safe_close(conn)
        await send_contacts_list_to_admin(message, state)

# =============================================================================
# Раздел "События"
# =============================================================================
async def send_events_list_to_admin(dest_message: Message, state: FSMContext):
    print("[Events] Запрос списка событий")
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("events_page", 1)
        per_page = 9
        offset = (page - 1) * per_page
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM events ORDER BY datetime DESC LIMIT %s OFFSET %s", (per_page, offset))
            events = await cur.fetchall()
        buttons = []
        buttons.append([InlineKeyboardButton(text="➕ Создать событие", callback_data="event_create")])
        if events:
            for event in events:
                title = event.get("title") or "-"
                datetime_str = event.get("datetime") or "-"
                eid = event.get("id")
                btn_text = f"{title} | {datetime_str}"
                buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"event_edit:{eid}")])
            if len(events) == per_page:
                buttons.append([InlineKeyboardButton(text="➡️ Следующая страница", callback_data="events_page:next")])
        else:
            buttons.append([InlineKeyboardButton(text="Нет событий", callback_data="none")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await dest_message.answer("События:", reply_markup=kb)
        print("[Events] Список событий отправлен")
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении событий: <code>{e}</code>")
        print("[Events ERROR при получении]", e)
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
    page = page + 1 if direction == "next" else max(1, page - 1)
    await state.update_data(events_page=page)
    await send_events_list_to_admin(query.message, state)
    await query.answer()

# Создание нового события
@router.callback_query(lambda q: q.data == "event_create")
async def event_create_callback(query: types.CallbackQuery, state: FSMContext):
    print("[Events] Начало создания события")
    await query.message.answer("Введите название события:")
    await state.set_state(EventCreation.waiting_for_title)
    await query.answer()

@router.message(EventCreation.waiting_for_title)
async def process_event_title(message: Message, state: FSMContext):
    await state.update_data(event_title=message.text)
    await message.answer("Введите дату и время события:")
    await state.set_state(EventCreation.waiting_for_datetime)
    print("[Events] Название:", message.text)

@router.message(EventCreation.waiting_for_datetime)
async def process_event_datetime(message: Message, state: FSMContext):
    await state.update_data(event_datetime=message.text)
    await message.answer("Введите описание события:")
    await state.set_state(EventCreation.waiting_for_description)
    print("[Events] Дата и время:", message.text)

@router.message(EventCreation.waiting_for_description)
async def process_event_description(message: Message, state: FSMContext):
    await state.update_data(event_description=message.text)
    await message.answer("Введите приз (или оставьте пустым):")
    await state.set_state(EventCreation.waiting_for_prize)
    print("[Events] Описание:", message.text)

@router.message(EventCreation.waiting_for_prize)
async def process_event_prize(message: Message, state: FSMContext):
    await state.update_data(event_prize=message.text)
    await message.answer("Отправьте изображение или голосовое сообщение для события или введите 'skip':")
    await state.set_state(EventCreation.waiting_for_media)
    print("[Events] Приз:", message.text)

@router.message(EventCreation.waiting_for_media)
async def process_event_media(message: Message, state: FSMContext):
    media = ""
    if message.text and message.text.lower() == "skip":
        media = ""
    else:
        if message.photo:
            media = message.photo[-1].file_id
        elif message.voice:
            media = message.voice.file_id
    data = await state.get_data()
    title = data.get("event_title")
    datetime_str = data.get("event_datetime")
    description = data.get("event_description")
    prize = data.get("event_prize")
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO events (title, description, prize, datetime, media, creator_id, published) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (title, description, prize, datetime_str, media, message.from_user.id, "{}")
            )
            await conn.commit()
            event_id = cur.lastrowid
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📣 Опубликовать", callback_data=f"event_publish:{event_id}"),
             InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"event_delete:{event_id}")],
            [InlineKeyboardButton(text="✏️ Редактировать событие", callback_data=f"event_edit:{event_id}")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_events_list")]
        ])
        await message.answer(f"Событие создано с ID: {event_id}. Теперь выберите действие:", reply_markup=kb)
        print("[Events] Событие создано, ID:", event_id)
    except Exception as e:
        await message.answer(f"Ошибка при создании события: <code>{e}</code>")
        print("[Events ERROR при создании]", e)
    finally:
        await state.clear()
        await safe_close(conn)

# Редактирование события
@router.callback_query(lambda q: q.data and q.data.startswith("event_edit:"))
async def event_edit_callback(query: types.CallbackQuery, state: FSMContext):
    eid_str = query.data.split(":", 1)[1]
    try:
        eid = int(eid_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            # Выбираем событие по id (убедитесь, что в таблице events есть поле id)
            await cur.execute("SELECT * FROM events WHERE id = %s", (eid,))
            event = await cur.fetchone()
        if not event:
            await query.message.answer("Событие не найдено.")
            return
        current_details = (
            f"Текущее название: {event.get('title')}\n"
            f"Дата и время: {event.get('datetime')}\n"
            f"Описание: {event.get('description')}\n"
            f"Приз: {event.get('prize')}\n"
            f"Медиа: {event.get('media') or 'нет'}\n\n"
            "Введите новые данные в формате:\n"
            "Название | Дата и время | Описание | Приз | Медиа (или 'skip')"
        )
        await query.message.answer(current_details)
        await state.update_data(edit_event_id=eid)
        await state.set_state(EventEditState.waiting_for_edit_details)
        await query.answer("Редактирование события начато.")
    except Exception as e:
        await query.message.answer(f"Ошибка при получении события: <code>{e}</code>")
        print("[Events ERROR при загрузке для редактирования]", e)
    finally:
        await safe_close(conn)

@router.message(EventEditState.waiting_for_edit_details)
async def process_event_edit(message: Message, state: FSMContext):
    parts = [s.strip() for s in message.text.split("|")]
    if len(parts) < 5:
        await message.answer("Неверный формат. Используйте: Название | Дата и время | Описание | Приз | Медиа (или 'skip')")
        return
    title, datetime_str, description, prize, media = parts
    if media.lower() == "skip":
        media = ""
    data = await state.get_data()
    eid = data.get("edit_event_id")
    if not eid:
        await message.answer("Ошибка: ID события не найден.")
        await state.clear()
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE events SET title=%s, datetime=%s, description=%s, prize=%s, media=%s WHERE id = %s",
                (title, datetime_str, description, prize, media, eid)
            )
            await conn.commit()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📣 Опубликовать", callback_data=f"event_publish:{eid}"),
             InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"event_delete:{eid}")]
        ])
        await message.answer("Событие обновлено успешно.", reply_markup=kb)
        print(f"[Events] Событие {eid} обновлено")
    except Exception as e:
        await message.answer(f"Ошибка при обновлении события: <code>{e}</code>")
        print("[Events ERROR при редактировании]", e)
    finally:
        await state.clear()
        await safe_close(conn)

# Публикация события
@router.callback_query(lambda q: q.data and q.data.startswith("event_publish:"))
async def event_publish_callback(query: types.CallbackQuery, state: FSMContext):
    eid_str = query.data.split(":", 1)[1]
    try:
        eid = int(eid_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM events WHERE id = %s", (eid,))
            event = await cur.fetchone()
        if not event:
            await query.message.answer("Событие не найдено.")
            return
        publish_text = (
            f"📢 <b>Событие!</b>\n\n"
            f"<b>Название:</b> {event.get('title')}\n"
            f"<b>Дата и время:</b> {event.get('datetime')}\n"
            f"<b>Описание:</b> {event.get('description')}\n"
            f"<b>Приз:</b> {event.get('prize')}"
        )
        if event.get("media"):
            try:
                sent = await query.bot.send_photo(
                    PUBLISH_CHANNEL_ID,
                    photo=event.get("media"),
                    caption=publish_text,
                    parse_mode="HTML"
                )
                published = {str(PUBLISH_CHANNEL_ID): sent.message_id}
                print(f"[Events] Публикация прошла успешно в канал {PUBLISH_CHANNEL_ID} как фото")
            except Exception as pub_e:
                print(f"[Events] Ошибка публикации фото в канале {PUBLISH_CHANNEL_ID}: {pub_e}")
                try:
                    sent = await query.bot.send_message(
                        PUBLISH_CHANNEL_ID,
                        publish_text,
                        parse_mode="HTML"
                    )
                    published = {str(PUBLISH_CHANNEL_ID): sent.message_id}
                    print(f"[Events] Публикация прошла успешно в канал {PUBLISH_CHANNEL_ID} как текст")
                except Exception as pub_e2:
                    print(f"[Events] Ошибка публикации текста в канале {PUBLISH_CHANNEL_ID}: {pub_e2}")
                    await query.message.answer(f"Ошибка публикации в канале: <code>{pub_e2}</code>")
                    return
        else:
            sent = await query.bot.send_message(PUBLISH_CHANNEL_ID, publish_text, parse_mode="HTML")
            published = {str(PUBLISH_CHANNEL_ID): sent.message_id}
            print(f"[Events] Публикация прошла успешно в канал {PUBLISH_CHANNEL_ID} как текст")
        async with conn.cursor() as cur:
            await cur.execute("UPDATE events SET published = %s WHERE id = %s", (json.dumps(published), eid))
            await conn.commit()
        await query.message.answer("Событие опубликовано в канале.")
        print(f"[Events] Событие {eid} опубликовано:", published)
    except Exception as e:
        await query.message.answer(f"Ошибка при публикации события: <code>{e}</code>")
        print("[Events ERROR при публикации]", e)
    finally:
        await safe_close(conn)
        await query.answer()

# Удаление события
@router.callback_query(lambda q: q.data and q.data.startswith("event_delete:"))
async def event_delete_callback(query: types.CallbackQuery, state: FSMContext):
    eid_str = query.data.split(":", 1)[1]
    try:
        eid = int(eid_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM events WHERE id = %s", (eid,))
            await conn.commit()
        await query.message.answer("Событие удалено.")
        print(f"[Events] Событие {eid} удалено")
    except Exception as e:
        await query.message.answer(f"Ошибка при удалении события: <code>{e}</code>")
        print("[Events ERROR при удалении]", e)
    finally:
        await safe_close(conn)
        await query.answer()

# =============================================================================
# Раздел "Пользователи"
# =============================================================================
async def send_users_list_to_admin(dest_message: Message, state: FSMContext):
    print("[Users] Запрос списка пользователей")
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("users_page", 1)
        per_page = 9
        offset = (page - 1) * per_page
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM users ORDER BY tg_id DESC LIMIT %s OFFSET %s", (per_page, offset))
            users = await cur.fetchall()
        buttons = []
        if users:
            for user in users:
                tg_id = user.get("tg_id")
                full_name = user.get("full_name") or "-"
                username = user.get("username") or "-"
                rank = user.get("rank") or "-"
                internal_id = user.get("internal_id", "N/A")
                btn_text = f"{internal_id} • {full_name} (@{username}) | {rank}"
                buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"user_manage:{tg_id}")])
            if len(users) == per_page:
                buttons.append([InlineKeyboardButton(text="➡️ Следующая страница", callback_data="users_page:next")])
        else:
            buttons.append([InlineKeyboardButton(text="Нет пользователей", callback_data="none")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await dest_message.answer("Пользователи:", reply_markup=kb)
        print("[Users] Список пользователей отправлен")
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении пользователей: <code>{e}</code>")
        print("[Users ERROR при получении]", e)
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
    page = page + 1 if direction == "next" else max(1, page - 1)
    await state.update_data(users_page=page)
    await send_users_list_to_admin(query.message, state)
    await query.answer()

# Меню управления для конкретного пользователя
@router.callback_query(lambda q: q.data and q.data.startswith("user_manage:"))
async def user_manage_callback(query: types.CallbackQuery, state: FSMContext):
    tg_id_str = query.data.split(":", 1)[1]
    try:
        tg_id = int(tg_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (tg_id,))
            user = await cur.fetchone()
        if not user:
            await query.message.answer("Пользователь не найден.")
            return
        buttons = [
            [InlineKeyboardButton(text="💎 Выдать алмазики", callback_data=f"user_give:{tg_id}"),
             InlineKeyboardButton(text="💎 Забрать алмазики", callback_data=f"user_take:{tg_id}")],
            [InlineKeyboardButton(text="🔄 Сменить ранг", callback_data=f"user_change_rank:{tg_id}")]
        ]
        if user.get("blocked"):
            buttons.append([InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"user_toggle_block:{tg_id}")])
        else:
            buttons.append([InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"user_toggle_block:{tg_id}")])
        buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="admin_users_list")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        details = (
            f"ID: {user.get('internal_id', 'N/A')}\n"
            f"Пользователь: {user.get('full_name')} (@{user.get('username')})\n"
            f"Ранг: {user.get('rank')}\n"
            f"Алмазики: {user.get('diamonds', 0)}\n"
            f"Статус: {'Заблокирован' if user.get('blocked') else 'Активен'}"
        )
        await query.message.answer(details, reply_markup=kb)
        await query.answer("Менеджер пользователя открыт.")
    except Exception as e:
        await query.message.answer(f"Ошибка при получении пользователя: {e}")
        print("[Users ERROR при менеджере]", e)
    finally:
        await safe_close(conn)

# Выдача/забор алмазиков
@router.callback_query(lambda q: q.data and (q.data.startswith("user_give:") or q.data.startswith("user_take:")))
async def user_diamonds_callback(query: types.CallbackQuery, state: FSMContext):
    action = "give" if query.data.startswith("user_give:") else "take"
    tg_id_str = query.data.split(":", 1)[1]
    try:
        tg_id = int(tg_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await state.update_data(edit_user_id=tg_id, diamond_action=action)
    prompt = "Введите количество 💎 для выдачи:" if action == "give" else "Введите количество 💎 для забора:"
    await query.message.answer(prompt)
    await state.set_state(DiamondsState.waiting_for_amount)
    await query.answer()

@router.message(DiamondsState.waiting_for_amount)
async def process_diamond_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")
        return
    data = await state.get_data()
    tg_id = data.get("edit_user_id")
    action = data.get("diamond_action")
    if tg_id is None or action is None:
        await message.answer("Ошибка: отсутствуют данные для операции.")
        await state.clear()
        return
    conn = await get_connection()
    try:
        if action == "give":
            query_str = "UPDATE users SET diamonds = diamonds + %s WHERE tg_id = %s"
        else:
            query_str = "UPDATE users SET diamonds = GREATEST(diamonds - %s, 0) WHERE tg_id = %s"
        async with conn.cursor() as cur:
            await cur.execute(query_str, (amount, tg_id))
            await conn.commit()
        await message.answer("Операция выполнена успешно!")
    except Exception as e:
        await message.answer(f"Ошибка при обновлении алмазиков: {e}")
        print("[Users ERROR при обновлении алмазиков]", e)
    finally:
        await state.clear()
        await safe_close(conn)

# Смена ранга пользователя
@router.callback_query(lambda q: q.data and q.data.startswith("user_change_rank:"))
async def user_change_rank_callback(query: types.CallbackQuery, state: FSMContext):
    tg_id_str = query.data.split(":", 1)[1]
    try:
        tg_id = int(tg_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (tg_id,))
            user = await cur.fetchone()
        if not user:
            await query.message.answer("Пользователь не найден.")
            return
        details = (
            f"Пользователь: {user.get('full_name')} (@{user.get('username')})\n"
            f"Текущий ранг: {user.get('rank')}\n\n"
            "Введите новый ранг для этого пользователя:"
        )
        await query.message.answer(details)
        await state.update_data(edit_user_id=tg_id)
        await state.set_state(UserEditState.waiting_for_new_rank)
        await query.answer("Введите новый ранг.")
    except Exception as e:
        await query.message.answer(f"Ошибка при получении пользователя: {e}")
        print("[Users ERROR при смене ранга]", e)
    finally:
        await safe_close(conn)

@router.message(UserEditState.waiting_for_new_rank)
async def process_user_edit(message: Message, state: FSMContext):
    new_rank = message.text.strip()
    data = await state.get_data()
    tg_id = data.get("edit_user_id")
    if not tg_id:
        await message.answer("Ошибка: пользователь не найден.")
        await state.clear()
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET rank = %s WHERE tg_id = %s", (new_rank, tg_id))
            await conn.commit()
        await message.answer("Ранг пользователя обновлён.")
        print(f"[Users] Ранг пользователя {tg_id} обновлён на: {new_rank}")
    except Exception as e:
        await message.answer(f"Ошибка при обновлении пользователя: {e}")
        print("[Users ERROR при обновлении]", e)
    finally:
        await state.clear()
        await safe_close(conn)

# Блокировка/разблокировка пользователя
@router.callback_query(lambda q: q.data and q.data.startswith("user_toggle_block:"))
async def user_toggle_block_callback(query: types.CallbackQuery, state: FSMContext):
    tg_id_str = query.data.split(":", 1)[1]
    try:
        tg_id = int(tg_id_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT blocked FROM users WHERE tg_id = %s", (tg_id,))
            result = await cur.fetchone()
        if result is None:
            await query.message.answer("Пользователь не найден.")
            return
        current_status = result[0]
        new_status = not current_status
        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET blocked = %s WHERE tg_id = %s", (new_status, tg_id))
            await conn.commit()
        status_text = "Заблокирован" if new_status else "Разблокирован"
        await query.message.answer(f"Пользователь теперь {status_text}.")
        print(f"[Users] Пользователь {tg_id} теперь {status_text}.")
        await query.answer()
    except Exception as e:
        await query.message.answer(f"Ошибка при изменении статуса: {e}")
        print("[Users ERROR при блокировке]", e)
    finally:
        await safe_close(conn)

# =============================================================================
# Заглушка для раздела "Объявления"
# =============================================================================
@router.callback_query(lambda q: q.data == "admin_broadcast")
async def broadcast_stub(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("Секция 'Объявления' пока не реализована.")
    await query.answer()
