import os
import json
from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo, InputMediaAudio
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiomysql import DictCursor
from database import get_connection

router = Router()

ADMIN_ID = 1016554091
PUBLISH_CHANNEL_ID = -1002292957980

async def safe_close(conn):
    if conn:
        try:
            ret = conn.close()
            if ret is not None and hasattr(ret, '__await__'):
                await ret
        except Exception as ex:
            print("safe_close error:", ex)

class BroadcastState(StatesGroup):
    waiting_for_broadcast_message = State()

class ContactReplyState(StatesGroup):
    waiting_for_reply = State()

class EventCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_datetime = State()
    waiting_for_description = State()
    waiting_for_prize = State()
    waiting_for_media = State()

class EventEditState(StatesGroup):
    waiting_for_edit_details = State()

class UserEditState(StatesGroup):
    waiting_for_new_rank = State()

class DiamondsState(StatesGroup):
    waiting_for_amount = State()

class PromoCreationState(StatesGroup):
    waiting_for_promo_details = State()


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

@router.message(lambda m: m.chat.type == "private" and m.from_user.id != ADMIN_ID)
async def handle_incoming_contact(m: Message, state: FSMContext):
    if await state.get_state() is not None:
        return
    if await is_user_blocked(m.from_user.id):
        await m.answer("🚫 Отказано в доступе.")
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `rank` FROM users WHERE tg_id = %s", (m.from_user.id,))
            result = await cur.fetchone()
        if result is None or result[0] == "Гость":
            await m.answer("🚫 Отказано в доступе.")
            return
        sender_info = f"{m.from_user.full_name} (@{m.from_user.username})" if m.from_user.username else m.from_user.full_name
        content = ""
        if m.text:
            content = m.text
        elif m.media_group_id:
            content = f"[Медиагруппа: {m.media_group_id}] Отправитель: {sender_info}"
        elif m.photo:
            content = f"[Фото] Отправитель: {sender_info}"
        elif m.video:
            content = f"[Видео] Отправитель: {sender_info}"
        elif m.audio:
            content = f"[Аудио] Отправитель: {sender_info}"
        elif m.voice:
            content = f"[Голосовое сообщение] Отправитель: {sender_info}"
        else:
            content = f"[Другой тип контента] Отправитель: {sender_info}"

        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO contacts (tg_id, full_name, username, message, answered) VALUES (%s, %s, %s, %s, %s)", (m.from_user.id, m.from_user.full_name, m.from_user.username, content, False))
            await conn.commit()
        await m.answer("Ваше обращение принято.")
    except Exception as e:
        await m.answer("Ошибка при отправке обращения.")
        print("Error in handle_incoming_contact:", e)
    finally:
        conn.close()

@router.message(lambda message: message.text and message.text.strip().lower() == "⚙️ управление")
async def admin_panel(message: Message, state: FSMContext):
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
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Обращения", callback_data="admin_contacts_list")],
            [InlineKeyboardButton(text="📅 События", callback_data="admin_events_list")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="📢 Объявления", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🎟️ Промокоды", callback_data="admin_promo_list")] # Добавлена кнопка "Промокоды"
        ])
        await message.answer("Панель управления. Выберите раздел:", reply_markup=kb)
        print("[Admin] Меню выведено")
    except Exception as e:
        await message.answer(f"Ошибка в админ-панели:\n<code>{e}</code>")
        print("[Admin ERROR]", e)
    finally:
        await safe_close(conn)

