from dataclasses import dataclass
import sys
import traceback
from typing import List, Optional, Tuple
import aiosqlite
from school_bot.db.database import get_db_connection

from datetime import datetime


@dataclass
class AssignmentData:
    teacher_username: str
    student_username: str
    assignment_text: str
    file_id: str
    file_type: str
    file_name: Optional[str]
    class_name: Optional[str] = None


async def register_user(
    conn: aiosqlite.Connection,
    username: str,
    chat_id: int,
    is_teacher: bool
) -> None:
    """Регистрирует пользователя (учителя или ученика) в БД"""
    cursor = await conn.cursor()
    table = "teachers" if is_teacher else "students"
    
    await cursor.execute(
        f'''
        INSERT OR IGNORE INTO {table} (username, chat_id, first_seen)
        VALUES (?, ?, ?)
        ''',
        (username, chat_id, datetime.now().isoformat())
    )
    
    await cursor.execute(
        f'''
        UPDATE {table} SET chat_id = ? WHERE username = ?
        ''',
        (chat_id, username)
    )
    await conn.commit()
    

async def get_assignment_info(
    conn: aiosqlite.Connection,
    assignment_id: int,
    student_username: str
) -> Optional[tuple[str, str]]:
    """Получает текст задания и username учителя по ID задания"""
    cursor = await conn.execute('''
    SELECT a.text, a.teacher_username 
    FROM assignments a
    WHERE a.id = ? AND a.student_username = ? AND a.status = 'active'
    ''', (assignment_id, student_username))
    return await cursor.fetchone()


async def get_active_assignments_for_student(
    conn: aiosqlite.Connection, 
    student_username: str
) -> list[tuple[int, int, str, str, str]]:
    """Получает активные задания для ученика с нумерацией для отображения"""
    cursor = await conn.cursor()
    await cursor.execute('''
    SELECT 
        ROW_NUMBER() OVER (ORDER BY a.assigned_at) as display_num,
        a.id,
        a.text,
        a.teacher_username,
        a.assigned_at
    FROM assignments a
    WHERE a.student_username = ? AND a.status = 'active'
    ORDER BY a.assigned_at
    ''', (student_username,))
    return await cursor.fetchall()


