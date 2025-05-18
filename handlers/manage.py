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

# Получаем список каналов для публикации событий из переменной окружения,
# например: "-1001234567890,-1009876543210"
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

# =========================================  
#         ГЛАВНАЯ АДМИН-ПАНЕЛЬ  
# =========================================  

@router.message(lambda message: message.text and message.text.strip() == "⚙️ Управление")
async def admin_panel(message: Message, state: FSMContext):
    print("[Admin] Запуск панели для", message.from_user.id)
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
        # Формируем меню разделов
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Обращения", callback_data="admin_contacts_list")],
            [InlineKeyboardButton(text="События", callback_data="admin_events_list")],
            [InlineKeyboardButton(text="Пользователи", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="Объявления", callback_data="admin_broadcast")]
        ])
        await message.answer("Панель управления. Выберите раздел:", reply_markup=kb)
        print("[Admin] Меню выведено")
    except Exception as e:
        await message.answer(f"Ошибка в админке:\n<code>{e}</code>")
        print("[Admin ERROR]", e)
    finally:
        await safe_close(conn)

# =========================================  
#          РАЗДЕЛ "ОБРАЩЕНИЯ"  
# =========================================  

async def send_contacts_list_to_admin(dest_message: Message, state: FSMContext):
    print("[Обращения] Запрос списка обращений")
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("contacts_page", 1)
        per_page = 9
        offset = (page - 1) * per_page
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM contacts WHERE answered = FALSE ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (per_page, offset)
            )
            contacts = await cur.fetchall()
        if not contacts:
            await dest_message.answer("Нет новых обращений.")
            return
        buttons = []
        for contact in contacts:
            full_name = (contact.get("full_name") or "-").strip()
            username = f"@{contact.get('username')}" if contact.get("username") and contact.get("username").strip() else "-"
            cid = contact.get("id")
            created_at = contact.get("created_at")
            date_str = str(created_at) if created_at else ""
            btn_text = f"{full_name} ({username} | {cid}) {date_str}"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"contact_reply:{cid}")])
        if len(contacts) == per_page:
            buttons.append([InlineKeyboardButton(text="Следующая страница", callback_data="contacts_page:next")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await dest_message.answer("Список обращений:", reply_markup=kb)
        print("[Обращения] Список отправлен")
    except Exception as e:
        await dest_message.answer(f"Ошибка при получении обращений: <code>{e}</code>")
        print("[Обращения ERROR]", e)
    finally:
        await safe_close(conn)

@router.callback_query(lambda q: q.data == "admin_contacts_list")
async def admin_contacts_list_callback(query: types.CallbackQuery, state: FSMContext):
    print("[Обращения] Кнопка 'Обращения' нажата")
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
    cid_str = query.data.split(":", 1)[1]
    try:
        cid = int(cid_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await state.update_data(contact_reply_id=cid)
    print(f"[Обращения] Выбрано обращение #{cid} для ответа")
    await query.message.answer("Введите ответ для данного обращения:")
    await query.answer("Ожидается ваш ответ.")

@router.message(lambda m: m.from_user.id == ADMIN_ID)
async def process_contact_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("contact_reply_id"):
        print("[Обращения] Нет выбранного обращения.")
        return
    cid = data["contact_reply_id"]
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
        user_id = contact.get("tg_id")
        if not user_id:
            await message.answer("Ошибка: отсутствует tg_id в обращении.")
            return
        print(f"[Обращения] Отправка ответа пользователю {user_id}")
        if message.content_type == 'text':
            await message.bot.send_message(user_id, f"📨 Ответ от администрации:\n\n{message.text}")
        else:
            await message.bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
        await message.answer("Ответ отправлен пользователю.")
        await send_contacts_list_to_admin(message, state)
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: <code>{e}</code>")
        print("[Обращения ERROR при ответе]", e)
    finally:
        # Сохраняем текущую страницу
        curr = await state.get_data()
        new_state = {}
        if curr.get("contacts_page"):
            new_state["contacts_page"] = curr["contacts_page"]
        await state.set_data(new_state)
        await safe_close(conn)

# =========================================  
#             РАЗДЕЛ "СОБЫТИЯ"  
# =========================================  

# FSM для создания события – добавлен шаг для media (фото/голосовое)
class EventCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_datetime = State()
    waiting_for_description = State()
    waiting_for_prize = State()
    waiting_for_media = State()  # опционально

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
    print("[События] Название:", message.text)

@router.message(EventCreation.waiting_for_datetime)
async def process_event_datetime(message: Message, state: FSMContext):
    await state.update_data(event_datetime=message.text)
    await message.answer("Введите описание события:")
    await EventCreation.next()
    print("[События] Дата и время:", message.text)

@router.message(EventCreation.waiting_for_description)
async def process_event_description(message: Message, state: FSMContext):
    await state.update_data(event_description=message.text)
    await message.answer("Введите приз (или оставьте пустым):")
    await EventCreation.next()
    print("[События] Описание:", message.text)

@router.message(EventCreation.waiting_for_prize)
async def process_event_prize(message: Message, state: FSMContext):
    await state.update_data(event_prize=message.text)
    await message.answer("Отправьте изображение или голосовое сообщение для события или напишите 'skip':")
    await EventCreation.next()
    print("[События] Приз:", message.text)

@router.message(EventCreation.waiting_for_media)
async def process_event_media(message: Message, state: FSMContext):
    # Если админ ввёл 'skip' или текстовое сообщение, считаем media пустой
    media = ""
    if message.text and message.text.lower() == "skip":
        media = ""
    else:
        # Если сообщение содержит фото, возьмем file_id первого фото; если голосовое – file_id
        if message.photo:
            media = message.photo[-1].file_id
        elif message.voice:
            media = message.voice.file_id
        else:
            media = ""  # можно расширить на другие типы
    data = await state.get_data()
    title = data.get("event_title")
    datetime_str = data.get("event_datetime")
    description = data.get("event_description")
    prize = data.get("event_prize")
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            # Вставляем событие; поле published хранит JSON (начальное "{}")
            await cur.execute(
                "INSERT INTO events (title, description, prize, datetime, media, creator_id, published) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (title, description, prize, datetime_str, media, message.from_user.id, "{}")
            )
            await conn.commit()
            event_id = cur.lastrowid
        # Выводим меню для созданного события
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Опубликовать событие", callback_data=f"event_publish:{event_id}")],
            [InlineKeyboardButton(text="Редактировать событие", callback_data=f"event_edit:{event_id}")],
            [InlineKeyboardButton(text="Удалить событие", callback_data=f"event_delete:{event_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_events_list")]
        ])
        await message.answer(f"Событие создано с ID: {event_id}. Теперь выберите действие:", reply_markup=kb)
        print("[События] Событие создано, ID:", event_id)
    except Exception as e:
        await message.answer(f"Ошибка при создании события: <code>{e}</code>")
        print("[События ERROR]", e)
    finally:
        await state.clear()
        await safe_close(conn)

@router.callback_query(lambda q: q.data == "admin_events_list")
async def admin_events_list_callback(query: types.CallbackQuery, state: FSMContext):
    await send_events_list_to_admin(query.message, state)
    await query.answer()

async def send_events_list_to_admin(dest_message: Message, state: FSMContext):
    print("[События] Получение списка событий")
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("events_page", 1)
        per_page = 9
        offset = (page - 1) * per_page
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM events ORDER BY datetime DESC LIMIT %s OFFSET %s",
                (per_page, offset)
            )
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
            f"📢 Событие!\n\nНазвание: {event.get('title')}\nДата и время: {event.get('datetime')}\n"
            f"Описание: {event.get('description')}\nПриз: {event.get('prize')}"
        )
        # Если для события задан media, можно добавить опцию: например, присоединить его
        if event.get("media"):
            publish_text += f"\n(Медиа: {event.get('media')})"
        published = {}
        for ch in CHANNEL_IDS:
            try:
                sent = await query.bot.send_message(ch, publish_text)
                published[str(ch)] = sent.message_id
            except Exception as pub_e:
                print(f"[События] Ошибка публикации в канале {ch}: {pub_e}")
        async with conn.cursor() as cur:
            await cur.execute("UPDATE events SET published = %s WHERE id = %s", (json.dumps(published), eid))
            await conn.commit()
        await query.message.answer("Событие опубликовано во всех каналах.")
        print(f"[События] Событие {eid} опубликовано:", published)
    except Exception as e:
        await query.message.answer(f"Ошибка при публикации события: <code>{e}</code>")
        print("[События ERROR при публикации]", e)
    finally:
        await safe_close(conn)
        await query.answer()

