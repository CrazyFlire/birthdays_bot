import asyncio
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Вставьте ваш токен в кавычки ниже:
API_TOKEN = '8947789741:AAGTwMkWzgvXgpT8SiQaCqVWQBEDbrqKQh8'

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    conn = sqlite3.connect('birthdays.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            bday_day INTEGER,
            bday_month INTEGER
        )
    ''')
    conn.commit()
    conn.close()

init_db()

class AddContact(StatesGroup):
    name = State()
    date = State()

class DeleteContact(StatesGroup):
    name = State()

# Главное меню с кнопками
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить день рождения")],
        [KeyboardButton(text="📋 Мой список"), KeyboardButton(text="❌ Удалить контакт")],
    ],
    resize_keyboard=True
)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я помогу не забыть о днях рождения близких.\n"
        "За 4 часа до наступления дня рождения я пришлю вам напоминание!",
        reply_markup=main_kb
    )

@dp.message(F.text == "➕ Добавить день рождения")
async def add_start(message: Message, state: FSMContext):
    await message.answer("Введите имя человека:")
    await state.set_state(AddContact.name)

@dp.message(AddContact.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Теперь введите дату рождения в формате ДД.ММ (например: 15.05):")
    await state.set_state(AddContact.date)

@dp.message(AddContact.date)
async def process_date(message: Message, state: FSMContext):
    try:
        day, month = map(int, message.text.strip().split('.'))
        if not (1 <= day <= 31 and 1 <= month <= 12):
            raise ValueError
    except ValueError:
        await message.answer("Неверный формат! Введите дату в формате ДД.ММ (например: 15.05):")
        return

    data = await state.get_data()
    name = data['name']
    
    conn = sqlite3.connect('birthdays.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO contacts (user_id, name, bday_day, bday_month) VALUES (?, ?, ?, ?)',
        (message.from_user.id, name, day, month)
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(f"✅ Успешно сохранено: {name} ({day:02d}.{month:02d})", reply_markup=main_kb)

@dp.message(F.text == "📋 Мой список")
async def list_contacts(message: Message):
    conn = sqlite3.connect('birthdays.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT name, bday_day, bday_month FROM contacts WHERE user_id = ? ORDER BY bday_month, bday_day',
        (message.from_user.id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("У вас пока нет сохраненных дней рождения.")
        return

    text = "🗓 **Ваши контакты:**\n\n"
    for name, day, month in rows:
        text += f"• {name} — {day:02d}.{month:02d}\n"
    
    await message.answer(text, parse_mode="Markdown")

# --- Логика удаления контактов ---

@dp.message(F.text == "❌ Удалить контакт")
async def delete_start(message: Message, state: FSMContext):
    conn = sqlite3.connect('birthdays.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT name FROM contacts WHERE user_id = ?',
        (message.from_user.id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("У вас нет сохраненных контактов для удаления.")
        return

    await message.answer("Введите точное имя человека, которого хотите удалить из списка:")
    await state.set_state(DeleteContact.name)

@dp.message(DeleteContact.name)
async def process_delete(message: Message, state: FSMContext):
    target_name = message.text.strip()

    conn = sqlite3.connect('birthdays.db')
    cursor = conn.cursor()
    
    # Проверяем наличие контакта
    cursor.execute(
        'SELECT id FROM contacts WHERE user_id = ? AND name = ?',
        (message.from_user.id, target_name)
    )
    contact = cursor.fetchone()

    if not contact:
        await message.answer(f"Контакт с именем «{target_name}» не найден. Попробуйте еще раз или нажмите /start.")
        await state.clear()
        conn.close()
        return

    # Удаляем запись из базы данных
    cursor.execute(
        'DELETE FROM contacts WHERE user_id = ? AND name = ?',
        (message.from_user.id, target_name)
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(f"🗑 Контакт «{target_name}» успешно удален!", reply_markup=main_kb)

# --- Цикл проверки дней рождения ---

async def check_birthdays_loop():
    while True:
        now = datetime.now()
        target_time = now + timedelta(hours=4)
        
        if target_time.hour == 20:
            target_day = (now + timedelta(days=1)).day
            target_month = (now + timedelta(days=1)).month

            conn = sqlite3.connect('birthdays.db')
            cursor = conn.cursor()
            cursor.execute(
                'SELECT user_id, name FROM contacts WHERE bday_day = ? AND bday_month = ?',
                (target_day, target_month)
            )
            matches = cursor.fetchall()
            conn.close()

            for user_id, name in matches:
                try:
                    await bot.send_message(
                        user_id, 
                        f"⏰ **Напоминание!**\n\nЧерез 4 часа (завтра) день рождения у: **{name}**! 🎉"
                    )
                except Exception as e:
                    print(f"Ошибка отправки пользователю {user_id}: {e}")

        await asyncio.sleep(3600)

async def main():
    asyncio.create_task(check_birthdays_loop())
    print("Бот успешно запущен с функцией удаления!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())