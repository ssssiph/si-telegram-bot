import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def get_connection():
    return await asyncpg.connect(DATABASE_URL)

async def init_db():
    conn = await get_connection()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            rank TEXT DEFAULT 'Гость',
            balance INTEGER DEFAULT 0,
            blocked BOOLEAN DEFAULT FALSE
        );
    """)
    # Если есть таблица events — создаём её:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title TEXT,
            description TEXT,
            prize TEXT,
            datetime TEXT,
            media TEXT,
            creator_id BIGINT
        );
    """)
    await conn.close()
