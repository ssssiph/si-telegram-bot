import aiomysql
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def parse_mysql_url(url: str):
    url = url.replace("mysql://", "")
    user_pass, host_db = url.split("@")
    user, password = user_pass.split(":")
    host_port, db_name = host_db.split("/")
    host, port = host_port.split(":")
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": int(port),
        "db": db_name,
        "autocommit": True
    }

DB_CONFIG = parse_mysql_url(DATABASE_URL)

async def get_connection():
    return await aiomysql.connect(**DB_CONFIG)

async def init_db():
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    tg_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    full_name VARCHAR(255),
                    `rank` VARCHAR(50) DEFAULT 'Гость',
                    balance INT DEFAULT 0,
                    blocked BOOLEAN DEFAULT FALSE
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    prize TEXT,
                    datetime TEXT,
                    media TEXT,
                    creator_id BIGINT
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    tg_id BIGINT,
                    username VARCHAR(255),
                    full_name VARCHAR(255),
                    message TEXT,
                    answered BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    finally:
        conn.close()
