import asyncio
import os
import random
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8710959012:AAHvJW3kU1RH3lgkoEM97TUt9k5f6yU1kOI"
ADMIN_IDS = [605614562, 531226742]

# ПУТЬ К ЛОГОТИПУ
LOGO_PATH = "logo.png"

# ПУТЬ К БАЗЕ ДАННЫХ НА ПОСТОЯННОМ ДИСКЕ RENDER
DB_PATH = "/data/ggc.db"

SOCIAL_LINKS = {
    "telegram": "https://t.me/GGCapitalist",
    "youtube": "https://www.youtube.com/@GGCapitalist"
}

WALLETS = {
    "TRC20": "TTnDwpzWX1WDAnAkaqbaoVVNGojjamujou",
    "BEP20": "0x7b05503a4a657a302c059c1c340206ac551be6d6"
}

TARIFFS = {
    "monthly": {"name": "1 месяц", "price": 30, "days": 30},
    "seasonal": {"name": "3 месяца", "price": 75, "days": 90}
}

PROMOCODES = {
    "GGC10": 10
}
# =====================================================

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class OrderState(StatesGroup):
    choosing_tariff = State()
    entering_promo = State()
    waiting_for_screenshot = State()

class AdminState(StatesGroup):
    waiting_for_link = State()
    waiting_for_mass_message = State()
    waiting_for_reset_confirmation = State()

class UserState(StatesGroup):
    waiting_for_support_message = State()

# ==================== РАБОТА С БАЗОЙ ДАННЫХ ====================

def init_db():
    """Создаёт таблицы в базе данных, если их нет"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            joined_at TEXT,
            subscription_end TEXT,
            ref_code TEXT UNIQUE,
            ref_by TEXT,
            ref_count INTEGER DEFAULT 0,
            ref_monthly_count INTEGER DEFAULT 0,
            ref_monthly_reset TEXT,
            ref_free_month_used INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица промокодов (реферальных)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ref_promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            code TEXT UNIQUE,
            discount INTEGER,
            created_at TEXT,
            used INTEGER DEFAULT 0,
            from_user TEXT
        )
    ''')
    
    # Таблица заявок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            user_id TEXT,
            username TEXT,
            tariff TEXT,
            price REAL,
            network TEXT,
            status TEXT,
            created_at TEXT,
            promo TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def reset_db():
    """Полностью очищает базу данных (удаляет все таблицы и создаёт заново)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Удаляем все таблицы
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS ref_promocodes")
    cursor.execute("DROP TABLE IF EXISTS orders")
    
    conn.commit()
    conn.close()
    
    # Создаём таблицы заново
    init_db()

def get_connection():
    """Возвращает соединение с базой данных"""
    return sqlite3.connect(DB_PATH)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def generate_ref_code(user_id: int) -> str:
    return f"ref_{user_id}"

def get_user_by_ref_code(ref_code: str) -> Optional[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE ref_code = ?", (ref_code,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def reset_monthly_ref_counts():
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("SELECT user_id, ref_monthly_reset FROM users")
    rows = cursor.fetchall()
    for user_id, last_reset in rows:
        if last_reset:
            last_reset_date = datetime.fromisoformat(last_reset)
            if (datetime.now() - last_reset_date).days >= 30:
                cursor.execute("UPDATE users SET ref_monthly_count = 0, ref_monthly_reset = ? WHERE user_id = ?", (now, user_id))
    conn.commit()
    conn.close()

# ==================== КЛАВИАТУРЫ ====================

def get_bottom_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Главное меню")],
            [KeyboardButton(text="💰 Купить"), KeyboardButton(text="👥 Рефералка")],
            [KeyboardButton(text="👤 Статус"), KeyboardButton(text="📩 Поддержка")],
            [KeyboardButton(text="ℹ️ Информация"), KeyboardButton(text="⭐ Отзывы")],
            [KeyboardButton(text="🌐 Соцсети")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )
    return builder

def get_tariff_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"📆 {TARIFFS['monthly']['name']} — ${TARIFFS['monthly']['price']}", callback_data="tariff_monthly")
    builder.button(text=f"📅 {TARIFFS['seasonal']['name']} — ${TARIFFS['seasonal']['price']}", callback_data="tariff_seasonal")
    builder.button(text="◀️ Отмена", callback_data="cancel_action")
    builder.adjust(1)
    return builder.as_markup()

def get_social_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Telegram канал", url=SOCIAL_LINKS["telegram"])
    builder.button(text="🎥 YouTube канал", url=SOCIAL_LINKS["youtube"])
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_support_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Написать в поддержку", callback_data="write_to_support")
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_referral_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Скопировать ссылку", callback_data="copy_ref_link")
    builder.button(text="🎟 Мои промокоды", callback_data="my_promocodes")
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