async def get_assignment_details(
    assignment_id: int,
    student_username: str
) -> Optional[Tuple[int, str, str]]:
    """Получает детали задания из БД"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
        SELECT id, text, assigned_at 
        FROM assignments 
        WHERE id = ? AND student_username = ? AND status = 'active'
        ''', (assignment_id, student_username))
        return await cursor.fetchone()

async def update_assignment_response(
    assignment_id: int,
    response_text: str,
    file_id: Optional[str],
    file_type: Optional[str],
    file_name: Optional[str]  # Оставляем параметр, но не используем в запросе
) -> bool:
    """Обновляет задание с ответом ученика"""
    try:
        async with get_db_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute('''
            UPDATE assignments SET
                status = 'submitted',
                response_text = ?,
                response_file_id = ?,
                response_file_type = ?,
                submitted_at = ?
            WHERE id = ?
            ''', (
                response_text,
                file_id,
                file_type,
                datetime.now().isoformat(),
                assignment_id
            ))
            await conn.commit()
            return True
    except Exception as e:
        print(f"⚠ Ошибка при обновлении задания {assignment_id}: {e}")
        return False
    

async def get_active_assignments(
    student_username: str,
    conn: Optional[aiosqlite.Connection] = None
) -> List[Tuple[int, str, str, str, Optional[str], Optional[str], Optional[str], Optional[str]]]:
    """Получает активные задания ученика с информацией о файлах"""
    if conn is None:
        async with get_db_connection() as conn:
            return await _fetch_assignments(conn, student_username)
    else:
        return await _fetch_assignments(conn, student_username)

async def _fetch_assignments(
    conn: aiosqlite.Connection,
    student_username: str
) -> List[Tuple[int, str, str, str, Optional[str], Optional[str], Optional[str], Optional[str]]]:
    """Вспомогательная функция для получения заданий с файлами"""
    cursor = await conn.cursor()
    await cursor.execute('''
    SELECT 
        a.id,
        a.text,
        a.teacher_username,
        a.assigned_at,
        a.deadline,
        a.file_id,
        a.file_type,
        a.file_name
    FROM assignments a
    WHERE a.student_username = ? AND a.status = 'active'
    ORDER BY a.assigned_at
    ''', (student_username,))
    return await cursor.fetchall()


async def create_individual_assignment(
    conn: aiosqlite.Connection,
    teacher_username: str,
    student_username: str,
    assignment_text: str,
    file_id: Optional[str] = None,
    file_type: Optional[str] = None,
    file_name: Optional[str] = None
) -> bool:
    """Создает новое индивидуальное задание"""
    try:
        cursor = await conn.cursor()
        await cursor.execute('''
        INSERT INTO assignments (
            teacher_username, student_username, text,
            assignment_type, file_id, file_type, file_name,
            assigned_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), 'active')
        ''', (
            teacher_username, student_username, assignment_text,
            'individual', file_id, file_type, file_name
        ))
        return True
    except Exception as e:
        print(f"Ошибка при создании задания: {e}")
        return False


async def create_class_assignment(
    conn: aiosqlite.Connection,
    teacher_username: str,
    student_username: str,
    class_name: str,
    assignment_text: str,
    file_id: str,
    file_type: str,
    file_name: Optional[str]
) -> int:
    """Создает классное задание в БД"""
    cursor = await conn.cursor()
    await cursor.execute('''
    INSERT INTO assignments (
        teacher_username, student_username, text, 
        assignment_type, file_id, file_type, file_name,
        assigned_at, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), 'active')
    ''', (
        teacher_username, student_username, assignment_text,
        'class', file_id, file_type, file_name
    ))
    return cursor.lastrowid


async def update_assignment_message_id(
    conn: aiosqlite.Connection,
    message_id: int,
    filters: dict
) -> None:
    """Обновляет message_id задания"""
    cursor = await conn.cursor()
    query = '''
    UPDATE assignments SET
        message_id = ?
    WHERE teacher_username = ? 
      AND student_username = ?
      AND text = ?
      AND status = 'active'
    '''
    await cursor.execute(query, (
        message_id,
        filters['teacher_username'],
        filters['student_username'],
        filters['assignment_text']
    ))


async def save_assignment_to_db(assignment: AssignmentData) -> bool:
    """Сохраняет задание в базе данных"""
    async with get_db_connection() as conn:
        try:
            if assignment.class_name:
                # Для классного задания
                from school_bot.handlers.teacher import process_class_assignment
                await process_class_assignment(
                    conn,
                    assignment.teacher_username,
                    assignment.class_name,
                    assignment.assignment_text,
                    assignment.file_id,
                    assignment.file_type,
                    assignment.file_name
                )
            else:
                # Для индивидуального задания
                from school_bot.handlers.teacher import process_individual_assignment
                await process_individual_assignment(
                    conn,
                    assignment.teacher_username,
                    assignment.student_username,
                    assignment.assignment_text,
                    assignment.file_id,
                    assignment.file_type,
                    assignment.file_name
                )
            await conn.commit()
            return True
        except Exception as e:
            print(f"Database error: {e}")
            return False
    

async def get_class_by_name(teacher_username: str, class_name: str) -> Optional[str]:
    """Проверяет существование класса и возвращает его оригинальное название"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
        SELECT name FROM classes 
        WHERE LOWER(name) = ? AND teacher_username = ?
        ''', (class_name.lower(), teacher_username))
        result = await cursor.fetchone()
        return result[0] if result else None


async def get_teacher_classes(teacher_username: str) -> List[str]:
    """Возвращает список классов учителя"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
        SELECT name FROM classes WHERE teacher_username = ?
        ORDER BY name
        ''', (teacher_username,))
        return [row[0] for row in await cursor.fetchall()]


async def check_class_exists(teacher_username: str, class_name: str, conn: Optional[aiosqlite.Connection] = None) -> bool:
    """Проверяет существование класса (регистронезависимо с обработкой кавычек)"""
    # Удаляем лишние кавычки если они есть
    cleaned_class_name = class_name.strip().replace('"', '').replace("'", "")
    
    async def _check(connection):
        cursor = await connection.cursor()
        await cursor.execute('''
            SELECT 1 FROM classes 
            WHERE (name = ? OR REPLACE(REPLACE(name, '"', ''), "'", '') = ?)
            AND teacher_username = ?
        ''', (class_name, cleaned_class_name, teacher_username))
        return bool(await cursor.fetchone())
    
    if conn:
        return await _check(conn)
    else:
        async with get_db_connection() as new_conn:
            return await _check(new_conn)
    

async def check_class_exists_case_insensitive(teacher_username: str, class_name: str) -> bool:
    """Проверяет существование класса (регистронезависимо)"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
            SELECT 1 FROM classes 
            WHERE LOWER(name) = LOWER(?) AND teacher_username = ?
        ''', (class_name, teacher_username))
        return bool(await cursor.fetchone())


async def create_new_class(teacher_username: str, class_name: str) -> None:
    """Создает новый класс в базе данных"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
            INSERT INTO classes (name, teacher_username)
            VALUES (?, ?)
        ''', (class_name, teacher_username))
        await conn.commit()


async def get_submitted_work_details(work_id: int, teacher_username: str) -> Optional[tuple]:
    """Получает детали выполненного задания из базы данных"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
            SELECT 
                a.id, s.username, s.name, a.text, a.response_text, 
                a.response_file_id, a.submitted_at, a.grade
            FROM assignments a
            JOIN students s ON a.student_username = s.username
            WHERE a.id = ? AND a.teacher_username = ? AND a.status = 'submitted'
        ''', (work_id, teacher_username))
        return await cursor.fetchone()
    

