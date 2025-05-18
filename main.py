import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from database import init_db, get_connection
from handlers import start, account, events, contact, manage

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())

dp.include_routers(
    start.router,
    account.router,
    events.router,
    contact.router,
    manage.router
)

async def ensure_director():
    conn = await get_connection()
    try:
        tg_id = 1016554091
        exists = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", tg_id)
        if not exists:
            await conn.execute(
                "INSERT INTO users (tg_id, username, full_name, rank, balance) VALUES ($1, $2, $3, 'Генеральный директор', 0)",
                tg_id, 'siph_director', 'Siph Director'
            )
        else:
            await conn.execute(
                "UPDATE users SET rank = 'Генеральный директор' WHERE tg_id = $1",
                tg_id
            )
    finally:
        await conn.close()

async def main():
    await init_db()
    await ensure_director()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
