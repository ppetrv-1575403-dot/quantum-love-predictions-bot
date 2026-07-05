import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from aiohttp import web
import os
import sys

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["TG_BOT_TOKEN"]

# ===== Webhook конфигурация =====
WEBHOOK_URL = os.environ.get("WEBHOOK_URL",
    os.environ.get("RENDER_EXTERNAL_URL", "")
)

SECRET_TOKEN = os.environ.get("TELEGRAM_SECRET_TOKEN", "")  # опциональная защита

PORT = int(os.environ.get("PORT", 8080))
HOST = "0.0.0.0"

from constants import (
    LOVE_PREDICTIONS, logger, love_keywords, get_stars_str,
    get_mood, about_text_str, fill_status_str, get_source_str,
    get_compatibility_data, stats_text_str, welcome_str,
    compatibility_reply_str, compatibility_response_str,
    compatibility_info_str, about_info_str, get_last_refill_str,
    get_prediction_response_str, get_love_prediction_response_str
)
from cached_quantum_rng import CachedQuantumGenerator

# ===== ГЛОБАЛЬНЫЙ ГЕНЕРАТОР =====
qrng = CachedQuantumGenerator(cache_size=500, preload_threshold=0.3)

# Глобальная ссылка на application (нужна для webhook handler)
application: Application = None


