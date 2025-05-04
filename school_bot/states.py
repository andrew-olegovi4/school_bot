from aiogram.fsm.state import State, StatesGroup

class TeacherStates(StatesGroup):
    waiting_for_new_class_name = State()
    waiting_for_class_name = State()
    waiting_for_student_username = State()
    waiting_for_assignment_text = State()
    waiting_for_student_selection = State()
    waiting_for_assignment_type = State()
    waiting_for_assignment_file = State()
    viewing_student_work = State()
    waiting_for_new_teacher_username = State()

class StudentStates(StatesGroup):
    waiting_for_assignment_number = State()
    waiting_for_assignment_response = State()
    waiting_for_file_response = State()