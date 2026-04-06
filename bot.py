import asyncio
import json
import os
import random
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
    "GGC10": 10,
    "GGC20": 20,
    "NEWYEAR": 15
}

DATA_FILE = "data.json"
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

class UserState(StatesGroup):
    waiting_for_support_message = State()

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "orders": []}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_ref_code(user_id: int) -> str:
    return f"ref_{user_id}"

def get_user_by_ref_code(ref_code: str) -> Optional[str]:
    data = load_data()
    for user_id, user_data in data["users"].items():
        if user_data.get("ref_code") == ref_code:
            return user_id
    return None

def reset_monthly_ref_counts():
    data = load_data()
    now = datetime.now()
    for user_id, user_data in data["users"].items():
        last_reset = user_data.get("ref_monthly_reset")
        if last_reset:
            last_reset_date = datetime.fromisoformat(last_reset)
            if (now - last_reset_date).days >= 30:
                user_data["ref_monthly_count"] = 0
                user_data["ref_monthly_reset"] = now.isoformat()
        else:
            user_data["ref_monthly_reset"] = now.isoformat()
            user_data["ref_monthly_count"] = 0
    save_data(data)

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

Наша цель — не просто обучать техническим инструментам. *Мы помогаем формировать мышление и структуру*, которые позволяют выдерживать давление рынка и принимать взвешенные решения.

Мы создаём сообщество, где каждый участник получает поддержку, делится опытом и прогрессом, а также учится объективно смотреть на рынок через призму вероятностей. 

Мы сделаем всё, чтобы ваше пребывание здесь было максимально комфортным и продуктивным. Мы всегда направим, поддержим и поможем. 

Мы строим не просто коммьюнити — мы строим семью.
"""

def get_whats_inside_text() -> str:
    return """
📦 *Что входит в подписку GGC Community:*

Доступ в приватный Discord-сервер:

1️⃣  *Ежедневный Pre-market анализ* — составление торговых планов на неделю/день

2️⃣  *Образовательные лекции* — принципы анализа рынка, которые действительно работают

3️⃣  *Бектесты с участниками* — демонстрируете экран и на основе полученных знаний рассказываете, как бы вы анализировали график. Менторы GGC разбирают и исправляют ошибки. Рост навыков в реальном времени

4️⃣  *Weekly + QA конференции* — разбираем торговую неделю, сделки участников. Отвечаем на любые вопросы

5️⃣  *Настроим терминал* — полная подготовка софта к торговле. Поможем зарегистрировать аккаунт. Расскажем, как получить финансирование от проп компании

6️⃣  *Лайв-торговля* — совместно с менторами GGC - работаем в реальном рынке. Открываем сделки, получаем результат

