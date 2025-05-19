from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Аккаунт"), KeyboardButton(text="🎯 События")],
        [KeyboardButton(text="📩 Связь"), KeyboardButton(text="🎟️ Промокоды"), KeyboardButton(text="⚙️ Управление")]
    ],
    resize_keyboard=True
)

back_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="◀️ Назад")]
    ],
    resize_keyboard=True
)
