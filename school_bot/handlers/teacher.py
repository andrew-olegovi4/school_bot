from datetime import datetime
from typing import List, Optional, Tuple, Union
from aiogram import types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram import F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, Document, PhotoSize
from aiogram.utils.keyboard import ReplyKeyboardBuilder
import aiosqlite

from school_bot.db.controllers import AssignmentData, check_class_exists_case_insensitive, create_class_assignment, create_individual_assignment, create_new_class, get_original_class_name, get_submitted_work_details, get_submitted_works, get_teacher_classes, grade_assignment_work, update_assignment_message_id, update_individual_assignment
from school_bot.db.students import add_new_student, add_student_to_class, check_student_exists, check_student_in_class, get_student_chat_id, get_student_notification_info, get_students_in_class
from school_bot.db.teachers import get_completed_assignments_teacher, is_user_teacher, get_teacher_classes_with_students
from school_bot.db.database import get_db_connection
from school_bot.states import TeacherStates
from main import dp, bot
from school_bot.config import BOT_USERNAME, MAX_FILE_SIZE, DIRECTOR_USERNAME


@dp.message(F.text == "👨‍🏫 Добавить учителя")
async def add_teacher_handler(message: types.Message, state: FSMContext):
    """Обработчик начала процесса добавления учителя"""
    if message.from_user.username != DIRECTOR_USERNAME:
        from school_bot.handlers.universal import get_user_menu
        await message.answer("⛔ Доступно только директору", reply_markup=await get_user_menu(message.from_user.username))
        return
    
    await message.answer(
        "✏️ Введите username нового учителя (без @):\n\n"
        "Пример: <code>ivanov_teacher</code>",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="HTML"
    )
    await state.set_state(TeacherStates.waiting_for_new_teacher_username)


@dp.message(TeacherStates.waiting_for_new_teacher_username)
async def process_new_teacher_username(message: types.Message, state: FSMContext):
    """Обработчик ввода username нового учителя"""
    from school_bot.db.teachers import teacher_exists, add_teacher
    from school_bot.db.students import student_exists
    from school_bot.handlers.universal import get_user_menu
    
    username = message.text.strip()
    
    # Валидация username
    if not username.replace('_', '').isalnum():
        await message.answer(
            "❌ Некорректный username. Используйте только буквы, цифры и подчеркивание.\n"
            "Попробуйте еще раз:"
        )
        return
    
    if len(username) > 32:
        await message.answer("❌ Слишком длинный username. Максимум 32 символа.\nПопробуйте еще раз:")
        return
    
    async with get_db_connection() as conn:
        # Проверяем существование учителя
        if await teacher_exists(conn, username):
            await message.answer(
                f"❌ Учитель @{username} уже существует.\n"
                "Введите другой username:"
            )
            return
        
        # Проверяем, не является ли учеником
        if await student_exists(conn, username):
            await message.answer(
                f"❌ Пользователь @{username} уже зарегистрирован как ученик.\n"
                "Введите другой username:"
            )
            return
        
        # Добавляем нового учителя
        if await add_teacher(conn, username):
            await message.answer(
                f"✅ Учитель @{username} успешно добавлен!\n\n"
                "Отправьте ему эту ссылку для регистрации:\n"
                f"<code>https://t.me/{BOT_USERNAME}?start=teacher_{username}</code>",
                parse_mode="HTML",
                reply_markup=await get_user_menu(message.from_user.username)
            )
        else:
            await message.answer(
                "❌ Произошла ошибка при добавлении учителя. Попробуйте позже.",
                reply_markup=await get_user_menu(message.from_user.username)
            )
    
    await state.clear()


@dp.message(F.text == "🏫 Управление школой")
async def school_management_handler(message: types.Message):
    if message.from_user.username != DIRECTOR_USERNAME:
        await message.answer("⛔ Доступно только директору")
        return
    
    await message.answer("⛔ TODO")
    return

    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📊 Статистика школы"))
    builder.row(KeyboardButton(text="📝 Рассылка сообщений"))
    builder.row(KeyboardButton(text="⬅️ Назад"))
    
    await message.answer(
        "🏫 <b>Управление школой</b>\n\nВыберите действие:",
        reply_markup=builder.as_markup(resize_keyboard=True),
        parse_mode="HTML"
    )


def get_teacher_main_menu(is_director: bool = False) -> ReplyKeyboardMarkup:
    """Возвращает основное меню учителя или расширенное меню директора"""
    builder = ReplyKeyboardBuilder()
    
    # Общие кнопки для всех учителей
    builder.row(
        KeyboardButton(text="📝 Дать задание"),
        KeyboardButton(text="👥 Мои классы")
    )
    builder.row(
        KeyboardButton(text="📊 Проверка работ"),
        KeyboardButton(text="🔄 Обновить")
    )
    
    if is_director:
        # Дополнительные кнопки только для директора
        builder.row(
            KeyboardButton(text="👨‍🏫 Добавить учителя"),
            KeyboardButton(text="🏫 Управление школой")
        )
    else:
        # Кнопки для обычных учителей
        builder.row(
            KeyboardButton(text="➕ Создать класс"),
            KeyboardButton(text="🎓 Добавить ученика")
        )
    
    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )

