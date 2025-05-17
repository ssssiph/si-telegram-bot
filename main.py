import asyncio, os
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, select, update
from sqlalchemy.orm import sessionmaker

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

engine = create_async_engine(DATABASE_URL, echo=False)
Base = declarative_base()
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    username = Column(String)
    rank = Column(String, default="Гость")
    balance = Column(Integer, default=0)

async def create_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

menu_keyboard = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="👤 Аккаунт"), KeyboardButton(text="🎯 События")],
    [KeyboardButton(text="⚙ Настройки"), KeyboardButton(text="📩 Связь")],
    [KeyboardButton(text="🛠 Управление")]
], resize_keyboard=True)

@dp.message(F.text.in_({"/start", "начать"}))
async def start_handler(message: Message):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == message.from_user.id))
        if not user:
            user = User(
                tg_id=message.from_user.id,
                username=message.from_user.username,
                rank="Гость",
                balance=0
            )
            session.add(user)
            await session.commit()
    await message.answer(f"Добро пожаловать, <b>{message.from_user.full_name}</b>!", reply_markup=menu_keyboard)

@dp.message(F.text == "👤 Аккаунт")
async def account_handler(message: Message):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == message.from_user.id))
        if user:
            await message.answer(
                f"<b>🧾 Ваш аккаунт:</b>\n"
                f"ID: <code>{user.tg_id}</code>\n"
                f"Имя: {message.from_user.full_name}\n"
                f"Юзернейм: @{user.username}\n"
                f"Ранг: {user.rank}\n"
                f"💎 Баланс: {user.balance}"
            )

@dp.message(F.text.startswith("/выдать"))
async def give_diamonds(message: Message):
    async with async_session() as session:
        sender = await session.scalar(select(User).where(User.tg_id == message.from_user.id))
        if not sender or sender.rank != "Генеральный директор":
            return await message.answer("⛔ Доступ запрещён.")
        try:
            parts = message.text.split()
            target_id = int(parts[1])
            amount = int(parts[2])
        except:
            return await message.answer("⚠️ Использование: /выдать <tg_id> <кол-во>")
        user = await session.scalar(select(User).where(User.tg_id == target_id))
        if not user:
            return await message.answer("Пользователь не найден.")
        user.balance += amount
        await session.commit()
        await message.answer(f"✅ Выдано {amount} 💎 пользователю {user.username or user.tg_id}")

@dp.message(F.text.startswith("/забрать"))
async def take_diamonds(message: Message):
    async with async_session() as session:
        sender = await session.scalar(select(User).where(User.tg_id == message.from_user.id))
        if not sender or sender.rank != "Генеральный директор":
            return await message.answer("⛔ Доступ запрещён.")
        try:
            parts = message.text.split()
            target_id = int(parts[1])
            amount = int(parts[2])
        except:
            return await message.answer("⚠️ Использование: /забрать <tg_id> <кол-во>")
        user = await session.scalar(select(User).where(User.tg_id == target_id))
        if not user:
            return await message.answer("Пользователь не найден.")
        user.balance = max(0, user.balance - amount)
        await session.commit()
        await message.answer(f"❌ Забрано {amount} 💎 у пользователя {user.username or user.tg_id}")

async def main():
    await create_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