# ===== ОБРАБОТЧИКИ КОМАНД =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветственное сообщение."""
    user_name = update.effective_user.first_name if update.effective_user else "Путник"
    welcome = welcome_str(user_name)

    keyboard = [
        [InlineKeyboardButton("💘 Гадание на любовь", callback_data="love")],
        [InlineKeyboardButton("💑 Совместимость имен", callback_data="compatibility_info")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def love_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Гадание на любовь."""
    await send_love_prediction(update.message, update.effective_user)


async def compatibility_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка совместимости."""
    if context.args and len(context.args) >= 2:
        name1 = context.args[0]
        name2 = context.args[1]
        await send_compatibility(update.message, name1, name2)
    else:
        await update.message.reply_text(
            compatibility_reply_str,
            parse_mode="Markdown"
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Статистика."""
    stats = qrng.get_cache_stats()
    fill = stats['fill_percentage']
    status = fill_status_str(fill)
    last_refill = stats['last_refill']
    last_refill_str = get_last_refill_str(last_refill)
    
    stats_text = stats_text_str(stats, status, last_refill_str)

    keyboard = [[InlineKeyboardButton("💘 Гадание на любовь", callback_data="love")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode="Markdown")


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """О технологии."""
    about = about_text_str()
    keyboard = [[InlineKeyboardButton("💘 Испытать судьбу", callback_data="love")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        about,
        reply_markup=reply_markup,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик сообщений."""
    text = update.message.text.lower()

    # Проверяем на имена для совместимости
    if " и " in text or " + " in text:
        separator = " и " if " и " in text else " + "
        names = text.split(separator)
        if len(names) == 2 and len(names[0].strip()) > 0 and len(names[1].strip()) > 0:
            await send_compatibility(update.message, names[0].strip(), names[1].strip())
            return

    if any(word in text for word in love_keywords):
        await send_love_prediction(update.message, update.effective_user)
    else:
        # Если непонятно — даем любовное гадание по умолчанию
        await send_love_prediction(update.message, update.effective_user)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопок."""
    query = update.callback_query
    await query.answer()

    if query.data == "love":
        await send_love_prediction_callback(query)
    elif query.data == "stats":
        await send_stats_callback(query)
    elif query.data == "compatibility_info":
        await query.edit_message_text(
            compatibility_info_str,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💘 К гаданию", callback_data="love")
            ]]),
            parse_mode="Markdown"
        )
    elif query.data == "about":
        keyboard = [[InlineKeyboardButton("💘 Гадать", callback_data="love")]]
        await query.edit_message_text(
            about_info_str,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )


async def send_love_prediction(message, user) -> None:
    """Отправка любовного предсказания."""
    user_name = user.first_name if user else "Путник"

    random_index, is_quantum = await qrng.get_random_number(0, len(LOVE_PREDICTIONS) - 1)
    prediction = LOVE_PREDICTIONS[random_index]

    mood, category = get_mood(random_index)
    source = get_source_str(is_quantum)
    response = get_prediction_response_str(mood, user_name, prediction, category, source, random_index)

    keyboard = [
        [InlineKeyboardButton("💘 Еще гадание", callback_data="love")],
        [InlineKeyboardButton("💑 Совместимость", callback_data="compatibility_info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(response, reply_markup=reply_markup, parse_mode="Markdown")


async def send_love_prediction_callback(query) -> None:
    """Отправка предсказания из callback."""
    user_name = query.from_user.first_name if query.from_user else "Путник"

    random_index, is_quantum = await qrng.get_random_number(0, len(LOVE_PREDICTIONS) - 1)
    prediction = LOVE_PREDICTIONS[random_index]

    mood, category = get_mood(random_index)
    source = get_source_str(is_quantum)
    response = get_love_prediction_response_str(mood, user_name, prediction, category, source, random_index)

    keyboard = [
        [InlineKeyboardButton("💘 Еще", callback_data="love")],
        [InlineKeyboardButton("💑 Совместимость", callback_data="compatibility_info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(response, reply_markup=reply_markup, parse_mode="Markdown")


async def send_compatibility(message, name1: str, name2: str) -> None:
    """Расчет совместимости имен."""
    import hashlib

    combined = (name1.lower() + name2.lower()).encode()
    name_hash = int(hashlib.md5(combined).hexdigest()[:8], 16)

    quantum_num, is_quantum = await qrng.get_random_number(0, 100)
    compatibility = (name_hash % 51 + quantum_num // 2) % 101

    source = get_source_str(is_quantum)
    stars, verdict, emoji = get_compatibility_data(compatibility)
    response = compatibility_response_str(emoji, name1, name2, compatibility, stars, verdict, source)

    keyboard = [
        [InlineKeyboardButton("💘 Гадание на любовь", callback_data="love")],
        [InlineKeyboardButton("🔄 Проверить еще", callback_data="compatibility_info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(response, reply_markup=reply_markup, parse_mode="Markdown")


async def send_stats_callback(query) -> None:
    """Статистика через callback."""
    stats = qrng.get_cache_stats()
    fill = stats['fill_percentage']
    status = fill_status_str(fill)
    last_refill = stats['last_refill']
    last_refill_str = get_last_refill_str(last_refill)

    stats_text = stats_text_str(stats, status, last_refill_str)

    keyboard = [[InlineKeyboardButton("💘 Гадать", callback_data="love")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode="Markdown")

# ===== WEBHOOK HTTP-СЕРВЕР =====

async def health_handler(request: web.Request) -> web.Response:
    """Health check endpoint для Render."""
    return web.Response(text="OK 💝", status=200)

async def webhook_handler(request: web.Request) -> web.Response:
    """Обработка входящих обновлений от Telegram."""
    # Проверка secret token (дополнительная защита)
    if SECRET_TOKEN:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_secret != SECRET_TOKEN:
            logger.warning("⚠️ Неверный secret token!")
            return web.Response(status=403)

    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"❌ Ошибка обработки update: {e}")
        return web.Response(status=500)

# ===== ЗАПУСК =====

async def on_startup(app: web.Application) -> None:
    """Действия при старте HTTP-сервера."""
    global application

    print("💝 Инициализация Любовного Оракула...")

    # Инициализируем квантовый кеш
    await qrng.initialize_cache()

    # Создаём и настраиваем PTB Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("love", love_command))
    application.add_handler(CommandHandler("compatibility", compatibility_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Инициализируем PTB (это инициализирует bot для set_webhook)
    await application.initialize()
    await application.start()

    # Устанавливаем webhook в Telegram
    full_webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    webhook_kwargs = {"url": full_webhook_url, "allowed_updates": Update.ALL_TYPES}
    if SECRET_TOKEN:
        webhook_kwargs["secret_token"] = SECRET_TOKEN

    await application.bot.set_webhook(**webhook_kwargs)

    print("\n" + "=" * 50)
    print("💝 Любовный Оракул с квантовым генератором")
    print("=" * 50)
    print(f"🌐 Webhook URL: {full_webhook_url}")
    print(f"🔌 Порт: {PORT}")
    print(f"💕 100 уникальных предсказаний о любви")
    print(f"💑 Гадание на совместимость имен")
    print(f"⚛️ Квантовая энтропия ANU")
    print(f"🔒 Secret token: {'✅ установлен' if SECRET_TOKEN else '❌ не установлен'}")
    print("=" * 50 + "\n")
    print("✅ Бот готов принимать обновления!\n")

async def on_shutdown(app: web.Application) -> None:
    """Действия при остановке HTTP-сервера."""
    print("\n💔 Завершение работы...")

    if application:
        # Удаляем webhook
        try:
            await application.bot.delete_webhook()
            print("✅ Webhook удалён")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить webhook: {e}")

        await application.stop()
        await application.shutdown()

    await qrng.close()
    print("🧹 Ресурсы освобождены")

def create_web_app() -> web.Application:
    """Создание aiohttp веб-приложения."""
    app = web.Application()

    # Маршруты
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_post(f"/{BOT_TOKEN}", webhook_handler)

    # Хуки запуска/остановки
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    return app


def main() -> None:
    """Точка входа."""
    # Проверка обязательных переменных
    if not BOT_TOKEN:
        print("❌ TG_BOT_TOKEN не установлен в переменных окружения!")
        sys.exit(1)

    if not WEBHOOK_URL:
        print("❌ WEBHOOK_URL не установлен!")
        print("💡 Установите переменную окружения WEBHOOK_URL")
        print("   Например: https://quantum-love-predictions-bot.onrender.com")
        sys.exit(1)

    # Создаём и запускаем веб-сервер
    app = create_web_app()
    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n💔 Оракул завершил работу")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)