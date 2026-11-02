import asyncio
import html
import os
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "ggstar.db"

load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError(
        "Не найден BOT_TOKEN. Проверь файл .env в папке проекта."
    )

ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()

# Временные пользовательские шаги: ввод номинала или получателя подарка.
pending_inputs = {}


# --------------------------------------------------
# КАТАЛОГ
# Цена None означает, что цена ещё не настроена.
# --------------------------------------------------

CATALOG = {
    "stars": {
        "title": "Telegram Stars",
        "emoji": "⭐",
        "description": "Пополнение Telegram Stars",
        "products": [
            ("stars_100", "100 звёзд"),
            ("stars_200", "200 звёзд"),
            ("stars_500", "500 звёзд"),
            ("stars_1000", "1000 звёзд"),
        ],
    },
    "premium": {
        "title": "Telegram Premium",
        "emoji": "💎",
        "description": "Выбери срок подписки",
        "products": [
            ("premium_3", "Premium на 3 месяца"),
            ("premium_6", "Premium на 6 месяцев"),
            ("premium_12", "Premium на 12 месяцев"),
        ],
    },
    "steam": {
        "title": "Пополнение Steam",
        "emoji": "💳",
        "description": "Пополнение баланса Steam",
        "products": [
            ("steam_100", "Пополнение на 100 ₽"),
            ("steam_300", "Пополнение на 300 ₽"),
            ("steam_500", "Пополнение на 500 ₽"),
            ("steam_1000", "Пополнение на 1000 ₽"),
            ("steam_custom", "Другая сумма"),
        ],
    },
    "games": {
        "title": "Игры",
        "emoji": "🎮",
        "description": "Игровая валюта и подарочные карты",
        "products": [],
    },
}

GAMES = {
    "pubg": {
        "title": "PUBG Mobile",
        "emoji": "🎯",
        "description": "UC и игровые наборы",
        "products": [
            ("pubg_uc_60", "60 UC"),
            ("pubg_uc_325", "325 UC"),
            ("pubg_uc_660", "660 UC"),
            ("pubg_uc_1800", "1800 UC"),
            ("pubg_uc_3850", "3850 UC"),
            ("pubg_uc_8100", "8100 UC"),
            ("pubg_weekly", "Weekly Deal Pack"),
            ("pubg_monthly", "Monthly Pack"),
            ("pubg_prime", "Prime"),
            ("pubg_elite", "Elite Pass"),
        ],
    },
    "standoff": {
        "title": "Standoff 2",
        "emoji": "🔫",
        "description": "Пополнение Gold",
        "products": [
            ("standoff_gold_100", "100 Gold"),
            ("standoff_gold_300", "300 Gold"),
            ("standoff_gold_500", "500 Gold"),
            ("standoff_gold_1000", "1000 Gold"),
            ("standoff_gold_3000", "3000 Gold"),
            ("standoff_gold_5000", "5000 Gold"),
        ],
    },
    "genshin": {
        "title": "Genshin Impact",
        "emoji": "✨",
        "description": "Пополнение кристаллов",
        "products": [
            ("genshin_60", "60 Genesis Crystals"),
            ("genshin_300", "300 + 30 кристаллов"),
            ("genshin_980", "980 Genesis Crystals"),
            ("genshin_1980", "1980 Genesis Crystals"),
            ("genshin_3280", "3280 Genesis Crystals"),
            ("genshin_6480", "6480 Genesis Crystals"),
            ("genshin_welkin", "Благословение полой луны"),
        ],
    },
    "roblox": {
        "title": "Roblox",
        "emoji": "🧱",
        "description": "Подарочные карты Roblox",
        "products": [
            ("roblox_gift_10", "Подарочная карта Roblox — $10"),
            ("roblox_gift_15", "Подарочная карта Roblox — $15"),
            ("roblox_gift_20", "Подарочная карта Roblox — $20"),
            ("roblox_gift_25", "Подарочная карта Roblox — $25"),
            ("roblox_gift_50", "Подарочная карта Roblox — $50"),
        ],
    },
    "brawl": {
        "title": "Brawl Stars",
        "emoji": "⭐",
        "description": "Гемы и игровые предложения",
        "products": [
            ("brawl_gems_30", "30 гемов"),
            ("brawl_gems_80", "80 гемов"),
            ("brawl_gems_170", "170 гемов"),
            ("brawl_gems_360", "360 гемов"),
            ("brawl_gems_950", "950 гемов"),
            ("brawl_pass", "Brawl Pass"),
        ],
    },
    "mlbb": {
        "title": "Mobile Legends",
        "emoji": "⚔️",
        "description": "Пополнение Diamonds",
        "products": [
            ("mlbb_diamonds_86", "86 Diamonds"),
            ("mlbb_diamonds_172", "172 Diamonds"),
            ("mlbb_diamonds_257", "257 Diamonds"),
            ("mlbb_diamonds_706", "706 Diamonds"),
            ("mlbb_diamonds_1412", "1412 Diamonds"),
            ("mlbb_weekly", "Weekly Diamond Pass"),
        ],
    },
    "valorant": {
        "title": "Valorant",
        "emoji": "🎯",
        "description": "Подарочные карты Riot / Valorant",
        "products": [
            ("valorant_gift_10", "Подарочная карта Valorant — $10"),
            ("valorant_gift_20", "Подарочная карта Valorant — $20"),
            ("valorant_gift_25", "Подарочная карта Valorant — $25"),
            ("valorant_gift_50", "Подарочная карта Valorant — $50"),
        ],
    },
    "freefire": {
        "title": "Free Fire",
        "emoji": "🔥",
        "description": "Подарочные карты Free Fire",
        "products": [
            ("freefire_gift_10", "Подарочная карта Free Fire — $10"),
            ("freefire_gift_20", "Подарочная карта Free Fire — $20"),
            ("freefire_gift_50", "Подарочная карта Free Fire — $50"),
        ],
    },
    "other": {
        "title": "Другие игры",
        "emoji": "🕹️",
        "description": "Запросить товар для другой игры",
        "products": [
            ("other_request", "Запросить другую игру"),
        ],
    },
}
# --------------------------------------------------
# БАЗА ДАННЫХ
# --------------------------------------------------

