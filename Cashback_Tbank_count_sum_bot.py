from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, ConversationHandler, CallbackQueryHandler, filters
from itertools import combinations
import logging

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
WAITING_FOR_NUMBERS, WAITING_FOR_TOTAL = range(2)

# Хранилище данных пользователей
user_data = {}

def validate_cashback_input(input_str):
    parts = input_str.split(',')
    validated_numbers = []
    errors = []
    
    for index, part in enumerate(parts, 1):
        part = part.strip()
        if not part:
            errors.append(f"• Позиция {index}: Пустое значение")
            continue

        # Проверка что это число
        if not part.replace('.', '').replace(',', '').isdigit():
            errors.append(f"• Позиция {index}: '{part}' - не является числом")
            continue

        # Преобразование с учетом возможных десятичных разделителей
        try:
            num_str = part.replace(',', '.')
            num = float(num_str)

            # Проверка на отрицательное значение
            if num < 0:
                errors.append(f"• Позиция {index}: '{part}' - отрицательная сумма")
                continue
            else:
                validated_numbers.append(num)

        except ValueError:
            errors.append(f"• Позиция {index}: '{part}' - некорректный формат числа")

    return validated_numbers, errors

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 Привет! Я бот для подбора комбинаций кэшбэка.\n\n"
        "📝 Пожалуйста, введите суммы кэшбэка через запятую (например: 100, 200.50, 150.75):"
    )
    return WAITING_FOR_NUMBERS

async def handle_numbers_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введенных чисел"""
    user_id = update.message.from_user.id
    input_str = update.message.text
    
    # Валидация ввода
    validated_numbers, errors = validate_cashback_input(input_str)
    
    if errors and not validated_numbers:
        # Только ошибки, нет валидных чисел
        error_msg = "❌ Ошибки ввода:\n" + "\n".join(errors) + "\n\nПожалуйста, введите суммы заново:"
        await update.message.reply_text(error_msg)
        return WAITING_FOR_NUMBERS
    
    elif errors and validated_numbers:
        # Есть ошибки, но есть и валидные числа
        error_msg = "⚠️ Найдены ошибки:\n" + "\n".join(errors) + f"\n\n✅ Корректные суммы: {validated_numbers}"
        
        # Создаем клавиатуру с кнопками
        keyboard = [
            [InlineKeyboardButton("✅ Продолжить с корректными суммами", callback_data='proceed')],
            [InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Сохраняем валидные числа в контексте
        context.user_data['validated_numbers'] = validated_numbers
        
        await update.message.reply_text(error_msg, reply_markup=reply_markup)
        return WAITING_FOR_NUMBERS
    
    else:
        # Все числа валидны
        context.user_data['validated_numbers'] = validated_numbers
        await update.message.reply_text(
            f"✅ Получены суммы: {validated_numbers}\n\n"
            "💰 Теперь введите общую сумму (целевое значение), к которой нужно приблизиться:"
        )
        return WAITING_FOR_TOTAL

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'proceed':
        # Пользователь хочет продолжить с валидными числами
        await query.edit_message_text(
            f"✅ Продолжаем с суммами: {context.user_data['validated_numbers']}\n\n"
            "💰 Теперь введите общую сумму (целевое значение):"
        )
        return WAITING_FOR_TOTAL
    
    elif query.data == 'reenter':
        # Пользователь хочет ввести заново
        await query.edit_message_text("📝 Введите суммы кэшбэка через запятую:")
        return WAITING_FOR_NUMBERS

async def handle_total_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода общей суммы"""
    user_id = update.message.from_user.id
    input_str = update.message.text
    
    try:
        # Преобразуем ввод в число
        total_sum = float(input_str.replace(',', '.'))
        
        if total_sum <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной. Введите снова:")
            return WAITING_FOR_TOTAL
        
        # Получаем валидные числа из контекста
        validated_numbers = context.user_data.get('validated_numbers', [])
        
        if not validated_numbers:
            await update.message.reply_text("❌ Не найдены суммы кэшбэка. Начните снова командой /start")
            return ConversationHandler.END
        
        # Вычисляем результат
        result = find_the_closer_sum_of_cashback(validated_numbers, total_sum)
        
        # Отправляем результат
        await update.message.reply_text(result)
        
        # Предлагаем начать заново
        keyboard = [[InlineKeyboardButton("🔄 Новый расчет", callback_data='restart')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("Хотите сделать новый расчет?", reply_markup=reply_markup)
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Некорректный формат числа. Введите сумму снова:")
        return WAITING_FOR_TOTAL

async def restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезапуск расчета"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("📝 Введите суммы кэшбэка через запятую:")
    return WAITING_FOR_NUMBERS

def find_the_closer_sum_of_cashback(validated_numbers, total_sum):
    """Поиск ближайшей суммы (возвращает форматированный текст)"""
    best_diff = float('inf')
    best_combinations = []
    
    for i in range(1, len(validated_numbers) + 1):
        for comb in combinations(validated_numbers, i):
            current_sum = sum(comb)
            diff = total_sum - current_sum
            
            if diff >= 0:
                if diff < best_diff:
                    best_diff = diff
                    best_combinations = [comb]
                elif diff == best_diff:
                    best_combinations.append(comb)
    
    # Форматируем результат
    result_text = []
    result_text.append("🎯 **РЕЗУЛЬТАТЫ ПОИСКА**")
    result_text.append(f"📊 Целевая сумма: {total_sum}")
    result_text.append(f"🔢 Доступные суммы: {validated_numbers}")
    result_text.append(f"📉 Минимальная разница: {best_diff:.2f}")
    result_text.append(f"🔍 Найдено комбинаций: {len(best_combinations)}")
    result_text.append("")
    result_text.append("📋 **Найденные комбинации:**")
    
    for i, comb in enumerate(best_combinations, 1):
        result_text.append(f"{i}. {comb} = {sum(comb):.2f}")
    
    if best_diff > 0 and best_combinations:
        result_text.append("")
        result_text.append(f"💡 Рекомендация: использовать комбинацию №1")
        result_text.append(f"   Недобор до цели: {best_diff:.2f}")
    
    return "\n".join(result_text)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text("Операция отменена. Используйте /start для начала.")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    help_text = """
🤖 **Помощь по боту**

**Как использовать:**
1. Введите суммы кэшбэка через запятую
   Пример: 100, 200.50, 150, 75.25
2. Введите целевую сумму
3. Получите список комбинаций, наиболее близких к цели

**Команды:**
/start - начать расчет
/help - показать эту справку
/cancel - отменить текущую операцию

**Примечание:**
- Используйте точку или запятую для десятичных дробей
- Отрицательные суммы не допускаются
- Бот ищет комбинации, не превышающие целевую сумму
    """
    await update.message.reply_text(help_text)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    if update and update.message:
        await update.message.reply_text(
            "❌ Произошла ошибка. Пожалуйста, попробуйте снова командой /start"
        )

def main():
    """Запуск бота"""
    # Вставьте ваш токен от BotFather
    TOKEN = "ВАШ_ТОКЕН_БОТА"
    
    # Создаем Application
    application = Application.builder().token(TOKEN).build()
    
    # Настраиваем ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            WAITING_FOR_NUMBERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_numbers_input),
                CallbackQueryHandler(button_callback, pattern='^(proceed|reenter)$')
            ],
            WAITING_FOR_TOTAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_total_input)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )
    
    # Добавляем обработчики
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('cancel', cancel))
    application.add_handler(CallbackQueryHandler(restart_callback, pattern='^restart$'))
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    print("🤖 Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()