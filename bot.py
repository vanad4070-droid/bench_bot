import sqlite3
import matplotlib.pyplot as plt
from datetime import datetime
import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters, ConversationHandler
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

# ==================== КНОПКИ ====================
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🏋️ Программа"), KeyboardButton("📊 Прогресс")],
        [KeyboardButton("📈 График"), KeyboardButton("🎯 Цель")],
        [KeyboardButton("📝 Записать тренировку"), KeyboardButton("ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_after_log_keyboard():
    keyboard = [
        [KeyboardButton("📝 Записать ещё"), KeyboardButton("📊 Прогресс")],
        [KeyboardButton("➕ Следующий вес"), KeyboardButton("🏋️ Программа")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS workouts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT,
                  weight REAL,
                  reps INTEGER,
                  sets INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS goals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  target_weight REAL,
                  set_date TEXT)''')
    conn.commit()
    conn.close()

init_db()

def save_workout(weight, reps, sets):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO workouts (date, weight, reps, sets) VALUES (?, ?, ?, ?)",
              (date, weight, reps, sets))
    conn.commit()
    conn.close()

def get_workouts():
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT date, weight, reps, sets FROM workouts ORDER BY date")
    data = c.fetchall()
    conn.close()
    return data

def calculate_1rm(weight, reps, sets):
    if sets >= 4 and reps >= 4:
        return round(weight * 1.2, 1)
    else:
        return round(weight / (1.0278 - 0.0278 * reps), 1)

def create_chart():
    data = get_workouts()
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
    plt.title('Динамика прогресса в жиме лёжа', fontsize=16)
    plt.xlabel('Дата', fontsize=12)
    plt.ylabel('Вес (кг)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('progress.png')
    plt.close()
    return 'progress.png'

def set_goal(weight):
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d")
    c.execute("DELETE FROM goals")
    c.execute("INSERT INTO goals (target_weight, set_date) VALUES (?, ?)", (weight, date))
    conn.commit()
    conn.close()

def get_goal():
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT target_weight FROM goals ORDER BY id DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def get_last_workout():
    conn = sqlite3.connect('training.db')
    c = conn.cursor()
    c.execute("SELECT weight, reps, sets FROM workouts ORDER BY id DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result if result else None

# ==================== КОМАНДЫ ====================
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🏋️‍♂️ *Твой силовой тренер*\n\n👇 Нажми на кнопку:",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def program(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🏋️‍♂️ *Программа:*\n1️⃣ Жим — 65 кг × 5×5\n2️⃣ Тяга гантели — 24–26 кг × 5×8–10\n3️⃣ Гиперэкстензия — 3×12–15\n4️⃣ Вис на турнике — 2×30–40 сек",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def start_log(update: Update, context: CallbackContext):
    await update.message.reply_text("📝 *Введи:* `65 5 5`\n(вес, повторы, подходы)", parse_mode='Markdown')
    return WAITING_FOR_LOG

async def handle_log(update: Update, context: CallbackContext):
    try:
        parts = update.message.text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Нужно три числа. Пример: `65 5 5`", parse_mode='Markdown')
            return WAITING_FOR_LOG
        
        weight = float(parts[0])
        reps = int(parts[1])
        sets = int(parts[2])
        
        save_workout(weight, reps, sets)
        one_rm = calculate_1rm(weight, reps, sets)
        
        goal = get_goal()
        goal_text = ""
        if goal:
            remaining = goal - one_rm
            if remaining > 0:
                goal_text = f"\n🎯 До цели {goal} кг осталось: {remaining:.1f} кг"
            else:
                goal_text = f"\n🎉 Поздравляю! Ты достиг цели {goal} кг!"
        
        await update.message.reply_text(
            f"✅ *Записано:* {weight} кг × {sets}×{reps}\n📈 1ПМ = {one_rm} кг{goal_text}",
            parse_mode='Markdown',
            reply_markup=get_after_log_keyboard()
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Ошибка. Пример: `65 5 5`", parse_mode='Markdown')
        return WAITING_FOR_LOG

async def cancel_log(update: Update, context: CallbackContext):
    await update.message.reply_text("❌ Запись отменена", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def start_target(update: Update, context: CallbackContext):
    await update.message.reply_text("🎯 *Введи цель (кг):*", parse_mode='Markdown')
    return WAITING_FOR_TARGET

async def handle_target(update: Update, context: CallbackContext):
    try:
        target_weight = float(update.message.text)
        set_goal(target_weight)
        last = get_last_workout()
        if last:
            one_rm = calculate_1rm(last[0], last[1], last[2])
            remaining = target_weight - one_rm
            await update.message.reply_text(
                f"🎯 *Цель:* {target_weight} кг\n📊 Текущий 1ПМ: {one_rm} кг\n💪 Осталось: {remaining:.1f} кг",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(f"🎯 Цель {target_weight} кг установлена!", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введи число", parse_mode='Markdown')
        return WAITING_FOR_TARGET

async def progress_command(update: Update, context: CallbackContext):
    data = get_workouts()
    if not data:
        await update.message.reply_text("📭 Нет записанных тренировок", reply_markup=get_main_keyboard())
        return
    
    text = "📊 *Твой прогресс:*\n\n"
    for date, weight, reps, sets in data[-10:]:
        one_rm = calculate_1rm(weight, reps, sets)
        text += f"📅 {date[:10]}: {weight} кг × {sets}×{reps} → 1ПМ = {one_rm} кг\n"
    
    if len(data) > 1:
        diff = data[-1][1] - data[0][1]
        text += f"\n📈 *Общий прогресс:* +{diff} кг за {len(data)} тренировок"
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_main_keyboard())

async def chart_command(update: Update, context: CallbackContext):
    await update.message.reply_text("📊 Строю график...")
    chart_file = create_chart()
    if chart_file:
        with open(chart_file, 'rb') as f:
            await update.message.reply_photo(f, caption="📈 Динамика жима лёжа", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("❌ Недостаточно данных", reply_markup=get_main_keyboard())

async def next_weight_command(update: Update, context: CallbackContext):
    last = get_last_workout()
    if last:
        await update.message.reply_text(
            f"📈 *Следующий вес:* {last[0] + 2.5} кг × {last[2]}×{last[1]}",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text("📭 Нет данных", reply_markup=get_main_keyboard())

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🏋️‍♂️ *Помощь*\n\n"
        "📋 *Команды:*\n"
        "/log вес повторы подходы — записать\n"
        "/progress — прогресс\n"
        "/chart — график\n"
        "/target вес — цель\n"
        "/next — следующий вес\n\n"
        "👇 Или нажимай на кнопки!",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

# ==================== ОБРАБОТКА ТЕКСТОВЫХ КНОПОК ====================
async def handle_text(update: Update, context: CallbackContext):
    text = update.message.text
    
    if text == "🏋️ Программа":
        await program(update, context)
    elif text == "📊 Прогресс":
        await progress_command(update, context)
    elif text == "📈 График":
        await chart_command(update, context)
    elif text == "🎯 Цель":
        await start_target(update, context)
    elif text == "📝 Записать тренировку":
        await start_log(update, context)
    elif text == "📝 Записать ещё":
        await start_log(update, context)
    elif text == "➕ Следующий вес":
        await next_weight_command(update, context)
    elif text == "ℹ️ Помощь":
        await help_command(update, context)
    else:
        # Если бот не в режиме ожидания — просто игнорируем
        pass

# ==================== ЗАПУСК ====================
def main():
    app = Application.builder().token(TOKEN).request(request).build()
    
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
        fallbacks=[CommandHandler("cancel", cancel_log)],
    )
    
    # ConversationHandler для цели
    target_conv = ConversationHandler(
        entry_points=[
            CommandHandler("target", start_target),
            MessageHandler(filters.Regex("^🎯 Цель$"), start_target)
        ],
        states={
            WAITING_FOR_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_target)],
        },
        fallbacks=[CommandHandler("cancel", cancel_log)],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("program", program))
    app.add_handler(log_conv)
    app.add_handler(target_conv)
    app.add_handler(CommandHandler("progress", progress_command))
    app.add_handler(CommandHandler("chart", chart_command))
    app.add_handler(CommandHandler("next", next_weight_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🤖 Бот запущен! Напиши /start в Телеграме")
    app.run_polling()

if __name__ == '__main__':
    main()