def get_teacher_cancel_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)


@dp.message(F.text == "📝 Дать задание")
async def give_assignment_button(message: types.Message, state: FSMContext):
    await give_assignment_start(message, state)


@dp.message(F.text == "👥 Мои классы")
async def view_classes_button(message: types.Message):
    await view_classes(message)


@dp.message(F.text == "➕ Создать класс")
async def create_class_button(message: types.Message, state: FSMContext):
    await create_class_start(message, state)


@dp.message(F.text == "🎓 Добавить ученика")
async def add_student_button(message: types.Message, state: FSMContext):
    await add_student_start(message, state)


@dp.message(F.text == "📊 Проверка работ")
async def view_completed_button(message: types.Message, state: FSMContext):
    await view_completed_start(message, state)


@dp.message(Command("view_completed"))
async def view_completed_start(message: types.Message, state: FSMContext):
    """Обработчик просмотра выполненных заданий"""
    teacher_username = message.from_user.username
    
    # Проверяем права доступа
    if not await is_user_teacher(teacher_username):
        await message.answer("⛔ Доступ только для учителей")
        return
    
    completed_works, total_count = await get_completed_assignments_teacher(teacher_username)
    
    if not completed_works:
        from school_bot.handlers.universal import get_user_menu
        await message.answer(
            "📭 Нет выполненных заданий для проверки.",
            reply_markup=await get_user_menu(str(message.from_user.username))
        )
        return
    
    await state.update_data(
        completed_works=completed_works,
        current_page=0,
        total_works=total_count
    )
    await show_completed_works_page(message, state)


async def show_completed_works_page(message: types.Message, state: FSMContext):
    data = await state.get_data()
    completed_works = data["completed_works"]
    current_page = data["current_page"]
    works_per_page = 5
    
    total_pages = (len(completed_works) + works_per_page - 1) // works_per_page
    start_idx = current_page * works_per_page
    end_idx = start_idx + works_per_page
    
    # Формируем сообщение
    response = (
        f"📚 <b>Выполненные задания</b> (страница {current_page + 1}/{total_pages})\n\n"
        f"Всего работ: {len(completed_works)}\n\n"
    )
    
    for i, work in enumerate(completed_works[start_idx:end_idx], start_idx + 1):
        response += (
            f"🔹 <b>Работа #{i}</b>\n"
            f"👤 Ученик: {work['student_name']} (@{work['student']})\n"
            f"📝 Задание: {work['assignment'][:50]}...\n"
            f"📅 Дата отправки: {work['submitted_at'][:10]}\n"
            f"🏆 Оценка: {work['grade']}\n\n"
        )
    
    # Создаем клавиатуру
    keyboard = []
    
    # Кнопки навигации
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_page"))
    
    if end_idx < len(completed_works):
        nav_buttons.append(types.InlineKeyboardButton(text="Вперед ➡️", callback_data="next_page"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопки для детального просмотра
    for i, work in enumerate(completed_works[start_idx:end_idx], start_idx + 1):
        keyboard.append([
            types.InlineKeyboardButton(
                text=f"Просмотреть работу #{i}",
                callback_data=f"view_work_{start_idx + i - 1}"
            )
        ])
    
    await message.answer(
        response,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data in ["prev_page", "next_page"])
async def handle_page_navigation(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_page = data["current_page"]
    
    if callback.data == "prev_page" and current_page > 0:
        await state.update_data(current_page=current_page - 1)
    elif callback.data == "next_page":
        await state.update_data(current_page=current_page + 1)
    
    await callback.message.delete()
    await show_completed_works_page(callback.message, state)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("view_work_"))
async def view_specific_work(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    work_idx = int(callback.data.split("_")[-1])
    work = data["completed_works"][work_idx]
    
    response = (
        f"📄 <b>Подробности работы</b>\n\n"
        f"👤 Ученик: {work['student_name']} (@{work['student']})\n"
        f"📝 Задание: {work['assignment']}\n"
        f"📅 Дата отправки: {work['submitted_at'][:10]}\n"
        f"🏆 Оценка: {work['grade']}\n\n"
        f"📋 Ответ ученика:\n{work['response'][:1000]}\n"
    )
    
    keyboard = [
        [types.InlineKeyboardButton(text="Поставить оценку", callback_data=f"grade_work_{work_idx}")],
        [types.InlineKeyboardButton(text="Назад к списку", callback_data="back_to_list")]
    ]
    
    try:
        if work["file_id"]:
            if work["file_type"] == "document":
                await bot.send_document(
                    chat_id=callback.message.chat.id,
                    document=work["file_id"],
                    caption=response[:1024],
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
                    parse_mode="HTML"
                )
            elif work["file_type"] == "photo":
                await bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=work["file_id"],
                    caption=response[:1024],
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
                    parse_mode="HTML"
                )
            else:
                await callback.message.answer(
                    response,
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
                    parse_mode="HTML"
                )
        else:
            await callback.message.answer(
                response,
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
    except Exception as e:
        print(f"Error sending work details: {e}")
        await callback.message.answer(
            "Не удалось загрузить прикрепленный файл.\n" + response,
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )
    
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("grade_work_"))
async def start_grading_work(callback: types.CallbackQuery, state: FSMContext):
    work_idx = int(callback.data.split("_")[-1])
    await state.update_data(current_work_idx=work_idx)
    
    # Создаем клавиатуру с оценками
    grades_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=str(i), callback_data=f"set_grade_{i}") for i in range(1, 6)],
        [types.InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel_grading")]
    ])
    
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\nВыберите оценку:",
        reply_markup=grades_keyboard
    )
    await callback.answer()