async def get_submitted_works(teacher_username: str, limit: int = 50) -> list[tuple]:
    """Получает список выполненных работ для учителя"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
            SELECT 
                a.id, s.username, s.name, a.text, a.submitted_at
            FROM assignments a
            JOIN students s ON a.student_username = s.username
            WHERE a.teacher_username = ? AND a.status = 'submitted'
            ORDER BY a.submitted_at DESC
            LIMIT ?
        ''', (teacher_username, limit))
        return await cursor.fetchall()
    

async def get_work_details(work_id: int) -> Optional[tuple]:
    """Получает полные данные о работе по ID"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
            SELECT 
                a.id, s.username, s.name, a.text, a.response_text, 
                a.response_file_id, a.response_file_type, a.submitted_at, a.grade
            FROM assignments a
            JOIN students s ON a.student_username = s.username
            WHERE a.id = ?
        ''', (work_id,))
        return await cursor.fetchone()
    

async def grade_assignment_work(work_id: int, grade: int) -> tuple[str, str] | None:
    """Обновляет оценку работы и возвращает данные для уведомления (student_username, assignment_text)"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        
        # 1. Обновляем оценку в базе данных
        await cursor.execute('''
        UPDATE assignments SET
            grade = ?,
            graded_at = datetime('now')
        WHERE id = ?
        RETURNING student_username, text
        ''', (grade, work_id))
        
        updated_work = await cursor.fetchone()
        
        if not updated_work:
            return None
        
        student_username, assignment_text = updated_work
        await conn.commit()
        
        return student_username, assignment_text
    

async def create_individual_assignment_db(
    teacher_username: str,
    student_username: str,
    assignment_text: str
) -> tuple[bool, str]:
    """Создает индивидуальное задание в БД"""
    async with get_db_connection() as conn:
        try:
            from school_bot.handlers.teacher import process_individual_assignment
            success, status = await process_individual_assignment(
                conn,
                teacher_username,
                student_username,
                assignment_text
            )
            await conn.commit()
            return success, status
        except Exception as e:
            await conn.rollback()
            print(f"Ошибка при создании индивидуального задания: {e}")
            return False, "Ошибка при создании задания"


async def create_class_assignment_db(
    teacher_username: str,
    class_name: str,
    assignment_text: str,
    file_id: Optional[str] = None,
    file_type: Optional[str] = None,
    file_name: Optional[str] = None
) -> str:
    """Создает классное задание в БД"""
    async with get_db_connection() as conn:
        try:
            from school_bot.handlers.teacher import process_class_assignment
            await process_class_assignment(
                conn,
                teacher_username,
                class_name,
                assignment_text,
                file_id,
                file_type,
                file_name
            )
            await conn.commit()
            return f"Задание для класса {class_name} успешно создано!"
        except Exception as e:
            await conn.rollback()
            
            # Получаем полную информацию об исключении
            exc_type, exc_value, exc_traceback = sys.exc_info()
            
            # Формируем детализированное сообщение об ошибке
            error_details = [
                "⚠️ Произошла критическая ошибка при создании задания",
                f"Тип ошибки: {exc_type.__name__}",
                f"Сообщение: {str(exc_value)}",
                "Трассировка стека:",
                *traceback.format_tb(exc_traceback)
            ]
            
            # Логируем полную информацию
            full_error_msg = "\n".join(error_details)
            print(full_error_msg, file=sys.stderr)
            
            # Для пользователя возвращаем укороченную версию
            user_error_msg = (
                f"Ошибка при создании задания для класса {class_name}.\n"
                f"Тип: {exc_type.__name__}\n"
                f"Ошибка: {str(exc_value)}"
            )
            
            return user_error_msg
    

async def get_original_class_name(teacher_username: str, input_name: str) -> Optional[str]:
    """Возвращает оригинальное название класса (с учетом регистра)"""
    async with get_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
            SELECT name FROM classes 
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) 
            AND teacher_username = ?
        ''', (input_name, teacher_username))
        result = await cursor.fetchone()
        return result[0] if result else None
    

async def update_individual_assignment(
    conn: aiosqlite.Connection,
    teacher_username: str,
    student_username: str,
    assignment_text: str,
    file_id: str,
    file_type: str,
    file_name: Optional[str]
) -> bool:
    """Обновляет индивидуальное задание в БД"""
    try:
        cursor = await conn.cursor()
        await cursor.execute('''
        UPDATE assignments SET
            file_id = ?,
            file_type = ?,
            file_name = ?,
            status = 'active'
        WHERE teacher_username = ? 
          AND student_username = ?
          AND text = ?
          AND status = 'active'
        ''', (file_id, file_type, file_name, teacher_username, student_username, assignment_text))
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Ошибка при обновлении задания: {e}")
        return False


async def update_class_assignments(
    conn: aiosqlite.Connection,
    assignment_ids: List[int],
    file_id: str,
    file_type: str,
    file_name: str
) -> None:
    """Обновляет классные задания с файлом"""
    cursor = await conn.cursor()
    await cursor.executemany('''
    UPDATE assignments
    SET file_id = ?, file_type = ?, file_name = ?
    WHERE id = ?
    ''', [(file_id, file_type, file_name, aid) for aid in assignment_ids])