7️⃣  *Поддержка 24/7* — составляем плана обучения, формируем торговую стратегию. Индивидуальный подход к каждому участнику"""

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

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    ref_code = None
    if message.text and " " in message.text:
        ref_code = message.text.split(" ", 1)[1]
    
    data = load_data()
    if str(user_id) not in data["users"]:
        invited_by = None
        if ref_code:
            inviter_id = get_user_by_ref_code(ref_code)
            if inviter_id and inviter_id != str(user_id):
                invited_by = inviter_id
        
        data["users"][str(user_id)] = {
            "username": username,
            "joined_at": datetime.now().isoformat(),
            "subscription_end": None,
            "ref_code": generate_ref_code(user_id),
            "ref_by": invited_by,
            "ref_count": 0,
            "ref_monthly_count": 0,
            "ref_monthly_reset": datetime.now().isoformat(),
            "ref_promocodes": [],
            "ref_free_month_used": False
        }
        
        if invited_by:
            inviter = data["users"].get(invited_by, {})
            inviter["ref_count"] = inviter.get("ref_count", 0) + 1
            inviter["ref_monthly_count"] = inviter.get("ref_monthly_count", 0) + 1
            
            last_reset = inviter.get("ref_monthly_reset")
            if last_reset:
                last_reset_date = datetime.fromisoformat(last_reset)
                if (datetime.now() - last_reset_date).days >= 30:
                    inviter["ref_monthly_count"] = 1
                    inviter["ref_monthly_reset"] = datetime.now().isoformat()
            
            promo_code = f"REF{user_id}_{random.randint(1000, 9999)}"
            inviter["ref_promocodes"].append({
                "code": promo_code,
                "discount": 10,
                "created_at": datetime.now().isoformat(),
                "used": False,
                "from_user": username
            })
            
            try:
                await bot.send_message(
                    int(invited_by),
                    f"🎉 *Новый реферал!*\n\n"
                    f"Пользователь @{username} перешёл по вашей ссылке!\n"
                    f"Вы получили промокод на скидку 10$: `{promo_code}`\n\n"
                    f"Всего приглашений: {inviter['ref_count']}\n"
                    f"За этот месяц: {inviter['ref_monthly_count']}",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            if inviter["ref_monthly_count"] >= 3 and not inviter.get("ref_free_month_used"):
                current_end = inviter.get("subscription_end")
                if current_end:
                    end_date = datetime.fromisoformat(current_end)
                    if end_date > datetime.now():
                        new_end = end_date + timedelta(days=30)
                    else:
                        new_end = datetime.now() + timedelta(days=30)
                else:
                    new_end = datetime.now() + timedelta(days=30)
                
                inviter["subscription_end"] = new_end.isoformat()
                inviter["ref_free_month_used"] = True
                
                try:
                    await bot.send_message(
                        int(invited_by),
                        f"🎁 *Бесплатный месяц подписки!*\n\n"
                        f"Вы пригласили 3 друзей за месяц!\n"
                        f"Ваша подписка продлена до {new_end.strftime('%d.%m.%Y')}\n\n"
                        f"Продолжайте приглашать — новые бонусы ждут!",
                        parse_mode="Markdown"
                    )
                except:
                    pass
        
        save_data(data)
    
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
        data = load_data()
        user_id = str(message.from_user.id)
        sub_end = data["users"].get(user_id, {}).get("subscription_end")
        
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
    data = load_data()
    user_data = data["users"].get(str(user_id), {})
    
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_data.get('ref_code', '')}"
    ref_count = user_data.get("ref_count", 0)
    ref_monthly = user_data.get("ref_monthly_count", 0)
    free_month_used = user_data.get("ref_free_month_used", False)
    
    text = f"""
👥 *Реферальная программа GGC*

🔗 *Ваша реферальная ссылка:*
`{ref_link}`

📊 *Ваша статистика:*
• Всего приглашений: {ref_count}
• За этот месяц: {ref_monthly}

🎁 *Бонусы:*
• За 1 приглашение → промокод на скидку 10$
• За 3 приглашения за месяц → бесплатный месяц подписки

{f"✅ *Бесплатный месяц уже получен!*" if free_month_used else "⚠️ *До бесплатного месяца:* " + str(3 - min(ref_monthly, 3)) + " приглашений"}