# Регистрация обработчика
@dp.callback_query(lambda c: c.data.startswith("set_grade_"))
async def handle_set_grade(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик установки оценки"""
    try:
        grade = int(callback.data.split("_")[-1])
        data = await state.get_data()
        
        # Получаем текущий индекс работы
        work_idx = data.get("current_work_idx")
        if work_idx is None:
            await callback.answer("Ошибка: работа не найдена")
            return
            
        # Получаем список работ
        completed_works = data.get("completed_works", [])
        if work_idx >= len(completed_works):
            await callback.answer("Ошибка: неверный индекс работы")
            return
            
        work = completed_works[work_idx]
        
        # Обновляем оценку в БД
        success = await grade_assignment_work(work['id'], grade)
        if not success:
            await callback.answer("Ошибка при обновлении оценки")
            return
            
        # Обновляем данные в state
        completed_works[work_idx]['grade'] = grade
        await state.update_data(completed_works=completed_works)
        
        # Уведомляем ученика
        try:
            student_data = await get_student_notification_info(work['student'])
            if student_data:
                student_chat_id, student_name = student_data
                from school_bot.handlers.student import get_student_main_menu
                
                # Формируем текст сообщения с проверкой имени
                student_display_name = student_name if student_name else f"@{work['student']}"
                message_text = (
                    f"📢 {student_display_name}, ваша работа проверена!\n\n"
                    f"Задание: {work['assignment'][:100]}\n"
                    f"Оценка: {grade}"
                )
                
                await bot.send_message(
                    chat_id=student_chat_id,
                    text=message_text,
                    reply_markup=get_student_main_menu()
                )
            else:
                print(f"Не удалось отправить уведомление ученику @{work['student']}")
        except Exception as e:
            print(f"Error notifying student @{work['student']}: {e}")
        
        await callback.answer(f"Оценка {grade} поставлена!")
        await back_to_work_details(callback, state)
        
    except ValueError:
        await callback.answer("Некорректная оценка")
    except Exception as e:
        print(f"Error in handle_set_grade: {e}")
        await callback.answer("Произошла ошибка")


@dp.callback_query(lambda c: c.data == "cancel_grading")
async def cancel_grading(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик отмены оценки"""
    try:
        await back_to_work_details(callback, state)
        await callback.answer("Оценка не изменена")
    except Exception as e:
        print(f"Error in cancel_grading: {e}")
        await callback.answer("Произошла ошибка")


@dp.callback_query(lambda c: c.data == "back_to_list")
async def back_to_list(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await show_completed_works_page(callback.message, state)
    await callback.answer()


def format_work_details(work: tuple) -> str:
    """Форматирует детали работы для отображения"""
    return (
        f"📄 <b>Подробности работы</b>\n\n"
        f"👤 Ученик: {work[2]} (@{work[1]})\n"
        f"📝 Задание: {work[3]}\n"
        f"📅 Дата отправки: {work[7][:10]}\n"
        f"🏆 Оценка: {work[8] if work[8] else 'ещё не оценено'}\n\n"
        f"📋 Ответ ученика:\n{work[4][:1000] if work[4] else 'Нет текстового ответа'}\n"
    )


def create_work_details_keyboard(work_id: int) -> types.InlineKeyboardMarkup:
    """Создает клавиатуру для управления работой"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text="Изменить оценку", 
            callback_data=f"grade_work_{work_id}"
        )],
        [types.InlineKeyboardButton(
            text="Назад к списку", 
            callback_data="back_to_list"
        )]
    ])


async def back_to_work_details(callback: types.CallbackQuery, state: FSMContext):
    """Возвращает к деталям работы"""
    try:
        data = await state.get_data()
        work_idx = data.get("current_work_idx")
        if work_idx is None:
            await callback.answer("Ошибка: работа не найдена")
            return
            
        completed_works = data.get("completed_works", [])
        if work_idx >= len(completed_works):
            await callback.answer("Ошибка: неверный индекс работы")
            return
            
        work = completed_works[work_idx]
        
        response = (
            f"📄 <b>Подробности работы</b>\n\n"
            f"👤 Ученик: {work['student_name']} (@{work['student']})\n"
            f"📝 Задание: {work['assignment']}\n"
            f"📅 Дата отправки: {work['submitted_at'][:10]}\n"
            f"🏆 Оценка: {work['grade']}\n\n"
            f"📋 Ответ ученика:\n{work['response'][:1000]}\n"
        )
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="Поставить оценку", 
                callback_data=f"grade_work_{work_idx}"
            )],
            [types.InlineKeyboardButton(
                text="Назад к списку", 
                callback_data="back_to_list"
            )]
        ])
        
        try:
            if work.get("file_id"):
                if work.get("file_type") == "document":
                    await callback.message.edit_caption(
                        caption=response,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                else:
                    await callback.message.edit_media(
                        media=types.InputMediaPhoto(
                            media=work["file_id"],
                            caption=response,
                            parse_mode="HTML"
                        ),
                        reply_markup=keyboard
                    )
            else:
                await callback.message.edit_text(
                    text=response,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        except Exception as e:
            print(f"Error editing message: {e}")
            await callback.message.delete()
            await callback.message.answer(
                response,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
    except Exception as e:
        print(f"Error in back_to_work_details: {e}")
        await callback.answer("Произошла ошибка")


def build_works_keyboard(works: list[tuple], page: int = 0) -> types.InlineKeyboardMarkup:
    """Создает клавиатуру для отображения списка работ"""
    start_idx = page * 10
    end_idx = start_idx + 10
    current_works = works[start_idx:end_idx]
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text=f"{i+1+start_idx}. {work[2]} (@{work[1]}): {work[3][:20]}...",
            callback_data=f"view_work_{work[0]}"
        )] for i, work in enumerate(current_works)
    ])
    
    # Добавляем кнопки навигации если нужно
    if len(works) > 10:
        buttons = []
        if page > 0:
            buttons.append(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_works_page"))
        if end_idx < len(works):
            buttons.append(types.InlineKeyboardButton(text="➡️ Вперед", callback_data="next_works_page"))
        keyboard.inline_keyboard.append(buttons)
    
    return keyboard


@dp.callback_query(lambda c: c.data == "view_all_works")
async def view_all_works(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает просмотр всех работ"""
    teacher_username = callback.from_user.username
    
    works = await get_submitted_works(teacher_username)
    if not works:
        await callback.answer("Нет работ для просмотра")
        return
    
    # Сохраняем работы в state для постраничного просмотра
    await state.update_data(all_works=works, current_page=0)
    
    # Формируем и отправляем клавиатуру
    keyboard = build_works_keyboard(works)
    await callback.message.edit_text(
        text="Выберите работу для просмотра:",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "next_works_page")
async def next_works_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    works = data.get("all_works", [])
    current_page = data.get("current_page", 0)
    
    if not works:
        await callback.answer("Нет данных о работах")
        return
    
    next_page = current_page + 1
    start_idx = next_page * 10
    end_idx = start_idx + 10
    
    if start_idx >= len(works):
        await callback.answer("Это последняя страница")
        return
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text=f"{start_idx+i+1}. {work[2]} (@{work[1]}): {work[3][:20]}...",
            callback_data=f"view_work_{work[0]}"
        )] for i, work in enumerate(works[start_idx:end_idx])
    ])
    
    # Добавляем кнопки навигации
    nav_buttons = []
    if next_page > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_works_page"))
    if end_idx < len(works):
        nav_buttons.append(types.InlineKeyboardButton(text="➡️ Вперед", callback_data="next_works_page"))
    
    if nav_buttons:
        keyboard.inline_keyboard.append(nav_buttons)
    
    await state.update_data(current_page=next_page)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "prev_works_page")
