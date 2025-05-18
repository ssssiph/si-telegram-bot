import os
import json
from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State  # для aiogram v3.x
from aiomysql import DictCursor  # для работы с результатами запросов в виде словаря
from database import get_connection

router = Router()
ADMIN_ID = 1016554094               # Актуальный ID администратора
PUBLISH_CHANNEL_ID = 2292957980      # Канал для публикации событий (убедитесь, что бот администратор)

async def safe_close(conn):
    if conn:
        try:
            ret = conn.close()
            if ret is not None and hasattr(ret, '__await__'):
                await ret
        except Exception as ex:
            print("safe_close error:", ex)

# =============================================================================
# FSM для ответа на обращение
# =============================================================================
class ContactReplyState(StatesGroup):
    waiting_for_reply = State()

# =============================================================================
# FSM для создания события
# =============================================================================
class EventCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_datetime = State()
    waiting_for_description = State()
    waiting_for_prize = State()
    waiting_for_media = State()

# =============================================================================
# FSM для редактирования события
# =============================================================================
class EventEditState(StatesGroup):
    waiting_for_edit_details = State()

# =============================================================================
# Главная админ-панель
# =============================================================================
@router.message(lambda message: message.text and message.text.strip().lower() == "⚙️ управление")
async def admin_panel(message: Message, state: FSMContext):
    # Очистим предыдущее состояние, чтобы не пересекались FSM-события
    await state.clear()
    print("[Admin] Запуск панели для", message.from_user.id)
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `rank` FROM users WHERE tg_id = %s", (message.from_user.id,))
            result = await cur.fetchone()
            if not result:
                await message.answer("❗ Пользователь не найден. Используйте /start для регистрации.")
                return
            user_rank = result[0]
        if user_rank != "Генеральный директор":
            await message.answer("Отказано в доступе.")
            return
        # Выводим меню с кнопками для секций: Обращения и События
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Обращения", callback_data="admin_contacts_list")],
            [InlineKeyboardButton(text="События", callback_data="admin_events_list")]
        ])
        await message.answer("Панель управления. Выберите раздел:", reply_markup=kb)
        print("[Admin] Меню выведено")
    except Exception as e:
        await message.answer(f"Ошибка в админке:\n<code>{e}</code>")
        print("[Admin ERROR]", e)
    finally:
        await safe_close(conn)

# =============================================================================
# Раздел "Обращения" – (код оставить без изменений, так как работает)
# =============================================================================
async def send_contacts_list_to_admin(dest_message: Message, state: FSMContext):
    # ... (код обращений из предыдущей версии, не изменялся) ...
    pass

@router.callback_query(lambda q: q.data == "admin_contacts_list")
async def admin_contacts_list_callback(query: types.CallbackQuery, state: FSMContext):
    # ... (код обращений) ...
    pass

# =============================================================================
# Раздел "События"
# =============================================================================
async def send_events_list_to_admin(dest_message: Message, state: FSMContext):
    print("[Events] Получение списка событий")
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
        buttons.append([InlineKeyboardButton(text="Создать событие", callback_data="event_create")])
        if events:
            for event in events:
                title = event.get("title") or "-"
                datetime_str = event.get("datetime") or "-"
                eid = event.get("id")
                btn_text = f"{title} | {datetime_str}"
                buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"event_edit:{eid}")])
            if len(events) == per_page:
                buttons.append([InlineKeyboardButton(text="Следующая страница", callback_data="events_page:next")])
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
    if direction == "next":
        page += 1
    else:
        page = max(1, page - 1)
    await state.update_data(events_page=page)
    await send_events_list_to_admin(query.message, state)
    await query.answer()

# Создание нового события через FSM (EventCreation)
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
        # После создания события выводим панель редактирования с кнопками "Опубликовать" и "Удалить" и "Редактировать событие"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Опубликовать", callback_data=f"event_publish:{event_id}"),
             InlineKeyboardButton(text="Удалить", callback_data=f"event_delete:{event_id}")],
            [InlineKeyboardButton(text="Редактировать событие", callback_data=f"event_edit:{event_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_events_list")]
        ])
        await message.answer(f"Событие создано с ID: {event_id}. Теперь выберите действие:", reply_markup=kb)
        print("[Events] Событие создано, ID:", event_id)
    except Exception as e:
        await message.answer(f"Ошибка при создании события: <code>{e}</code>")
        print("[Events ERROR при создании]", e)
    finally:
        await state.clear()
        await safe_close(conn)

# Редактирование события – вывод панели редактирования с кнопками "Опубликовать" и "Удалить"
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
        # После редактирования выводим панель с кнопками "Опубликовать" и "Удалить"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Опубликовать", callback_data=f"event_publish:{eid}"),
             InlineKeyboardButton(text="Удалить", callback_data=f"event_delete:{eid}")]
        ])
        await message.answer("Событие обновлено успешно.", reply_markup=kb)
        print(f"[Events] Событие {eid} обновлено")
    except Exception as e:
        await message.answer(f"Ошибка при обновлении события: <code>{e}</code>")
        print("[Events ERROR при редактировании]", e)
    finally:
        await state.clear()
        await safe_close(conn)

# Публикация события – отправка его в канал с ID PUBLISH_CHANNEL_ID
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
            publish_text += f"\n(Медиа: {event.get('media')})"
        published = {}
        try:
            sent = await query.bot.send_message(PUBLISH_CHANNEL_ID, publish_text, parse_mode="HTML")
            published[str(PUBLISH_CHANNEL_ID)] = sent.message_id
            print(f"[Events] Публикация прошла успешно в канал {PUBLISH_CHANNEL_ID}")
        except Exception as pub_e:
            print(f"[Events] Ошибка публикации в канале {PUBLISH_CHANNEL_ID}: {pub_e}")
            await query.message.answer(f"Ошибка публикации в канале: <code>{pub_e}</code>")
            return
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
# Заглушки для разделов "Пользователи" и "Объявления"
# =============================================================================
@router.callback_query(lambda q: q.data == "admin_users_list")
async def users_list_stub(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("Секция 'Пользователи' пока не реализована.")
    await query.answer()

@router.callback_query(lambda q: q.data == "admin_broadcast")
async def broadcast_stub(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("Секция 'Объявления' пока не реализована.")
    await query.answer()