*Как это работает:*
1. Отправьте ссылку другу
2. Друг регистрируется и покупает подписку
3. Вы получаете промокод на 10$
4. Пригласите 3 друзей за месяц — получите месяц бесплатно
"""
    
    await msg.answer(text, parse_mode="Markdown", reply_markup=get_referral_keyboard())

@dp.callback_query(lambda c: c.data == "copy_ref_link")
async def copy_ref_link(callback: types.CallbackQuery):
    data = load_data()
    user_data = data["users"].get(str(callback.from_user.id), {})
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_data.get('ref_code', '')}"
    
    await callback.answer(f"Ссылка скопирована!", show_alert=False)
    await callback.message.answer(
        f"🔗 *Ваша реферальная ссылка:*\n`{ref_link}`\n\nОтправьте её другу!",
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data == "my_promocodes")
async def my_promocodes(callback: types.CallbackQuery):
    data = load_data()
    user_data = data["users"].get(str(callback.from_user.id), {})
    promocodes = user_data.get("ref_promocodes", [])
    
    active_codes = [p for p in promocodes if not p.get("used", False)]
    
    if not active_codes:
        text = "🎟 *Ваши промокоды*\n\nУ вас пока нет активных промокодов.\nПригласите друга, и вы получите скидку 10$!"
    else:
        text = "🎟 *Ваши промокоды:*\n\n"
        for p in active_codes:
            text += f"• `{p['code']}` — скидка ${p['discount']} (от {p['created_at'][:10]})\n"
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
            "🎟 *Введите промокод:*\n\nНапишите код в сообщении.\nПример: `GGC10` или `REF123456_7890`\n\nДля отмены введите /cancel",
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
    
    data = load_data()
    found = False
    for user_id, user_data in data["users"].items():
        for p in user_data.get("ref_promocodes", []):
            if p.get("code") == promo and not p.get("used", False):
                discount = p.get("discount", 10)
                p["used"] = True
                save_data(data)
                await state.update_data(discount=discount, promo_code=promo, is_ref_promo=True)
                await message.answer(f"✅ Реферальный промокод применён! Скидка ${discount}")
                await show_payment_info(message, state)
                found = True
                return
    
    if not found:
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
    await msg.edit_text(payment_text, parse_mode="Markdown", reply_markup=keyboard)

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
    
    order = {
        "order_id": data["order_id"],
        "user_id": message.from_user.id,
        "username": message.from_user.username or message.from_user.first_name,
        "tariff": data["tariff"],
        "price": data["final_price"],
        "network": data.get("network"),
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "promo": data.get("promo_code")
    }
    
    all_data = load_data()
    all_data["orders"].append(order)
    save_data(all_data)
    
    admin_text = f"""
🆕 *НОВАЯ ЗАЯВКА #{order['order_id']}*

👤 Пользователь: @{order['username']} (ID: {order['user_id']})
💰 Тариф: {TARIFFS[order['tariff']]['name']}
💵 Сумма: ${order['price']} USDT
🌐 Сеть: {order['network']}
🎟 Промокод: {order.get('promo', 'нет')}

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