async def prev_works_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    works = data.get("all_works", [])
    current_page = data.get("current_page", 0)
    
    if current_page <= 0:
        await callback.answer("Это первая страница")
        return
    
    prev_page = current_page - 1
    start_idx = prev_page * 10
    end_idx = start_idx + 10
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text=f"{start_idx+i+1}. {work[2]} (@{work[1]}): {work[3][:20]}...",
            callback_data=f"view_work_{work[0]}"
        )] for i, work in enumerate(works[start_idx:end_idx])
    ])
    
    # Добавляем кнопки навигации
    nav_buttons = []
    if prev_page > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_works_page"))
    if end_idx < len(works):
        nav_buttons.append(types.InlineKeyboardButton(text="➡️ Вперед", callback_data="next_works_page"))
    
    if nav_buttons:
        keyboard.inline_keyboard.append(nav_buttons)
    
    await state.update_data(current_page=prev_page)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


def format_work_response(work: tuple) -> str:
    """Форматирует информацию о работе для отправки"""
    return (
        f"👨🎓 Ученик: {work[2]} (@{work[1]})\n"
        f"📝 Задание: {work[3]}\n"
        f"📅 Дата выполнения: {work[6][:10]}\n"
        f"🏆 Оценка: {work[7] if work[7] else 'ещё не оценено'}\n\n"
        f"📄 Ответ:\n{work[4] or 'Нет текстового ответа'}"
    )


