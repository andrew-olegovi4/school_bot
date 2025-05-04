from functools import lru_cache
from typing import List, Optional, Tuple
import aiosqlite
from school_bot.db.database import get_db_connection


# school_bot/db/students.py


async def student_exists(conn: aiosqlite.Connection, username: str) -> bool:
    """Проверяет, существует ли ученик с таким username"""
    cursor = await conn.cursor()
    await cursor.execute('SELECT 1 FROM students WHERE username = ?', (username,))
    return await cursor.fetchone() is not None


@lru_cache(maxsize=128)
async def is_user_student(username: str, conn: aiosqlite.Connection) -> bool:
    """Проверяет, является ли пользователь учеником (с кэшированием)"""
    cursor = await conn.cursor()
    await cursor.execute(
        'SELECT 1 FROM students WHERE username = ? AND chat_id IS NOT NULL',
        (username,)
    )
    return await cursor.fetchone() is not None


async def get_student_notification_info(student_username: str) -> tuple[int, str] | None:
    """Получает chat_id и имя ученика для уведомления"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('SELECT chat_id, name FROM students WHERE username = ?', (student_username,))
        return await cursor.fetchone()
    

async def add_student_to_class(student_username: str, class_name: str) -> None:
    """Добавляет ученика в указанный класс"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
            INSERT INTO student_classes (student_username, class_name)
            VALUES (?, ?)
        ''', (student_username, class_name))
        await conn.commit()


async def add_new_student(student_username: str) -> None:
    """Добавляет нового ученика в базу"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('INSERT INTO students (username) VALUES (?)', (student_username,))
        await conn.commit()


async def check_student_exists(student_username: str) -> bool:
    """Проверяет существование ученика в базе данных"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('SELECT 1 FROM students WHERE username = ?', (student_username,))
        return bool(await cursor.fetchone())
    

async def get_student_chat_id(conn: aiosqlite.Connection, username: str) -> Optional[int]:
    """Получает chat_id ученика по username"""
    cursor = await conn.cursor()
    await cursor.execute('SELECT chat_id FROM students WHERE username = ?', (username,))
    result = await cursor.fetchone()
    return result[0] if result else None


async def get_students_in_class(conn: aiosqlite.Connection, class_name: str) -> List[Tuple[str, Optional[int]]]:
    """Получает список учеников класса"""
    cursor = await conn.cursor()
    await cursor.execute('''
    SELECT sc.student_username, s.chat_id
    FROM student_classes sc
    LEFT JOIN students s ON sc.student_username = s.username
    WHERE sc.class_name = ?
    ''', (class_name,))
    return await cursor.fetchall()


async def check_student_in_class(student_username: str, class_name: str) -> bool:
    """Проверяет, есть ли ученик в указанном классе"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
            SELECT 1 FROM student_classes
            WHERE student_username = ? AND class_name = ?
        ''', (student_username, class_name))
        return bool(await cursor.fetchone())
    

async def get_completed_assignments_student(student_username: str, limit: int = 10) -> List[Tuple[int, str, str, str, Optional[int]]]:
    """Получает выполненные задания ученика"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
        SELECT 
            a.id,
            a.text,
            a.teacher_username,
            a.submitted_at,
            a.grade
        FROM assignments a
        WHERE a.student_username = ? AND a.status = 'submitted'
        ORDER BY a.submitted_at DESC
        LIMIT ?
        ''', (student_username, limit))
        return await cursor.fetchall()
    

async def get_student_classes_with_assignments(
    conn: aiosqlite.Connection,
    student_username: str
) -> list[tuple[str, int]]:
    """Получает список классов ученика с количеством активных заданий"""
    cursor = await conn.cursor()
    await cursor.execute('''
    SELECT 
        c.name,
        (SELECT COUNT(*) FROM assignments a 
         WHERE a.student_username = ? AND a.status = 'active' AND a.class_name = c.name) as active_count
    FROM classes c
    JOIN student_classes sc ON c.name = sc.class_name
    WHERE sc.student_username = ?
    ORDER BY c.name
    ''', (student_username, student_username))
    return await cursor.fetchall()


async def get_student_display_name(conn: aiosqlite.Connection, username: str) -> str:
    """Получает отображаемое имя ученика (имя или username)"""
    cursor = await conn.cursor()
    await cursor.execute('SELECT COALESCE(name, username) FROM students WHERE username = ?', (username,))
    student_data = await cursor.fetchone()
    return student_data[0] if student_data else username