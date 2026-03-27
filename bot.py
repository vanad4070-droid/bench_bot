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

# Состояния
WAITING_FOR_BODYWEIGHT = 1
WAITING_FOR_BENCH = 2
WAITING_FOR_LEGPRESS = 3
WAITING_FOR_SQUAT = 4
WAITING_FOR_LOG = 10
WAITING_FOR_TARGET = 11
WAITING_FOR_EXERCISE_NAME = 12
WAITING_FOR_EXERCISE_DETAILS = 13
WAITING_FOR_EDIT_SELECT = 14
WAITING_FOR_EDIT_WEIGHT = 15
WAITING_FOR_EDIT_REPS_SETS = 16
WAITING_FOR_DELETE_SELECT = 17
WAITING_FOR_CUSTOM_EXERCISE_NAME = 18
WAITING_FOR_CUSTOM_EXERCISE_VALUE = 19
WAITING_FOR_TARGET_SELECT = 20
WAITING_FOR_TARGET_VALUE = 21
WAITING_FOR_PROGRESS_SELECT = 22

# ==================== КНОПКИ ====================
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🏋️ Моя программа"), KeyboardButton("📊 Мой прогресс")],
        [KeyboardButton("📈 График"), KeyboardButton("🎯 Мои цели")],
        [KeyboardButton("📝 Записать тренировку"), KeyboardButton("⚙️ Мои показатели")],
        [KeyboardButton("✏️ Управление программой"), KeyboardButton("ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_stats_keyboard():
    keyboard = [
        [KeyboardButton("📊 Посмотреть показатели")],
        [KeyboardButton("✏️ Редактировать показатель")],
        [KeyboardButton("➕ Добавить свой показатель")],
        [KeyboardButton("🔙 Назад")]
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
    c.execute('''CREATE TABLE IF NOT EXISTS user_stats
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  stat_name TEXT,
                  current_value REAL,
                  updated_date TEXT,
                  UNIQUE(user_id, stat_name))''')
    c.execute('''CREATE TABLE IF NOT EXISTS program
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  exercise_name TEXT,
                  weight REAL,
                  reps INTEGER,
                  sets INTEGER,
                  order_num INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workouts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  exercise_name TEXT,
                  date TEXT,
                  weight REAL,
                  reps INTEGER,
                  sets INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS goals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  target_weight REAL,
                  stat_name TEXT,
                  set_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_profile
                 (user_id INTEGER PRIMARY KEY,
                  is_onboarded INTEGER DEFAULT 0,
                  onboarded_date TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_user_id(update):
    return update.effective_user.id

def is_onboarded(user_id):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT is_onboarded FROM user_profile WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == 1

def set_onboarded(user_id):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO user_profile (user_id, is_onboarded, onboarded_date) VALUES (?, 1, ?)",
              (user_id, date))
    conn.commit()
    conn.close()

def save_user_stat(user_id, stat_name, value):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT OR REPLACE INTO user_stats (user_id, stat_name, current_value, updated_date) VALUES (?, ?, ?, ?)",
              (user_id, stat_name, value, date))
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT stat_name, current_value, updated_date FROM user_stats WHERE user_id = ? ORDER BY stat_name", (user_id,))
    data = c.fetchall()
    conn.close()
    return data

def get_user_stat(user_id, stat_name):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT current_value FROM user_stats WHERE user_id = ? AND stat_name = ?", (user_id, stat_name))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

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

def calculate_1rm(weight, reps, sets):
    if sets >= 4 and reps >= 4:
        return round(weight * 1.2, 1)
    else:
        return round(weight / (1.0278 - 0.0278 * reps), 1)

def create_chart(user_id, stat_name):
    data = get_workouts(user_id, stat_name)
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
    plt.title(f'Динамика: {stat_name}', fontsize=16)
    plt.xlabel('Дата', fontsize=12)
    plt.ylabel('Вес (кг)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('progress.png')
    plt.close()
    return 'progress.png'

def set_goal(user_id, stat_name, weight):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d")
    c.execute("DELETE FROM goals WHERE user_id = ? AND stat_name = ?", (user_id, stat_name))
    c.execute("INSERT INTO goals (user_id, target_weight, stat_name, set_date) VALUES (?, ?, ?, ?)", 
              (user_id, weight, stat_name, date))
    conn.commit()
    conn.close()

def get_goal(user_id, stat_name):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT target_weight FROM goals WHERE user_id = ? AND stat_name = ? ORDER BY id DESC LIMIT 1", 
              (user_id, stat_name))
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

# ==================== ФУНКЦИЯ START ====================
async def start(update: Update, context: CallbackContext):
    user_id = get_user_id(update)
    
    if is_onboarded(user_id):
        await update.message.reply_text(
            "🏋️‍♂️ *С возвращением!*\n\n"
            "👇 Нажми на кнопку:",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    else:
        await onboard_user(update, context)

# ==================== АНКЕТА ====================
async def onboard_user(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🏋️‍♂️ *Давай познакомимся!*\n\n"
        "Я помогу тебе отслеживать прогресс и достигать целей.\n\n"
        "Для начала укажи свой *вес тела (кг)*:",
        parse_mode='Markdown'
    )
    return WAITING_FOR_BODYWEIGHT

async def get_bodyweight(update: Update, context: CallbackContext):
    try:
        bodyweight = float(update.message.text)
        user_id = get_user_id(update)
        save_user_stat(user_id, "Вес тела", bodyweight)
        await update.message.reply_text(
            f"✅ Вес тела: {bodyweight} кг\n\n"
            "Теперь укажи свой *жим лёжа (на раз, кг)*:",
            parse_mode='Markdown'
        )
        return WAITING_FOR_BENCH
    except:
        await update.message.reply_text("❌ Введи число, например: `70`", parse_mode='Markdown')
        return WAITING_FOR_BODYWEIGHT

async def get_bench(update: Update, context: CallbackContext):
    try:
        bench = float(update.message.text)
        user_id = get_user_id(update)
        save_user_stat(user_id, "Жим лёжа", bench)
        await update.message.reply_text(
            f"✅ Жим лёжа: {bench} кг\n\n"
            "Теперь укажи свой *жим ногами (на раз, кг)*:",
            parse_mode='Markdown'
        )
        return WAITING_FOR_LEGPRESS
    except:
        await update.message.reply_text("❌ Введи число, например: `100`", parse_mode='Markdown')
        return WAITING_FOR_BENCH

async def get_legpress(update: Update, context: CallbackContext):
    try:
        legpress = float(update.message.text)
        user_id = get_user_id(update)
        save_user_stat(user_id, "Жим ногами", legpress)
        await update.message.reply_text(
            f"✅ Жим ногами: {legpress} кг\n\n"
            "Теперь укажи свой *присед со штангой (на раз, кг)*:",
            parse_mode='Markdown'
        )
        return WAITING_FOR_SQUAT
    except:
        await update.message.reply_text("❌ Введи число, например: `80`", parse_mode='Markdown')
        return WAITING_FOR_LEGPRESS

async def get_squat(update: Update, context: CallbackContext):
    try:
        squat = float(update.message.text)
        user_id = get_user_id(update)
        save_user_stat(user_id, "Присед", squat)
        set_onboarded(user_id)
        
        await update.message.reply_text(
            f"✅ *Анкета заполнена!*\n\n"
            f"📊 *Твои показатели:*\n"
            f"• Вес тела: {get_user_stat(user_id, 'Вес тела')} кг\n"
            f"• Жим лёжа: {get_user_stat(user_id, 'Жим лёжа')} кг\n"
            f"• Жим ногами: {get_user_stat(user_id, 'Жим ногами')} кг\n"
            f"• Присед: {get_user_stat(user_id, 'Присед')} кг\n\n"
            "Теперь можешь:\n"
            "• Создать программу тренировок\n"
            "• Отслеживать прогресс\n"
            "• Ставить цели\n\n"
            "👇 Нажми на кнопку:",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введи число, например: `80`", parse_mode='Markdown')
        return WAITING_FOR_SQUAT

# ==================== ПОКАЗАТЕЛИ ====================
async def show_stats(update: Update, context: CallbackContext):
    user_id = get_user_id(update)
    stats = get_user_stats(user_id)
    
    if not stats:
        await update.message.reply_text(
            "📭 *Показатели не найдены*\n\n"
            "Нажми *⚙️ Мои показатели* → *➕ Добавить свой показатель*",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        return
    
    text = "📊 *Мои показатели:*\n\n"
    for stat_name, value, date in stats:
        goal = get_goal(user_id, stat_name)
        text += f"• *{stat_name}*: {value} кг"
        if goal:
            text += f" (цель: {goal} кг)"
        text += f"\n   📅 {date[:10]}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_stats_keyboard())

async def edit_stat_select(update: Update, context: CallbackContext):
    user_id = get_user_id(update)
    stats = get_user_stats(user_id)
    
    if not stats:
        await update.message.reply_text("📭 Нет показателей для редактирования", reply_markup=get_main_keyboard())
        return
    
    text = "✏️ *Какой показатель редактировать?*\n\n"
    buttons = []
    for stat_name, value, date in stats:
        buttons.append([InlineKeyboardButton(f"✏️ {stat_name}", callback_data=f"edit_stat_{stat_name}")])
    buttons.append([InlineKeyboardButton("➕ Добавить новый", callback_data="add_stat")])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_stats")])
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(buttons))

async def edit_stat_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("edit_stat_"):
        stat_name = query.data.replace("edit_stat_", "")
        context.user_data['edit_stat'] = stat_name
        await query.message.reply_text(
            f"✏️ *{stat_name}*\n\n"
            f"Текущее значение: {get_user_stat(query.from_user.id, stat_name)} кг\n\n"
            "Введи новое значение (кг):",
            parse_mode='Markdown'
        )
        return WAITING_FOR_EDIT_WEIGHT
    elif query.data == "add_stat":
        await query.message.reply_text(
            "➕ *Добавить свой показатель*\n\n"
            "Введи название показателя\n"
            "Например: `Становая тяга`\n\n"
            "Для отмены введи /cancel",
            parse_mode='Markdown'
        )
        return WAITING_FOR_CUSTOM_EXERCISE_NAME
    elif query.data == "back_to_stats":
        await query.message.reply_text("🔙 Назад", reply_markup=get_stats_keyboard())
        return ConversationHandler.END

async def edit_stat_value(update: Update, context: CallbackContext):
    try:
        new_value = float(update.message.text)
        user_id = get_user_id(update)
        stat_name = context.user_data['edit_stat']
        save_user_stat(user_id, stat_name, new_value)
        
        await update.message.reply_text(
            f"✅ *{stat_name}* обновлён! Новое значение: {new_value} кг",
            parse_mode='Markdown',
            reply_markup=get_stats_keyboard()
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введи число, например: `100`", parse_mode='Markdown')
        return WAITING_FOR_EDIT_WEIGHT

async def add_custom_stat(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "➕ *Добавить свой показатель*\n\n"
        "Введи название показателя\n"
        "Например: `Становая тяга` или `Тяга штанги`\n\n"
        "Для отмены введи /cancel",
        parse_mode='Markdown'
    )
    return WAITING_FOR_CUSTOM_EXERCISE_NAME

async def get_custom_stat_name(update: Update, context: CallbackContext):
    name = update.message.text
    context.user_data['custom_stat'] = {'name': name}
    await update.message.reply_text(
        f"📝 *{name}*\n\n"
        "Введи текущее значение (кг):\n"
        "Например: `100`",
        parse_mode='Markdown'
    )
    return WAITING_FOR_CUSTOM_EXERCISE_VALUE

async def get_custom_stat_value(update: Update, context: CallbackContext):
    try:
        value = float(update.message.text)
        user_id = get_user_id(update)
        name = context.user_data['custom_stat']['name']
        save_user_stat(user_id, name, value)
        
        await update.message.reply_text(
            f"✅ *{name}* добавлен! Текущее значение: {value} кг",
            parse_mode='Markdown',
            reply_markup=get_stats_keyboard()
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введи число, например: `100`", parse_mode='Markdown')
        return WAITING_FOR_CUSTOM_EXERCISE_VALUE

# ==================== ЦЕЛИ ====================
async def show_goals(update: Update, context: CallbackContext):
    user_id = get_user_id(update)
    stats = get_user_stats(user_id)
    
    if not stats:
        await update.message.reply_text(
            "📭 *Нет показателей*\n\n"
            "Сначала добавь показатели в *⚙️ Мои показатели*",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        return
    
    text = "🎯 *Мои цели:*\n\n"
    for stat_name, value, date in stats:
        goal = get_goal(user_id, stat_name)
        if goal:
            remaining = goal - value
            text += f"• *{stat_name}*: {value} кг → цель {goal} кг"
            if remaining > 0:
                text += f" (осталось {remaining:.1f} кг)\n"
            else:
                text += f" ✅ Достигнута!\n"
        else:
            text += f"• *{stat_name}*: {value} кг → цель не установлена\n"
    
    text += "\nЧтобы установить цель, нажми *🎯 Мои цели* и выбери показатель."
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_main_keyboard())

async def set_goal_select(update: Update, context: CallbackContext):
    user_id = get_user_id(update)
    stats = get_user_stats(user_id)
    
    if not stats:
        await update.message.reply_text("📭 Нет показателей", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    
    text = "🎯 *Для какого показателя установить цель?*\n\n"
    buttons = []
    for stat_name, value, date in stats:
        buttons.append([InlineKeyboardButton(f"🎯 {stat_name} (сейчас {value} кг)", callback_data=f"set_goal_{stat_name}")])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(buttons))
    return WAITING_FOR_TARGET_SELECT

async def goal_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("set_goal_"):
        stat_name = query.data.replace("set_goal_", "")
        context.user_data['goal_stat'] = stat_name
        await query.message.reply_text(
            f"🎯 *{stat_name}*\n\n"
            f"Текущее значение: {get_user_stat(query.from_user.id, stat_name)} кг\n\n"
            "Введи целевую цифру (кг):\n"
            "Например: `100`\n\n"
            "Или нажми /cancel для отмены",
            parse_mode='Markdown'
        )
        return WAITING_FOR_TARGET_VALUE
    elif query.data == "back_to_menu":
        await query.message.reply_text("🔙 Возврат", reply_markup=get_main_keyboard())
        return ConversationHandler.END

async def set_goal_value(update: Update, context: CallbackContext):
    try:
        target = float(update.message.text)
        user_id = get_user_id(update)
        stat_name = context.user_data.get('goal_stat')
        
        if not stat_name:
            await update.message.reply_text("❌ Что-то пошло не так. Попробуй снова через /goals", reply_markup=get_main_keyboard())
            return ConversationHandler.END
        
        set_goal(user_id, stat_name, target)
        current = get_user_stat(user_id, stat_name)
        
        await update.message.reply_text(
            f"✅ *Цель установлена!*\n\n"
            f"• {stat_name}: {current} кг → {target} кг\n"
            f"💪 Осталось: {target - current:.1f} кг",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        context.user_data.pop('goal_stat', None)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введи число, например: `100`", parse_mode='Markdown')
        return WAITING_FOR_TARGET_VALUE
    except Exception as e:
        await update.message.reply_text("❌ Ошибка. Попробуй ещё раз", reply_markup=get_main_keyboard())
        return ConversationHandler.END

# ==================== ПРОГРЕСС ====================
async def show_progress(update: Update, context: CallbackContext):
    user_id = get_user_id(update)
    stats = get_user_stats(user_id)
    
    if not stats:
        await update.message.reply_text(
            "📭 *Нет данных*\n\n"
            "Сначала заполни анкету и записывай тренировки",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        return
    
    text = "📊 *Мой прогресс:*\n\n"
    for stat_name, value, date in stats:
        last = get_last_workout(user_id, stat_name)
        if last:
            one_rm = calculate_1rm(last[0], last[1], last[2])
            text += f"• *{stat_name}*: последний результат {last[0]} кг × {last[2]}×{last[1]} → 1ПМ = {one_rm} кг\n"
        else:
            text += f"• *{stat_name}*: {value} кг (начальный)\n"
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_main_keyboard())

async def show_chart_select(update: Update, context: CallbackContext):
    user_id = get_user_id(update)
    stats = get_user_stats(user_id)
    
    if not stats:
        await update.message.reply_text("📭 Нет данных", reply_markup=get_main_keyboard())
        return
    
    text = "📈 *График для какого показателя?*\n\n"
    buttons = []
    for stat_name, value, date in stats:
        buttons.append([InlineKeyboardButton(f"📈 {stat_name}", callback_data=f"chart_{stat_name}")])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(buttons))
    return WAITING_FOR_PROGRESS_SELECT

async def chart_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("chart_"):
        stat_name = query.data.replace("chart_", "")
        await query.message.reply_text(f"📊 Строю график для *{stat_name}*...", parse_mode='Markdown')
        chart_file = create_chart(query.from_user.id, stat_name)
        if chart_file:
            with open(chart_file, 'rb') as f:
                await query.message.reply_photo(f, caption=f"📈 Динамика: {stat_name}", reply_markup=get_main_keyboard())
        else:
            await query.message.reply_text(f"❌ Недостаточно данных для {stat_name}", reply_markup=get_main_keyboard())
    elif query.data == "back_to_menu":
        await query.message.reply_text("🔙 Возврат", reply_markup=get_main_keyboard())
    return ConversationHandler.END

# ==================== ПРОГРАММА ТРЕНИРОВОК ====================
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

# ==================== ЗАПИСЬ ТРЕНИРОВКИ ====================
async def start_log(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📝 *Запись тренировки*\n\n"
        "Введи: *название, вес, повторы, подходы*\n"
        "Например: `Жим лёжа 65 5 5`\n\n"
        "Для отмены введи /cancel",
        parse_mode='Markdown'
    )
    return WAITING_FOR_LOG

async def handle_log(update: Update, context: CallbackContext):
    try:
        parts = update.message.text.split()
        if len(parts) < 4:
            await update.message.reply_text("❌ Нужно 4 параметра. Пример: `Жим лёжа 65 5 5`", parse_mode='Markdown')
            return WAITING_FOR_LOG
        
        if len(parts) > 4:
            exercise_name = " ".join(parts[:-3])
            weight = float(parts[-3])
            reps = int(parts[-2])
            sets = int(parts[-1])
        else:
            exercise_name = parts[0]
            weight = float(parts[1])
            reps = int(parts[2])
            sets = int(parts[3])
        
        user_id = get_user_id(update)
        save_workout(user_id, exercise_name, weight, reps, sets)
        one_rm = calculate_1rm(weight, reps, sets)
        
        current = get_user_stat(user_id, exercise_name)
        if not current or weight > current:
            save_user_stat(user_id, exercise_name, weight)
        
        goal = get_goal(user_id, exercise_name)
        goal_text = ""
        if goal:
            remaining = goal - one_rm
            if remaining > 0:
                goal_text = f"\n🎯 До цели {goal} кг осталось: {remaining:.1f} кг"
            else:
                goal_text = f"\n🎉 Поздравляю! Ты достиг цели {goal} кг!"
        
        await update.message.reply_text(
            f"✅ *Записано:* {exercise_name} — {weight} кг × {sets}×{reps}\n"
            f"📈 Расчётный максимум (1ПМ): *{one_rm} кг*{goal_text}",
            parse_mode='Markdown',
            reply_markup=get_after_log_keyboard()
        )
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка. Пример: `Жим лёжа 65 5 5`", parse_mode='Markdown')
        return WAITING_FOR_LOG

# ==================== ОСТАЛЬНЫЕ КОМАНДЫ ====================
async def next_weight_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📈 *Следующий вес*\n\n"
        "Сначала запиши тренировку, чтобы я мог рассчитать следующий вес",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🏋️‍♂️ *Помощь*\n\n"
        "📋 *Основные команды:*\n"
        "/start — начать работу\n"
        "/program — показать программу\n"
        "/log — записать тренировку\n"
        "/progress — прогресс\n"
        "/chart — график\n"
        "/stats — мои показатели\n"
        "/goals — мои цели\n"
        "/help — помощь\n\n"
        "👇 Или нажимай на кнопки внизу экрана!",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("❌ Действие отменено", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def handle_text(update: Update, context: CallbackContext):
    text = update.message.text
    
    if text == "🏋️ Моя программа":
        await show_program(update, context)
    elif text == "📊 Мой прогресс":
        await show_progress(update, context)
    elif text == "📈 График":
        await show_chart_select(update, context)
    elif text == "🎯 Мои цели":
        await show_goals(update, context)
    elif text == "📝 Записать тренировку":
        await start_log(update, context)
    elif text == "⚙️ Мои показатели":
        await show_stats(update, context)
    elif text == "✏️ Управление программой":
        await program_management(update, context)
    elif text == "➕ Добавить упражнение":
        await add_exercise_start(update, context)
    elif text == "📊 Посмотреть показатели":
        await show_stats(update, context)
    elif text == "✏️ Редактировать показатель":
        await edit_stat_select(update, context)
    elif text == "➕ Добавить свой показатель":
        await add_custom_stat(update, context)
    elif text == "🔙 Назад":
        await update.message.reply_text("🔙 Возврат в главное меню", reply_markup=get_main_keyboard())
    elif text == "ℹ️ Помощь":
        await help_command(update, context)

# ==================== ЗАПУСК ====================
def main():
    app = Application.builder().token(TOKEN).request(request).build()
    
    # ConversationHandler для анкеты
    onboard_conv = ConversationHandler(
        entry_points=[CommandHandler("start", onboard_user)],
        states={
            WAITING_FOR_BODYWEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_bodyweight)],
            WAITING_FOR_BENCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_bench)],
            WAITING_FOR_LEGPRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_legpress)],
            WAITING_FOR_SQUAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_squat)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # ConversationHandler для добавления упражнения в программу
    add_exercise_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add_exercise", add_exercise_start),
            MessageHandler(filters.Regex("^➕ Добавить упражнение$"), add_exercise_start)
        ],
        states={
            WAITING_FOR_EXERCISE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_exercise_name)],
            WAITING_FOR_EXERCISE_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_exercise_details)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # ConversationHandler для записи тренировки
    log_conv = ConversationHandler(
        entry_points=[
            CommandHandler("log", start_log),
            MessageHandler(filters.Regex("^📝 Записать тренировку$"), start_log),
            MessageHandler(filters.Regex("^📝 Записать ещё$"), start_log)
        ],
        states={
            WAITING_FOR_LOG: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_log)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # ConversationHandler для добавления своего показателя
    add_stat_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add_stat", add_custom_stat),
            MessageHandler(filters.Regex("^➕ Добавить свой показатель$"), add_custom_stat)
        ],
        states={
            WAITING_FOR_CUSTOM_EXERCISE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_stat_name)],
            WAITING_FOR_CUSTOM_EXERCISE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_stat_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # ConversationHandler для установки цели
    set_goal_conv = ConversationHandler(
        entry_points=[
            CommandHandler("set_goal", set_goal_select),
            MessageHandler(filters.Regex("^🎯 Мои цели$"), set_goal_select)
        ],
        states={
            WAITING_FOR_TARGET_SELECT: [CallbackQueryHandler(goal_callback)],
            WAITING_FOR_TARGET_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_goal_value),
                CommandHandler("cancel", cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # ConversationHandler для графика
    chart_conv = ConversationHandler(
        entry_points=[
            CommandHandler("chart", show_chart_select),
            MessageHandler(filters.Regex("^📈 График$"), show_chart_select)
        ],
        states={
            WAITING_FOR_PROGRESS_SELECT: [CallbackQueryHandler(chart_callback)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # ConversationHandler для редактирования показателей
    edit_stat_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^✏️ Редактировать показатель$"), edit_stat_select)
        ],
        states={
            WAITING_FOR_EDIT_SELECT: [CallbackQueryHandler(edit_stat_callback)],
            WAITING_FOR_EDIT_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_stat_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(onboard_conv)
    app.add_handler(add_exercise_conv)
    app.add_handler(log_conv)
    app.add_handler(add_stat_conv)
    app.add_handler(set_goal_conv)
    app.add_handler(chart_conv)
    app.add_handler(edit_stat_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("program", show_program))
    app.add_handler(CommandHandler("progress", show_progress))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("goals", show_goals))
    app.add_handler(CommandHandler("next", next_weight_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🤖 Бот запущен! Напиши /start в Телеграме")
    app.run_polling()

if __name__ == '__main__':
    main()