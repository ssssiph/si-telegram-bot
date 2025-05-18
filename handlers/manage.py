import os
import json
from aiogram import Router, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State  # для aiogram v3.x
from aiomysql import DictCursor  # для получения результатов в виде словаря
from database import get_connection

router = Router()
ADMIN_ID = 1016554094  # Укажите актуальный ID администратора

# (Если потребуется, CHANNEL_IDS можно использовать для других разделов.)
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

# ======================================================================
# FSM для ответа на обращение (рабочая версия)
# ======================================================================
class ContactReplyState(StatesGroup):
    waiting_for_reply = State()

# ======================================================================
# ГЛАВНАЯ АДМИН-ПАНЕЛЬ (содержит только раздел "Обращения" в данном примере)
# ======================================================================
@router.message(lambda message: message.text and message.text.strip() == "⚙️ Управление")
async def admin_panel(message: Message, state: FSMContext):
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
        # Выводим меню с единственной кнопкой "Обращения"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Обращения", callback_data="admin_contacts_list")]
        ])
        await message.answer("Панель управления. Выберите раздел:", reply_markup=kb)
        print("[Admin] Меню выведено")
    except Exception as e:
        await message.answer(f"Ошибка в админке:\n<code>{e}</code>")
        print("[Admin ERROR]", e)
    finally:
        await safe_close(conn)

# ======================================================================
# РАЗДЕЛ "ОБРАЩЕНИЯ" – вывод списка обращений и ответы
# ======================================================================
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
            cid = contact.get("id")
            full_name = contact.get("full_name") or "-"
            username = contact.get("username") or "-"
            created_at = contact.get("created_at")
            date_str = str(created_at) if created_at else ""
            btn_text = f"{full_name} (@{username} | {cid}) {date_str}"
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
    await state.set_state(ContactReplyState.waiting_for_reply)  # Используем set_state через FSMContext
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
        # Помечем обращение как обработанное
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
        print(f"[Обращения] Отправка ответа пользователю {target_id}")
        if message.content_type == "text":
            await message.bot.send_message(target_id, f"📨 Ответ от администрации:\n\n{message.text}")
        else:
            await message.bot.copy_message(
                chat_id=target_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
        await message.answer("Ответ отправлен пользователю.")
    except Exception as e:
        await message.answer(f"Ошибка при отправке ответа: <code>{e}</code>")
        print("[Обращения ERROR при ответе]", e)
    finally:
        await state.clear()
        await safe_close(conn)
        await send_contacts_list_to_admin(message, state)

# =========================================
# Остальные разделы – заглушки (События, Пользователи, Объявления)
# =========================================
@router.callback_query(lambda q: q.data == "admin_events_list")
async def events_list_stub(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("Секция 'События' пока не реализована.")
    await query.answer()

@router.callback_query(lambda q: q.data == "admin_users_list")
async def users_list_stub(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("Секция 'Пользователи' пока не реализована.")
    await query.answer()

@router.callback_query(lambda q: q.data == "admin_broadcast")
async def broadcast_stub(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("Секция 'Объявления' пока не реализована.")
    await query.answer()