@router.callback_query(lambda q: q.data and q.data.startswith("event_edit:"))
async def event_edit_callback(query: types.CallbackQuery, state: FSMContext):
    eid_str = query.data.split(":", 1)[1]
    try:
        eid = int(eid_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await query.message.answer(f"Редактирование события {eid} не реализовано.")
    await query.answer()

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
        print(f"[События] Событие {eid} удалено")
    except Exception as e:
        await query.message.answer(f"Ошибка при удалении события: <code>{e}</code>")
        print("[События ERROR при удалении]", e)
    finally:
        await safe_close(conn)
        await query.answer()

# =========================================  
#            РАЗДЕЛ "ПОЛЬЗОВАТЕЛИ"  
# =========================================  

async def send_users_list_to_admin(dest_message: Message, state: FSMContext):
    print("[Пользователи] Получение списка пользователей")
    conn = await get_connection()
    try:
        data = await state.get_data()
        page = data.get("users_page", 1)
        per_page = 9
        offset = (page - 1) * per_page
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM users ORDER BY tg_id LIMIT %s OFFSET %s", (per_page, offset))
            users = await cur.fetchall()
        if not users:
            await dest_message.answer("Нет зарегистрированных пользователей.")
            return
        buttons = []
        for user in users:
            full_name = (user.get("full_name") or "-").strip()
            username = f"@{user.get('username')}" if user.get("username") and user.get("username").strip() else "-"
            tg_id = user.get("tg_id")
            rank = user.get("rank") or "-"
            balance = user.get("balance") or 0
            prefix = "❌" if user.get("blocked") else ""
            btn_text = f"{prefix}{full_name} ({username} | {tg_id}) Ранг: {rank} Баланс: {balance}"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"user_manage:{tg_id}")])
        if len(users) == per_page:
            buttons.append([InlineKeyboardButton(text="Следующая страница", callback_data="users_page:next")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await dest_message.answer("Пользователи:", reply_markup=kb)
        print("[Пользователи] Список отправлен")
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
    uid_str = query.data.split(":", 1)[1]
    try:
        uid = int(uid_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await state.update_data(manage_user_id=uid)
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE tg_id = %s", (uid,))
            user = await cur.fetchone()
        if not user:
            await query.message.answer("Пользователь не найден.")
            return
        # Формируем текст информации о пользователе
        info = (
            f"Информация о пользователе:\n"
            f"Имя: {user.get('full_name') or '-'}\n"
            f"Юзернейм: @{user.get('username') or '-'}\n"
            f"ID: {user.get('tg_id')}\n"
            f"Ранг: {user.get('rank') or '-'}\n"
            f"Баланс: {user.get('balance') or 0}"
        )
        await query.message.answer(info)
        # Меню управления: выдача/снятие алмазиков, изменение ранга, блокировка/разблокировка, Назад
        options = [
            InlineKeyboardButton(text="Выдать алмазики", callback_data=f"user_diamond:{uid}:give"),
            InlineKeyboardButton(text="Забрать алмазики", callback_data=f"user_diamond:{uid}:take"),
            InlineKeyboardButton(text="Изменить ранг", callback_data=f"user_rank:{uid}"),
        ]
        if user.get("blocked"):
            options.append(InlineKeyboardButton(text="Разблокировать", callback_data=f"user_toggle:{uid}"))
        else:
            options.append(InlineKeyboardButton(text="Блокировать", callback_data=f"user_toggle:{uid}"))
        options.append(InlineKeyboardButton(text="Назад", callback_data="admin_users_list"))
        kb = InlineKeyboardMarkup(inline_keyboard=[options])
        await query.message.answer("Управление пользователем:", reply_markup=kb)
        print(f"[Пользователи] Управление для пользователя {uid}")
        await query.answer()
    except Exception as e:
        await query.message.answer(f"Ошибка при получении данных пользователя: <code>{e}</code>")
        print("[Пользователи ERROR при управлении]", e)
    finally:
        await safe_close(conn)

# FSM для изменения баланса (алмазики)
class UserDiamondState(StatesGroup):
    waiting_for_diamond_value = State()

@router.callback_query(lambda q: q.data and q.data.startswith("user_diamond:"))
async def user_diamond_callback(query: types.CallbackQuery, state: FSMContext):
    parts = query.data.split(":")
    try:
        uid = int(parts[1])
        action = parts[2]  # "give" или "take"
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await state.update_data(manage_user_id=uid, diamond_action=action)
    await query.message.answer("Введите количество алмазиков:")
    await UserDiamondState.waiting_for_diamond_value.set()
    print(f"[Пользователи] Изменение баланса для {uid}, действие {action}")
    await query.answer()

@router.message(UserDiamondState.waiting_for_diamond_value)
async def process_diamond_change(message: Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("manage_user_id")
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
                await cur.execute("UPDATE users SET balance = balance + %s WHERE tg_id = %s", (value, uid))
            else:
                await cur.execute("UPDATE users SET balance = GREATEST(balance - %s, 0) WHERE tg_id = %s", (value, uid))
            await conn.commit()
        if action == "give":
            notif = f"Вам было выдано {value} 💎."
        else:
            notif = f"У вас было снято {value} 💎."
        await message.bot.send_message(uid, notif)
        await message.answer("Баланс обновлен.")
        print(f"[Пользователи] Баланс для {uid} изменён: {action} {value}")
    except Exception as e:
        await message.answer(f"Ошибка при изменении баланса: <code>{e}</code>")
        print("[Пользователи ERROR при балансе]", e)
    finally:
        await state.clear()
        await safe_close(conn)
        await send_users_list_to_admin(message, state)

# FSM для изменения ранга пользователя
class UserRankState(StatesGroup):
    waiting_for_new_rank = State()

@router.callback_query(lambda q: q.data and q.data.startswith("user_rank:"))
async def user_rank_callback(query: types.CallbackQuery, state: FSMContext):
    uid_str = query.data.split(":", 1)[1]
    try:
        uid = int(uid_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    await state.update_data(manage_user_id=uid)
    await query.message.answer("Введите новый ранг для пользователя:")
    await UserRankState.waiting_for_new_rank.set()
    print(f"[Пользователи] Изменение ранга для {uid}")
    await query.answer()

@router.message(UserRankState.waiting_for_new_rank)
async def process_new_rank(message: Message, state: FSMContext):
    new_rank = message.text.strip()
    data = await state.get_data()
    uid = data.get("manage_user_id")
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET rank = %s WHERE tg_id = %s", (new_rank, uid))
            await conn.commit()
        await message.answer(f"Ранг обновлён на {new_rank}.")
        try:
            await message.bot.send_message(uid, f"Ваш ранг изменён на {new_rank}.")
        except Exception as ex:
            print(f"[Пользователи] Невозможно отправить уведомление пользователю {uid}: {ex}")
        print(f"[Пользователи] Ранг для {uid} изменён на {new_rank}")
    except Exception as e:
        await message.answer(f"Ошибка при изменении ранга: <code>{e}</code>")
        print("[Пользователи ERROR при изменении ранга]", e)
    finally:
        await state.clear()
        await safe_close(conn)
        await send_users_list_to_admin(message, state)

@router.callback_query(lambda q: q.data and q.data.startswith("user_toggle:"))
async def user_toggle_callback(query: types.CallbackQuery, state: FSMContext):
    uid_str = query.data.split(":", 1)[1]
    try:
        uid = int(uid_str)
    except ValueError:
        await query.answer("Неверные данные.", show_alert=True)
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT blocked FROM users WHERE tg_id = %s", (uid,))
            result = await cur.fetchone()
            if not result:
                await query.message.answer("Пользователь не найден.")
                return
            curr_block = result[0]
            new_block = not curr_block
            await cur.execute("UPDATE users SET blocked = %s WHERE tg_id = %s", (new_block, uid))
            await conn.commit()
        await query.message.answer("Статус блокировки обновлён.")
        print(f"[Пользователи] Блокировка для {uid} изменена на {new_block}")
        await query.answer()
        await send_users_list_to_admin(query.message, state)
    except Exception as e:
        await query.message.answer(f"Ошибка при изменении статуса: <code>{e}</code>")
        print("[Пользователи ERROR при блокировке]", e)
    finally:
        await safe_close(conn)

# =========================================  
#           РАЗДЕЛ "ОБЪЯВЛЕНИЯ"  
# =========================================  

class BroadcastState(StatesGroup):
    waiting_for_broadcast = State()

@router.callback_query(lambda q: q.data == "admin_broadcast")
async def broadcast_callback(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("Отправьте объявление (текст, голос, фото, видео и т.п.) для рассылки всем пользователям:")
    await BroadcastState.waiting_for_broadcast.set()
    print("[Объявления] Начало рассылки объявления")
    await query.answer()

@router.message(BroadcastState.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT tg_id FROM users")
            users = await cur.fetchall()
        count = 0
        # Если объявление текстовое, рассылаем как сообщение; если медиа – используем copy_message
        if message.content_type == 'text':
            ann_text = message.text
            for user in users:
                try:
                    await message.bot.send_message(user.get("tg_id"), f"📣 Объявление:\n\n{ann_text}")
                    count += 1
                except Exception as ex:
                    print(f"[Объявления] Ошибка отправки пользователю {user.get('tg_id')}: {ex}")
        else:
            # Если объявление содержит медиа (фото, голос, видео), рассылаем через copy_message
            for user in users:
                try:
                    await message.bot.copy_message(
                        chat_id=user.get("tg_id"),
                        from_chat_id=message.chat.id,
                        message_id=message.message_id
                    )
                    count += 1
                except Exception as ex:
                    print(f"[Объявления] Ошибка отправки медиа пользователю {user.get('tg_id')}: {ex}")
        await message.answer(f"Объявление отправлено {count} пользователям.")
        print(f"[Объявления] Рассылка завершена, {count} получателей.")
    except Exception as e:
        await message.answer(f"Ошибка при рассылке объявления: <code>{e}</code>")
        print("[Объявления ERROR]", e)
    finally:
        await state.clear()
        await safe_close(conn)
