from aiogram import types
from aiogram.filters import Command
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove

from school_bot.config import DIRECTOR_USERNAME
from school_bot.db.controllers import get_active_assignments, register_user
from school_bot.db.students import is_user_student
from school_bot.db.teachers import is_user_teacher
from school_bot.db.database import get_db_connection
from main import dp


@dp.message(Command("start"))
async def universal_start(message: types.Message):
    user = message.from_user
    
    if not user.username:
        await message.answer("⚠️ Для работы с ботом необходимо иметь username в Telegram.")
        return
    
    async with get_db_connection() as conn:
        is_teacher = await is_user_teacher(user.username, conn)
        is_director = user.username == DIRECTOR_USERNAME
        print(is_teacher, is_director)

        await register_user(conn, user.username, message.chat.id, is_teacher or is_director)
        
        if is_teacher or is_director:
            from school_bot.handlers.teacher import get_teacher_main_menu
            
            role = "директора" if is_director else "учителя"
            await message.answer(
                f"👔 <b>Панель {role}</b>\n\n"
                "Выберите действие из меню ниже:",
                reply_markup=get_teacher_main_menu(is_director=is_director),
                parse_mode="HTML"
            )
            return
        
        # Для учеников получаем активные задания
        active_assignments = await get_active_assignments(user.username, conn)
    
    # Формируем сообщение для ученика
    welcome_msg = "👨‍🎓 <b>Панель ученика</b>\n\n"
    
    if active_assignments:
        welcome_msg += f"🔔 У вас {len(active_assignments)} активных заданий:\n"
        for i, (_, text, _, assigned_at, _) in enumerate(active_assignments, 1):
            assignment_text = (text[:30] + '...') if len(text) > 30 else text
            welcome_msg += f"{i}. {assignment_text} (от {assigned_at[:10]})\n"
        welcome_msg += "\n"
    
    welcome_msg += "Выберите действие из меню ниже:"
    
    from school_bot.handlers.student import get_student_main_menu
    await message.answer(
        welcome_msg,
        reply_markup=get_student_main_menu(),
        parse_mode="HTML"
    )


@dp.message(F.text == "🔄 Обновить")
async def student_refresh_menu(message: types.Message):
    await universal_start(message)


async def get_user_menu(username: str) -> types.ReplyKeyboardMarkup:
    """
    Возвращает соответствующую клавиатуру меню для пользователя
    с учетом его роли (директор, учитель, ученик)
    
    Args:
        username: Telegram username пользователя (без @)
        
    Returns:
        ReplyKeyboardMarkup: Клавиатура меню или ReplyKeyboardRemove()
    """
    if not username:
        return types.ReplyKeyboardRemove()
    
    # Проверяем директора (самый частый случай)
    if username == DIRECTOR_USERNAME:
        from school_bot.handlers.teacher import get_teacher_main_menu
        return get_teacher_main_menu(is_director=True)
    
    async with get_db_connection() as conn:
        # Проверяем учителя (включая директора)
        is_teacher = await is_user_teacher(username, conn)
        if is_teacher:
            from school_bot.handlers.teacher import get_teacher_main_menu
            return get_teacher_main_menu(is_director=False)
        
        # Проверяем ученика
        is_student = await is_user_student(username, conn)
        if is_student:
            from school_bot.handlers.student import get_student_main_menu
            return get_student_main_menu()
    
    return types.ReplyKeyboardRemove()


@dp.message(F.text == "❌ Отмена")
async def universal_cancel_action(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено.",
        reply_markup=await get_user_menu(str(message.from_user.username))
    )