async def send_work_file(chat_id: int, file_id: str, caption: str) -> None:
    """Отправляет файл работы с подписью"""
    try:
        file_type = "document" if file_id.startswith("BQ") else "photo"
        
        if file_type == "document":
            await bot.send_document(
                chat_id=chat_id,
                document=file_id,
                caption=caption[:1000]
            )
        else:
            await bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=caption[:1000]
            )
    except Exception as e:
        raise ValueError(f"Ошибка отправки файла: {str(e)}")


@dp.callback_query(lambda c: c.data.startswith("view_work_"))
async def view_specific_work(callback: types.CallbackQuery):
    """Обрабатывает просмотр конкретной работы"""
    work_id = int(callback.data.split("_")[-1])
    teacher_username = callback.from_user.username
    
    work = await get_submitted_work_details(work_id, teacher_username)
    if not work:
        await callback.answer("Работа не найдена")
        return
    
    response = format_work_response(work)
    
    try:
        if work[5]:  # Если есть файл
            await send_work_file(callback.from_user.id, work[5], response)
        else:
            await callback.message.answer(response)
    except ValueError as e:
        await callback.message.answer(
            f"{response}\n\n⚠ {str(e)}",
            parse_mode="HTML"
        )
    
    await callback.answer()


@dp.message(Command("create_class"))
async def create_class_start(message: types.Message, state: FSMContext):
    """Обработчик создания нового класса"""
    teacher_username = message.from_user.username
    
    # Проверяем права доступа
    if not await is_user_teacher(teacher_username):
        await message.answer("⛔ Только учителя могут создавать классы")
        return
    
    await state.update_data(teacher_username=teacher_username)
    await state.set_state(TeacherStates.waiting_for_new_class_name)
    await message.answer(
        "Введите название нового класса:",
        reply_markup=get_teacher_cancel_menu()
    )


@dp.message(TeacherStates.waiting_for_new_class_name)
async def process_new_class_name(message: types.Message, state: FSMContext):
    """Обрабатывает создание нового класса"""
    class_name = message.text.strip()
    teacher_username = message.from_user.username
    
    if not class_name:
        await message.answer("Название класса не может быть пустым!")
        return
    
    if await check_class_exists_case_insensitive(teacher_username, class_name):
        await message.answer("Класс с таким названием уже существует!")
    else:
        await create_new_class(teacher_username, class_name)
        from school_bot.handlers.universal import get_user_menu
        await message.answer(
            f"Класс '{class_name}' успешно создан!",
            reply_markup=await get_user_menu(str(message.from_user.username))
        )
    
    await state.clear()


@dp.message(Command("add_student"))
async def add_student_start(message: types.Message, state: FSMContext):
    """Обработчик начала добавления ученика в класс"""
    teacher_username = message.from_user.username
    
    # Проверяем права доступа
    if not await is_user_teacher(teacher_username):
        await message.answer("⛔ Только учителя могут добавлять учеников")
        return
    
    # Получаем список классов учителя для проверки
    teacher_classes = await get_teacher_classes(teacher_username)
    if not teacher_classes:
        from school_bot.handlers.universal import get_user_menu
        await message.answer(
            "У вас нет классов. Сначала создайте класс.",
            reply_markup=await get_user_menu(str(message.from_user.username))
        )
        return
    
    await state.update_data(teacher_username=teacher_username)
    await state.set_state(TeacherStates.waiting_for_class_name)
    await message.answer(
        "Введите название класса, в который нужно добавить ученика:",
        reply_markup=get_teacher_cancel_menu()
    )


@dp.message(TeacherStates.waiting_for_class_name)
async def select_class_for_student(message: types.Message, state: FSMContext):
    """Обрабатывает выбор класса для добавления ученика"""
    class_name = message.text.strip()
    teacher_username = message.from_user.username
    
    # Проверяем существование класса (регистронезависимо)
    original_class_name = await get_original_class_name(teacher_username, class_name)
    
    if original_class_name:
        await state.update_data(class_name=original_class_name)
        await state.set_state(TeacherStates.waiting_for_student_username)
        await message.answer(f"Теперь введите @username ученика для класса '{original_class_name}':")
    else:
        # Показываем список доступных классов
        available_classes = await get_teacher_classes(teacher_username)
        classes_list = "\n".join([f"- {class_name}" for class_name in available_classes])
        
        from school_bot.handlers.universal import get_user_menu
        await message.answer(
            f"Класс '{class_name}' не найден. Ваши классы:\n{classes_list}\n"
            "Попробуйте снова или нажмите /cancel",
            reply_markup=await get_user_menu(str(message.from_user.username))
        )