def connect_db():
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with connect_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                price_rub REAL,
                is_active INTEGER NOT NULL DEFAULT 0
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                price_rub REAL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        valid_product_ids = []

        for category, data in CATALOG.items():
            for product_id, name in data["products"]:
                valid_product_ids.append(product_id)
                db.execute("""
                    INSERT INTO products
                    (product_id, category, name, price_rub, is_active)
                    VALUES (?, ?, ?, NULL, 0)
                    ON CONFLICT(product_id) DO UPDATE SET
                        category = excluded.category,
                        name = excluded.name
                """, (product_id, category, name))

        for game_id, game in GAMES.items():
            for product_id, name in game["products"]:
                valid_product_ids.append(product_id)
                db.execute("""
                    INSERT INTO products
                    (product_id, category, name, price_rub, is_active)
                    VALUES (?, ?, ?, NULL, 0)
                    ON CONFLICT(product_id) DO UPDATE SET
                        category = excluded.category,
                        name = excluded.name
                """, (product_id, game_id, name))

        # Удаляем из каталога устаревшие позиции. История заказов хранит
        # название товара отдельно и останется нетронутой.
        placeholders = ",".join("?" for _ in valid_product_ids)
        db.execute(
            f"DELETE FROM products WHERE product_id NOT IN ({placeholders}) "
            "AND product_id NOT LIKE 'stars_custom_%'",
            valid_product_ids,
        )

        db.commit()
        db.commit()


def save_user(user_id, username, full_name):
    with connect_db() as db:
        db.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
        """, (user_id, username, full_name))


def get_product(product_id):
    with connect_db() as db:
        return db.execute(
            "SELECT * FROM products WHERE product_id = ?",
            (product_id,),
        ).fetchone()


def get_user_orders(user_id):
    with connect_db() as db:
        return db.execute("""
            SELECT id, product_name, price_rub, status, created_at
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 10
        """, (user_id,)).fetchall()


def create_order(user_id, product):
    with connect_db() as db:
        cursor = db.execute("""
            INSERT INTO orders
            (user_id, product_id, product_name, price_rub, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (
            user_id,
            product["product_id"],
            product["name"],
            product["price_rub"],
        ))
        return cursor.lastrowid


