import traceback
from typing import List, Optional, Tuple
from aiogram import types
from aiogram.types import Message, ContentType, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram import F
import httpx

from school_bot.db.controllers import get_active_assignments, get_active_assignments_for_student, get_assignment_details, get_assignment_info, update_assignment_response
from school_bot.db.students import get_completed_assignments_student, get_student_classes_with_assignments, get_student_display_name
from school_bot.db.teachers import get_teacher_chat_id
from school_bot.db.database import get_db_connection
from school_bot.config import MAX_FILE_SIZE, SCHOOL_URL
from main import dp, bot


from school_bot.parse import parse_school_info, parse_school_schedule
from school_bot.states import StudentStates


def get_student_main_menu() -> ReplyKeyboardMarkup:
    """Главное меню ученика с кнопкой информации о школе"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📚 Мои задания"),
        KeyboardButton(text="🏫 Мои классы")
    )
    builder.row(
        KeyboardButton(text="📤 Отправить работу"),
        KeyboardButton(text="🏛️ О школе")
    )
    builder.row(
        KeyboardButton(text="🔄 Обновить"),
        KeyboardButton(text="📅 Расписание")
    )
    return builder.as_markup(resize_keyboard=True)


@dp.message(F.text == "🏛️ О школе")
async def show_school_info(message: types.Message):
    """Вывод информации о школе"""
    try:
        school_info = await parse_school_info()
        
        response = []
        
        # Название школы
        if school_info.get('name'):
            response.append(f"<b>{school_info['name']}</b>")
        else:
            response.append("<b>МОУ-СОШ №1 г.Красный Кут</b>")  # fallback
        
        response.append("")

        # Адрес (добавляем в начало, если есть)
        if school_info.get('address'):
            response.append(f"📍 <u>Адрес:</u> {school_info['address']}")
            response.append("")

        # Директор
        if school_info.get('director'):
            response.append("<u>Руководство:</u>")
            response.append(school_info['director'])
            response.append("")

        # Контакты
        if school_info.get('contacts'):
            response.append("<u>Контакты:</u>")
            # Убираем адрес из контактов, так как он уже выведен отдельно
            contacts = [c for c in school_info['contacts'].split('\n') if not c.startswith('📍')]
            response.append("\n".join(contacts))
            response.append("")

        # Описание
        if school_info.get('description'):
            response.append("<u>О школе:</u>")
            response.append(school_info['description'])
            response.append("")

        response.append(f"<a href='{SCHOOL_URL}'>🌐 Официальный сайт</a>")

        await message.answer(
            "\n".join(response),
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    except Exception as e:
        print(f"Ошибка: {e}")
        await message.answer(
            "⚠️ Не удалось загрузить информацию. Попробуйте позже.",
            reply_markup=get_student_main_menu()
        )


@dp.message(F.text == "📅 Расписание")
async def send_schedule(message: types.Message):
    """Отправляет пользователю все PDF с расписанием"""
    try:
        schedules = await parse_school_schedule()
        
        if not schedules:
            await message.answer("На данный момент расписания не найдены.")
            return
            
        await message.answer("📅 Отправляю расписания...")
        
        for schedule in schedules:
            try:
                # Скачиваем файл
                async with httpx.AsyncClient() as client:
                    response = await client.get(schedule['url'])
                    response.raise_for_status()
                    
                    # Отправляем файл пользователю
                    await message.answer_document(
                        types.BufferedInputFile(
                            response.content,
                            filename=f"{schedule['name']}.pdf"
                        ),
                        caption=f"📅 {schedule['name']}"
                    )
                    
            except Exception as e:
                print(f"Ошибка при отправке файла {schedule['name']}: {e}")
                await message.answer(
                    f"⚠️ Не удалось отправить расписание: {schedule['name']}"
                )
                
    except Exception as e:
        print(f"Ошибка при обработке расписания: {e}")
        await message.answer(
            "⚠️ Не удалось загрузить расписание. Попробуйте позже.",
            reply_markup=get_student_main_menu()
        )


def get_student_cancel_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)


@dp.message(F.text == "📚 Мои задания")
async def my_assignments_button(message: types.Message):
    await view_assignments(message)


@dp.message(F.text == "🏫 Мои классы")
async def my_classes_button(message: types.Message):
    await view_classes_student(message)


@dp.message(F.text == "📤 Отправить работу")
async def submit_assignment_button(message: types.Message, state: FSMContext):
    await start_submit_assignment(message, state)


def format_assignments(
    active_assignments: list,
    completed_assignments: list
) -> str:
    """Форматирует список заданий для отображения"""
    response = ""
    
    if active_assignments:
        response += "📋 <b>Активные задания:</b>\n\n"
        for i, assignment in enumerate(active_assignments, 1):
            # Обрабатываем как полные, так и неполные данные
            id_ = assignment[0]
            text = assignment[1]
            teacher = assignment[2]
            assigned_at = assignment[3]
            deadline = assignment[4] if len(assignment) > 4 else None
            
            deadline_str = deadline[:10] if deadline else "не указан"
            response += (
                f"{i}. {text}\n"
                f"👤 От: @{teacher}\n"
                f"⌛ Срок: {deadline_str}\n\n"
            )
    
    if completed_assignments:
        response += "\n✅ <b>Последние выполненные задания:</b>\n"
        for i, assignment in enumerate(completed_assignments, 1):
            id_ = assignment[0]
            text = assignment[1]
            teacher = assignment[2]
            submitted_at = assignment[3]
            grade = assignment[4] if len(assignment) > 4 else None
            
            grade_str = grade if grade is not None else "ещё не оценено"
            response += (
                f"{i}. {text}\n"
                f"📅 Отправлено: {submitted_at[:10]}\n"
                f"🏷 Оценка: {grade_str}\n\n"
            )
    
    return response if response else "📭 У вас пока нет заданий."


@dp.message(Command("my_assignments"), lambda message: str(message.from_user.username))
async def view_assignments(message: types.Message):
    student_username = message.from_user.username
    
    active = await get_active_assignments(student_username)
    completed = await get_completed_assignments_student(student_username)
    
    response = format_assignments(active, completed)
    
    await message.answer(
        response,
        reply_markup=get_student_main_menu(),
        parse_mode="HTML"
    )

    await send_assignment_files(message.chat.id, active)


async def send_assignment_files(chat_id: int, assignments: list):
    """Отправляет файлы из заданий с нумерацией"""
    for i, assignment in enumerate(assignments, 1):
        # Проверяем, есть ли информация о файлах в данных
        if len(assignment) >= 8:  # Если есть полные данные с файлами
            *_, file_id, file_type, file_name = assignment
        else:  # Если файлов нет, пропускаем
            continue
            
        if file_id:
            try:
                caption = f"Файл к заданию {i}"
                if file_type == "document":
                    await bot.send_document(
                        chat_id=chat_id,
                        document=file_id,
                        caption=caption
                    )
                else:  # photo
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=file_id,
                        caption=caption
                    )
            except Exception as e:
                print(f"Ошибка при отправке файла к заданию {i}: {e}")


def format_classes_response(classes: list[tuple[str, int]]) -> str:
    """Форматирует список классов для отображения"""
    response = "🏫 <b>Ваши классы:</b>\n"
    for class_name, active_count in classes:
        response += f"• {class_name}"
        if active_count > 0:
            response += f" ({active_count} активных заданий)"
        response += "\n"
    return response


@dp.message(Command("my_classes"), lambda message: str(message.from_user.username))
async def view_classes_student(message: types.Message):
    student_username = message.from_user.username
    
    async with get_db_connection() as conn:
        classes = await get_student_classes_with_assignments(conn, student_username)
    
    if not classes:
        await message.answer(
            "Вы пока не добавлены ни в один класс.",
            reply_markup=get_student_main_menu(),
            parse_mode="HTML"
        )
        return
    
    await message.answer(
        format_classes_response(classes),
        parse_mode="HTML",
        reply_markup=get_student_main_menu()
    )


def format_assignments_list(assignments: list[tuple[int, int, str, str, str]]) -> str:
    """Форматирует список заданий для отображения пользователю"""
    return "\n".join(
        f"{display_num}. {text} (от @{teacher_username})"
        for display_num, _, text, teacher_username, _ in assignments
    )

@dp.message(Command("submit_assignment"), lambda message: str(message.from_user.username))
async def start_submit_assignment(message: Message, state: FSMContext):
    student_username = message.from_user.username
    
    async with get_db_connection() as conn:
        active_assignments = await get_active_assignments_for_student(conn, student_username)
    
    if not active_assignments:
        await message.answer(
            "❌ У вас нет активных заданий для отправки.",
            reply_markup=get_student_main_menu()
        )
        return
    
    # Формируем и отправляем список заданий
    await message.answer(
        f"📝 <b>Ваши активные задания:</b>\n"
        f"{format_assignments_list(active_assignments)}\n\n"
        "Введите номер задания из списка выше:",
        parse_mode="HTML",
        reply_markup=get_student_cancel_menu()
    )
    
    # Сохраняем маппинг номеров к ID заданий
    await state.update_data({
        "assignments_mapping": {display_num: id for display_num, id, _, _, _ in active_assignments},
        "active_assignments_count": len(active_assignments)
    })
    await state.set_state(StudentStates.waiting_for_assignment_number)


@dp.message(StudentStates.waiting_for_assignment_number, F.text.regexp(r'^\d+$'))
async def process_assignment_number(message: Message, state: FSMContext):
    assignment_number = int(message.text)
    student_username = message.from_user.username
    
    # Получаем данные из state
    data = await state.get_data()
    assignments_mapping = data.get("assignments_mapping", {})
    active_assignments_count = data.get("active_assignments_count", 0)
    
    # Валидация номера задания
    if not 1 <= assignment_number <= active_assignments_count:
        await message.answer(
            f"❌ Неверный номер задания. Введите число от 1 до {active_assignments_count}:",
            reply_markup=get_student_cancel_menu()
        )
        return
    
    # Получаем ID выбранного задания
    assignment_id = assignments_mapping.get(assignment_number)
    if not assignment_id:
        await message.answer(
            "❌ Ошибка: задание не найдено",
            reply_markup=get_student_main_menu()
        )
        await state.clear()
        return
    
    async with get_db_connection() as conn:
        # Получаем информацию о задании
        assignment = await get_assignment_info(conn, assignment_id, student_username)
        
        if not assignment:
            await message.answer(
                "❌ Задание не найдено или уже выполнено",
                reply_markup=get_student_main_menu()
            )
            await state.clear()
            return
        
        assignment_text, teacher_username = assignment
        
        # Сохраняем данные в состоянии
        await state.update_data(
            assignment_id=assignment_id,
            assignment_text=assignment_text,
            teacher_username=teacher_username
        )
        
        await message.answer(
            f"📄 <b>Вы выбрали задание:</b>\n{assignment_text}\n\n"
            "Пришлите текстовый ответ или файл с выполненным заданием.\n"
            "Вы можете отправить:\n"
            "• Текст\n"
            "• Документ (PDF, Word)\n"
            "• Фото",
            parse_mode="HTML",
            reply_markup=get_student_cancel_menu()
        )
        await state.set_state(StudentStates.waiting_for_assignment_response)


@dp.message(StudentStates.waiting_for_assignment_number)
async def wrong_assignment_number(message: Message):
    await message.answer("❌ Пожалуйста, введите номер задания цифрами:")


@dp.message(StudentStates.waiting_for_assignment_response, F.content_type.in_({ContentType.TEXT}))
async def process_text_response(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(response_text=message.text)
    
    await message.answer(
        "Хотите прикрепить файл к ответу? (документ или фото)\n"
        "Отправьте файл или нажмите /skip чтобы пропустить."
    )
    await state.set_state(StudentStates.waiting_for_file_response)


async def submit_assignment(
    student_username: str,
    assignment_id: int,
    response_text: str,
    file_id: Optional[str],
    file_type: Optional[str],
    file_name: Optional[str],
    teacher_username: str
) -> bool:
    """
    Основная бизнес-логика отправки задания
    
    Args:
        student_username: Логин ученика
        assignment_id: ID задания
        response_text: Текст ответа
        file_id: ID файла (если есть)
        file_type: Тип файла
        file_name: Имя файла
        teacher_username: Логин учителя
        
    Returns:
        bool: Статус операции
    """
    try:
        # 1. Получаем данные задания
        assignment = await get_assignment_details(assignment_id, student_username)
        if not assignment:
            print(f"⚠ Задание {assignment_id} не найдено или уже выполнено")
            return False
        
        # 2. Обновляем задание
        update_success = await update_assignment_response(
            assignment_id,
            response_text,
            file_id,
            file_type,
            file_name
        )
        
        if not update_success:
            return False
        
        # 3. Уведомляем учителя
        notification_sent = await notify_teacher(
            teacher_username=teacher_username,
            student_username=student_username,
            assignment_text=assignment[1],
            response_text=response_text,
            file_id=file_id,
            file_type=file_type,
            file_name=file_name
        )
        
        if not notification_sent:
            print(f"⚠ Уведомление учителю @{teacher_username} не отправлено")
        
        return True
        
    except Exception as e:
        print(f"⚠ Ошибка при обработке задания {assignment_id}: {e}")
        return False


@dp.message(StudentStates.waiting_for_assignment_response, F.content_type.in_({ContentType.DOCUMENT, ContentType.PHOTO}))
async def process_file_response(message: Message, state: FSMContext):
    data = await state.get_data()
    
    # Проверяем наличие всех необходимых данных
    required_keys = ['assignment_id', 'teacher_username']
    missing_keys = [key for key in required_keys if key not in data]
    
    if missing_keys:
        await message.answer(
            "❌ Ошибка: отсутствуют необходимые данные. Попробуйте начать заново.",
            reply_markup=get_student_main_menu()
        )
        await state.clear()
        return
    
    response_text = ""
    
    # Обработка файла
    if message.document:
        if message.document.file_size > MAX_FILE_SIZE:
            await message.answer(f"❌ Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE//1024//1024}MB")
            return
        
        file_id = message.document.file_id
        file_type = "document"
        file_name = message.document.file_name
    else:  # photo
        file_id = message.photo[-1].file_id
        file_type = "photo"
        file_name = None
    
    try:
        await submit_assignment(
            student_username=message.from_user.username,
            assignment_id=data["assignment_id"],
            response_text=response_text,
            file_id=file_id,
            file_type=file_type,
            file_name=file_name,
            teacher_username=data["teacher_username"]
        )
        
        await message.answer(
            "✅ Ваш ответ с файлом успешно отправлен на проверку!",
            reply_markup=get_student_main_menu()
        )
    except Exception as e:
        await message.answer(
            f"❌ Произошла ошибка при отправке ответа: {str(e)}",
            reply_markup=get_student_main_menu()
        )
    finally:
        await state.clear()


@dp.message(StudentStates.waiting_for_file_response, F.content_type.in_({ContentType.DOCUMENT, ContentType.PHOTO}))
async def process_additional_file(message: Message, state: FSMContext):
    data = await state.get_data()
    
    if message.document:
        if message.document.file_size > MAX_FILE_SIZE:
            await message.answer(f"❌ Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE//1024//1024}MB")
            return
        
        file_id = message.document.file_id
        file_type = "document"
        file_name = message.document.file_name
    else:  # photo
        file_id = message.photo[-1].file_id
        file_type = "photo"
        file_name = None
    
    await submit_assignment(
        message.from_user.username,
        data["assignment_index"],
        data.get("response_text", ""),
        file_id,
        file_type,
        file_name,
        data["teacher_username"]
    )
    
    await message.answer("✅ Ваш ответ с файлом успешно отправлен на проверку!")
    await state.clear()

@dp.message(Command("skip"), StudentStates.waiting_for_file_response)
async def skip_file_upload(message: Message, state: FSMContext):
    data = await state.get_data()
    
    await submit_assignment(
        message.from_user.username,
        data["assignment_index"],
        data.get("response_text", ""),
        None,
        None,
        None,
        data["teacher_username"]
    )
    
    await message.answer("✅ Ваш текстовый ответ успешно отправлен на проверку!")
    await state.clear()


async def send_file_notification(
    chat_id: int,
    message_text: str,
    file_id: str,
    file_type: str,
    file_name: Optional[str] = None
) -> bool:
    """Отправляет уведомление с файлом"""
    try:
        if file_type == "document":
            await bot.send_document(
                chat_id=chat_id,
                document=file_id,
                caption=message_text[:1024]
            )
        elif file_type == "photo":
            await bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=message_text[:1024]
            )
        print(f"✅ Файл отправлен (chat_id: {chat_id})")
        return True
    except Exception as file_error:
        print(f"⚠ Ошибка отправки файла: {file_error}")
        return False


async def send_text_notification(chat_id: int, message_text: str) -> bool:
    """Отправляет текстовое уведомление"""
    try:
        await bot.send_message(chat_id=chat_id, text=message_text)
        print(f"✅ Уведомление отправлено (chat_id: {chat_id})")
        return True
    except Exception as text_error:
        print(f"⚠ Ошибка отправки текста: {text_error}")
        return False

async def notify_teacher(
    teacher_username: str,
    student_username: str,
    assignment_text: str,
    response_text: str = "",
    file_id: str = None,
    file_type: str = None,
    file_name: str = None
) -> bool:
    """Надежная функция уведомления учителя с проверкой всех возможных ошибок"""
    try:
        async with get_db_connection() as conn:
            # 1. Проверка наличия учителя и получение chat_id
            chat_id = await get_teacher_chat_id(conn, teacher_username)
            if not chat_id:
                print(f"⚠ Учитель @{teacher_username} не найден или chat_id отсутствует")
                return False
            
            # 2. Проверка валидности chat_id
            if not isinstance(chat_id, (int, str)) or not str(chat_id).strip():
                print(f"⚠ Неверный формат chat_id для учителя @{teacher_username}: {chat_id}")
                return False
            
            # 3. Получаем имя ученика
            student_name = await get_student_display_name(conn, student_username)
            
            # 4. Подготовка сообщения
            message_text = (
                f"📬 Новый ответ на задание!\n"
                f"👤 Ученик: {student_name} (@{student_username})\n"
                f"📚 Задание: {assignment_text}\n"
            )
            
            if response_text:
                message_text += f"📝 Ответ: {response_text[:500]}\n"
            
            # 5. Отправка сообщения
            success = False
            if file_id and file_type:
                message_text += f"📎 Приложен файл: {file_name if file_name else file_type}"
                success = await send_file_notification(chat_id, message_text, file_id, file_type, file_name)
                if not success:
                    message_text += "\n⚠ Не удалось отправить вложение"
            
            # Если файл не отправлен или не приложен, отправляем текст
            if not success:
                success = await send_text_notification(chat_id, message_text)
            
            return success

    except Exception as e:
        print(f"⚠ Критическая ошибка при уведомлении учителя @{teacher_username}: {e}")
        return False