@dp.message(TeacherStates.waiting_for_student_username)
async def process_student_username(message: types.Message, state: FSMContext):
    """Обрабатывает добавление ученика в класс"""
    student_username = message.text.strip("@")
    data = await state.get_data()
    class_name = data["class_name"]
    
    # Проверяем, есть ли ученик уже в классе
    if await check_student_in_class(student_username, class_name):
        from school_bot.handlers.universal import get_user_menu
        await message.answer("Этот ученик уже в данном классе.",
                           reply_markup=await get_user_menu(str(message.from_user.username)))
        await state.clear()
        return
    
    # Если ученика нет в базе - добавляем
    if not await check_student_exists(student_username):
        await add_new_student(student_username)
    
    # Добавляем ученика в класс
    await add_student_to_class(student_username, class_name)
    
    from school_bot.handlers.universal import get_user_menu
    await message.answer(
        f"Ученик @{student_username} добавлен в класс '{class_name}'!",
        reply_markup=await get_user_menu(str(message.from_user.username))
    )
    await state.clear()


@dp.message(Command("give_assignment"))
async def give_assignment_start(message: types.Message, state: FSMContext):
    """Обработчик начала создания задания"""
    teacher_username = message.from_user.username
    
    # Проверяем права доступа
    if not await is_user_teacher(teacher_username):
        await message.answer("⛔ Только учителя могут создавать задания")
        return
    
    # Получаем классы учителя
    classes = await get_teacher_classes(teacher_username)
    
    if not classes:
        from school_bot.handlers.universal import get_user_menu
        await message.answer(
            "У вас нет классов. Сначала создайте класс.",
            reply_markup=await get_user_menu(str(message.from_user.username))
        )
        return
    
    # Сохраняем данные для последующих шагов
    await state.update_data(teacher_username=teacher_username)
    await state.set_state(TeacherStates.waiting_for_assignment_type)
    
    # Формируем список классов
    classes_list = "\n".join([f"- {class_name}" for class_name in classes])
    
    await message.answer(
        "Выберите тип задания:\n"
        "1. Для всего класса - введите название класса:\n"
        f"{classes_list}\n"
        "2. Индивидуальное - введите 'individual'",
        reply_markup=get_teacher_cancel_menu()
    )


@dp.message(TeacherStates.waiting_for_assignment_type)
async def process_assignment_type(message: types.Message, state: FSMContext):
    """Обрабатывает выбор типа задания (класс/индивидуальное)"""
    input_text = message.text.strip()
    teacher_username = message.from_user.username
    
    # Проверяем, не выбрано ли индивидуальное задание
    if input_text.lower() == "individual":
        await state.set_state(TeacherStates.waiting_for_student_selection)
        await state.update_data(assignment_type="individual")
        await message.answer("Введите @username ученика (без @):")
        return
    
    # Проверяем существование класса (регистронезависимо с сохранением оригинального названия)
    async with get_db_connection() as conn:
        original_class_name = await get_original_class_name(teacher_username, input_text)
        
        if original_class_name:
            await state.set_state(TeacherStates.waiting_for_assignment_text)
            await state.update_data(
                assignment_type="class",
                class_name=original_class_name
            )
            await message.answer(f"Введите текст задания для класса {original_class_name}:")
        else:
            # Получаем классы с правильным регистром названий
            available_classes = await get_teacher_classes(teacher_username)
            classes_list = "\n".join([f"- {class_name}" for class_name in available_classes])
            
            await message.answer(
                f"Класс '{input_text}' не найден. Доступные классы:\n{classes_list}\n\n"
                "Выберите класс из списка или введите:\n"
                "'individual' - для индивидуального задания\n"
                "'/cancel' - для отмены",
                reply_markup=get_teacher_cancel_menu()
            )


@dp.message(TeacherStates.waiting_for_student_selection)
async def process_student_selection(message: types.Message, state: FSMContext):
    """Обрабатывает выбор ученика для индивидуального задания"""
    student_username = message.text.strip().lower().replace("@", "")
    
    if await check_student_exists(student_username):
        await state.update_data(student_username=student_username)
        await state.set_state(TeacherStates.waiting_for_assignment_text)
        await message.answer("Введите текст индивидуального задания:")
    else:
        await message.answer("Ученик не найден. Проверьте username и попробуйте снова")


