from aiogram.fsm.state import State, StatesGroup

class CreateEvent(StatesGroup):
    title = State()
    description = State()
    prize = State()
    datetime = State()
    media = State()
