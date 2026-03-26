import sqlite3
import matplotlib.pyplot as plt
from datetime import datetime
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import os

# ... остальные импорты ...

# Замени строку с TOKEN на эту:
TOKEN = os.environ.get('TELEGRAM_TOKEN')

# Добавь проверку, чтобы бот не запускался без токена
if not TOKEN:
    print("❌ Ошибка: не найден токен. Установи переменную окружения TELEGRAM_TOKEN")
    exit()
# ==================== НАСТРОЙКИ ====================

# ===================================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

# База данных
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

def calculate_1rm(weight, reps):
    return round(weight * (1 + reps / 30), 1)

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

# ==================== КОМАНДЫ БОТА ====================

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🏋️‍♂️ *Твой силовой тренер*\n\n"
        "📋 *Команды:*\n"
        "/log *вес* *повторы* *подходы* — записать тренировку\n"
        "/progress — показать прогресс\n"
        "/chart — показать график\n"
        "/target *вес* — установить цель (кг)\n"
        "/next — следующий вес\n"
        "/help — помощь",
        parse_mode='Markdown'
    )

async def log_workout(update: Update, context: CallbackContext):
    try:
        weight = float(context.args[0])
        reps = int(context.args[1])
        sets = int(context.args[2])
        
        save_workout(weight, reps, sets)
        one_rm = calculate_1rm(weight, reps)
        
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
            parse_mode='Markdown'
        )
    except:
        await update.message.reply_text(
            "❌ *Ошибка*\n"
            "Используй: `/log вес повторы подходы`\n"
            "Пример: `/log 65 5 5`",
            parse_mode='Markdown'
        )

async def progress(update: Update, context: CallbackContext):
    data = get_workouts()
    if not data:
        await update.message.reply_text("📭 Нет записанных тренировок")
        return
    
    text = "📊 *Твой прогресс:*\n\n"
    for i, (date, weight, reps, sets) in enumerate(data[-10:]):
        one_rm = calculate_1rm(weight, reps)
        text += f"📅 {date[:10]}: {weight} кг × {sets}×{reps} → 1ПМ = {one_rm} кг\n"
    
    if len(data) > 1:
        first = data[0][1]
        last = data[-1][1]
        diff = last - first
        text += f"\n📈 *Общий прогресс:* +{diff} кг за {len(data)} тренировок"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def chart(update: Update, context: CallbackContext):
    await update.message.reply_text("📊 Строю график...")
    chart_file = create_chart()
    if chart_file:
        with open(chart_file, 'rb') as f:
            await update.message.reply_photo(f, caption="📈 Динамика жима лёжа")
    else:
        await update.message.reply_text("❌ Недостаточно данных")

async def target(update: Update, context: CallbackContext):
    try:
        target_weight = float(context.args[0])
        set_goal(target_weight)
        last = get_last_workout()
        if last:
            one_rm = calculate_1rm(last[0], last[1])
            remaining = target_weight - one_rm
            await update.message.reply_text(
                f"🎯 *Цель:* {target_weight} кг\n"
                f"📊 Текущий 1ПМ: {one_rm} кг\n"
                f"💪 Осталось: {remaining:.1f} кг",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"🎯 Цель {target_weight} кг установлена!", parse_mode='Markdown')
    except:
        await update.message.reply_text("❌ Используй: `/target 100`", parse_mode='Markdown')

async def next_weight(update: Update, context: CallbackContext):
    last = get_last_workout()
    if last:
        weight = last[0]
        reps = last[1]
        sets = last[2]
        next_w = weight + 2.5
        await update.message.reply_text(
            f"📈 *Следующий вес:* {next_w} кг × {sets}×{reps}\n"
            f"🎯 Это +2.5 кг к твоему последнему результату ({weight} кг)",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("📭 Нет данных. Сделай /log чтобы начать.")

async def help_command(update: Update, context: CallbackContext):
    await start(update, context)

# ==================== ЗАПУСК ====================

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", log_workout))
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("chart", chart))
    app.add_handler(CommandHandler("target", target))
    app.add_handler(CommandHandler("next", next_weight))
    app.add_handler(CommandHandler("help", help_command))
    
    print("🤖 Бот запущен! Напиши /start в Телеграме")
    app.run_polling()

if __name__ == '__main__':
    main()