import logging
import json
import time
import subprocess
import sys
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

pip install -r requirements.txt

# ================== НАСТРОЙКИ GOOGLE SHEETS ==================
SPREADSHEET_ID = "1Sk4HHpQl9Z30vytkIFrHxTOty5W6xj9wdPwAeAamWGE"
CREDS_FILE = "google-credentials.json"
# =============================================================

# Настройки бота
BOT_TOKEN = "8473361909:AAG0NpO-L_iNwiBbRj7JDXtZP1K8q8FiDlI"
ADMIN_CHAT_ID = 1256912072  # Ваш ID в Telegram

# Настройки перезапуска
RESTART_INTERVAL = 6 * 60 * 60  # 6 часов в секундах
MAX_RESTART_ATTEMPTS = 10  # Максимальное количество попыток перезапуска
RESTART_DELAY = 60  # Задержка перед перезапуском в секундах

# Состояния диалога
CHILD_NAME, CHILD_AGE, INTEREST, CONTACT = range(4)

# Глобальные переменные
restart_count = 0
last_restart_time = 0

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def setup_google_sheets():
    """Настройка подключения к Google Sheets"""
    try:
        from google.oauth2.service_account import Credentials
        import gspread

        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=[
            'https://spreadsheets.google.com/feeds'
        ])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.sheet1

        logging.info(f"✅ Таблица '{spreadsheet.title}' доступна!")
        return worksheet

    except Exception as e:
        logging.error(f"❌ Ошибка подключения к Google Sheets: {e}")
        return None

def save_to_google_sheets(user_data):
    """Сохранение данных в Google Sheets"""
    try:
        worksheet = setup_google_sheets()
        if not worksheet:
            return False

        row_data = [
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            user_data.get('child_name', ''),
            user_data.get('child_age', ''),
            user_data.get('interest', ''),
            user_data.get('contact', ''),
            user_data.get('username', ''),
            str(user_data.get('telegram_id', ''))
        ]

        worksheet.append_row(row_data)
        logging.info("✅ Данные успешно сохранены в Google Sheets")
        return True

    except Exception as e:
        logging.error(f"❌ Ошибка сохранения в Google Sheets: {e}")
        return False

def save_to_json_file(user_data):
    """Сохранение данных в JSON файл (резервное)"""
    try:
        filename = 'applications.json'

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            data = []

        record = {
            'timestamp': datetime.now().isoformat(),
            **user_data
        }
        data.append(record)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logging.info(f"✅ Данные сохранены в файл: {user_data.get('child_name', '')}")
        return True

    except Exception as e:
        logging.error(f"❌ Ошибка сохранения в файл: {e}")
        return False

def save_application_data(user_data):
    """Основная функция сохранения данных"""
    sheets_success = save_to_google_sheets(user_data)

    if sheets_success:
        save_to_json_file(user_data)
        return "google_sheets"

    file_success = save_to_json_file(user_data)
    return "backup_file" if file_success else "error"

def schedule_restart(application):
    """Планирует перезапуск бота через заданное время"""
    import threading

    def restart_job():
        global restart_count, last_restart_time

        time.sleep(RESTART_INTERVAL)

        if restart_count >= MAX_RESTART_ATTEMPTS:
            logging.error("❌ Достигнут лимит перезапусков. Остановка бота.")
            send_admin_notification("❌ Бот остановлен: достигнут лимит перезапусков")
            return

        logging.info("🔄 Запланированный перезапуск бота...")
        send_admin_notification("🔄 Запланированный перезапуск бота")

        restart_count += 1
        last_restart_time = time.time()

        # Останавливаем бота и перезапускаем
        application.stop()
        time.sleep(5)
        restart_bot()

    thread = threading.Thread(target=restart_job, daemon=True)
    thread.start()

def send_admin_notification(message):
    """Отправляет уведомление администратору"""
    try:
        from telegram import Bot
        bot = Bot(token=BOT_TOKEN)
        bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
    except Exception as e:
        logging.error(f"❌ Ошибка отправки уведомления админу: {e}")

