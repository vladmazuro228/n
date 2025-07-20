from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import sqlite3
import logging
from datetime import datetime

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
MAIN_BOT_TOKEN = '8134477300:AAEu8-wqll5T6Q6D2THgXWsGhn5lQHm1UZQ'
ADMIN_BOT_TOKEN = '8010374415:AAFHqi-NIwxqNx9bIWEh4UKs3P66rUacrR8'
ADMIN_CHAT_ID = '7687325093'

# Состояния для FSM
class PurchaseStates(StatesGroup):
    waiting_for_token = State()
    waiting_for_id = State()

# Инициализация ботов
main_bot = Bot(token=MAIN_BOT_TOKEN)
admin_bot = Bot(token=ADMIN_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(main_bot, storage=storage)

# База данных
conn = sqlite3.connect('bans.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''CREATE TABLE IF NOT EXISTS bans
                (user_id INTEGER PRIMARY KEY, 
                 username TEXT,
                 reason TEXT,
                 admin_id INTEGER,
                 ban_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS referrals
                (user_id INTEGER PRIMARY KEY, referrer_id INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS balances
                (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS purchases
                (user_id INTEGER, package TEXT, bot_token TEXT, bot_id TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

# Цены пакетов
PRICES = {
    "option1": ("100 рублей", "❤️ Простая ратка"),
    "option2": ("500 рублей", "💎 Премиум пакет"),
    "option3": ("1000 рублей", "🚀 VIP пакет")
}

# ===================== СИСТЕМА БАНОВ =====================
async def is_banned(user_id):
    """Проверяет, забанен ли пользователь"""
    cursor.execute("SELECT reason FROM bans WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None

async def ban_user(user_id, username=None, reason="Не указана", admin_id=ADMIN_CHAT_ID):
    """Добавляет пользователя в бан-лист"""
    try:
        username = username.lstrip('@').lower() if username else None
        cursor.execute(
            "INSERT OR REPLACE INTO bans (user_id, username, reason, admin_id) VALUES (?, ?, ?, ?)",
            (user_id, username, reason, admin_id)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка бана пользователя: {e}")
        return False

async def unban_user(user_id):
    """Удаляет пользователя из бан-листа"""
    try:
        cursor.execute("DELETE FROM bans WHERE user_id=?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Ошибка разбана пользователя: {e}")
        return False

async def get_ban_list():
    """Возвращает список всех забаненных пользователей"""
    cursor.execute("SELECT user_id, username, reason, admin_id, ban_date FROM bans")
    return cursor.fetchall()

# Проверка админских прав
def is_admin(user_id):
    return str(user_id) == ADMIN_CHAT_ID

# Получение баланса (с автоматическим созданием записи)
def get_balance(user_id):
    cursor.execute("INSERT OR IGNORE INTO balances (user_id, balance) VALUES (?, 0)", (user_id,))
    conn.commit()
    cursor.execute("SELECT balance FROM balances WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

# ===================== ОБРАБОТКА КОМАНД =====================
@dp.message_handler(commands=['start'], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()
    
    ban_reason = await is_banned(message.from_user.id)
    if ban_reason:
        await message.answer(f"❌ Вы заблокированы!\nПричина: {ban_reason}")
        return

    # Реферальная система
    args = message.get_args()
    if args.startswith('ref_'):
        try:
            referrer_id = int(args.split('_')[1])
            current_user_id = message.from_user.id
            
            if referrer_id != current_user_id:
                cursor.execute("SELECT 1 FROM referrals WHERE user_id=?", (current_user_id,))
                if not cursor.fetchone():
                    cursor.execute("INSERT OR IGNORE INTO balances (user_id, balance) VALUES (?, 0)", (referrer_id,))
                    cursor.execute("INSERT INTO referrals VALUES (?, ?)", (current_user_id, referrer_id))
                    cursor.execute("UPDATE balances SET balance = balance + 10 WHERE user_id = ?", (referrer_id,))
                    conn.commit()
                    
                    try:
                        await main_bot.send_message(
                            referrer_id,
                            f"🎉 Новый реферал! +10₽\nТекущий баланс: {get_balance(referrer_id)}₽"
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления: {e}")

        except (IndexError, ValueError, sqlite3.Error) as e:
            logger.error(f"Ошибка реферальной системы: {e}")

    # Главное меню
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("❤️ 100р - Простая ратка", callback_data="option1"),
        InlineKeyboardButton("💎 500р - Премиум пакет", callback_data="option2"),
        InlineKeyboardButton("🚀 1000р - VIP пакет", callback_data="option3")
    )
    
    try:
        await message.answer_photo(
            InputFile("troll.jpg"),
            caption="Привет✋! Давно хотел ратку, чтобы потроллить школьников, но нет пк?😿\n"
                   "Наша команда jikoRAT предлагает вам лучшего бота, за лучшую цену!\n"
                   "(если хотите функции, пропишите /info), также есть реферальная система /ref, чтобы проверить баланс напишите /balance",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка отправки фото: {e}")
        await message.answer(
            "Привет✋! Давно хотел ратку, чтобы потроллить школьников, но нет пк?😿\n"
            "Наша команда jikoRAT предлагает вам лучшего бота, за лучшую цену!",
            reply_markup=keyboard
        )

@dp.message_handler(commands=['info'])
async def show_info(message: types.Message):
    functions = [
        "📸 Скриншот - делает снимок экрана",
        "💻 Данные ПК - показывает информацию о компьютере",
        "📷 Фото с вебкамеры - делает фото с камеры",
        "🔗 Открыть ссылку - открывает URL в браузере",
        "📁 Создать папку - создает новую директорию",
        "🗑️ Удалить папку - удаляет указанную папку",
        "📝 Окно с текстом - показывает текстовое сообщение",
        "❌ Удалить файл - удаляет указанный файл",
        "⬇️ Скачать файл - загружает файл с URL",
        "🚀 Запустить файл - выполняет указанный файл",
        "🔊 Включить звук на 100% - устанавливает максимальную громкость",
        "🔇 Выключить звук - отключает звук полностью",
        "⏻ Выключить ПК - завершает работу компьютера",
        "🔄 Перезагрузить ПК - перезапускает систему",
        "⌨️ ALT + F4 - закрывает активное окно",
        "⬇️ Свернуть все окна - минимизирует все окна",
        "🌀 Свести с ума курсор - хаотично двигает курсор",
        "🖼️ Поменять обои - изменяет фоновое изображение",
        "✏️ Переименовать файл - изменяет имя файла",
        "🔒 Зашифровать файл - шифрует указанный файл",
        "🔓 Расшифровать файл - расшифровывает файл",
        "🎮 Логи Steam - собирает данные Steam",
        "🌐 Логи Chrome - собирает данные браузера",
        "🌐 Логи Opera - собирает данные Opera",
        "📱 Логи Telegram - собирает данные Telegram",
        "👻 Скример - показывает пугающее изображение",
        "📂 Скачать папку - загружает всю папку",
        "📊 Список процессов - показывает запущенные процессы",
        "❌ Закрыть программу - завершает указанный процесс",
        "💥 Самоуничтожение - удаляет следы программы",
        "🔄 Повернуть моник - меняет ориентацию экрана",
        "⌨️ Напечатать текст - имитирует ввод текста",
        "📄 Файл - работает с указанным файлом"
    ]
    
    response = "🚀 Доступные функции бота:\n\n" + "\n".join(f"• {func}" for func in functions)
    await message.answer(response)

# ===================== АДМИН КОМАНДЫ ДЛЯ БАНОВ =====================
@dp.message_handler(commands=['ban'])
async def ban_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /ban <user_id> [причина]")
        return

    try:
        user_id = int(args[1])
        reason = args[2] if len(args) > 2 else "Не указана"
        
        if await ban_user(user_id, reason=reason, admin_id=message.from_user.id):
            await message.reply(f"✅ Пользователь {user_id} забанен\nПричина: {reason}")
            try:
                await main_bot.send_message(user_id, f"❌ Вы были заблокированы в боте!\nПричина: {reason}")
            except:
                pass
        else:
            await message.reply("❌ Ошибка при бане пользователя")
    except ValueError:
        await message.reply("❌ ID должен быть числом")

@dp.message_handler(commands=['unban'])
async def unban_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /unban <user_id>")
        return

    try:
        user_id = int(args[1])
        if await unban_user(user_id):
            await message.reply(f"✅ Пользователь {user_id} разбанен")
            try:
                await main_bot.send_message(user_id, "🎉 Вы были разблокированы в боте!")
            except:
                pass
        else:
            await message.reply("❌ Пользователь не найден в бан-листе")
    except ValueError:
        await message.reply("❌ ID должен быть числом")

@dp.message_handler(commands=['banlist'])
async def ban_list_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    bans = await get_ban_list()
    if not bans:
        await message.reply("📭 Бан-лист пуст")
        return

    ban_list = "\n".join(
        f"{uid} | @{uname or 'нет'} | {reason} | {admin} | {date}"
        for uid, uname, reason, admin, date in bans
    )
    await message.reply(f"🚫 Бан-лист:\n\n{ban_list}")

# ===================== ОСТАЛЬНЫЕ КОМАНДЫ =====================
@dp.message_handler(commands=['ref'])
async def show_ref_link(message: types.Message):
    try:
        user_id = message.from_user.id
        bot_username = (await main_bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        await message.reply(
            f"🔗 Ваша реферальная ссылка:\n<code>{ref_link}</code>\n\n"
            f"За каждого приглашённого друга вы получаете <b>10₽</b>!\n"
            f"Ваш текущий баланс: <b>{get_balance(user_id)}₽</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка в команде /ref: {e}")
        await message.reply("❌ Произошла ошибка при генерации ссылки. Попробуйте позже.")

@dp.message_handler(commands=['balance'])
async def show_balance(message: types.Message):
    try:
        balance = get_balance(message.from_user.id)
        await message.reply(
            f"💰 Ваш баланс: <b>{balance}₽</b>\n\n"
            f"10₽ = 1 приглашённый друг",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка проверки баланса: {e}")
        await message.reply("❌ Не удалось проверить баланс. Попробуйте позже.")

# ===================== ОБРАБОТКА КНОПОК =====================
@dp.callback_query_handler(lambda call: True, state="*")
async def handle_buttons(call: types.CallbackQuery, state: FSMContext):
    try:
        if await is_banned(call.from_user.id):
            await call.answer("❌ Вы заблокированы!", show_alert=True)
            return

        if call.data in ["option1", "option2", "option3"]:
            price, name = PRICES[call.data]
            desc = {
                "option1": "❤️ Простая ратка, без ничего",
                "option2": "💎 Включает:\n- Ратку\n- Личную Поддержку владельца\n- Пак троллинга(очень лютый)",
                "option3": "🚀 Включает:\n- Ратку\n- Тутор как делать сами ратки\n- Личная Поддержка автора\n- Пак троллинга(очень лютый)\n- Поддержку автора для продолжения проекта ❤️"
            }[call.data]

            await call.message.answer(
                f"{name} за {price}\n{desc}",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("Купить ✅", callback_data=f"buy_{call.data}")
                )
            )

        elif call.data.startswith("buy_"):
            package = call.data.split("_")[1]
            price_rub = int(PRICES[package][0].split()[0])
            user_balance = get_balance(call.from_user.id)

            if user_balance >= price_rub:
                keyboard = InlineKeyboardMarkup()
                keyboard.add(
                    InlineKeyboardButton("Оплатить балансом 💰", callback_data=f"pay_balance_{package}")
                )
                await call.message.answer(
                    f"У вас достаточно средств! Баланс: <b>{user_balance}₽</b>\n"
                    f"Стоимость пакета: <b>{price_rub}₽</b>",
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                await call.message.answer(
                    f"💳 Оплата {PRICES[package][0]}:\n"
                    "https://www.donationalerts.com/r/jikorat\n\n"
                    "В комментарии укажите:\n"
                    f"1. Ваш @username\n"
                    f"2. Пакет: {PRICES[package][1]}\n\n"
                    "После оплаты нажмите:",
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("Я оплатил ✅", callback_data=f"paid_{package}")
                    )
                )

        elif call.data.startswith("paid_") or call.data.startswith("pay_balance_"):
            if call.data.startswith("paid_"):
                package = call.data.split("_")[1]
                payment_method = "DonationAlerts"
            else:
                package = call.data.split("_")[2]
                payment_method = "Баланс"
                price_rub = int(PRICES[package][0].split()[0])
                cursor.execute("UPDATE balances SET balance = balance - ? WHERE user_id = ?",
                              (price_rub, call.from_user.id))
                conn.commit()

            await PurchaseStates.waiting_for_token.set()
            await state.update_data(package=package, payment_method=payment_method)
            await call.message.answer("Введите токен бота:", reply_markup=ReplyKeyboardRemove())

        await call.answer()
    except Exception as e:
        logger.error(f"Ошибка обработки callback: {e}")
        await call.message.answer("❌ Произошла ошибка. Попробуйте позже.")

# ===================== ОБРАБОТКА СОСТОЯНИЙ =====================
@dp.message_handler(state=PurchaseStates.waiting_for_token)
async def process_token(message: types.Message, state: FSMContext):
    try:
        async with state.proxy() as data:
            data['bot_token'] = message.text
        
        await PurchaseStates.next()
        await message.answer("Теперь введите ID бота:")
    except Exception as e:
        logger.error(f"Ошибка обработки токена: {e}")
        await message.answer("❌ Ошибка обработки токена. Начните заново.")
        await state.finish()

@dp.message_handler(state=PurchaseStates.waiting_for_id)
async def process_id(message: types.Message, state: FSMContext):
    try:
        async with state.proxy() as data:
            user_id = message.from_user.id
            package = data['package']
            bot_token = data['bot_token']
            bot_id = message.text
            payment_method = data['payment_method']

            cursor.execute("INSERT INTO purchases VALUES (?, ?, ?, ?, datetime('now'))",
                          (user_id, package, bot_token, bot_id))
            conn.commit()

            if admin_bot:
                username = f"@{message.from_user.username}" if message.from_user.username else f"ID:{user_id}"
                text = (
                    f"🛒 Новая покупка!\n\n"
                    f"👤 Покупатель: {username}\n"
                    f"🆔 ID покупателя: `{user_id}`\n"
                    f"📦 Пакет: {PRICES[package][1]}\n"
                    f"💳 Способ оплаты: {payment_method}\n"
                    f"🔑 Токен бота: `{bot_token}`\n"
                    f"🆔 ID бота: `{bot_id}`\n\n"
                    f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                await admin_bot.send_message(ADMIN_CHAT_ID, text, parse_mode="Markdown")

        await message.answer(
            "✅ Данные получены! С вами свяжутся в ближайшее время.",
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        logger.error(f"Ошибка обработки ID: {e}")
        await message.answer("❌ Ошибка обработки данных. Попробуйте позже.")
    finally:
        await state.finish()

# ===================== ДОПОЛНИТЕЛЬНЫЕ АДМИН КОМАНДЫ =====================
@dp.message_handler(commands=['add_balance'])
async def add_balance(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    try:
        args = message.text.split()
        if len(args) < 3:
            await message.reply("Использование: /add_balance <user_id> <сумма>")
            return

        user_id = int(args[1])
        amount = int(args[2])
        
        cursor.execute("INSERT OR IGNORE INTO balances VALUES (?, ?)",
                      (user_id, 0))
        cursor.execute("UPDATE balances SET balance = balance + ? WHERE user_id = ?",
                      (amount, user_id))
        conn.commit()

        await message.reply(f"✅ Баланс пользователя {user_id} пополнен на {amount}₽")
        await main_bot.send_message(user_id, f"🎉 Вам начислено <b>{amount}₽</b>!", parse_mode="HTML")

    except (IndexError, ValueError):
        await message.reply("❌ Неверный формат команды. Использование: /add_balance <user_id> <сумма>")
    except Exception as e:
        logger.error(f"Ошибка добавления баланса: {e}")
        await message.reply("❌ Произошла ошибка при пополнении баланса")

if __name__ == '__main__':
    logger.info("Бот запущен")
    executor.start_polling(dp, skip_updates=True)