@dp.callback_query(lambda c: c.data == "admin_view_orders")
async def admin_view_orders(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = load_data()
    pending_orders = [o for o in data["orders"] if o["status"] == "pending"]
    if not pending_orders:
        await callback.message.edit_text("📭 *Нет новых заявок*", parse_mode="Markdown", reply_markup=get_admin_keyboard())
    else:
        text = "📋 *Заявки на подтверждение:*\n\n"
        for o in pending_orders:
            text += f"🆕 #{o['order_id']} | @{o['username']} | ${o['price']}\n"
        
        builder = InlineKeyboardBuilder()
        for o in pending_orders:
            builder.button(text=f"#{o['order_id']} - @{o['username']}", callback_data=f"approve_{o['order_id']}")
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
    
    all_data = load_data()
    order = next((o for o in all_data["orders"] if o["order_id"] == order_id), None)
    
    if not order:
        await message.answer(f"❌ Заявка #{order_id} не найдена")
        await state.clear()
        return
    
    if order["status"] != "pending":
        await message.answer(f"❌ Заявка #{order_id} уже обработана (статус: {order['status']})")
        await state.clear()
        return
    
    order["status"] = "approved"
    order["approved_at"] = datetime.now().isoformat()
    
    user_id = str(order["user_id"])
    tariff = TARIFFS[order["tariff"]]
    end_date = datetime.now() + timedelta(days=tariff["days"])
    
    if user_id not in all_data["users"]:
        all_data["users"][user_id] = {"username": order["username"], "joined_at": datetime.now().isoformat()}
    
    all_data["users"][user_id]["subscription_end"] = end_date.isoformat()
    all_data["users"][user_id]["active_tariff"] = order["tariff"]
    save_data(all_data)
    
    user_message = f"""
✅ *Оплата подтверждена!*

Доступ к GGC Community активирован до {end_date.strftime('%d.%m.%Y')}

🔗 *Ваша ссылка-приглашение в Discord:*  
{discord_link}

⚠️ Ссылка одноразовая. Если не сработала — напишите в поддержку.

Добро пожаловать в комьюнити! 🚀
"""
    
    try:
        await bot.send_message(order["user_id"], user_message, parse_mode="Markdown", reply_markup=get_back_keyboard())
        await message.answer(
            f"✅ *Заявка #{order_id} подтверждена!*\n\n"
            f"Пользователь: @{order['username']}\n"
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
    data = load_data()
    active = []
    now = datetime.now()
    for user_id, user_data in data["users"].items():
        if user_data.get("subscription_end"):
            end_date = datetime.fromisoformat(user_data["subscription_end"])
            if end_date > now:
                days_left = (end_date - now).days
                active.append(f"@{user_data['username']} — осталось {days_left} дн. (до {end_date.strftime('%d.%m.%Y')})")
    text = f"📊 *Активные подписки ({len(active)})*\n\n" + ("\n".join(active) if active else "Нет активных подписок")
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    data = load_data()
    now = datetime.now()
    
    total_users = len(data["users"])
    
    active_count = 0
    for user_data in data["users"].values():
        sub_end = user_data.get("subscription_end")
        if sub_end:
            end_date = datetime.fromisoformat(sub_end)
            if end_date > now:
                active_count += 1
    
    total_revenue = 0
    monthly_revenue = 0
    current_month = now.month
    current_year = now.year
    
    for order in data["orders"]:
        if order.get("status") == "approved":
            price = order.get("price", 0)
            total_revenue += price
            
            created_at = datetime.fromisoformat(order.get("created_at", now.isoformat()))
            if created_at.month == current_month and created_at.year == current_year:
                monthly_revenue += price
    
    total_refs = 0
    for user_data in data["users"].values():
        total_refs += user_data.get("ref_count", 0)
    
    stats_text = f"""
📈 *СТАТИСТИКА GGC COMMUNITY*

👥 *Пользователи:*
• Всего подписчиков: {total_users}
• Активных подписок: {active_count}

💰 *Доход:*
• За всё время: ${total_revenue}
• За текущий месяц: ${monthly_revenue}

👥 *Реферальная программа:*
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
    
    data = load_data()
    now = datetime.now()
    active_users = []
    
    for user_id, user_data in data["users"].items():
        sub_end = user_data.get("subscription_end")
        if sub_end:
            end_date = datetime.fromisoformat(sub_end)
            if end_date > now:
                active_users.append(int(user_id))
    
    if not active_users:
        await message.answer("❌ Нет активных подписчиков для рассылки.")
        await state.clear()
        return
    
    success_count = 0
    fail_count = 0
    
    if message.photo:
        photo = message.photo[-1]
        caption = message.caption or "📢 *Массовое уведомление от администрации GGC*"
        
        for user_id in active_users:
            try:
                await bot.send_photo(user_id, photo.file_id, caption=caption, parse_mode="Markdown")
                success_count += 1
                await asyncio.sleep(0.05)
            except:
                fail_count += 1
    
    elif message.document:
        doc = message.document
        caption = message.caption or "📢 *Массовое уведомление от администрации GGC*"
        
        for user_id in active_users:
            try:
                await bot.send_document(user_id, doc.file_id, caption=caption, parse_mode="Markdown")
                success_count += 1
                await asyncio.sleep(0.05)
            except:
                fail_count += 1
    
    else:
        text = f"📢 *Массовое уведомление от администрации GGC*\n\n{message.text}"
        
        for user_id in active_users:
            try:
                await bot.send_message(user_id, text, parse_mode="Markdown")
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
            data = load_data()
            now = datetime.now()
            for user_id, user_data in data["users"].items():
                sub_end_str = user_data.get("subscription_end")
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
    asyncio.create_task(check_expiring_subscriptions())
    print("Бот GGC Community запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