# Обращения
async def send_contacts_list_to_admin(dest_message: Message, state: FSMContext):
    print("[Contacts] Запрос списка обращений")
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("contacts_page", 1)
        per_page = 9
        offset = (page - 1) * per_page
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT c.*, u.username AS sender_username, u.full_name AS sender_full_name FROM contacts c LEFT JOIN users u ON c.tg_id = u.tg_id WHERE answered = FALSE ORDER BY created_at DESC LIMIT %s OFFSET %s", (per_page, offset))
            contacts = await cur.fetchall()
        if not contacts:
            await dest_message.answer("Нет новых обращений.")
            return
        buttons = []
        for contact in contacts:
            cid = contact.get("id")
            full_name = contact.get("sender_full_name") or "-"
            username = contact.get("sender_username") or "-"
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
            await cur.execute("SELECT c.*, u.username AS sender_username, u.full_name AS sender_full_name FROM contacts c LEFT JOIN users u ON c.tg_id = u.tg_id WHERE c.id = %s", (cid,))
            contact = await cur.fetchone()
        if contact:
            sender_info = f"{contact.get('sender_full_name','-')}" + (f" (@{contact.get('sender_username','-')})" if contact.get("sender_username") else "")
            original_text = contact.get("message")
            if original_text.startswith("[Медиагруппа:"):
                await query.message.answer(f"✉️ Сообщение от {sender_info}:\n\n{original_text}\n\nВведите ваш ответ:")
            elif original_text.startswith("[Фото]"):
                await query.message.answer(f"✉️ Сообщение от {sender_info}:\n\n{original_text}\n\nВведите ваш ответ:")
            elif original_text.startswith("[Видео]"):
                await query.message.answer(f"✉️ Сообщение от {sender_info}:\n\n{original_text}\n\nВведите ваш ответ:")
            elif original_text.startswith("[Аудио]"):
                await query.message.answer(f"✉️ Сообщение от {sender_info}:\n\n{original_text}\n\nВведите ваш ответ:")
            elif original_text.startswith("[Голосовое сообщение]"):
                await query.message.answer(f"✉️ Сообщение от {sender_info}:\n\n{original_text}\n\nВведите ваш ответ:")
            else:
                await query.message.answer(f"✉️ Сообщение от {sender_info}:\n\n{original_text}\n\nВведите ваш ответ:")
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
            await cur.execute("SELECT c.*, u.username AS sender_username, u.full_name AS sender_full_name FROM contacts c LEFT JOIN users u ON c.tg_id = u.tg_id WHERE c.id = %s", (cid,))
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
        sender_info = f"{contact.get('sender_full_name','-')}" + (f" (@{contact.get('sender_username','-')})" if contact.get("sender_username") else "")
        original_text = contact.get("message")
        header = f"Ваше обращение от {sender_info}:\n\n{original_text}\n\nОтвет от администрации:"
        if message.content_type == "text":
            await message.bot.send_message(target_id, header + "\n\n" + message.text)
        elif message.photo:
            await message.bot.send_photo(target_id, message.photo[-1].file_id, caption=header + "\n\nОтвет ниже:")
        elif message.video:
            await message.bot.send_video(target_id, message.video.file_id, caption=header + "\n\nОтвет ниже:")
        elif message.audio:
            await message.bot.send_audio(target_id, message.audio.file_id, caption=header + "\n\nОтвет ниже:")
        elif message.voice:
            await message.bot.send_voice(target_id, message.voice.file_id, caption=header + "\n\nОтвет ниже:")
        else:
            await message.bot.send_message(target_id, header + "\n\nОтвет ниже:")
            await message.bot.copy_message(chat_id=target_id, from_chat_id=message.chat.id, message_id=message.message_id)
        await message.answer("Ответ отправлен пользователю.")
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: <code>{e}</code>")
        print("[Contacts ERROR при ответе]", e)
    finally:
        await state.clear()
        await safe_close(conn)
        await send_contacts_list_to_admin(message, state)

# События
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
    await message.answer("Введите приз за участие/победу:")
    await state.set_state(EventCreation.waiting_for_prize)
    print("[Events] Описание:", message.text)

@router.message(EventCreation.waiting_for_prize)
async def process_event_prize(message: Message, state: FSMContext):
    await state.update_data(event_prize=message.text)
    await message.answer("Отправьте медиафайл (фото/видео/гиф):")
    await state.set_state(EventCreation.waiting_for_media)
    print("[Events] Приз:", message.text)

@router.message(EventCreation.waiting_for_media, content_types=types.ContentType.ANY)
async def process_event_media(message: Message, state: FSMContext):
    if message.photo:
        await state.update_data(event_media=message.photo[-1].file_id, event_media_type="photo")
    elif message.video:
        await state.update_data(event_media=message.video.file_id, event_media_type="video")
    elif message.animation:
        await state.update_data(event_media=message.animation.file_id, event_media_type="animation")
    else:
        await message.answer("Неверный тип медиа. Отправьте фото, видео или GIF.")
        return
    data = await state.get_data()
    event_title = data.get("event_title")
    event_datetime = data.get("event_datetime")
    event_description = data.get("event_description")
    event_prize = data.get("event_prize")
    event_media = data.get("event_media")
    event_media_type = data.get("event_media_type")
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO events (title, description, prize, datetime, media, creator_id, published) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (event_title, event_description, event_prize, event_datetime, event_media, message.from_user.id, json.dumps({"published": False}))
            )
            await conn.commit()
        await message.answer("Событие сохранено. /publish для публикации.")
        print("[Events] Событие сохранено")
    except Exception as e:
        await message.answer(f"Ошибка сохранения: <code>{e}</code>")
        print("[Events ERROR]", e)
    finally:
        await state.clear()
        await safe_close(conn)