@dp.message(TeacherStates.waiting_for_assignment_text)
async def process_assignment_text(message: types.Message, state: FSMContext):
    """Обработчик текста задания (без создания дубликатов)"""
    assignment_text = message.text
    data = await state.get_data()
    teacher_username = message.from_user.username
    
    await state.update_data(assignment_text=assignment_text)
    
    try:
        # Только сохраняем данные, не создаем задание
        await message.answer(
            "Текст задания сохранён. Теперь можно прикрепить файл.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(TeacherStates.waiting_for_assignment_file)
        await message.answer(
            "Хотите прикрепить файл к заданию? (PDF, Word, изображение)\n"
            "Отправьте файл или нажмите <b>❌ Отмена</b> чтобы завершить",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Ошибка при обработке задания: {e}")
        from school_bot.handlers.universal import get_user_menu
        await message.answer(
            "Произошла ошибка при сохранении задания",
            reply_markup=await get_user_menu(str(message.from_user.username))
        )
        await state.clear()


@dp.message(
    TeacherStates.waiting_for_assignment_file,
    Command("skip")
)
async def skip_file_attachment(message: Message, state: FSMContext):
    await state.clear()
    from school_bot.handlers.universal import get_user_menu
    await message.answer("Задание опубликовано без файла", reply_markup=await get_user_menu(str(message.from_user.username)))


@dp.message(
    TeacherStates.waiting_for_assignment_file,
    ~F.document,
    ~F.photo
)
async def process_invalid_file(message: Message):
    await message.answer("Пожалуйста, отправьте файл (PDF, Word, изображение) или нажмите /skip")


async def get_file_info(message: Union[Document, PhotoSize]) -> Tuple[str, str, Optional[str]]:
    """Извлекает информацию о файле из сообщения"""
    if isinstance(message, Document):
        if message.file_size > MAX_FILE_SIZE:
            raise ValueError(f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE//1024//1024}MB")
        return message.file_id, "document", message.file_name
    else:  # Photo
        return message.file_id, "photo", None


async def notify_student_with_file(
    chat_id: int,
    text: str,
    file_id: str,
    file_type: str,
    caption: str
) -> Optional[int]:
    """Отправляет уведомление ученику с файлом"""
    try:
        msg = await bot.send_message(chat_id=chat_id, text=text)
        
        if file_type == "document":
            await bot.send_document(
                chat_id=chat_id,
                document=file_id,
                caption=caption,
                reply_to_message_id=msg.message_id
            )
        else:
            await bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=caption,
                reply_to_message_id=msg.message_id
            )
        
        return msg.message_id
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")
        return None


async def process_individual_assignment(
    conn: aiosqlite.Connection,
    teacher_username: str,
    student_username: str,
    assignment_text: str,
    file_id: str,
    file_type: str,
    file_name: Optional[str]
) -> None:
    """Обрабатывает индивидуальное задание"""
    await update_individual_assignment(
        conn,
        teacher_username,
        student_username,
        assignment_text,
        file_id,
        file_type,
        file_name
    )
    
    student_chat_id = await get_student_chat_id(conn, student_username)
    if not student_chat_id:
        return
    
    msg_id = await notify_student_with_file(
        chat_id=student_chat_id,
        text=f"📌 Новое индивидуальное задание (с файлом):\n{assignment_text}",
        file_id=file_id,
        file_type=file_type,
        caption="Прикрепленный файл к заданию"
    )
    
    if msg_id:
        await update_assignment_message_id(conn, msg_id, {
            'teacher_username': teacher_username,
            'student_username': student_username,
            'assignment_text': assignment_text
        })


async def process_class_assignment(
    conn: aiosqlite.Connection,
    teacher_username: str,
    class_name: str,
    assignment_text: str,
    file_id: Optional[str] = None,
    file_type: Optional[str] = None,
    file_name: Optional[str] = None
) -> None:
    """Обрабатывает задание для класса (без message_id)"""
    students = await get_students_in_class(conn, class_name)
    
    for student_username, student_chat_id in students:
        # Создаем задание в БД
        await create_class_assignment(
            conn,
            teacher_username,
            student_username,
            class_name,
            assignment_text,
            file_id,
            file_type,
            file_name
        )
        
        # Отправляем уведомление ученику
        if student_chat_id:
            try:
                if file_id:
                    if file_type == "document":
                        await bot.send_document(
                            chat_id=student_chat_id,
                            document=file_id,
                            caption=f"📌 Новое задание для класса {class_name}:\n{assignment_text}"
                        )
                    else:
                        await bot.send_photo(
                            chat_id=student_chat_id,
                            photo=file_id,
                            caption=f"📌 Новое задание для класса {class_name}:\n{assignment_text}"
                        )
                else:
                    await bot.send_message(
                        chat_id=student_chat_id,
                        text=f"📌 Новое задание для класса {class_name}:\n{assignment_text}"
                    )
            except Exception as e:
                print(f"Ошибка при отправке уведомления ученику {student_username}: {e}")


async def prepare_assignment_data(
    message: Message,
    state: FSMContext
) -> Optional[AssignmentData]:
    """Подготавливает данные для сохранения задания"""
    try:
        data = await state.get_data()
        file_content = message.document or message.photo[-1]
        file_id, file_type, file_name = await get_file_info(file_content)
        
        return AssignmentData(
            teacher_username=message.from_user.username,
            student_username=data.get("student_username"),
            assignment_text=data.get("assignment_text", ""),
            file_id=file_id,
            file_type=file_type,
            file_name=file_name,
            class_name=data.get("class_name")
        )
    except ValueError as e:
        await message.answer(str(e))
        return None


@dp.message(
    TeacherStates.waiting_for_assignment_file,
    F.document | F.photo
)
async def process_assignment_file(message: Message, state: FSMContext):
    """Окончательная обработка задания с файлом"""
    data = await state.get_data()
    teacher_username = message.from_user.username
    file_content = message.document or message.photo[-1]
    file_id, file_type, file_name = await get_file_info(file_content)
    
    async with get_db_connection() as conn:
        try:
            success = False
            
            if data["assignment_type"] == "individual":
                # Пытаемся обновить существующее
                updated = await update_individual_assignment(
                    conn,
                    teacher_username,
                    data["student_username"],
                    data["assignment_text"],
                    file_id,
                    file_type,
                    file_name
                )
                
                if not updated:
                    # Если не нашли для обновления, создаем новое
                    success = await create_individual_assignment(
                        conn,
                        teacher_username,
                        data["student_username"],
                        data["assignment_text"],
                        file_id,
                        file_type,
                        file_name
                    )
                else:
                    success = True
            else:
                # Для классного задания - проверяем функцию перед использованием
                try:
                    # Проверяем наличие необходимых параметров
                    required_params = ['class_name', 'assignment_text']
                    for param in required_params:
                        if param not in data:
                            raise ValueError(f"Отсутствует обязательный параметр: {param}")
                    
                    # Вызываем функцию с проверкой
                    await process_class_assignment(
                        conn,
                        teacher_username,
                        data["class_name"],
                        data["assignment_text"],
                        file_id,
                        file_type,
                        file_name
                    )
                    success = True
                except Exception as e:
                    print("Ошибка в process_class_assignment:")
                    print(f"Тип ошибки: {type(e).__name__}")
                    print(f"Аргументы: {e.args}")
                    print("Стек вызова:")
                    import traceback
                    traceback.print_exc()
                    raise  # Пробрасываем исключение дальше
            
            from school_bot.handlers.universal import get_user_menu
            if success:
                await conn.commit()
                await state.clear()
                await message.answer(
                    "✅ Задание успешно сохранено!",
                    reply_markup=await get_user_menu(str(message.from_user.username))
                )
            else:
                await message.answer(
                    "⚠️ Не удалось сохранить задание",
                    reply_markup=await get_user_menu(str(message.from_user.username))
                )
                
        except Exception as e:
            await conn.rollback()
            error_msg = [
                "⚠️ Критическая ошибка при сохранении задания",
                f"Тип: {type(e).__name__}",
                f"Сообщение: {str(e)}",
                "Стек вызова:",
                *traceback.format_tb(e.__traceback__)
            ]
            print("\n".join(error_msg))
            
            await message.answer(
                "⚠️ Произошла ошибка при сохранении задания\n"
                f"Тип: {type(e).__name__}\n"
                f"Ошибка: {str(e)}",
                reply_markup=await get_user_menu(str(message.from_user.username))
            )
            await state.clear()


def format_classes_response(classes: List[Tuple[str, Optional[str]]]) -> str:
    """Форматирует список классов для отображения"""
    if not classes:
        return "У вас пока нет классов."
    
    response = "🏫 <b>Ваши классы и ученики:</b>\n\n"
    for class_name, students_str in classes:
        response += f"<b>{class_name}</b>:\n"
        if students_str:
            students = students_str.split(', ')
            response += "\n".join([f"👤 @{username}" for username in students]) + "\n\n"
        else:
            response += "Нет учеников\n\n"
    return response


@dp.message(Command("view_classes"))
async def view_classes(message: types.Message):
    """Показывает список классов учителя с учениками"""
    teacher_username = message.from_user.username
    
    # Проверяем права доступа
    if not await is_user_teacher(teacher_username):
        await message.answer("⛔ Только учителя могут просматривать классы")
        return
    
    # Получаем и форматируем данные
    classes = await get_teacher_classes_with_students(teacher_username)
    
    if not classes:
        from school_bot.handlers.universal import get_user_menu
        await message.answer(
            "У вас пока нет классов.",
            reply_markup=await get_user_menu(str(message.from_user.username)),
            parse_mode="HTML"
        )
        return
    
    response = format_classes_response(classes)
    
    await message.answer(
        response,
        parse_mode="HTML",
        reply_markup=await get_user_menu(str(message.from_user.username))
    )