# --------------------------------------------------
# КЛАВИАТУРЫ
# --------------------------------------------------

def button(text, callback):
    return InlineKeyboardButton(text=text, callback_data=callback)


def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            button("⭐ Telegram Stars", "catalog:stars"),
            button("💎 Premium", "catalog:premium"),
        ],
        [
            button("💳 Пополнение Steam", "catalog:steam"),
        ],
        [
            button("🎮 Игры", "catalog:games"),
        ],
        [
            button("📦 Мои заказы", "orders"),
            button("👤 Профиль", "profile"),
        ],
        [
            button("💬 Поддержка", "support"),
        ],
    ])


def back_keyboard(destination="home"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            button("⬅️ Назад", destination),
            button("🏠 Главное меню", "home"),
        ],
    ])


def stars_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            button("⭐ 100", "product:stars_100"),
            button("⭐ 200", "product:stars_200"),
            button("⭐ 500", "product:stars_500"),
            button("⭐ 1000", "product:stars_1000"),
        ],
        [
            button("✍️ Другое количество", "stars:custom"),
        ],
        [
            button("⬅️ Назад", "home"),
            button("🎁 Подарить", "gift:stars"),
        ],
    ])


def games_keyboard():
    rows = []
    row = []

    for game_id, game in GAMES.items():
        row.append(button(
            f'{game["emoji"]} {game["title"]}',
            f"game:{game_id}",
        ))
        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append([
        button("⬅️ Назад", "home"),
        button("🏠 Главное меню", "home"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def products_keyboard(category, products):
    if category == "stars":
        return stars_keyboard()

    rows = []
    row = []
    columns = 2

    emoji = (
        CATALOG.get(category, {}).get("emoji")
        or GAMES.get(category, {}).get("emoji")
        or "🛍️"
    )

    for product in products:
        if not product["is_active"] or product["price_rub"] is None:
            label = f'{emoji} {product["name"]}'
        else:
            label = f'{emoji} {product["name"]} · {product["price_rub"]:g} ₽'

        row.append(button(label[:64], f'product:{product["product_id"]}'))

        if len(row) == columns:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    if category in GAMES:
        back = f"game:{category}"
    else:
        back = "home"

    rows.append([
        button("⬅️ Назад", back),
        button("🏠 Главное меню", "home"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_keyboard(product):
    rows = []

    if product["is_active"] and product["price_rub"] is not None:
        rows.append([
            button("🛒 Оформить заявку", f'order:{product["product_id"]}')
        ])
    else:
        rows.append([
            button("🔔 Скоро в продаже", f'notify:{product["product_id"]}')
        ])

    category = product["category"]
    back = f"game:{category}" if category in GAMES else f"catalog:{category}"

    rows.append([
        button("⬅️ Назад", back),
        button("🏠 Главное меню", "home"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)



async def show_page(target, text, reply_markup):
    if isinstance(target, CallbackQuery):
        await target.answer()
        try:
            await target.message.edit_text(
                text,
                reply_markup=reply_markup,
            )
        except TelegramAPIError:
            await target.message.answer(
                text,
                reply_markup=reply_markup,
            )
    else:
        await target.answer(text, reply_markup=reply_markup)


# --------------------------------------------------
# СТАРТ И ГЛАВНОЕ МЕНЮ
# --------------------------------------------------

WELCOME = (
    "🌟 <b>GGSTAR</b>\n"
    "<i>Твой магазин цифровых товаров</i>\n\n"
    "🎮 Игры • ⭐ Telegram Stars • 💎 Premium\n"
    "💳 Пополнение Steam и подарочные карты\n\n"
    "<b>Выбирай категорию — и погнали! 👇</b>"
)


@dp.message(CommandStart())
async def start(message: Message):
    user = message.from_user
    save_user(user.id, user.username, user.full_name)

    await message.answer(
        WELCOME,
        reply_markup=main_keyboard(),
    )


@dp.callback_query(F.data == "home")
async def home(callback: CallbackQuery):
    pending_inputs.pop(callback.from_user.id, None)
    await show_page(callback, WELCOME, main_keyboard())


# --------------------------------------------------
# КАТАЛОГ
# --------------------------------------------------

@dp.callback_query(F.data.startswith("catalog:"))
async def catalog(callback: CallbackQuery):
    pending_inputs.pop(callback.from_user.id, None)
    category = callback.data.split(":", 1)[1]

    if category == "games":
        await show_page(
            callback,
            "🎮 <b>Игры</b>\n\nВыбери игру:",
            games_keyboard(),
        )
        return

    data = CATALOG.get(category)

    if not data:
        await callback.answer("Раздел не найден", show_alert=True)
        return

    with connect_db() as db:
        products = db.execute("""
            SELECT * FROM products
            WHERE category = ?
            ORDER BY rowid
        """, (category,)).fetchall()

    if category == "stars":
        text = (
            "⭐ <b>Telegram Stars</b>\n\n"
            "Сколько звёзд тебе нужно?\n"
            "Выбери номинал или укажи своё количество 👇"
        )
    elif category == "premium":
        text = (
            "💎 <b>Telegram Premium</b>\n\n"
            "Выбери срок подписки 👇"
        )
    elif category == "steam":
        text = (
            "💳 <b>Пополнение Steam</b>\n\n"
            "Выбери сумму пополнения 👇\n"
            "<i>Итоговая цена зависит от региона аккаунта и курса.</i>"
        )
    else:
        text = (
            f'{data["emoji"]} <b>{data["title"]}</b>\n\n'
            f'{data["description"]}\n\n'
            "Выбери товар ниже 👇"
        )

    await show_page(
        callback,
        text,
        products_keyboard(category, products),
    )


@dp.callback_query(F.data.startswith("game:"))
async def game_page(callback: CallbackQuery):
    pending_inputs.pop(callback.from_user.id, None)
    game_id = callback.data.split(":", 1)[1]
    game = GAMES.get(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    with connect_db() as db:
        products = db.execute("""
            SELECT * FROM products
            WHERE category = ?
            ORDER BY rowid
        """, (game_id,)).fetchall()

    text = (
        f'{game["emoji"]} <b>{game["title"]}</b>\n\n'
        f'{game.get("description", "Выбери товар")}\n\n'
        "Выбери нужный вариант 👇"
    )

    await show_page(
        callback,
        text,
        products_keyboard(game_id, products),
    )






def gift_amount_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            button("⭐ 100", "giftamount:100"),
            button("⭐ 200", "giftamount:200"),
        ],
        [
            button("⭐ 500", "giftamount:500"),
            button("⭐ 1000", "giftamount:1000"),
        ],
        [button("✍️ Другое количество", "giftamount:custom")],
        [
            button("⬅️ Назад", "catalog:stars"),
            button("🏠 Главное меню", "home"),
        ],
    ])


@dp.callback_query(F.data == "stars:custom")
async def stars_custom_amount(callback: CallbackQuery):
    pending_inputs[callback.from_user.id] = {"mode": "stars_custom"}
    await show_page(
        callback,
        "✍️ <b>Другое количество Stars</b>\n\n"
        "Введи целое число от <b>50 до 5000</b>.\n"
        "Например: <code>350</code>\n\n"
        "После этого покажем карточку выбранного номинала.",
        back_keyboard("catalog:stars"),
    )


@dp.callback_query(F.data == "gift:stars")
async def gift_stars(callback: CallbackQuery):
    pending_inputs[callback.from_user.id] = {"mode": "gift_recipient"}
    await show_page(
        callback,
        "🎁 <b>Подарить Telegram Stars</b>\n\n"
        "Отправь username получателя, например <code>@username</code>.\n"
        "Затем выберешь номинал подарка.",
        back_keyboard("catalog:stars"),
    )


@dp.callback_query(F.data.startswith("giftamount:"))
async def gift_amount(callback: CallbackQuery):
    user_id = callback.from_user.id
    state = pending_inputs.get(user_id)

    if not state or state.get("mode") != "gift_amount":
        await callback.answer(
            "Начни оформление подарка заново.",
            show_alert=True,
        )
        return

    selected = callback.data.split(":", 1)[1]

    if selected == "custom":
        pending_inputs[user_id] = {
            "mode": "gift_custom_amount",
            "recipient": state["recipient"],
        }
        await show_page(
            callback,
            "✍️ <b>Свой номинал подарка</b>\n\n"
            "Введи количество Stars от 50 до 5000.",
            back_keyboard("catalog:stars"),
        )
        return

    amount = int(selected)
    product = get_product(f"stars_{amount}")

    if not product or not product["is_active"] or product["price_rub"] is None:
        await callback.answer(
            "Цена этого номинала ещё не настроена.",
            show_alert=True,
        )
        return

    gift_product = dict(product)
    gift_product["name"] = (
        f'🎁 Подарок {amount} Stars → {state["recipient"]}'
    )
    order_id = create_order(user_id, gift_product)
    pending_inputs.pop(user_id, None)

    await callback.answer("Заявка создана!")
    await callback.message.answer(
        f"🎁 <b>Заявка на подарок #{order_id}</b>\n\n"
        f"Получатель: {html.escape(state['recipient'])}\n"
        f"Количество: <b>{amount} Stars</b>\n"
        f"Цена: <b>{product['price_rub']:g} ₽</b>\n\n"
        "Это заявка, а не подтверждение оплаты. "
        "Дождись ответа поддержки.",
        reply_markup=main_keyboard(),
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🎁 <b>Заявка на подарок #{order_id}</b>\n\n"
                f"Пользователь: {user_id}\n"
                f"Получатель: {html.escape(state['recipient'])}\n"
                f"Номинал: {amount} Stars\n"
                f"Цена: {product['price_rub']:g} ₽",
            )
        except TelegramAPIError:
            pass
@dp.callback_query(F.data.startswith("product:"))
async def product_page(callback: CallbackQuery):
    pending_inputs.pop(callback.from_user.id, None)
    product_id = callback.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    if product["is_active"] and product["price_rub"] is not None:
        price_text = f'{product["price_rub"]:g} ₽'
        status_text = "✅ Товар доступен для оформления заявки."
    else:
        price_text = "Уточняется"
        status_text = (
            "🛠 Товар подготовлен к запуску, но цена пока не настроена.\n"
            "Мы добавим его в продажу после проверки поставщика."
        )

    text = (
        f'🛍 <b>{html.escape(product["name"])}</b>\n\n'
        f'💰 Цена: <b>{price_text}</b>\n\n'
        f'{status_text}\n\n'
        "Перед заказом проверяй регион и условия пополнения."
    )

    await show_page(
        callback,
        text,
        product_keyboard(product),
    )


# --------------------------------------------------
# ЗАЯВКИ И ЗАКАЗЫ
# --------------------------------------------------

@dp.callback_query(F.data.startswith("order:"))
async def order_product(callback: CallbackQuery):
    product_id = callback.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    if not product["is_active"] or product["price_rub"] is None:
        await callback.answer(
            "Товар пока недоступен.",
            show_alert=True,
        )
        return

    order_id = create_order(callback.from_user.id, product)

    await callback.answer("Заявка создана!")

    await callback.message.answer(
        f"✅ <b>Заявка #{order_id} создана</b>\n\n"
        f"Товар: {html.escape(product['name'])}\n"
        f"Цена: {product['price_rub']:g} ₽\n\n"
        "Это заявка, а не подтверждение оплаты. "
        "Дождись ответа поддержки."
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 <b>Новая заявка #{order_id}</b>\n\n"
                f"Пользователь: {callback.from_user.id}\n"
                f"Товар: {html.escape(product['name'])}\n"
                f"Цена: {product['price_rub']:g} ₽",
            )
        except TelegramAPIError:
            pass


@dp.callback_query(F.data.startswith("notify:"))
async def notify_product(callback: CallbackQuery):
    product_id = callback.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await callback.answer(
        "Товар пока не запущен. Загляни позже!",
        show_alert=True,
    )


@dp.callback_query(F.data == "orders")
async def orders(callback: CallbackQuery):
    rows = get_user_orders(callback.from_user.id)

    if not rows:
        text = (
            "📦 <b>Мои заказы</b>\n\n"
            "У тебя пока нет заказов."
        )
    else:
        lines = ["📦 <b>Последние заказы</b>\n"]

        for row in rows:
            price = (
                f'{row["price_rub"]:g} ₽'
                if row["price_rub"] is not None
                else "Цена не задана"
            )

            lines.append(
                f'№{row["id"]} · {html.escape(row["product_name"])}\n'
                f'💰 {price} · Статус: {html.escape(row["status"])}'
            )

        text = "\n\n".join(lines)

    await show_page(callback, text, back_keyboard())


# --------------------------------------------------
# ПРОФИЛЬ И ПОДДЕРЖКА
# --------------------------------------------------

@dp.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    user = callback.from_user

    with connect_db() as db:
        count = db.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = ?",
            (user.id,),
        ).fetchone()[0]

    username = f'@{user.username}' if user.username else "не указан"

    text = (
        "👤 <b>Твой профиль GGSTAR</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📛 Имя: {html.escape(user.full_name)}\n"
        f"🔗 Username: {html.escape(username)}\n"
        f"📦 Заявок и заказов: {count}"
    )

    await show_page(callback, text, back_keyboard())


@dp.callback_query(F.data == "support")
async def support(callback: CallbackQuery):
    text = (
        "💬 <b>Поддержка GGSTAR</b>\n\n"
        "Если возник вопрос по товару или заказу, "
        "напиши администратору.\n\n"
        "Контакт поддержки будет добавлен после настройки."
    )

    await show_page(callback, text, back_keyboard())


# --------------------------------------------------
# АДМИН-КОМАНДЫ
# --------------------------------------------------

def is_admin(user_id):
    return user_id in ADMIN_IDS


@dp.message(Command("admin"))
async def admin_help(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    await message.answer(
        "🛠 <b>Администрирование GGSTAR</b>\n\n"
        "<code>/products</code> — список товаров\n"
        "<code>/setprice ID ЦЕНА</code> — установить цену и включить товар\n"
        "<code>/disable ID</code> — выключить товар\n\n"
        "Пример:\n"
        "<code>/setprice stars_50 99</code>"
    )


@dp.message(Command("products"))
async def admin_products(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    with connect_db() as db:
        rows = db.execute("""
            SELECT product_id, name, price_rub, is_active
            FROM products
            ORDER BY category, rowid
        """).fetchall()

    lines = ["🛠 <b>Каталог товаров</b>\n"]

    for row in rows:
        price = (
            f'{row["price_rub"]:g} ₽'
            if row["price_rub"] is not None
            else "без цены"
        )
        status = "активен" if row["is_active"] else "выключен"

        lines.append(
            f'<code>{row["product_id"]}</code> — '
            f'{html.escape(row["name"])} — {price} ({status})'
        )

    text = "\n".join(lines)

    if len(text) > 4000:
        text = text[:3900] + "\n\nСписок сокращён."

    await message.answer(text)


@dp.message(Command("setprice"))
async def admin_setprice(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split()

    if len(parts) != 3:
        await message.answer(
            "Формат: <code>/setprice ID ЦЕНА</code>\n"
            "Пример: <code>/setprice stars_50 99</code>"
        )
        return

    product_id = parts[1]

    try:
        price = float(parts[2].replace(",", "."))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Цена должна быть положительным числом.")
        return

    with connect_db() as db:
        cursor = db.execute("""
            UPDATE products
            SET price_rub = ?, is_active = 1
            WHERE product_id = ?
        """, (price, product_id))

        if cursor.rowcount == 0:
            await message.answer("Товар с таким ID не найден.")
            return

    await message.answer(
        f"✅ Товар <code>{product_id}</code> включён.\n"
        f"Цена: <b>{price:g} ₽</b>"
    )


@dp.message(Command("disable"))
async def admin_disable(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split()

    if len(parts) != 2:
        await message.answer("Формат: <code>/disable ID</code>")
        return

    with connect_db() as db:
        cursor = db.execute("""
            UPDATE products SET is_active = 0
            WHERE product_id = ?
        """, (parts[1],))

        if cursor.rowcount == 0:
            await message.answer("Товар с таким ID не найден.")
            return

    await message.answer("✅ Товар выключен.")




@dp.message(Command("cancel"))
async def cancel_pending(message: Message):
    pending_inputs.pop(message.from_user.id, None)
    await message.answer(
        "✅ Текущий шаг отменён.",
        reply_markup=main_keyboard(),
    )


@dp.message(F.text)
async def handle_pending_text(message: Message):
    user_id = message.from_user.id
    state = pending_inputs.get(user_id)

    if not state:
        return

    raw = (message.text or "").strip()
    mode = state.get("mode")

    if mode in {"stars_custom", "gift_custom_amount"}:
        if not raw.isdigit():
            await message.answer(
                "Введи количество целым числом — например, <code>350</code>."
            )
            return

        amount = int(raw)
        if not 50 <= amount <= 5000:
            await message.answer(
                "Количество должно быть от <b>50 до 5000</b> Stars."
            )
            return

        product_id = f"stars_custom_{amount}"
        product_name = f"{amount} звёзд"

        with connect_db() as db:
            db.execute("""
                INSERT INTO products
                    (product_id, category, name, price_rub, is_active)
                VALUES (?, 'stars', ?, NULL, 0)
                ON CONFLICT(product_id) DO UPDATE SET
                    category = excluded.category,
                    name = excluded.name
            """, (product_id, product_name))

        product = get_product(product_id)

        if mode == "gift_custom_amount":
            recipient = state["recipient"]
            pending_inputs.pop(user_id, None)
            await message.answer(
                f"🎁 <b>Подарок для {html.escape(recipient)}</b>\n\n"
                f"Количество: <b>{amount} Stars</b>\n\n"
                "Этот номинал сохранён, но его цена ещё не настроена. "
                "Оформление подарка станет доступно после настройки цены "
                "и поставщика. Попробуй позже.",
                reply_markup=main_keyboard(),
            )
            return

        pending_inputs.pop(user_id, None)
        price_text = (
            f'{product["price_rub"]:g} ₽'
            if product["price_rub"] is not None
            else "Уточняется"
        )
        await message.answer(
            "⭐ <b>Твой номинал готов</b>\n\n"
            f"Количество: <b>{amount} Stars</b>\n"
            f"Цена: <b>{price_text}</b>\n\n"
            "Если цена ещё не настроена, товар появится в продаже "
            "после настройки администратором.",
            reply_markup=product_keyboard(product),
        )
        return

    if mode == "gift_recipient":
        recipient = raw
        if recipient.startswith("https://t.me/"):
            recipient = "@" + recipient.rstrip("/").split("/")[-1]
        elif not recipient.startswith("@"):
            recipient = "@" + recipient

        username = recipient[1:]
        if (
            not 5 <= len(username) <= 32
            or not all(char.isalnum() or char == "_" for char in username)
        ):
            await message.answer(
                "Не получилось распознать username. "
                "Отправь его в формате <code>@username</code>."
            )
            return

        pending_inputs[user_id] = {
            "mode": "gift_amount",
            "recipient": recipient,
        }
        await message.answer(
            f"🎁 Получатель: <b>{html.escape(recipient)}</b>\n\n"
            "Теперь выбери, сколько Stars подарить:",
            reply_markup=gift_amount_keyboard(),
        )
        return

    if mode == "gift_amount":
        await message.answer(
            "Выбери номинал подарка кнопкой ниже 👇",
            reply_markup=gift_amount_keyboard(),
        )

# --------------------------------------------------
# ЗАПУСК И ПОВТОРНЫЕ ПОПЫТКИ ПРИ СБОЕ СЕТИ
# --------------------------------------------------

async def main():
    init_db()

    print("GGSTAR: база данных готова.")
    print("GGSTAR: запускаю подключение к Telegram...")

    delay = 3

    while True:
        try:
            me = await bot.get_me()
            print(f"GGSTAR запущен: @{me.username}")

            delay = 3
            await dp.start_polling(
                bot,
                close_bot_session=False,
            )

        except TelegramNetworkError as error:
            print(f"Нет соединения с Telegram: {error}")
            print(f"Повторная попытка через {delay} сек.")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

        except (KeyboardInterrupt, SystemExit):
            break

        except Exception as error:
            print(f"Ошибка запуска: {type(error).__name__}: {error}")
            print(f"Повторная попытка через {delay} сек.")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGGSTAR остановлен.")