@router.message(lambda message: message.text and message.text.strip().lower() == "/publish")
async def publish_event(message: Message):
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM events WHERE published = %s", (json.dumps({"published": False}),))
            event = await cur.fetchone()
        if not event:
            await message.answer("Нет неопубликованных событий.")
            return
        event_id = event.get("id")
        title = event.get("title")
        description = event.get("description")
        prize = event.get("prize")
        datetime_str = event.get("datetime")
        media = event.get("media")
        media_type = event.get("media_type")
        text = f"<b>{title}</b>\n\n{description}\n\nПриз: {prize}\nДата и время: {datetime_str}"
        if media:
            if media_type == "photo":
                await message.bot.send_photo(chat_id=PUBLISH_CHANNEL_ID, photo=media, caption=text)
            elif media_type == "video":
                await message.bot.send_video(chat_id=PUBLISH_CHANNEL_ID, video=media, caption=text)
            elif media_type == "animation":
                await message.bot.send_animation(chat_id=PUBLISH_CHANNEL_ID, animation=media, caption=text)
        else:
            await message.bot.send_message(chat_id=PUBLISH_CHANNEL_ID, text=text)
        async with conn.cursor() as cur:
            await cur.execute("UPDATE events SET published = %s WHERE id = %s", (json.dumps({"published": True}), event_id))
            await conn.commit()
        await message.answer("Событие опубликовано.")
        print("[Events] Событие опубликовано")
    except Exception as e:
        await message.answer(f"Ошибка публикации: <code>{e}</code>")
        print("[Events ERROR]", e)
    finally:
        await safe_close(conn)

@router.callback_query(lambda q: q.data and q.data.startswith("event_edit:"))
async def event_edit_callback(query: types.CallbackQuery, state: FSMContext):
    event_id = int(query.data.split(":")[1])
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditState.waiting_for_edit_details)
    await query.message.answer("Введите новые данные для события в формате:\nНазвание | Дата и время | Описание | Приз")
    await query.answer()

@router.message(EventEditState.waiting_for_edit_details)
async def process_event_edit(message: Message, state: FSMContext):
    new_data = message.text.split("|")
    if len(new_data) != 4:
        await message.answer("Неверный формат данных. Попробуйте еще раз.")
        return
    new_title, new_datetime, new_description, new_prize = [s.strip() for s in new_data]
    event_id = (await state.get_data()).get("event_id")
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE events SET title = %s, datetime = %s, description = %s, prize = %s WHERE id = %s",
                (new_title, new_datetime, new_description, new_prize, event_id)
            )
            await conn.commit()
        await message.answer("Данные события обновлены.")
        print("[Events] Данные события обновлены")
    except Exception as e:
        await message.answer(f"Ошибка обновления: <code>{e}</code>")
        print("[Events ERROR]", e)
    finally:
        await state.clear()
        await safe_close(conn)

