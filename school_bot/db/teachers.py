from typing import List, Optional, Tuple
import aiosqlite
from school_bot.config import DIRECTOR_USERNAME
from school_bot.db.database import get_db_connection


async def teacher_exists(conn: aiosqlite.Connection, username: str) -> bool:
    """Проверяет, существует ли учитель с таким username"""
    cursor = await conn.cursor()
    await cursor.execute('SELECT 1 FROM teachers WHERE username = ?', (username,))
    return await cursor.fetchone() is not None


async def add_teacher(conn: aiosqlite.Connection, username: str) -> bool:
    """Добавляет нового учителя в базу данных"""
    try:
        cursor = await conn.cursor()
        await cursor.execute(
            'INSERT INTO teachers (username, first_seen) VALUES (?, datetime("now"))',
            (username,)
        )
        await conn.commit()
        return True
    except Exception as e:
        print(f"Error adding teacher: {e}")
        await conn.rollback()
        return False
    

async def is_user_teacher(username: str, conn: Optional[aiosqlite.Connection] = None) -> bool:
    """Проверяет, является ли пользователь учителем
    
    Args:
        username: Имя пользователя для проверки (без @)
        conn: Существующее соединение с БД (необязательное)
        
    Returns:
        bool: True если пользователь учитель, False если нет или произошла ошибка
    """
    if not username:
        return False
    
    if username == DIRECTOR_USERNAME:
        return True
    
    # Убрали комментарии из SQL запроса
    query = '''
    SELECT 1 FROM teachers 
    WHERE username = ? 
    AND chat_id IS NOT NULL
    '''
    
    try:
        if conn is None:
            async with get_db_connection() as new_conn:
                cursor = await new_conn.cursor()
                await cursor.execute(query, (username,))
                return bool(await cursor.fetchone())
        else:
            cursor = await conn.cursor()
            await cursor.execute(query, (username,))
            return bool(await cursor.fetchone())
    except Exception as e:
        print(f"Error checking teacher status for @{username}: {e}")
        return False


async def get_completed_assignments_teacher(teacher_username: str, limit: int = 100) -> tuple[list[dict], int]:
    """Получает выполненные задания для учителя"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
            SELECT 
                a.id,
                s.username,
                COALESCE(s.name, s.username) as student_name,
                a.text,
                a.response_text,
                a.response_file_id,
                a.response_file_type,
                a.submitted_at,
                COALESCE(a.grade, 'не оценено') as grade,
                COUNT(a.id) OVER() as total_count
            FROM assignments a
            JOIN students s ON a.student_username = s.username
            WHERE a.teacher_username = ? 
              AND a.status = 'submitted'
            ORDER BY a.submitted_at DESC
            LIMIT ?
            ''', (teacher_username, limit))
        
        works = await cursor.fetchall()
        
        # Форматируем результат
        completed_works = [{
            "id": work[0],
            "student": work[1],
            "student_name": work[2],
            "assignment": work[3],
            "response": work[4],
            "file_id": work[5],
            "file_type": work[6],
            "submitted_at": work[7],
            "grade": work[8]
        } for work in works]
        
        total_count = works[0][9] if works else 0
        
        return completed_works, total_count
    

async def get_teacher_classes_with_students(teacher_username: str) -> List[Tuple[str, Optional[str]]]:
    """Получает список классов учителя с учениками"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
        SELECT c.name, GROUP_CONCAT(s.username, ', ')
        FROM classes c
        LEFT JOIN student_classes sc ON c.name = sc.class_name
        LEFT JOIN students s ON sc.student_username = s.username
        WHERE c.teacher_username = ?
        GROUP BY c.name
        ''', (teacher_username,))
        return await cursor.fetchall()
    

async def get_teacher_chat_id(conn: aiosqlite.Connection, username: str) -> Optional[int]:
    """Получает chat_id учителя из БД"""
    cursor = await conn.cursor()
    await cursor.execute('SELECT chat_id FROM teachers WHERE username = ?', (username,))
    teacher_data = await cursor.fetchone()
    return teacher_data[0] if teacher_data else None