def get_admin_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Просмотр заявок", callback_data="admin_view_orders")
    builder.button(text="📊 Активные подписки", callback_data="admin_active")
    builder.button(text="📈 Статистика", callback_data="admin_stats")
    builder.button(text="📢 Массовое уведомление", callback_data="admin_mass_message")
    builder.button(text="🔙 Выйти", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

# ==================== ТЕКСТЫ ====================

def get_welcome_text(username: str) -> str:
    return f"""
*Добро пожаловать в GGC —  здесь трейдинг перестаёт быть хаотичной гонкой за сделками и превращается в путь системного развития 🧠*

Мы сосредоточены на том, что действительно делает трейдера профессионалом: ясное понимание стратегии, дисциплина, грамотный риск-менеджмент и психологическая устойчивость.

Наша цель — не просто обучать техническим инструментам. *Мы помогаем формировать мышление и структуру,* которые позволяют выдерживать давление рынка и принимать взвешенные решения.

Мы создаём сообщество, где каждый участник получает поддержку, делится опытом и прогрессом, а также учится объективно смотреть на рынок через призму вероятностей. 

Мы сделаем всё, чтобы ваше пребывание здесь было максимально комфортным и продуктивным. Мы всегда направим, поддержим и поможем. 

Мы строим не просто коммьюнити — мы строим семью.
"""

def get_whats_inside_text() -> str:
    return """
📦 **Что входит в подписку GGC Community:**

Доступ в приватный Discord-сервер:

1️⃣  *Ежедневный Pre-market анализ* — составление торговых планов на неделю/день

2️⃣  *Образовательные лекции* — принципы анализа рынка, которые действительно работают

3️⃣  *Бектесты с участниками* — демонстрируете экран и на основе полученных знаний рассказываете, как бы вы анализировали график. Менторы GGC разбирают и исправляют ошибки. Рост навыков в реальном времени

4️⃣  *Weekly + QA конференции* — разбираем торговую неделю, сделки участников. Отвечаем на любые вопросы

5️⃣  *Настроим терминал* — полная подготовка софта к торговле. Поможем зарегистрировать аккаунт. Расскажем, как получить финансирование от проп компании

6️⃣  *Лайв-торговля* — совместно с менторами GGC - работаем в реальном рынке. Открываем сделки, получаем результат

7️⃣  *Поддержка 24/7* — составление плана обучения, формируем торговую стратегию. Индивидуальный подход к каждому участнику"""

def get_reviews_text() -> str:
    return """
⭐ *Отзывы наших участников:*

• https://t.me/GGCapitalist/120
• https://t.me/GGCapitalist/186
• https://t.me/GGCapitalist/167
• https://t.me/GGCapitalist/156
• https://t.me/GGCapitalist/142
• https://t.me/GGCapitalist/125

📈 *Сделки, которые мы открываем:*

[Сделка 1](https://t.me/GGCapitalist/188) • [Сделка 2](https://t.me/GGCapitalist/181) • [Сделка 3](https://t.me/GGCapitalist/179) • [Сделка 4](https://t.me/GGCapitalist/178) • [Сделка 5](https://t.me/GGCapitalist/174) • [Сделка 6](https://t.me/GGCapitalist/149) • [Сделка 7](https://t.me/GGCapitalist/140) • [Сделка 8](https://t.me/GGCapitalist/138) • [Сделка 9](https://t.me/GGCapitalist/107) • [Сделка 10](https://t.me/GGCapitalist/92) • [Сделка 11](https://t.me/GGCapitalist/53)

*Больше результатов — в нашем канале!* 🔥
"""

def get_social_text() -> str:
    return """
🌐 *Наши соцсети:*

📱 *Telegram-канал:* там публикуем результаты сделок, успехи участников и анонсы
🎥 *YouTube-канал:* обучающие видео, разборы рынка, настройка терминала

Подписывайся, чтобы быть в курсе! 👇
"""

# ==================== ОСНОВНЫЕ ОБРАБОТЧИКИ ====================

async def send_welcome_with_logo(target, username: str):
    """Утилита для отправки приветствия с логотипом"""
    try:
        photo = FSInputFile(LOGO_PATH)
        await target.answer_photo(
            photo=photo,
            caption=get_welcome_text(username),
            parse_mode="Markdown",
            reply_markup=get_bottom_keyboard()
        )
    except Exception as e:
        print(f"Ошибка при отправке логотипа: {e}")
        await target.answer(
            get_welcome_text(username),
            parse_mode="Markdown",
            reply_markup=get_bottom_keyboard()
        )

# КОМАНДА ДЛЯ СБРОСА БАЗЫ ДАННЫХ (ТОЛЬКО ДЛЯ АДМИНОВ)
@dp.message(Command("reset_db"))
async def cmd_reset_db(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ДА, УДАЛИТЬ ВСЁ", callback_data="reset_confirm")],
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="reset_cancel")]
    ])
    
    await message.answer(
        "⚠️ *ВНИМАНИЕ!*\n\n"
        "Вы собираетесь полностью очистить базу данных.\n\n"
        "Будут удалены:\n"
        "• Все пользователи\n"
        "• Все подписки\n"
        "• Все заявки\n"
        "• Все реферальные промокоды\n\n"
        "Это действие НЕЛЬЗЯ отменить.\n\n"
        "Вы уверены?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await state.set_state(AdminState.waiting_for_reset_confirmation)

@dp.callback_query(lambda c: c.data == "reset_confirm")
async def reset_confirm(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    # Очищаем базу данных
    reset_db()
    
    await callback.message.edit_text(
        "✅ *База данных полностью очищена!*\n\n"
        "Бот готов к релизу. Все тестовые данные удалены.",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data == "reset_cancel")
async def reset_cancel(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "❌ Очистка базы данных отменена.",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()
    await callback.answer()

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    username = message.from_user.username or message.from_user.first_name
    
    ref_code = None
    if message.text and " " in message.text:
        ref_code = message.text.split(" ", 1)[1]
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Проверяем, существует ли пользователь
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user_exists = cursor.fetchone()
    
    if not user_exists:
        invited_by = None
        if ref_code:
            inviter_id = get_user_by_ref_code(ref_code)
            if inviter_id and inviter_id != user_id:
                invited_by = inviter_id
        
        # Создаём пользователя
        ref_code_gen = generate_ref_code(int(user_id))
        now_str = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO users (user_id, username, joined_at, subscription_end, ref_code, ref_by, ref_monthly_reset)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, now_str, None, ref_code_gen, invited_by, now_str))
        
        # --- ЛОГИКА ПРИГЛАШЕНИЯ (БЕЗ ВЫДАЧИ ПРОМОКОДА) ---
        if invited_by:
            # Увеличиваем счётчик приглашений
            cursor.execute("UPDATE users SET ref_count = ref_count + 1, ref_monthly_count = ref_monthly_count + 1 WHERE user_id = ?", (invited_by,))
            
            # Проверяем сброс месячного счётчика
            cursor.execute("SELECT ref_monthly_reset FROM users WHERE user_id = ?", (invited_by,))
            last_reset_row = cursor.fetchone()
            if last_reset_row and last_reset_row[0]:
                last_reset_date = datetime.fromisoformat(last_reset_row[0])
                if (datetime.now() - last_reset_date).days >= 30:
                    cursor.execute("UPDATE users SET ref_monthly_count = 1, ref_monthly_reset = ? WHERE user_id = ?", (datetime.now().isoformat(), invited_by))
            
            # Отправляем уведомление о новом реферале, но БЕЗ ПРОМОКОДА
            try:
                await bot.send_message(
                    int(invited_by),
                    f"🔔 *Новый реферал!*\n\n"
                    f"Пользователь @{username} перешёл по вашей ссылке и зарегистрировался.\n"
                    f"💰 Промокод на скидку 10$ будет начислен *после оплаты подписки* новым пользователем.\n\n"
                    f"Всего приглашений: (обновится позже)\n"
                    f"За этот месяц: (обновится позже)",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        conn.commit()
    
    conn.close()
    await send_welcome_with_logo(message, username)

@dp.message(lambda message: message.text == "🏠 Главное меню")
async def main_menu_button(message: types.Message, state: FSMContext):
    await state.clear()
    await send_welcome_with_logo(message, message.from_user.first_name)

@dp.message(lambda message: message.text in ["💰 Купить", "👥 Рефералка", "👤 Статус", "📩 Поддержка", "ℹ️ Информация", "⭐ Отзывы", "🌐 Соцсети"])
async def handle_bottom_buttons(message: types.Message, state: FSMContext):
    await state.clear()
    text = message.text
    
    if text == "💰 Купить":
        await message.answer(
            "💳 *Выбери тариф подписки:*\n\n_После выбора ты сможешь ввести промокод при наличии._",
            parse_mode="Markdown",
            reply_markup=get_tariff_keyboard()
        )
    elif text == "👥 Рефералка":
        await show_referral_info(message, message.from_user.id)
    elif text == "👤 Статус":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT subscription_end FROM users WHERE user_id = ?", (str(message.from_user.id),))
        row = cursor.fetchone()
        conn.close()
        
        sub_end = row[0] if row else None
        
        if sub_end:
            end_date = datetime.fromisoformat(sub_end)
            days_left = (end_date - datetime.now()).days
            if days_left > 0:
                status_text = f"✅ *Подписка активна*\nОсталось дней: {days_left}\nДействует до: {end_date.strftime('%d.%m.%Y')}"
            else:
                status_text = "❌ *Подписка истекла*\nПриобретите новую для доступа в Discord."
        else:
            status_text = "ℹ️ *Нет активной подписки*\nНажми «💰 Купить», чтобы получить доступ."
        
        await message.answer(status_text, parse_mode="Markdown", reply_markup=get_back_keyboard())
    elif text == "📩 Поддержка":
        await message.answer(
            "🆘 *Поддержка GGC*\n\nНапишите нам, и мы поможем:",
            parse_mode="Markdown",
            reply_markup=get_support_keyboard()
        )
    elif text == "ℹ️ Информация":
        await message.answer(get_whats_inside_text(), parse_mode="Markdown", reply_markup=get_back_keyboard())
    elif text == "⭐ Отзывы":
        await message.answer(get_reviews_text(), parse_mode="Markdown", reply_markup=get_back_keyboard())
    elif text == "🌐 Соцсети":
        await message.answer(get_social_text(), parse_mode="Markdown", reply_markup=get_social_keyboard())

@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await send_welcome_with_logo(callback.message, callback.from_user.first_name)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel_action")
async def cancel_action(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await send_welcome_with_logo(callback.message, callback.from_user.first_name)
    await callback.answer()

async def show_referral_info(msg: types.Message, user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ref_code, ref_count, ref_monthly_count, ref_free_month_used FROM users WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await msg.answer("Ошибка: пользователь не найден")
        return
    
    ref_code, ref_count, ref_monthly, free_month_used = row
    
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={ref_code}"
    
    text = f"""
👥 *Реферальная программа GGC*

🔗 *Ваша реферальная ссылка:*
`{ref_link}`

📊 *Ваша статистика:*
• Всего приглашений: {ref_count}
• За этот месяц: {ref_monthly}

🎁 *Бонусы:*
• За 1 приглашение → промокод на скидку 10$ (выдаётся ПОСЛЕ оплаты подписки новым пользователем)
• За 3 приглашения за месяц → бесплатный месяц подписки

{f"✅ *Бесплатный месяц уже получен!*" if free_month_used else "⚠️ *До бесплатного месяца:* " + str(3 - min(ref_monthly, 3)) + " приглашений"}

*Как это работает:*
1. Отправьте ссылку другу
2. Друг переходит по ссылке и регистрируется
3. Друг покупает подписку
4. Вы получаете промокод на 10$ и +1 к счётчику
5. Пригласите 3 друзей за месяц — получите месяц бесплатно
"""
    
    await msg.answer(text, parse_mode="Markdown", reply_markup=get_referral_keyboard())

@dp.callback_query(lambda c: c.data == "copy_ref_link")
async def copy_ref_link(callback: types.CallbackQuery):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ref_code FROM users WHERE user_id = ?", (str(callback.from_user.id),))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await callback.answer("Ошибка", show_alert=True)
        return
    
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={row[0]}"
    
    await callback.answer(f"Ссылка скопирована!", show_alert=False)
    await callback.message.answer(
        f"🔗 *Ваша реферальная ссылка:*\n`{ref_link}`\n\nОтправьте её другу!",
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data == "my_promocodes")
async def my_promocodes(callback: types.CallbackQuery):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT code, discount, created_at, used FROM ref_promocodes WHERE user_id = ? ORDER BY created_at DESC", (str(callback.from_user.id),))
    rows = cursor.fetchall()
    conn.close()
    
    active_codes = [row for row in rows if not row[3]]
    
    if not active_codes:
        text = "🎟 *Ваши промокоды*\n\nУ вас пока нет активных промокодов.\nПригласите друга, и после его оплаты вы получите скидку 10$!"
    else:
        text = "🎟 *Ваши промокоды:*\n\n"
        for p in active_codes:
            text += f"• `{p[0]}` — скидка ${p[1]} (от {p[2][:10]})\n"
        text += "\n*Как использовать:*\nПри оформлении подписки введите промокод в специальное поле."
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_referral_keyboard())
    await callback.answer()

# ==================== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (ПОДПИСКА) ====================

@dp.callback_query(lambda c: c.data.startswith("tariff_"))
async def handle_tariff(callback: types.CallbackQuery, state: FSMContext):
    tariff_key = callback.data.replace("tariff_", "")
    if tariff_key not in TARIFFS:
        await callback.answer("Неверный тариф", show_alert=True)
        return
    
    tariff = TARIFFS[tariff_key]
    await state.update_data(tariff=tariff_key, price=tariff["price"])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Есть промокод", callback_data="has_promo")],
        [InlineKeyboardButton(text="🚫 Без промокода", callback_data="no_promo")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel_action")]
    ])
    
    await callback.message.edit_text(
        f"💳 *Выбран тариф: {tariff['name']} — ${tariff['price']}*\n\nУ вас есть промокод на скидку?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["has_promo", "no_promo"])
async def handle_promo_choice(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "has_promo":
        await callback.message.edit_text(
            "🎟 *Введите промокод:*\n\nНапишите код в сообщении.\n\nДля отмены введите /cancel",
            parse_mode="Markdown"
        )
        await state.set_state(OrderState.entering_promo)
    else:
        await state.update_data(discount=0, promo_code=None)
        await show_payment_info(callback.message, state)
    await callback.answer()

@dp.message(OrderState.entering_promo)
async def process_promo(message: types.Message, state: FSMContext):
    promo = message.text.strip().upper()
    discount = 0
    
    if promo in PROMOCODES:
        discount = PROMOCODES[promo]
        await state.update_data(discount=discount, promo_code=promo, is_ref_promo=False)
        await message.answer(f"✅ Промокод применён! Скидка ${discount}")
        await show_payment_info(message, state)
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, discount FROM ref_promocodes WHERE code = ? AND used = 0", (promo,))
    row = cursor.fetchone()
    
    if row:
        discount = row[1]
        cursor.execute("UPDATE ref_promocodes SET used = 1 WHERE code = ?", (promo,))
        conn.commit()
        await state.update_data(discount=discount, promo_code=promo, is_ref_promo=True)
        await message.answer(f"✅ Реферальный промокод применён! Скидка ${discount}")
        await show_payment_info(message, state)
        conn.close()
        return
    
    conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Попробовать другой", callback_data="has_promo")],
        [InlineKeyboardButton(text="🚫 Продолжить без промокода", callback_data="no_promo")]
    ])
    await message.answer(
        f"❌ Промокод «{promo}» не найден или уже использован.\n\nПопробуйте другой или продолжите без скидки.",
        reply_markup=keyboard
    )

async def show_payment_info(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    tariff_key = data["tariff"]
    tariff = TARIFFS[tariff_key]
    base_price = tariff["price"]
    discount = data.get("discount", 0)
    final_price = base_price - discount
    
    await state.update_data(final_price=final_price)
    
    order_id = random.randint(100000, 999999)
    await state.update_data(order_id=order_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 TRC20 (USDT)", callback_data=f"network_TRC20_{order_id}")],
        [InlineKeyboardButton(text="🌐 BEP20 (USDT)", callback_data=f"network_BEP20_{order_id}")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel_action")]
    ])
    
    payment_text = f"""
💳 *Детали заказа #{order_id}*

Тариф: {tariff['name']}
Базовая цена: ${base_price}
Скидка: ${discount}
*Итого к оплате: ${final_price}*

Выберите сеть для оплаты USDT:
"""
    await msg.answer(payment_text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("network_"))
async def handle_network(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    network = parts[1]
    order_id = int(parts[2])
    await state.update_data(network=network, order_id=order_id)
    
    wallet_address = WALLETS[network]
    final_price = (await state.get_data()).get("final_price", 0)
    
    payment_text = f"""
💳 *Оплата заказа #{order_id}*

Сеть: {network}
Кошелёк: `{wallet_address}`
Сумма: ${final_price} USDT

*Инструкция:*
1. Отправьте ровно указанную сумму USDT на кошелёк
2. Сделайте скриншот успешной транзакции
3. Пришлите скриншот в этот чат

❗ *Важно:* Отправляйте точную сумму. После оплаты пришлите скриншот для подтверждения администратором.
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="paid")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel_action")]
    ])
    await callback.message.edit_text(payment_text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "paid")
async def handle_paid(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📸 *Отправьте скриншот оплаты*\n\nПришлите фото или скриншот, подтверждающий перевод.\nАдминистратор проверит и подтвердит доступ.\n\nДля отмены введите /cancel",
        parse_mode="Markdown"
    )
    await state.set_state(OrderState.waiting_for_screenshot)
    await callback.answer()

@dp.message(OrderState.waiting_for_screenshot, lambda m: m.photo or m.document)
async def process_screenshot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    order_id = data["order_id"]
    user_id = str(message.from_user.id)
    username = message.from_user.username or message.from_user.first_name
    tariff = data["tariff"]
    price = data["final_price"]
    network = data.get("network")
    promo = data.get("promo_code")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (order_id, user_id, username, tariff, price, network, status, created_at, promo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (order_id, user_id, username, tariff, price, network, "pending", datetime.now().isoformat(), promo))
    conn.commit()
    conn.close()
    
    admin_text = f"""
🆕 *НОВАЯ ЗАЯВКА #{order_id}*

👤 Пользователь: @{username} (ID: {user_id})
💰 Тариф: {TARIFFS[tariff]['name']}
💵 Сумма: ${price} USDT
🌐 Сеть: {network}
🎟 Промокод: {promo if promo else 'нет'}

✅ Статус: ожидает подтверждения
"""
    for admin_id in ADMIN_IDS:
        try:
            if message.photo:
                file_id = message.photo[-1].file_id
                await bot.send_photo(admin_id, file_id, caption=admin_text, parse_mode="Markdown")
            elif message.document:
                file_id = message.document.file_id
                await bot.send_document(admin_id, file_id, caption=admin_text, parse_mode="Markdown")
        except Exception as e:
            print(f"Не удалось отправить админу {admin_id}: {e}")
    
    await message.answer(
        "✅ *Заявка отправлена!*\n\nАдминистратор проверит оплату в ближайшее время.\nКак только подтвердим — вы получите ссылку-приглашение в Discord.\n\nСпасибо, что с нами! 🙌",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    await state.clear()

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        parse_mode="Markdown",
        reply_markup=get_bottom_keyboard()
    )

# ==================== АДМИНКА ====================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    await message.answer("🔐 *Панель администратора*\n\nВыберите действие:", parse_mode="Markdown", reply_markup=get_admin_keyboard())

# НОВАЯ КОМАНДА ДЛЯ ИЗМЕНЕНИЯ ДАТЫ ОКОНЧАНИЯ ПОДПИСКИ
@dp.message(Command("set_end_date"))
async def cmd_set_end_date(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    
    args = message.text.split()
    if len(args) != 3:
        await message.answer(
            "❌ *Неверный формат команды*\n\n"
            "Использование:\n"
            "`/set_end_date @username ДД.ММ.ГГГГ`\n\n"
            "Пример:\n"
            "`/set_end_date @timgymof 15.05.2025`",
            parse_mode="Markdown"
        )
        return
    
    username = args[1].lstrip('@')
    new_date_str = args[2]
    
    # Проверяем формат даты
    try:
        new_end_date = datetime.strptime(new_date_str, "%d.%m.%Y")
    except ValueError:
        await message.answer(
            "❌ *Неверный формат даты*\n\n"
            "Используйте формат: `ДД.ММ.ГГГГ`\n"
            "Пример: `15.05.2025`",
            parse_mode="Markdown"
        )
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Ищем пользователя по username
    cursor.execute("SELECT user_id, subscription_end, username FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    
    if not user:
        # Пробуем найти по @username (без @)
        cursor.execute("SELECT user_id, subscription_end, username FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
    
    if not user:
        await message.answer(f"❌ Пользователь @{username} не найден в базе данных.")
        conn.close()
        return
    
    user_id, old_end_date_str, user_username = user
    
    # Обновляем дату
    cursor.execute("UPDATE users SET subscription_end = ? WHERE user_id = ?", (new_end_date.isoformat(), user_id))
    conn.commit()
    conn.close()
    
    # Формируем ответ
    old_end_date = datetime.fromisoformat(old_end_date_str) if old_end_date_str else None
    old_date_str = old_end_date.strftime('%d.%m.%Y') if old_end_date else "не была установлена"
    
    await message.answer(
        f"✅ *Дата окончания подписки обновлена!*\n\n"
        f"👤 Пользователь: @{user_username}\n"
        f"📅 Было: {old_date_str}\n"
        f"📅 Стало: {new_end_date.strftime('%d.%m.%Y')}\n\n"
        f"Пользователь получит уведомление об изменении.",
        parse_mode="Markdown"
    )
    
    # Отправляем уведомление пользователю
    try:
        await bot.send_message(
            int(user_id),
            f"📅 *Изменение даты подписки*\n\n"
            f"Администратор изменил дату окончания вашей подписки.\n"
            f"Новая дата: *{new_end_date.strftime('%d.%m.%Y')}*\n\n"
            f"Если у вас есть вопросы — напишите в поддержку.",
            parse_mode="Markdown",
            reply_markup=get_back_keyboard()
        )
    except Exception as e:
        await message.answer(f"⚠️ Не удалось отправить уведомление пользователю: {e}")

@dp.callback_query(lambda c: c.data == "admin_view_orders")
async def admin_view_orders(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT order_id, username, price FROM orders WHERE status = 'pending'")
    pending_orders = cursor.fetchall()
    conn.close()
    
    if not pending_orders:
        await callback.message.edit_text("📭 *Нет новых заявок*", parse_mode="Markdown", reply_markup=get_admin_keyboard())
    else:
        text = "📋 *Заявки на подтверждение:*\n\n"
        for o in pending_orders:
            text += f"🆕 #{o[0]} | @{o[1]} | ${o[2]}\n"
        
        builder = InlineKeyboardBuilder()
        for o in pending_orders:
            builder.button(text=f"#{o[0]} - @{o[1]}", callback_data=f"approve_{o[0]}")
        builder.button(text="◀️ Назад", callback_data="back_to_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("approve_"))
async def admin_approve_order(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    order_id = int(callback.data.replace("approve_", ""))
    await state.update_data(approve_order_id=order_id)
    
    await callback.message.edit_text(
        f"🔗 *Введите ссылку-приглашение в Discord для заявки #{order_id}*\n\n"
        f"Пример: `https://discord.gg/xxxxxx`\n\n"
        f"Отправьте ссылку одним сообщением.\n"
        f"Для отмены введите /cancel",
        parse_mode="Markdown"
    )
    await state.set_state(AdminState.waiting_for_link)
    await callback.answer()

@dp.message(AdminState.waiting_for_link)
async def process_admin_link(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        await state.clear()
        return
    
    discord_link = message.text.strip()
    
    if not ("discord.gg" in discord_link or "discord.com/invite" in discord_link):
        await message.answer(
            "❌ Ссылка не похожа на приглашение в Discord.\n"
            "Ссылка должна содержать discord.gg или discord.com/invite\n\n"
            "Попробуйте ещё раз или отправьте /cancel"
        )
        return
    
    data = await state.get_data()
    order_id = data.get("approve_order_id")
    
    if not order_id:
        await message.answer("❌ Ошибка: заявка не найдена. Начните заново через /admin")
        await state.clear()
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id, username, tariff FROM orders WHERE order_id = ? AND status = 'pending'", (order_id,))
    order = cursor.fetchone()
    
    if not order:
        await message.answer(f"❌ Заявка #{order_id} не найдена или уже обработана")
        conn.close()
        await state.clear()
        return
    
    user_id, username, tariff_key = order
    
    # --- 1. Обновляем статус заявки ---
    cursor.execute("UPDATE orders SET status = 'approved' WHERE order_id = ?", (order_id,))
    
    # --- 2. Активируем подписку ---
    tariff = TARIFFS[tariff_key]
    end_date = datetime.now() + timedelta(days=tariff["days"])
    
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO users (user_id, username, joined_at, subscription_end, ref_code)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, datetime.now().isoformat(), end_date.isoformat(), generate_ref_code(int(user_id))))
    else:
        cursor.execute("UPDATE users SET subscription_end = ? WHERE user_id = ?", (end_date.isoformat(), user_id))
    
    # --- 3. ВЫДАЁМ РЕФЕРАЛЬНЫЙ ПРОМОКОД (ЕСЛИ ЕСТЬ ПРИГЛАСИВШИЙ) ---
    cursor.execute("SELECT ref_by FROM users WHERE user_id = ?", (user_id,))
    ref_result = cursor.fetchone()
    if ref_result and ref_result[0]:
        inviter_id = ref_result[0]
        # Генерируем уникальный промокод для пригласившего
        promo_code = f"REF{user_id}_{random.randint(1000, 9999)}"
        cursor.execute('''
            INSERT INTO ref_promocodes (user_id, code, discount, created_at, from_user)
            VALUES (?, ?, ?, ?, ?)
        ''', (inviter_id, promo_code, 10, datetime.now().isoformat(), username))
        
        # Отправляем уведомление пригласившему
        try:
            await bot.send_message(
                int(inviter_id),
                f"🎉 *Вы получили промокод!*\n\n"
                f"Пользователь @{username}, которого вы пригласили, только что оплатил подписку!\n"
                f"Ваш промокод на скидку 10$: `{promo_code}`\n\n"
                f"Спасибо, что делитесь GGC!",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Не удалось отправить промокод пригласившему {inviter_id}: {e}")
    
    conn.commit()
    conn.close()
    
    # --- 4. Отправляем ссылку пользователю ---
    user_message = f"""
✅ *Оплата подтверждена!*

Доступ к GGC Community активирован до {end_date.strftime('%d.%m.%Y')}

🔗 *Ваша ссылка-приглашение в Discord:*  
{discord_link}

⚠️ Ссылка одноразовая. Если не сработала — напишите в поддержку.

Добро пожаловать в комьюнити! 🚀
"""
    
    try:
        await bot.send_message(int(user_id), user_message, parse_mode="Markdown", reply_markup=get_back_keyboard())
        await message.answer(
            f"✅ *Заявка #{order_id} подтверждена!*\n\n"
            f"Пользователь: @{username}\n"
            f"Тариф: {tariff['name']}\n"
            f"Подписка действует до: {end_date.strftime('%d.%m.%Y')}\n\n"
            f"✅ Ссылка отправлена пользователю!"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке пользователю: {e}\n\nПодписка активирована, но ссылку придётся отправить вручную.\nСсылка: {discord_link}")
    
    await message.answer("🔐 *Панель администратора*\n\nВыберите действие:", parse_mode="Markdown", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_active")
async def admin_active(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("SELECT username, subscription_end FROM users WHERE subscription_end > ?", (now,))
    active = cursor.fetchall()
    conn.close()
    
    if not active:
        text = "📊 *Активные подписки*\n\nНет активных подписок"
    else:
        text = "📊 *Активные подписки*\n\n"
        for username, sub_end in active:
            end_date = datetime.fromisoformat(sub_end)
            days_left = (end_date - datetime.now()).days
            text += f"• @{username} — осталось {days_left} дн. (до {end_date.strftime('%d.%m.%Y')})\n"
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end > ?", (now.isoformat(),))
    active_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(price) FROM orders WHERE status = 'approved'")
    total_revenue_row = cursor.fetchone()
    total_revenue = total_revenue_row[0] if total_revenue_row[0] else 0
    
    current_month = now.month
    current_year = now.year
    cursor.execute('''
        SELECT SUM(price) FROM orders 
        WHERE status = 'approved' 
        AND strftime('%m', created_at) = ? AND strftime('%Y', created_at) = ?
    ''', (str(current_month).zfill(2), str(current_year)))
    monthly_revenue_row = cursor.fetchone()
    monthly_revenue = monthly_revenue_row[0] if monthly_revenue_row[0] else 0
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE ref_count > 0")
    users_with_refs = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(ref_count) FROM users")
    total_refs_row = cursor.fetchone()
    total_refs = total_refs_row[0] if total_refs_row[0] else 0
    
    conn.close()
    
    stats_text = f"""
📈 *СТАТИСТИКА GGC COMMUNITY*

👥 *Пользователи:*
• Всего подписчиков: {total_users}
• Активных подписок: {active_count}

💰 *Доход:*
• За всё время: ${total_revenue:.2f}
• За текущий месяц: ${monthly_revenue:.2f}

👥 *Реферальная программа:*
• Пользователей с рефералами: {users_with_refs}
• Всего приглашений: {total_refs}
"""
    
    await callback.message.edit_text(stats_text, parse_mode="Markdown", reply_markup=get_admin_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_mass_message")
async def admin_mass_message(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📢 *Массовое уведомление*\n\n"
        "Отправьте сообщение для всех активных подписчиков.\n\n"
        "Вы можете отправить:\n"
        "• Текст\n"
        "• Текст + фото\n"
        "• Текст + ссылку\n\n"
        "Для отмены введите /cancel",
        parse_mode="Markdown"
    )
    await state.set_state(AdminState.waiting_for_mass_message)
    await callback.answer()

@dp.message(AdminState.waiting_for_mass_message)
async def process_mass_message(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        await state.clear()
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("SELECT user_id FROM users WHERE subscription_end > ?", (now,))
    active_users = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if not active_users:
        await message.answer("❌ Нет активных подписчиков для рассылки.")
        await state.clear()
        return
    
    success_count = 0
    fail_count = 0
    
    if message.photo:
        photo = message.photo[-1]
        caption = message.caption or "📢 *Уведомление от администрации GGC*"
        
        for user_id in active_users:
            try:
                await bot.send_photo(int(user_id), photo.file_id, caption=caption, parse_mode="Markdown")
                success_count += 1
                await asyncio.sleep(0.05)
            except:
                fail_count += 1
    
    elif message.document:
        doc = message.document
        caption = message.caption or "📢 *Уведомление от администрации GGC*"
        
        for user_id in active_users:
            try:
                await bot.send_document(int(user_id), doc.file_id, caption=caption, parse_mode="Markdown")
                success_count += 1
                await asyncio.sleep(0.05)
            except:
                fail_count += 1
    
    else:
        text = f"📢 *Уведомление от администрации GGC*\n\n{message.text}"
        
        for user_id in active_users:
            try:
                await bot.send_message(int(user_id), text, parse_mode="Markdown")
                success_count += 1
                await asyncio.sleep(0.05)
            except:
                fail_count += 1
    
    await message.answer(
        f"✅ *Рассылка завершена!*\n\n"
        f"📤 Отправлено: {success_count}\n"
        f"❌ Не доставлено: {fail_count}\n"
        f"👥 Всего подписчиков: {len(active_users)}",
        parse_mode="Markdown"
    )
    
    await message.answer("🔐 *Панель администратора*\n\nВыберите действие:", parse_mode="Markdown", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.callback_query(lambda c: c.data == "write_to_support")
async def write_to_support(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 *Написать в поддержку*\n\n"
        "Напишите ваше сообщение одним сообщением.\n"
        "Администраторы GGC ответят вам в ближайшее время.\n\n"
        "Для отмены введите /cancel",
        parse_mode="Markdown"
    )
    await state.set_state(UserState.waiting_for_support_message)
    await callback.answer()

@dp.message(UserState.waiting_for_support_message)
async def process_support_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    admin_text = f"""
📩 *НОВОЕ СООБЩЕНИЕ В ПОДДЕРЖКУ*

👤 Пользователь: @{username} (ID: {user_id})
💬 Сообщение:
{message.text}

*Чтобы ответить:* отправьте сообщение этому пользователю напрямую
"""
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, parse_mode="Markdown")
        except:
            pass
    
    await message.answer(
        "✅ *Сообщение отправлено!*\n\n"
        "Администраторы GGC свяжутся с вами в ближайшее время.\n\n"
        "А пока можете вернуться в меню:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    await state.clear()

# ==================== НАПОМИНАНИЯ ====================

async def check_expiring_subscriptions():
    while True:
        try:
            reset_monthly_ref_counts()
            conn = get_connection()
            cursor = conn.cursor()
            now = datetime.now()
            cursor.execute("SELECT user_id, subscription_end FROM users WHERE subscription_end IS NOT NULL")
            rows = cursor.fetchall()
            conn.close()
            
            for user_id, sub_end_str in rows:
                if not sub_end_str:
                    continue
                end_date = datetime.fromisoformat(sub_end_str)
                days_left = (end_date - now).days
                if days_left == 7:
                    await bot.send_message(int(user_id), f"⏰ *Напоминание:* Ваша подписка истекает через 7 дней — {end_date.strftime('%d.%m.%Y')}\n\nПродлите доступ, чтобы не потерять связь с комьюнити!", parse_mode="Markdown")
                elif days_left == 3:
                    await bot.send_message(int(user_id), f"⚠️ *Подписка истекает через 3 дня!*\n\nДата окончания: {end_date.strftime('%d.%m.%Y')}\nНажмите /start и выберите «Купить подписку» для продления.", parse_mode="Markdown")
            await asyncio.sleep(86400)
        except Exception as e:
            print(f"Ошибка в фоновой задаче: {e}")
            await asyncio.sleep(3600)

async def main():
    # Создаем папку для базы данных, если её нет
    os.makedirs("/data", exist_ok=True)
    # Инициализируем базу данных
    init_db()
    # Запускаем фоновые задачи
    asyncio.create_task(check_expiring_subscriptions())
    print("Бот GGC Community запущен!")
    print(f"База данных находится по пути: {DB_PATH}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