def restart_bot():
    """Перезапускает бота"""
    logging.info("🔄 Перезапуск бота...")

    python = sys.executable
    script = os.path.abspath(__file__)

    try:
        subprocess.Popen([python, script])
        sys.exit(0)
    except Exception as e:
        logging.error(f"❌ Ошибка при перезапуске: {e}")
        # Если перезапуск не удался, пытаемся запустить обычным способом
        time.sleep(RESTART_DELAY)
        main()

def setup_application():
    """Настройка и возврат приложения"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHILD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_child_info)],
            INTEREST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_interest)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_contact)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('test', test_sheets))
    application.add_handler(CommandHandler('stats', stats))
    application.add_handler(CommandHandler('restart', manual_restart))
    application.add_handler(CommandHandler('status', bot_status))

    # Обработчик ошибок
    application.add_error_handler(error_handler)

    return application

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logging.info(f"👤 Пользователь {user.username} начал диалог")

    await update.message.reply_text(
        '👋 Добрый день! Я помогу вам подобрать программу для вашего ребенка.\n'
        'Как зовут вашего ребенка и сколько ему лет? (Например: Маша, 4 года)',
        reply_markup=ReplyKeyboardRemove()
    )

    context.user_data.update({
        'username': user.username or user.first_name,
        'telegram_id': user.id,
        'start_time': datetime.now().isoformat()
    })

    return CHILD_NAME

async def get_child_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    parts = text.split(',')
    if len(parts) >= 2:
        child_name = parts[0].strip()
        child_age = parts[1].strip().replace('лет', '').replace('года', '').strip()

        context.user_data.update({
            'child_name': child_name,
            'child_age': child_age
        })

        try:
            age = int(child_age)
            if age < 3:
                programs = {
                    '1': 'Раннее развитие (1-3 года)',
                    '2': 'Музыкальные занятия',
                    '3': 'Игровая комната'
                }
            elif age <= 6:
                programs = {
                    '1': 'Мини-сад (4 часа без мамы)',
                    '2': 'Творческая мастерская',
                    '3': 'Подготовка к школе'
                }
            else:
                programs = {
                    '1': 'Продленка',
                    '2': 'Творческие курсы',
                    '3': 'Индивидуальные занятия'
                }
        except:
            programs = {
                '1': 'Мини-сад (4 часа без мамы)',
                '2': 'Творческая мастерская',
                '3': 'Подготовка к школе'
            }

        context.user_data['available_programs'] = programs

        keyboard = [['1', '2', '3'], ['Другое']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        programs_text = '\n'.join([f'{key}. {value}' for key, value in programs.items()])

        await update.message.reply_text(
            f"Отлично! Для {child_name} ({child_age} лет) у нас есть:\n\n"
            f"{programs_text}\n\n"
            "Что интересует? (ответьте цифрой)",
            reply_markup=reply_markup
        )

        return INTEREST
    else:
        await update.message.reply_text("Пожалуйста, введите данные в формате: Имя, возраст\nНапример: Маша, 4 года")
        return CHILD_NAME

async def get_interest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text

    programs = context.user_data.get('available_programs', {
        '1': 'Мини-сад (4 часа без мамы)',
        '2': 'Творческая мастерская',
        '3': 'Подготовка к школе',
        'Другое': 'Другая программа'
    })

    selected_program = programs.get(choice, choice)
    context.user_data['interest'] = selected_program

    await update.message.reply_text(
        "📞 Отлично! Как с вами связаться? (телефон, email или WhatsApp)",
        reply_markup=ReplyKeyboardRemove()
    )

    return CONTACT

async def get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.text

    context.user_data['contact'] = contact
    save_result = save_application_data(context.user_data)

    if save_result == "google_sheets":
        storage_info = "✅ Данные сохранены в Google Sheets и локальный файл"
    elif save_result == "backup_file":
        storage_info = "⚠️ Google Sheets недоступен, данные только в локальном файле"
    else:
        storage_info = "❌ Ошибка сохранения данных"

    admin_message = (
        "🎯 *НОВАЯ ЗАЯВКА*\n"
        f"👶 Ребенок: {context.user_data.get('child_name', '')} ({context.user_data.get('child_age', '')} лет)\n"
        f"📚 Программа: {context.user_data.get('interest', '')}\n"
        f"📞 Контакт: {contact}\n"
        f"👤 От: @{context.user_data.get('username', '')}\n"
        f"💾 {storage_info}"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"❌ Ошибка отправки админу: {e}")

    await update.message.reply_text("✅ *Спасибо! Ваша заявка принята!*\n\nМы свяжемся с вами в течение 15 минут! 🌟", parse_mode='Markdown')
    context.user_data.clear()

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text('Диалог прерван. Если потребуется помощь - напишите /start')
    return ConversationHandler.END

async def manual_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручной перезапуск бота"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Эта команда только для администратора")
        return

    await update.message.reply_text("🔄 Ручной перезапуск бота...")
    logging.info("🔄 Ручной перезапуск по команде администратора")

    # Даем время на отправку сообщения
    import asyncio
    await asyncio.sleep(2)

    restart_bot()

async def bot_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус бота"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Эта команда только для администратора")
        return

    status_text = (
        "🤖 *Статус бота*\n\n"
        f"🔄 Перезапусков: {restart_count}/{MAX_RESTART_ATTEMPTS}\n"
        f"⏰ Время работы: {time.time() - last_restart_time:.0f} сек\n"
        f"📊 Следующий перезапуск через: {RESTART_INTERVAL/3600:.1f} часов\n"
        f"🛡️ Статус: {'🟢 Активен' if restart_count < MAX_RESTART_ATTEMPTS else '🔴 Остановлен'}"
    )

    await update.message.reply_text(status_text, parse_mode='Markdown')

async def test_sheets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тест Google Sheets"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Эта команда только для администратора")
        return

    try:
        from google.oauth2.service_account import Credentials
        import gspread

        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=[
            'https://spreadsheets.google.com/feeds'
        ])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.sheet1

        test_data = [datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'Тест', '5', 'Тестовая программа']
        worksheet.append_row(test_data)

        await update.message.reply_text("✅ Тестовая запись добавлена в Google Sheets!")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка теста Google Sheets: {e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика заявок"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Эта команда только для администратора")
        return

    try:
        with open('applications.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        stats_text = f"📊 Статистика заявок: {len(data)} записей\n\n"
        programs = {}
        for record in data:
            program = record.get('interest', 'Не указано')
            programs[program] = programs.get(program, 0) + 1

        for program, count in programs.items():
            stats_text += f"• {program}: {count} заявок\n"

        await update.message.reply_text(stats_text)

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка получения статистики: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logging.error(f"Ошибка в обработчике: {context.error}")

    # При серьезной ошибке пытаемся перезапуститься
    if isinstance(context.error, Exception):
        logging.warning("🔄 Серьезная ошибка, планируем перезапуск...")
        time.sleep(RESTART_DELAY)
        restart_bot()

def main():
    global restart_count, last_restart_time

    logging.info("🚀 Запуск бота с системой перезапуска...")
    last_restart_time = time.time()

    if "ВАШ_ТОКЕН" in BOT_TOKEN:
        logging.error("❌ Токен бота не настроен!")
        return

    try:
        # Настраиваем приложение
        application = setup_application()

        # Планируем автоматический перезапуск
        schedule_restart(application)

        # Уведомляем администратора о запуске
        send_admin_notification("🤖 Бот запущен и готов к работе!")

        logging.info(f"✅ Бот запущен. Следующий перезапуск через {RESTART_INTERVAL/3600} часов")
        logging.info("💾 Данные сохраняются в Google Sheets + локальный файл")
        logging.info("🔄 Система автоматического перезапуска активна")

        # Запускаем бота
        application.run_polling()

    except Exception as e:
        logging.error(f"❌ Критическая ошибка: {e}")
        time.sleep(RESTART_DELAY)
        restart_bot()

if __name__ == '__main__':
    main()
