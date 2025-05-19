import os
import json
from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
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
# Определения состояний
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

class PromoCreateState(StatesGroup):
    waiting_for_code_and_reward = State()

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
# Обработка входящих обращений (доступ только для пользователей, у которых ранг не "гость")
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
        if result is None or result[0].lower() == "гость":
            await m.answer("🚫 Отказано в доступе.")
            return
        sender_info = f"{m.from_user.full_name} (@{m.from_user.username})" if m.from_user.username else m.from_user.full_name
        content = m.text if m.content_type == "text" else f"[Медиа: {m.content_type}]\nОтправитель: {sender_info}"
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO contacts (tg_id, full_name, username, message, answered) VALUES (%s, %s, %s, %s, %s)",
                              (m.from_user.id, m.from_user.full_name, m.from_user.username, content, False))
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
        if user_rank.lower() != "генеральный директор":
            await message.answer("🚫 Отказано в доступе.")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Обращения", callback_data="admin_contacts_list")],
            [InlineKeyboardButton(text="📅 События", callback_data="admin_events_list")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="🎫 Промокоды", callback_data="create_promo")],
            [InlineKeyboardButton(text="📢 Объявления", callback_data="admin_broadcast")]
        ])
        await message.answer("Панель управления. Выберите раздел:", reply_markup=kb)
        print("[Admin] Меню выведено")
    except Exception as e:
        await message.answer(f"Ошибка в админ-панели:\n<code>{e}</code>")
        print("[Admin ERROR]", e)
    finally:
        await safe_close(conn)
# Обработчики создания промокодов (админ)
@router.callback_query(lambda q: q.data == "create_promo")
async def create_promo_callback(query: types.CallbackQuery, state: FSMContext):
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `rank` FROM users WHERE tg_id = %s", (query.from_user.id,))
            res = await cur.fetchone()
        if not res or res[0].lower() != "генеральный директор":
            await query.message.answer("🚫 Отказано в доступе.")
            return
    except Exception as e:
        print("Error in create_promo_callback (rank check):", e)
        await query.message.answer("Ошибка при проверке прав доступа.")
        return
    finally:
        await safe_close(conn)
    promo_list = ""
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT code, reward FROM promo_codes")
            rows = await cur.fetchall()
        if rows:
            promo_list = "\n".join([f"{row[0]} | {row[1]}" for row in rows])
        else:
            promo_list = "Нет промокодов."
    except Exception as e:
        promo_list = "Ошибка при получении промокодов."
        print("[Promo ERROR] При получении промокодов:", e)
    finally:
        conn.close()
    text = (
        "Введите промокод и награду в формате:\n"
        "Название | Награда\n\n"
        "Например: NEWYEAR2025 | 100\n\n"
        "Текущие промокоды:\n" + promo_list
    )
    await query.message.answer(text)
    await state.set_state(PromoCreateState.waiting_for_code_and_reward)
    await query.answer("Ожидается ввод данных промокода.")

@router.message(PromoCreateState.waiting_for_code_and_reward)
async def process_create_promo(message: Message, state: FSMContext):
    parts = [s.strip() for s in message.text.split("|")]
    if len(parts) != 2:
        await message.answer("Неверный формат. Используйте: Название | Награда")
        return
    code, reward_str = parts
    try:
        reward = int(reward_str)
    except ValueError:
        await message.answer("Награда должна быть числом!")
        return
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO promo_codes (code, reward) VALUES (%s, %s)", (code, reward))
            await conn.commit()
        await message.answer(f"Промокод '{code}' с наградой {reward} 💎 успешно создан!")
    except Exception as e:
        await message.answer(f"Ошибка при создании промокода: {e}")
        print("[Promo ERROR]", e)
    finally:
        await state.clear()
        conn.close()
# Обработка обращений пользователей
@router.callback_query(lambda q: q.data == "admin_contacts_list")
async def admin_contacts_list_callback(query: types.CallbackQuery, state: FSMContext):
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
            await message.bot.copy_message(chat_id=target_id, from_chat_id=message.chat.id, message_id=message.message_id)
        await message.answer("Ответ отправлен пользователю.")
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: <code>{e}</code>")
        print("[Contacts ERROR при ответе]", e)
    finally:
        await state.clear()
        await safe_close(conn)
        await send_contacts_list_to_admin(message, state)

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

@router.callback_query(lambda q: q.data == "admin_broadcast")
async def broadcast_init(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("Введите текст объявления:")
    await state.set_state(BroadcastState.waiting_for_broadcast_message)
    await query.answer("Ожидается текст объявления.")

@router.message(BroadcastState.waiting_for_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext):
    broadcast_text = message.text
    conn = await get_connection()
    try:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT tg_id FROM users")
            users = await cur.fetchall()
        for user in users:
            try:
                await message.bot.send_message(user['tg_id'], broadcast_text)
            except Exception as e:
                print(f"Ошибка отправки объявления пользователю {user['tg_id']}: {e}")
        await message.answer("Объявление отправлено всем пользователям.")
    except Exception as e:
        await message.answer(f"Ошибка при рассылке объявления: {e}")
    finally:
        await state.clear()
        await safe_close(conn)
