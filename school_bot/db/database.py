from contextlib import asynccontextmanager
import aiosqlite
from pathlib import Path
from school_bot.config import DIRECTOR_USERNAME

DB_PATH = Path(__file__).parent / 'school_bot.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.cursor()
        
        # Таблица учителей
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            username TEXT PRIMARY KEY,
            chat_id INTEGER,
            first_seen TEXT
        )''')
        
        # Таблица классов
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            name TEXT PRIMARY KEY,
            teacher_username TEXT,
            FOREIGN KEY (teacher_username) REFERENCES teachers(username)
        )''')
        
        # Таблица учеников
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            username TEXT PRIMARY KEY,
            chat_id INTEGER,
            first_seen TEXT,
            name TEXT
        )''')
        
        # Таблица связей учеников и классов
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_classes (
            student_username TEXT,
            class_name TEXT,
            PRIMARY KEY (student_username, class_name),
            FOREIGN KEY (student_username) REFERENCES students(username),
            FOREIGN KEY (class_name) REFERENCES classes(name)
        )''')
        
        # Таблица заданий
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_username TEXT,
            student_username TEXT,
            text TEXT,
            assignment_type TEXT,
            file_id TEXT,
            file_name TEXT,
            file_type TEXT,
            assigned_at TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'active',
            response_text TEXT,
            response_file_id TEXT,
            response_file_type TEXT,
            submitted_at TEXT,
            grade INTEGER,
            graded_at TEXT,
            FOREIGN KEY (teacher_username) REFERENCES teachers(username),
            FOREIGN KEY (student_username) REFERENCES students(username)
        )''')
        
        # Добавляем учителя по умолчанию
        await cursor.execute('''
        INSERT OR IGNORE INTO teachers (username) VALUES (?)
        ''', (DIRECTOR_USERNAME,))
        
        await conn.commit()


@asynccontextmanager
async def get_db_connection():
    conn = await aiosqlite.connect(DB_PATH)
    try:
        yield conn
    finally:
        await conn.close()