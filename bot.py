import sqlite3
import matplotlib.pyplot as plt
from datetime import datetime
import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram.request import HTTPXRequest

TOKEN = os.environ.get('TELEGRAM_TOKEN')

if not TOKEN:
    print("❌ Ошибка: не найден токен")
    exit()

USE_PROXY = False

if USE_PROXY:
    request = HTTPXRequest(proxy_url="socks5://127.0.0.1:9050")
else:
    request = HTTPXRequest()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

# Состояния для ConversationHandler
WAITING_FOR_LOG = 1
WAITING_FOR_TARGET = 2
WAITING_FOR_EXERCISE_NAME = 3
WAITING_FOR_EXERCISE_DETAILS = 4
WAITING_FOR_EDIT_SELECT = 5
WAITING_FOR_EDIT_WEIGHT = 6
WAITING_FOR_EDIT_REPS_SETS = 7
WAITING_FOR_DELETE_SELECT = 8

# ==================== КНОПКИ ====================
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🏋️ Моя программа"), KeyboardButton("📊 Мой прогресс")],
        [KeyboardButton("📈 График"), KeyboardButton("🎯 Цель")],
        [KeyboardButton("📝 Записать тренировку"), KeyboardButton("✏️ Управление программой")],
        [KeyboardButton("ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_program_management_keyboard():
    keyboard = [
        [KeyboardButton("➕ Добавить упражнение")],
        [KeyboardButton("✏️ Редактировать упражнение")],
        [KeyboardButton("➖ Удалить упражнение")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_after_log_keyboard():
    keyboard = [
        [KeyboardButton("📝 Записать ещё"), KeyboardButton("📊 Мой прогресс")],
        [KeyboardButton("➕ Следующий вес"), KeyboardButton("🏋️ Моя программа")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    # Таблица для упражнений программы
    c.execute('''CREATE TABLE IF NOT EXISTS program
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  exercise_name TEXT,
                  weight REAL,
                  reps INTEGER,
                  sets INTEGER,
                  order_num INTEGER)''')
    # Таблица для тренировок (связь с упражнением)
    c.execute('''CREATE TABLE IF NOT EXISTS workouts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  exercise_name TEXT,
                  date TEXT,
                  weight REAL,
                  reps INTEGER,
                  sets INTEGER)''')
    # Таблица для целей
    c.execute('''CREATE TABLE IF NOT EXISTS goals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  target_weight REAL,
                  exercise_name TEXT,
                  set_date TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_user_id(update):
    return update.effective_user.id

def get_program(user_id):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT exercise_name, weight, reps, sets, order_num FROM program WHERE user_id = ? ORDER BY order_num", (user_id,))
    data = c.fetchall()
    conn.close()
    return data

def add_exercise(user_id, name, weight, reps, sets):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT MAX(order_num) FROM program WHERE user_id = ?", (user_id,))
    max_order = c.fetchone()[0] or 0
    order_num = max_order + 1
    c.execute("INSERT INTO program (user_id, exercise_name, weight, reps, sets, order_num) VALUES (?, ?, ?, ?, ?, ?)",
              (user_id, name, weight, reps, sets, order_num))
    conn.commit()
    conn.close()

def update_exercise_weight(user_id, order_num, new_weight):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("UPDATE program SET weight = ? WHERE user_id = ? AND order_num = ?", (new_weight, user_id, order_num))
    conn.commit()
    conn.close()

def update_exercise_reps_sets(user_id, order_num, new_reps, new_sets):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("UPDATE program SET reps = ?, sets = ? WHERE user_id = ? AND order_num = ?", (new_reps, new_sets, user_id, order_num))
    conn.commit()
    conn.close()

def delete_exercise(user_id, order_num):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("DELETE FROM program WHERE user_id = ? AND order_num = ?", (user_id, order_num))
    # Перенумеруем оставшиеся
    c.execute("SELECT id, order_num FROM program WHERE user_id = ? ORDER BY order_num", (user_id,))
    exercises = c.fetchall()
    for i, (id_, old_order) in enumerate(exercises):
        c.execute("UPDATE program SET order_num = ? WHERE id = ?", (i + 1, id_))
    conn.commit()
    conn.close()

def save_workout(user_id, exercise_name, weight, reps, sets):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO workouts (user_id, exercise_name, date, weight, reps, sets) VALUES (?, ?, ?, ?, ?, ?)",
              (user_id, exercise_name, date, weight, reps, sets))
    conn.commit()
    conn.close()

def get_workouts(user_id, exercise_name):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT date, weight, reps, sets FROM workouts WHERE user_id = ? AND exercise_name = ? ORDER BY date", 
              (user_id, exercise_name))
    data = c.fetchall()
    conn.close()
    return data

def get_all_workouts(user_id):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT exercise_name, date, weight, reps, sets FROM workouts WHERE user_id = ? ORDER BY date", (user_id,))
    data = c.fetchall()
    conn.close()
    return data

def calculate_1rm(weight, reps, sets):
    if sets >= 4 and reps >= 4:
        return round(weight * 1.2, 1)
    else:
        return round(weight / (1.0278 - 0.0278 * reps), 1)

def create_chart(user_id, exercise_name):
    data = get_workouts(user_id, exercise_name)
    if not data:
        return None
    dates = []
    weights = []
    for row in data:
        date = row[0][:10]
        if date not in dates:
            dates.append(date)
            weights.append(row[1])
    plt.figure(figsize=(10, 5))
    plt.plot(dates, weights, marker='o', linewidth=2, color='blue')
    plt.title(f'Динамика: {exercise_name}', fontsize=16)
    plt.xlabel('Дата', fontsize=12)
    plt.ylabel('Вес (кг)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('progress.png')
    plt.close()
    return 'progress.png'

def set_goal(user_id, exercise_name, weight):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d")
    c.execute("DELETE FROM goals WHERE user_id = ? AND exercise_name = ?", (user_id, exercise_name))
    c.execute("INSERT INTO goals (user_id, target_weight, exercise_name, set_date) VALUES (?, ?, ?, ?)", 
              (user_id, weight, exercise_name, date))
    conn.commit()
    conn.close()

def get_goal(user_id, exercise_name):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT target_weight FROM goals WHERE user_id = ? AND exercise_name = ? ORDER BY id DESC LIMIT 1", 
              (user_id, exercise_name))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def get_last_workout(user_id, exercise_name):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT weight, reps, sets FROM workouts WHERE user_id = ? AND exercise_name = ? ORDER BY id DESC LIMIT 1", 
              (user_id, exercise_name))
    result = c.fetchone()
    conn.close()
    return result if result else None

# ==================== КОМАНДЫ ====================
async def start(update: Update, context: CallbackContext):
    user_id = get_user_id(update)
    program = get_program(user_id)
    
    if not program:
        await update.message.reply_text(
            "🏋️‍♂️ *Добро пожаловать в силовой тренер!*\n\n"
            "📭 *Твоя программа пуста*\n\n"
            "Нажми *✏️ Управление программой* → *➕ Добавить упражнение*\n\n"
            "👇 Нажми на кнопку:",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "🏋️‍♂️ *Твой силовой тренер*\n\n"
            "👇 Нажми на кнопку:",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )

async def show_program(update: Update, context: CallbackContext):
    user_id = get_user_id(update)
    program = get_program(user_id)
    
    if not program:
        await update.message.reply_text(
            "📭 *Твоя программа пуста*\n\n"
            "Нажми *✏️ Управление программой* → *➕ Добавить упражнение*",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        return
    
    text = "🏋️ *Моя программа:*\n\n"
    for i, (name, weight, reps, sets, order) in enumerate(program, 1):
        text += f"{i}. *{name}* — {weight} кг × {sets}×{reps}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_main_keyboard())

# ==================== УПРАВЛЕНИЕ ПРОГРАММОЙ ====================
async def program_management(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "✏️ *Управление программой*\n\n"
        "Выбери действие:",
        parse_mode='Markdown',
        reply_markup=get_program_management_keyboard()
    )

async def add_exercise_start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "➕ *Добавить упражнение*\n\n"
        "Введи название упражнения\n"
        "Например: `Жим лёжа`\n\n"
        "Для отмены введи /cancel",
        parse_mode='Markdown'
    )
    return WAITING_FOR_EXERCISE_NAME

async def get_exercise_name(update: Update, context: CallbackContext):
    name = update.message.text
    context.user_data['temp_exercise'] = {'name': name}
    await update.message.reply_text(
        f"📝 *{name}*\n\n"
        "Введи: *вес, повторы, подходы*\n"
        "Например: `65 5 5`",
        parse_mode='Markdown'
    )
    return WAITING_FOR_EXERCISE_DETAILS

async def get_exercise_details(update: Update, context: CallbackContext):
    try:
        parts = update.message.text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Нужно три числа. Пример: `65 5 5`", parse_mode='Markdown')
            return WAITING_FOR_EXERCISE_DETAILS
        
        weight = float(parts[0])
        reps = int(parts[1])
        sets = int(parts[2])
        
        user_id = get_user_id(update)
        name = context.user_data['temp_exercise']['name']
        add_exercise(user_id, name, weight, reps, sets)
        
        await update.message.reply_text(
            f"✅ *{name}* добавлен в программу!",
            parse_mode='Markdown',
            reply_markup=get_program_management_keyboard()
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Ошибка. Пример: `65 5 5`", parse_mode='Markdown')
        return WAITING_FOR_EXERCISE_DETAILS

async def edit_exercise_select(update: Update, context: CallbackContext):
    user_id = get_user_id(update)
    program = get_program(user_id)
    
    if not program:
        await update.message.reply_text("📭 Программа пуста. Сначала добавь упражнения", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    
    text = "✏️ *Какое упражнение редактировать?*\n\n"
    buttons = []
    for i, (name, weight, reps, sets, order) in enumerate(program, 1):
        text += f"{i}. {name} — {weight} кг × {sets}×{reps}\n"
        buttons.append([InlineKeyboardButton(f"✏️ {name}", callback_data=f"edit_{order}")])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_management")])
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(buttons))
    return WAITING_FOR_EDIT_SELECT

async def edit_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("edit_"):
        order_num = int(query.data.split("_")[1])
        context.user_data['edit_order'] = order_num
        
        program = get_program(query.from_user.id)
        exercise = None
        for name, weight, reps, sets, order in program:
            if order == order_num:
                exercise = (name, weight, reps, sets)
                break
        
        if exercise:
            keyboard = [
                [InlineKeyboardButton("🏋️ Изменить вес", callback_data=f"edit_weight_{order_num}")],
                [InlineKeyboardButton("📊 Изменить повторы/подходы", callback_data=f"edit_reps_{order_num}")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back_to_edit")]
            ]
            await query.message.reply_text(
                f"✏️ *{exercise[0]}*\n\n"
                f"Текущий вес: {exercise[1]} кг\n"
                f"Текущая схема: {exercise[3]}×{exercise[2]}\n\n"
                f"Что хочешь изменить?",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return WAITING_FOR_EDIT_SELECT
    
    elif query.data.startswith("edit_weight_"):
        order_num = int(query.data.split("_")[2])
        context.user_data['edit_order'] = order_num
        await query.message.reply_text("🏋️ *Введи новый вес (кг):*", parse_mode='Markdown')
        return WAITING_FOR_EDIT_WEIGHT
    
    elif query.data
    