# Пользователи
async def send_users_list_to_admin(dest_message: Message, state: FSMContext):
    print("[Users] Запрос списка пользователей")
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("users_page", 1)
        per_page = 9
        offset = (page - 1) * per_page
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s", (per_page, offset))
            users = await cur.fetchall()
        buttons = []
        for user in users:
            tg_id = user.get("tg_id")
            full_name = user.get("full_name") or "-"
            username = user.get("username") or "-"
            rank = user.get("rank") or "Гость"
            btn_text = f"{full_name} (@{username} | {rank})"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"user_edit:{tg_id}")])
        if len(users) == per_page:
            buttons.append([InlineKeyboardButton(text="➡️ Следующая страница", callback_data="users_page:next")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await dest_message.answer("Пользователи:", reply_markup=kb)
        print("[Users] Список пользователей отправлен")
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении пользователей: <code>{e}</code>")
        print("[Users ERROR]", e)
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

@router.callback_query(lambda q: q.data and q.data.startswith("user_edit:"))
async def user_edit_callback(query: types.CallbackQuery, state: FSMContext):
    tg_id = int(query.data.split(":")[1])
    await state.update_data(edit_user_id=tg_id)
    await state.set_state(UserEditState.waiting_for_new_rank)
    await query.message.answer("Введите новый ранг для пользователя:")
    await query.answer()

@router.message(UserEditState.waiting_for_new_rank)
async def process_user_edit(message: Message, state: FSMContext):
    new_rank = message.text.strip()
    user_id = (await state.get_data()).get("edit_user_id")
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET `rank` = %s WHERE tg_id = %s", (new_rank, user_id))
            await conn.commit()
        await message.answer("Ранг пользователя обновлен.")
        print("[Users] Ранг пользователя обновлен")
    except Exception as e:
        await message.answer(f"Ошибка обновления ранга: <code>{e}</code>")
        print("[Users ERROR]", e)
    finally:
        await state.clear()
        await safe_close(conn)

# Рассылка
@router.callback_query(lambda q: q.data == "admin_broadcast")
async def admin_broadcast_callback(query: types.CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_broadcast_message)
    await query.message.answer("Введите текст объявления для рассылки:")
    await query.answer()

@router.message(BroadcastState.waiting_for_broadcast_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT tg_id FROM users")
            user_ids = await cur.fetchall()
        if not user_ids:
            await message.answer("Нет пользователей для рассылки.")
            await state.clear()
            return
        for user_id in user_ids:
            try:
                if message.content_type == "text":
                    await message.bot.send_message(user_id[0], message.text)
                elif message.photo:
                    await message.bot.send_photo(user_id[0], message.photo[-1].file_id, caption=message.caption)
                elif message.video:
                    await message.bot.send_video(user_id[0], message.video.file_id, caption=message.caption)
                elif message.audio:
                    await message.bot.send_audio(user_id[0], message.audio.file_id, caption=message.caption)
                elif message.voice:
                    await message.bot.send_voice(user_id[0], message.voice.file_id, caption=message.caption)
                else:
                    await message.bot.send_message(user_id[0], "Рассылка контента данного типа не поддерживается.")
            except Exception as e:
                print(f"Ошибка отправки сообщения пользователю {user_id[0]}: {e}")
        await message.answer("Рассылка завершена.")
        print("[Broadcast] Рассылка завершена")
    except Exception as e:
        await message.answer(f"Ошибка при рассылке: <code>{e}</code>")
        print("[Broadcast ERROR]", e)
    finally:
        await state.clear()
        await safe_close(conn)

# Промокоды - Функциональность администратора
@router.callback_query(lambda q: q.data == "admin_promo_list")
async def admin_promo_list(query: types.CallbackQuery, state: FSMContext):
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM promo_codes")
            promo_codes = await cur.fetchall()
        promo_list_text = "Текущие промокоды:\n"
        if promo_codes:
            for promo in promo_codes:
                promo_list_text += f"{promo['code']} | {promo['reward']}\n"
        else:
            promo_list_text = "Нет активных промокодов.\n"
        await query.message.answer(f"{promo_list_text}\nВведите промокод и награду в формате:\nНазвание | Награда\n\nНапример: example | 100")
        await state.set_state(PromoCreationState.waiting_for_promo_details)
    except Exception as e:
        await query.message.answer(f"Ошибка при получении списка промокодов: {e}")
        print("[Promo ERROR]", e)
    finally:
        await safe_close(conn)
    await query.answer()

@router.message(PromoCreationState.waiting_for_promo_details)
async def process_promo_creation(message: Message, state: FSMContext):
    try:
        code, reward_str = message.text.split("|")
        code = code.strip()
        reward = int(reward_str.strip())
        if not code or reward <= 0:
            await message.answer("Неверный формат. Пожалуйста, используйте 'Название | Награда', например: example | 100")
            return
    except ValueError:
        await message.answer("Неверный формат. Пожалуйста, используйте 'Название | Награда', например: example | 100")
        return

    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO promo_codes (code, reward) VALUES (%s, %s)", (code, reward))
            await conn.commit()
        await message.answer(f"Промокод '{code}' с наградой {reward} успешно создан.")
    except Exception as e:
        await message.answer(f"Ошибка при создании промокода: {e}")
        print("[Promo ERROR]", e)
    finally:
        await state.clear()
        await safe_close(conn)
