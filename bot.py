import sqlite3
import matplotlib.pyplot as plt
from datetime import datetime
import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters
from telegram.request import HTTPXRequest


TOKEN = os.environ.get('TELEGRAM_TOKEN')

if not TOKEN:
    print("❌ Ошибка: не найден токен. Установи переменную окружения TELEGRAM_TOKEN")
    exit()

USE_PROXY = False
PROXY_URL = "socks5://127.0.0.1:9050"

if USE_PROXY:
    request = HTTPXRequest(proxy_url=PROXY_URL)
else:
    request = HTTPXRequest()


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)


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


async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🏋️‍♂️ *Твой силовой тренер*\n\n👇 Нажми на кнопку, чтобы выбрать действие:",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def program(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🏋️‍♂️ *Программа на субботу:*\n\n"
        "1️⃣ Жим лёжа — 65 кг × 5×5\n"
        "2️⃣ Тяга гантели — 24–26 кг × 5×8–10\n"
        "3️⃣ Гиперэкстензия — 3×12–15\n"
        "4️⃣ Вис на турнике — 2×30–40 сек",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def log_workout(update: Update, context: CallbackContext):
    if update.message.text == "📝 Записать тренировку":
        context.user_data['waiting_for_log'] = True
        await update.message.reply_text(
            "📝 *Введи данные в формате:*\n`65 5 5`\n(вес, повторы, подходы)",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        return
    
    if context.user_data.get('waiting_for_log'):
        try:
            parts = update.message.text.split()
            if len(parts) != 3:
                raise ValueError
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
                f"✅ *Записано:* {weight} кг × {sets}×{reps}\n"
                f"📈 Расчётный максимум (1ПМ): *{one_rm} кг*{goal_text}",
                parse_mode='Markdown',
                reply_markup=get_after_log_keyboard()
            )
            context.user_data['waiting_for_log'] = False
        except:
            await update.message.reply_text(
                "❌ *Ошибка формата*\nИспользуй: `65 5 5`",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )
        return

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

async def target_command(update: Update, context: CallbackContext):
    if update.message.text == "🎯 Цель":
        context.user_data['waiting_for_target'] = True
        await update.message.reply_text(
            "🎯 *Введи свою цель в килограммах:*\nНапример: `100`",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        return
    
    if context.user_data.get('waiting_for_target'):
        try:
            target_weight = float(update.message.text)
            set_goal(target_weight)
            last = get_last_workout()
            if last:
                one_rm = calculate_1rm(last[0], last[1], last[2])
                remaining = target_weight - one_rm
                await update.message.reply_text(
                    f"🎯 *Цель:* {target_weight} кг\n"
                    f"📊 Текущий 1ПМ: {one_rm} кг\n"
                    f"💪 Осталось: {remaining:.1f} кг",
                    parse_mode='Markdown',
                    reply_markup=get_main_keyboard()
                )
            else:
                await update.message.reply_text(f"🎯 Цель {target_weight} кг установлена!", parse_mode='Markdown', reply_markup=get_main_keyboard())
            context.user_data['waiting_for_target'] = False
        except:
            await update.message.reply_text("❌ Введи число", parse_mode='Markdown', reply_markup=get_main_keyboard())
        return

async def next_weight_command(update: Update, context: CallbackContext):
    last = get_last_workout()
    if last:
        next_w = last[0] + 2.5
        await update.message.reply_text(
            f"📈 *Следующий вес:* {next_w} кг × {last[2]}×{last[1]}",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text("📭 Нет данных", reply_markup=get_main_keyboard())

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🏋️‍♂️ *Помощь*\n\n"
        "/log вес повторы подходы — записать\n"
        "/progress — прогресс\n"
        "/chart — график\n"
        "/target вес — цель\n"
        "/next — следующий вес",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def handle_text(update: Update, context: CallbackContext):
    text = update.message.text
    if text == "🏋️ Программа":
        await program(update, context)
    elif text == "📊 Прогресс":
        await progress_command(update, context)
    elif text == "📈 График":
        await chart_command(update, context)
    elif text == "🎯 Цель":
        await target_command(update, context)
    elif text == "📝 Записать тренировку":
        await log_workout(update, context)
    elif text == "📝 Записать ещё":
        context.user_data['waiting_for_log'] = True
        await update.message.reply_text("📝 *Введи данные:*\n`65 5 5`", parse_mode='Markdown', reply_markup=get_main_keyboard())
    elif text == "➕ Следующий вес":
        await next_weight_command(update, context)
    elif text == "ℹ️ Помощь":
        await help_command(update, context)


def main():
    if USE_PROXY:
        app = Application.builder().token(TOKEN).request(request).build()
    else:
        app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("program", program))
    app.add_handler(CommandHandler("log", log_workout))
    app.add_handler(CommandHandler("progress", progress_command))
    app.add_handler(CommandHandler("chart", chart_command))
    app.add_handler(CommandHandler("target", target_command))
    app.add_handler(CommandHandler("next", next_weight_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()