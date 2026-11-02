import asyncio
import html
import os
import sqlite3
import secrets
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "ggstar.db"
BANNER_DIR = BASE_DIR / "assets"

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


class UserActivityMiddleware:
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user") or getattr(event, "from_user", None)
        if user is not None:
            try:
                with connect_db() as db:
                    db.execute("UPDATE users SET last_seen_at=CURRENT_TIMESTAMP WHERE user_id=?", (user.id,))
            except sqlite3.Error:
                pass
        return await handler(event, data)


dp.message.outer_middleware(UserActivityMiddleware())
dp.callback_query.outer_middleware(UserActivityMiddleware())

# Временные пользовательские шаги: ввод номинала или получателя подарка.
pending_inputs = {}
user_promos = {}  # Промокоды, которые пользователь применяет к следующему заказу.
BOT_USERNAME = None


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
            ("stars_50", "50 звёзд"),
            ("stars_100", "100 звёзд"),
            ("stars_200", "200 звёзд"),
            ("stars_250", "250 звёзд"),
            ("stars_500", "500 звёзд"),
            ("stars_750", "750 звёзд"),
            ("stars_1000", "1000 звёзд"),
            ("stars_1500", "1500 звёзд"),
            ("stars_2000", "2000 звёзд"),
            ("stars_3000", "3000 звёзд"),
            ("stars_5000", "5000 звёзд"),
            ("stars_10000", "10000 звёзд"),
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

}
# --------------------------------------------------
# БАЗА ДАННЫХ
# --------------------------------------------------

@contextmanager
def connect_db():
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


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
        db.execute("DELETE FROM products WHERE category IN ('standoff', 'brawl', 'other')")
        db.commit()


def _table_columns(db, table_name):
    return {row[1] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_column(db, table_name, definition):
    column_name = definition.split()[0]
    if column_name not in _table_columns(db, table_name):
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {definition}")


def migrate_extended_db():
    """Добавляет новые возможности к существующей БД без удаления старых данных."""
    with connect_db() as db:
        for definition in (
            "last_seen_at TEXT",
            "referral_code TEXT",
            "referred_by INTEGER",
            "marketing_opt_in INTEGER NOT NULL DEFAULT 0",
            "banned INTEGER NOT NULL DEFAULT 0",
            "notes TEXT",
        ):
            _ensure_column(db, "users", definition)

        for definition in (
            "price_usdt REAL",
            "purchase_cost_rub REAL",
            "purchase_cost_usdt REAL",
            "supplier TEXT",
            "updated_at TEXT",
        ):
            _ensure_column(db, "products", definition)

        for definition in (
            "price_usdt REAL",
            "purchase_cost_rub REAL",
            "purchase_cost_usdt REAL",
            "discount_amount_rub REAL NOT NULL DEFAULT 0",
            "promo_code TEXT",
            "payment_method TEXT",
            "paid_at TEXT",
            "completed_at TEXT",
            "delay_eta TEXT",
            "delay_message TEXT",
            "delay_promo_code TEXT",
            "responsible TEXT",
            "updated_at TEXT",
            "source TEXT",
        ):
            _ensure_column(db, "orders", definition)

        db.execute("""CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            discount_type TEXT NOT NULL DEFAULT 'percent',
            discount_value REAL NOT NULL DEFAULT 0,
            usage_limit INTEGER,
            uses INTEGER NOT NULL DEFAULT 0,
            user_id INTEGER,
            category TEXT,
            starts_at TEXT,
            expires_at TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            reason TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS promo_redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            discount_amount_rub REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'reserved',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code, user_id, order_id)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL DEFAULT 'system',
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id TEXT,
            details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS order_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            old_status TEXT,
            new_status TEXT NOT NULL,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL DEFAULT 'Обращение в поддержку',
            status TEXT NOT NULL DEFAULT 'new',
            assigned_to TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            actor TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS customer_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            actor TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            product_id TEXT,
            product_name TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            moderated_by TEXT,
            moderated_at TEXT
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            first_order_id INTEGER,
            status TEXT NOT NULL DEFAULT 'registered',
            reward_code TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            converted_at TEXT
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS broadcast_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            message TEXT NOT NULL,
            audience TEXT NOT NULL,
            total_count INTEGER NOT NULL DEFAULT 0,
            sent_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS broadcast_recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")

        # Stable referral codes for existing users. Existing data is preserved.
        db.execute("UPDATE users SET referral_code = 'GG' || CAST(user_id AS TEXT) WHERE referral_code IS NULL OR referral_code = ''")
        db.execute("UPDATE users SET last_seen_at = COALESCE(last_seen_at, created_at, CURRENT_TIMESTAMP)")
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('tax_rate_percent','6')")
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('sbp_fee_percent','3')")
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('referral_reward_percent','5')")
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('usdt_rub_rate','84')")
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('delay_promo_percent','5')")
        db.commit()


def log_activity(actor, action, entity_type=None, entity_id=None, details=None):
    try:
        with connect_db() as db:
            db.execute(
                "INSERT INTO activity_log(actor,action,entity_type,entity_id,details) VALUES(?,?,?,?,?)",
                (str(actor), str(action), entity_type, str(entity_id) if entity_id is not None else None, details),
            )
    except sqlite3.Error as error:
        print(f"GGSTAR: не удалось записать событие: {error}")


def get_referral_by_code(code):
    if not code:
        return None
    with connect_db() as db:
        return db.execute("SELECT user_id FROM users WHERE referral_code = ?", (code,)).fetchone()


def create_order(user_id, product):
    promo = user_promos.get(user_id)
    original_price = product["price_rub"]
    price_rub = original_price
    price_usdt = product["price_usdt"] if "price_usdt" in product.keys() else None
    discount = 0.0
    applied_code = None

    if promo and promo.get("product_id") == product["product_id"] and original_price is not None:
        code = promo.get("code", "").upper()
        with connect_db() as db:
            promo_row = db.execute("SELECT * FROM promo_codes WHERE code = ? AND active = 1", (code,)).fetchone()
            existing = db.execute("SELECT 1 FROM promo_redemptions WHERE code = ? AND user_id = ? AND status != 'released' LIMIT 1", (code, user_id)).fetchone()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            valid = bool(promo_row)
            if promo_row:
                valid = valid and (promo_row["user_id"] is None or int(promo_row["user_id"]) == int(user_id))
                valid = valid and (promo_row["category"] is None or promo_row["category"] == product["category"])
                valid = valid and (promo_row["usage_limit"] is None or int(promo_row["uses"]) < int(promo_row["usage_limit"]))
                valid = valid and not existing
                valid = valid and (not promo_row["starts_at"] or promo_row["starts_at"] <= now)
                valid = valid and (not promo_row["expires_at"] or promo_row["expires_at"] >= now)
            if valid:
                if promo_row["discount_type"] == "percent":
                    discount = round(float(original_price) * float(promo_row["discount_value"]) / 100, 2)
                else:
                    discount = min(float(original_price), float(promo_row["discount_value"]))
                price_rub = round(max(0.01, float(original_price) - discount), 2)
                if price_usdt is not None:
                    price_usdt = round(max(0.0001, float(price_usdt) * (1 - discount / float(original_price))), 4)
                applied_code = code
            else:
                user_promos.pop(user_id, None)

    with connect_db() as db:
        columns = _table_columns(db, "orders")
        purchase_cost_rub = product["purchase_cost_rub"] if "purchase_cost_rub" in product.keys() else None
        purchase_cost_usdt = product["purchase_cost_usdt"] if "purchase_cost_usdt" in product.keys() else None
        created = db.execute("""
            INSERT INTO orders
            (user_id, product_id, product_name, price_rub, status,
             price_usdt, purchase_cost_rub, purchase_cost_usdt,
             discount_amount_rub, promo_code, updated_at, source)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'bot')
        """, (
            user_id,
            product["product_id"],
            product["name"],
            price_rub,
            price_usdt,
            purchase_cost_rub,
            purchase_cost_usdt,
            discount,
            applied_code,
        ))
        order_id = created.lastrowid
        db.execute(
            "INSERT INTO order_status_history(order_id,actor,old_status,new_status,note) VALUES(?,?,?,?,?)",
            (order_id, str(user_id), None, "pending", "Заказ создан через бота"),
        )
        if applied_code:
            db.execute(
                "INSERT INTO promo_redemptions(code,user_id,order_id,discount_amount_rub,status) VALUES(?,?,?,?,?)",
                (applied_code, user_id, order_id, discount, "reserved"),
            )
            db.execute("UPDATE promo_codes SET uses = uses + 1 WHERE code = ?", (applied_code,))

    user_promos.pop(user_id, None)
    log_activity(user_id, "order_created", "order", order_id, f"{product['name']}; price={price_rub}; promo={applied_code or '-'}")
    return order_id


def save_user(user_id, username, full_name, referrer_id=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_new = False
    with connect_db() as db:
        current = db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
        is_new = current is None
        referral_code = f"GG{user_id}"
        db.execute("""
            INSERT INTO users (user_id, username, full_name, created_at, last_seen_at, referral_code, marketing_opt_in)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                last_seen_at = excluded.last_seen_at
        """, (user_id, username, full_name, now, now, referral_code))

        if is_new and referrer_id and int(referrer_id) != int(user_id):
            referrer = db.execute("SELECT user_id FROM users WHERE user_id = ?", (int(referrer_id),)).fetchone()
            if referrer:
                db.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (int(referrer_id), int(user_id)))
                db.execute("INSERT OR IGNORE INTO referrals(inviter_id,referred_id,status) VALUES(?,?,'registered')", (int(referrer_id), int(user_id)))

    if is_new:
        log_activity(user_id, "user_registered", "user", user_id, f"username={username or '-'}")
    else:
        log_activity(user_id, "user_active", "user", user_id, "Запуск/активность бота")


def get_product(product_id):
    with connect_db() as db:
        return db.execute(
            "SELECT * FROM products WHERE product_id = ?",
            (product_id,),
        ).fetchone()


def get_user_orders(user_id):
    with connect_db() as db:
        return db.execute("""
            SELECT id, product_name, price_rub, price_usdt, payment_method, status, created_at
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 10
        """, (user_id,)).fetchall()


def get_order(order_id):
    with connect_db() as db:
        return db.execute("SELECT * FROM orders WHERE id = ?", (int(order_id),)).fetchone()


# --------------------------------------------------
# КЛАВИАТУРЫ
# --------------------------------------------------

def button(text, callback):
    return InlineKeyboardButton(text=text, callback_data=callback)


def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("⭐ Telegram Stars", "catalog:stars"), button("💎 Premium", "catalog:premium")],
        [button("💳 Пополнение Steam", "catalog:steam")],
        [button("🎮 Игры", "catalog:games")],
        [button("📦 Мои заказы", "orders"), button("👤 Профиль", "profile")],
        [button("🤝 Пригласить друга", "referral"), button("⭐ Отзывы", "reviews")],
        [button("🔔 Новости и акции", "marketing")],
        [button("💬 Поддержка", "support")],
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
        [button("⭐ 50", "product:stars_50"), button("⭐ 100", "product:stars_100"), button("⭐ 200", "product:stars_200")],
        [button("⭐ 250", "product:stars_250"), button("⭐ 500", "product:stars_500"), button("⭐ 750", "product:stars_750")],
        [button("⭐ 1 000", "product:stars_1000"), button("⭐ 1 500", "product:stars_1500"), button("⭐ 2 000", "product:stars_2000")],
        [button("⭐ 3 000", "product:stars_3000"), button("⭐ 5 000", "product:stars_5000"), button("⭐ 10 000", "product:stars_10000")],
        [button("✍️ Другое количество", "stars:custom")],
        [button("⬅️ Назад", "home"), button("🎁 Подарить", "gift:stars")],
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


def get_usdt_rate():
    try:
        with connect_db() as db:
            row = db.execute("SELECT value FROM settings WHERE key='usdt_rub_rate'").fetchone()
        return max(0.01, float(row["value"])) if row else 84.0
    except (sqlite3.Error, TypeError, ValueError):
        return 84.0


def product_usdt_price(product):
    if "price_usdt" in product.keys() and product["price_usdt"] is not None:
        return float(product["price_usdt"])
    if product["price_rub"] is not None:
        return round(float(product["price_rub"]) / 85.0, 4)
    return None


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
            usdt_price = product_usdt_price(product)
            if usdt_price is not None:
                label += f' / {usdt_price:g} USDT'

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

    rows.append([button("🎟️ Ввести промокод", f"promo:apply:{product['product_id']}")])

    category = product["category"]
    back = f"game:{category}" if category in GAMES else f"catalog:{category}"

    rows.append([
        button("⬅️ Назад", back),
        button("🏠 Главное меню", "home"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)



BANNER_ALIASES = {
    "main": ("main.gif", "GGSTAR_banner_animated_pro_640x360.gif", "ggstar_banner.gif", "main.png", "main.jpg", "GGSTAR_banner_640x360.jpg"),
    "stars": ("stars.png", "stars.jpg"),
    "premium": ("premium.png", "premium.jpg"),
    "steam": ("steam.png", "steam.jpg"),
    "games": ("games.png", "games.jpg"),
    "pubg": ("pubg.png", "pubg.jpg"),
    "genshin": ("genshin.png", "genshin.jpg"),
    "roblox": ("roblox.png", "roblox.jpg"),
    "mlbb": ("mlbb.png", "mlbb.jpg"),
    "valorant": ("valorant.png", "valorant.jpg"),
    "freefire": ("freefire.png", "freefire.jpg"),
    "vip": ("vip.png", "vip.jpg"),
    "order_success": ("order_success.png", "order_success.jpg"),
    "order_completed": ("order_completed.png", "order_completed.jpg"),
    "unavailable": ("unavailable.png", "unavailable.jpg"),
}


def get_banner(key):
    if not key:
        return None
    candidates = BANNER_ALIASES.get(key, tuple(f"{key}.{ext}" for ext in ("gif", "jpg", "png", "jpeg")))
    for name in candidates:
        for folder in (BANNER_DIR, BASE_DIR):
            file_path = folder / name
            if file_path.is_file():
                return file_path
    return None


async def _send_page_message(message, text, reply_markup, banner=None):
    if banner is not None:
        try:
            upload = FSInputFile(str(banner))
            if banner.suffix.lower() == ".gif":
                return await message.answer_animation(
                    animation=upload,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                )
            return await message.answer_photo(
                photo=upload,
                caption=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        except (TelegramAPIError, OSError) as error:
            print(f"GGSTAR: не удалось отправить баннер {banner.name}: {error}")
    return await message.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def show_page(target, text, reply_markup, banner_key=None):
    banner = get_banner(banner_key)
    if isinstance(target, CallbackQuery):
        await target.answer()
        message = target.message
        if message is None:
            return
        try:
            await message.delete()
        except TelegramAPIError:
            pass
        await _send_page_message(message, text, reply_markup, banner=banner)
        return
    await _send_page_message(target, text, reply_markup, banner=banner)

# --------------------------------------------------
# СТАРТ И ГЛАВНОЕ МЕНЮ
# --------------------------------------------------

WELCOME = (
    "🌟 <b>GGSTAR</b>\n"
    "<i>Твой магазин цифровых товаров</i>\n\n"
    "<b>Выбери нужный товар.</b>"
)


@dp.message(CommandStart())
async def start(message: Message):
    user = message.from_user
    referrer_id = None
    parts = (message.text or "").split(maxsplit=1)
    
    
    if len(parts) == 2 and parts[1].startswith("ref_"):
        referral = get_referral_by_code(parts[1][4:])
        if referral:
            referrer_id = referral["user_id"]
    save_user(user.id, user.username, user.full_name, referrer_id=referrer_id)
    await show_page(message, WELCOME, main_keyboard(), banner_key="main")


@dp.callback_query(F.data == "home")
async def home(callback: CallbackQuery):
    pending_inputs.pop(callback.from_user.id, None)
    await show_page(callback, WELCOME, main_keyboard(), banner_key="main")


@dp.callback_query(F.data == "marketing")
async def marketing_preferences(callback: CallbackQuery):
    with connect_db() as db:
        user = db.execute("SELECT marketing_opt_in FROM users WHERE user_id = ?", (callback.from_user.id,)).fetchone()
    enabled = bool(user and user["marketing_opt_in"])
    text = (
        "🔔 <b>Новости и акции GGSTAR</b>\n\n"
        + ("Уведомления включены. Ты будешь получать новости, конкурсы и промокоды." if enabled else "Уведомления выключены. Включи их, чтобы получать новости, конкурсы и промокоды.")
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [button("🔕 Выключить уведомления" if enabled else "🔔 Включить уведомления", "marketing:toggle")],
        [button("⬅️ Назад", "home")],
    ])
    await show_page(callback, text, keyboard)


@dp.callback_query(F.data == "marketing:toggle")
async def marketing_toggle(callback: CallbackQuery):
    with connect_db() as db:
        row = db.execute("SELECT marketing_opt_in FROM users WHERE user_id = ?", (callback.from_user.id,)).fetchone()
        enabled = not bool(row and row["marketing_opt_in"])
        db.execute("UPDATE users SET marketing_opt_in = ?, last_seen_at = CURRENT_TIMESTAMP WHERE user_id = ?", (1 if enabled else 0, callback.from_user.id))
    log_activity(callback.from_user.id, "marketing_opt_in" if enabled else "marketing_opt_out", "user", callback.from_user.id)
    text = (
        "🔔 <b>Новости и акции GGSTAR</b>\n\n"
        + ("Уведомления включены. Ты будешь получать новости, конкурсы и промокоды." if enabled else "Уведомления выключены. Ты больше не будешь получать рекламные рассылки.")
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [button("🔕 Выключить уведомления" if enabled else "🔔 Включить уведомления", "marketing:toggle")],
        [button("⬅️ Назад", "home")],
    ])
    await show_page(callback, text, keyboard)


@dp.callback_query(F.data == "referral")
async def referral_page(callback: CallbackQuery):
    with connect_db() as db:
        user = db.execute("SELECT referral_code FROM users WHERE user_id = ?", (callback.from_user.id,)).fetchone()
        count = db.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id = ?", (callback.from_user.id,)).fetchone()[0]
        converted = db.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id = ? AND status = 'rewarded'", (callback.from_user.id,)).fetchone()[0]
    code = user["referral_code"] if user else f"GG{callback.from_user.id}"
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{code}"
    text = (
        "🤝 <b>Приглашай друзей в GGSTAR</b>\n\n"
        "Отправь другу персональную ссылку. Когда приглашённый клиент совершит первую покупку, ты получишь промокод на следующую покупку.\n\n"
        f"👥 Приглашено: <b>{count}</b>\n"
        f"🎁 Покупка совершена: <b>{converted}</b>\n\n"
        f"🔗 <code>{html.escape(link)}</code>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={link}&text=Попробуй%20GGSTAR")],
        [button("⬅️ Назад", "home")],
    ])
    await show_page(callback, text, keyboard)


@dp.callback_query(F.data == "reviews")
async def public_reviews(callback: CallbackQuery):
    with connect_db() as db:
        rows = db.execute("SELECT product_name,rating,comment,created_at FROM reviews WHERE status = 'approved' ORDER BY id DESC LIMIT 10").fetchall()
    if not rows:
        text = "⭐ <b>Отзывы о GGSTAR</b>\n\nПока нет опубликованных отзывов. После завершения заказа ты сможешь оставить честный отзыв о покупке."
    else:
        lines = ["⭐ <b>Отзывы покупателей GGSTAR</b>"]
        for row in rows:
            stars = "⭐" * int(row["rating"])
            comment = html.escape(row["comment"] or "Без комментария")
            lines.append(f"\n{stars} <b>{html.escape(row['product_name'])}</b>\n{comment}\n<i>Проверенная покупка · {html.escape(str(row['created_at'] or ''))[:10]}</i>")
        text = "\n".join(lines)
    await show_page(callback, text, back_keyboard())


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
            banner_key="games",
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
        banner_key=category,
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
        banner_key=game_id,
    )






def checkout_destination_keyboard(product_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("👤 Себе", f"recipient:self:{product_id}"), button("🎁 В подарок", f"recipient:gift:{product_id}")],
        [button("⬅️ Назад", f"product:{product_id}"), button("🏠 Главное меню", "home")],
    ])


def checkout_payment_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("🏦 СБП", "checkoutpay:sbp"), button("₮ USDT", "checkoutpay:usdt")],
        [button("⬅️ Назад", "home"), button("❌ Отмена", "checkout:cancel")],
    ])


@dp.callback_query(F.data == "checkout:cancel")
async def checkout_cancel(callback: CallbackQuery):
    pending_inputs.pop(callback.from_user.id, None)
    user_promos.pop(callback.from_user.id, None)
    await show_page(callback, "Оформление отменено. Товар можно выбрать заново.", main_keyboard())


@dp.callback_query(F.data.startswith("recipient:"))
async def checkout_recipient(callback: CallbackQuery):
    parts = callback.data.split(":", 2)
    if len(parts) != 3 or parts[1] not in {"self", "gift"}:
        await callback.answer("Некорректный выбор.", show_alert=True)
        return
    choice, product_id = parts[1], parts[2]
    state = pending_inputs.get(callback.from_user.id, {})
    if state.get("mode") != "checkout_destination" or state.get("product_id") != product_id:
        await callback.answer("Начни оформление товара заново.", show_alert=True)
        return
    product = get_product(product_id)
    if not product or product["category"] not in {"stars", "premium"}:
        await callback.answer("Товар не найден.", show_alert=True)
        return
    if choice == "gift":
        pending_inputs[callback.from_user.id] = {"mode": "checkout_gift_recipient", "product_id": product_id}
        await show_page(callback, "🎁 <b>Кому отправить подарок?</b>\n\nВведи username получателя в формате <code>@username</code>.\nЧтобы отменить оформление, отправь /cancel.", back_keyboard(f"product:{product_id}"), banner_key=product["category"])
        return
    # Поставщикам Stars обычно нужен username. Если у пользователя его нет, запросим его.
    if not callback.from_user.username:
        pending_inputs[callback.from_user.id] = {"mode": "checkout_self_username", "product_id": product_id}
        await show_page(callback, "👤 <b>Username своего аккаунта</b>\n\nУ твоего Telegram-аккаунта нет username. Установи его в настройках Telegram или введи username аккаунта, который нужно пополнить.", back_keyboard(f"product:{product_id}"), banner_key=product["category"])
        return
    pending_inputs[callback.from_user.id] = {"mode": "checkout_payment", "product_id": product_id, "recipient": "@" + callback.from_user.username, "is_gift": False}
    await show_page(callback, "💳 <b>Выбери способ оплаты</b>\n\nПосле выбора будет создан заказ. Приём платежей пока обрабатывается вручную: не отправляй деньги до получения подтверждённых реквизитов от GGSTAR.", checkout_payment_keyboard(), banner_key=product["category"])


@dp.callback_query(F.data.startswith("checkoutpay:"))
async def checkout_payment(callback: CallbackQuery):
    payment_method = callback.data.split(":", 1)[1]
    if payment_method not in {"sbp", "usdt"}:
        await callback.answer("Неизвестный способ оплаты.", show_alert=True)
        return
    user_id = callback.from_user.id
    state = pending_inputs.get(user_id, {})
    if state.get("mode") != "checkout_payment":
        await callback.answer("Начни оформление товара заново.", show_alert=True)
        return
    product = get_product(state.get("product_id", ""))
    if not product or not product["is_active"] or product["price_rub"] is None:
        pending_inputs.pop(user_id, None)
        await callback.answer("Товар пока недоступен.", show_alert=True)
        return
    recipient = state.get("recipient", "")
    product_copy = dict(product)
    product_copy["name"] = f"{product['name']} → {recipient}"
    order_id = create_order(user_id, product_copy)
    order = get_order(order_id)
    price_rub = float(order["price_rub"] if order else product["price_rub"])
    rate = 84.0
    with connect_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key='usdt_rub_rate'").fetchone()
        if row:
            try: rate = float(row["value"])
            except (ValueError, TypeError): pass
    price_usdt = (order["price_usdt"] if order and order["price_usdt"] is not None else round(price_rub / 85.0, 4))
    if payment_method == "usdt":
        price_rub = round(float(price_usdt) * max(rate, 0.01), 2)
    with connect_db() as db:
        db.execute("UPDATE orders SET payment_method=?,price_usdt=?,price_rub=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (payment_method, price_usdt, price_rub, order_id))
    pending_inputs.pop(user_id, None)
    user_promos.pop(user_id, None)
    payment_label = "СБП" if payment_method == "sbp" else "USDT"
    amount_label = f"{price_rub:g} ₽" if payment_method == "sbp" else f"{price_usdt:g} USDT"
    message_text = (
        f"✅ <b>Заказ №{order_id} оформлен</b>\n\n"
        f"🛍 Товар: <b>{html.escape(product['name'])}</b>\n"
        f"📨 Получатель: <b>{html.escape(recipient)}</b>\n"
        f"💳 Способ оплаты: <b>{payment_label}</b>\n"
        f"💰 Сумма: <b>{amount_label}</b>\n\n"
        "⚠️ Приём оплат ещё подключается. Администратор пришлёт подтверждённые инструкции по оплате. Не отправляй средства на случайные реквизиты. После подтверждения оплаты заказ будет обработан."
    )
    await show_page(callback, message_text, main_keyboard(), banner_key="order_success")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id,
                f"🆕 <b>Заказ №{order_id}</b>\n\nПользователь: <code>{user_id}</code>\nТовар: {html.escape(product_copy['name'])}\nСумма: {html.escape(amount_label)}\nОплата: {payment_label}\nСтатус: {ORDER_STATUS_LABELS['pending']}")
        except TelegramAPIError as error:
            print(f"GGSTAR: не удалось уведомить администратора {admin_id}: {error}")
    log_activity(user_id, "checkout_created", "order", order_id, f"method={payment_method};recipient={recipient}")


def gift_amount_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("⭐ 50", "giftamount:50"), button("⭐ 100", "giftamount:100"), button("⭐ 200", "giftamount:200")],
        [button("⭐ 250", "giftamount:250"), button("⭐ 500", "giftamount:500"), button("⭐ 750", "giftamount:750")],
        [button("⭐ 1 000", "giftamount:1000"), button("⭐ 1 500", "giftamount:1500"), button("⭐ 2 000", "giftamount:2000")],
        [button("⭐ 3 000", "giftamount:3000"), button("⭐ 5 000", "giftamount:5000"), button("⭐ 10 000", "giftamount:10000")],
        [button("✍️ Другое количество", "giftamount:custom")],
        [button("⬅️ Назад", "catalog:stars"), button("🏠 Главное меню", "home")],
    ])


def upsert_custom_stars(amount: int):
    """Creates a custom Stars SKU using the same per-Star rate as the 100 Stars SKU."""
    base = get_product("stars_100")
    rate = 84.0
    with connect_db() as db:
        rate_row = db.execute("SELECT value FROM settings WHERE key='usdt_rub_rate'").fetchone()
        if rate_row:
            try:
                rate = float(rate_row["value"])
            except (TypeError, ValueError):
                pass
    ready = bool(base and base["is_active"] and base["price_rub"] is not None)
    price_rub = round(float(base["price_rub"]) * amount / 100, 2) if ready else None
    if ready and base["price_usdt"] is not None:
        price_usdt = round(float(base["price_usdt"]) * amount / 100, 4)
    else:
        price_usdt = round(price_rub / 85.0, 4) if ready else None
    purchase_cost_rub = round(float(base["purchase_cost_rub"]) * amount / 100, 2) if base and base["purchase_cost_rub"] is not None else None
    purchase_cost_usdt = round(float(base["purchase_cost_usdt"]) * amount / 100, 4) if base and base["purchase_cost_usdt"] is not None else None
    product_id = f"stars_custom_{amount}"
    product_name = f"{amount} звёзд"
    with connect_db() as db:
        db.execute("""INSERT INTO products(product_id,category,name,price_rub,is_active,price_usdt,purchase_cost_rub,purchase_cost_usdt,updated_at)
            VALUES(?, 'stars', ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(product_id) DO UPDATE SET name=excluded.name,price_rub=excluded.price_rub,is_active=excluded.is_active,
            price_usdt=excluded.price_usdt,purchase_cost_rub=excluded.purchase_cost_rub,purchase_cost_usdt=excluded.purchase_cost_usdt,updated_at=CURRENT_TIMESTAMP""",
            (product_id, product_name, price_rub, 1 if ready else 0, price_usdt, purchase_cost_rub, purchase_cost_usdt))
    return get_product(product_id)


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

    pending_inputs[user_id] = {
        "mode": "checkout_payment",
        "product_id": product["product_id"],
        "recipient": state["recipient"],
        "is_gift": True,
    }
    await show_page(
        callback,
        f"🎁 <b>Подарок на {amount} Stars</b>\n\n"
        f"Получатель: <b>{html.escape(state['recipient'])}</b>\n"
        f"Цена: <b>{product['price_rub']:g} ₽</b>\n\n"
        "Теперь выбери способ оплаты. Приём платежей пока обрабатывается вручную: не отправляй деньги до получения подтверждённых реквизитов.",
        checkout_payment_keyboard(),
        banner_key="stars",
    )
@dp.callback_query(F.data.startswith("product:"))
async def product_page(callback: CallbackQuery):
    pending_inputs.pop(callback.from_user.id, None)
    product_id = callback.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    log_activity(callback.from_user.id, "product_viewed", "product", product_id)

    if product["is_active"] and product["price_rub"] is not None:
        price_text = f'{product["price_rub"]:g} ₽'
        usdt_price = product_usdt_price(product)
        if usdt_price is not None:
            price_text += f' / {usdt_price:g} USDT'
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
        banner_key=product["category"],
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
        await callback.answer("Товар пока недоступен.", show_alert=True)
        return

    if product["category"] in {"stars", "premium"}:
        pending_inputs[callback.from_user.id] = {"mode": "checkout_destination", "product_id": product_id}
        title = "Telegram Stars" if product["category"] == "stars" else "Telegram Premium"
        await show_page(
            callback,
            f"📨 <b>Куда отправить покупку?</b>\n\nТовар: <b>{html.escape(product['name'])}</b>\nВыбери, для себя покупаешь или в подарок.",
            checkout_destination_keyboard(product_id),
            banner_key=product["category"],
        )
        return

    order_id = create_order(callback.from_user.id, product)
    order = get_order(order_id)
    price = order["price_rub"] if order else product["price_rub"]
    discount = order["discount_amount_rub"] if order else 0
    promo_line = f"\n🎟 Промокод: <code>{html.escape(order['promo_code'])}</code> (−{discount:g} ₽)" if order and order["promo_code"] else ""
    confirmation = (
        f"✅ <b>Заявка №{order_id} создана</b>\n\n"
        f"🛍 Товар: <b>{html.escape(product['name'])}</b>\n"
        f"💰 К оплате: <b>{price:g} ₽</b>{promo_line}\n"
        f"📌 Статус: <b>{order_status_label('pending')}</b>\n\n"
        "Мы проверим заказ и сообщим об изменениях. Создание заявки само по себе не подтверждает оплату."
    )
    await show_page(callback, confirmation, main_keyboard(), banner_key="order_success")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 <b>Новая заявка №{order_id}</b>\n\n"
                f"👤 Пользователь: <code>{callback.from_user.id}</code>\n"
                f"🛍 Товар: {html.escape(product['name'])}\n"
                f"💰 Цена: {price:g} ₽\n"
                f"📌 Статус: {order_status_label('pending')}",
            )
        except TelegramAPIError as error:
            print(f"GGSTAR: не удалось уведомить администратора {admin_id}: {error}")


@dp.callback_query(F.data.startswith("notify:"))
async def notify_product(callback: CallbackQuery):
    product_id = callback.data.split(":", 1)[1]
    product = get_product(product_id)
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    await show_page(
        callback,
        f"🔔 <b>Товар пока недоступен</b>\n\n{html.escape(product['name'])}\n\nМы ещё настраиваем цену или поставщика. Загляни позже или напиши в поддержку.",
        back_keyboard(f"product:{product_id}"),
        banner_key="unavailable",
    )


ORDER_STATUS_LABELS = {
    "pending": "🕓 Ожидает оплаты",
    "paid": "💳 Оплата подтверждена",
    "processing": "⚙️ В обработке",
    "delayed": "⏳ Задерживается",
    "completed": "✅ Выполнен",
    "cancelled": "❌ Отменён",
    "refunded": "↩️ Возврат",
    "problem": "⚠️ Требует внимания",
}

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
            if row["payment_method"] == "usdt" and row["price_usdt"] is not None:
                price = f'{row["price_usdt"]:g} USDT'
            else:
                price = f'{row["price_rub"]:g} ₽' if row["price_rub"] is not None else "Цена не задана"

            lines.append(
                f'№{row["id"]} · {html.escape(row["product_name"])}\n'
                f'💰 {price} · Статус: {html.escape(ORDER_STATUS_LABELS.get(row["status"], row["status"]))}'
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


def save_review(user_id, order_id, rating, comment):
    order = get_order(order_id)
    if not order or int(order["user_id"]) != int(user_id) or order["status"] != "completed":
        return False
    with connect_db() as db:
        try:
            db.execute("INSERT INTO reviews(order_id,user_id,product_id,product_name,rating,comment,status) VALUES(?,?,?,?,?,?,'pending')", (
                order_id, user_id, order["product_id"], order["product_name"], rating, comment[:1500],
            ))
        except sqlite3.IntegrityError:
            return False
    log_activity(user_id, "review_submitted", "review", order_id, f"rating={rating}")
    for admin_id in ADMIN_IDS:
        try:
            asyncio.create_task(bot.send_message(
                admin_id,
                f"⭐ <b>Новый отзыв на модерации</b>\n\nЗаказ №{order_id} · {html.escape(order['product_name'])}\nПокупатель: <code>{user_id}</code>\nОценка: {'⭐' * rating}\nКомментарий: {html.escape(comment or 'без комментария')}"
            ))
        except Exception:
            pass
    return True


def validate_promo(code, user_id, category=None):
    code = code.strip().upper()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect_db() as db:
        promo = db.execute("SELECT * FROM promo_codes WHERE code = ? AND active = 1", (code,)).fetchone()
        if not promo:
            return None, "Промокод не найден или отключён."
        if promo["user_id"] is not None and int(promo["user_id"]) != int(user_id):
            return None, "Этот промокод выдан другому покупателю."
        if promo["category"] and category and promo["category"] != category:
            return None, "Этот промокод не подходит для выбранной категории."
        if promo["usage_limit"] is not None and int(promo["uses"]) >= int(promo["usage_limit"]):
            return None, "Лимит использований этого промокода исчерпан."
        if promo["starts_at"] and promo["starts_at"] > now:
            return None, "Промокод пока не действует."
        if promo["expires_at"] and promo["expires_at"] < now:
            return None, "Срок действия промокода истёк."
        used = db.execute("SELECT 1 FROM promo_redemptions WHERE code = ? AND user_id = ? AND status != 'released' LIMIT 1", (code, user_id)).fetchone()
        if used:
            return None, "Ты уже использовал этот промокод."
    return promo, None


def support_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("✉️ Написать в поддержку", "support:write")],
        [button("⬅️ Назад", "home")],
    ])


@dp.callback_query(F.data == "support")
async def support(callback: CallbackQuery):
    text = (
        "💬 <b>Поддержка GGSTAR</b>\n\n"
        "Напиши нам, если есть вопрос по товару, оплате или заказу.\n\n"
        "Укажи номер заказа, если обращение связано с покупкой. Не отправляй пароли и коды входа."
    )
    await show_page(callback, text, support_keyboard())


@dp.callback_query(F.data == "support:write")
async def support_write(callback: CallbackQuery):
    pending_inputs[callback.from_user.id] = {"mode": "support_message"}
    await show_page(
        callback,
        "✉️ <b>Сообщение в поддержку</b>\n\nНапиши обращение одним сообщением. Чтобы отменить, отправь /cancel.",
        back_keyboard("support"),
    )


@dp.callback_query(F.data.startswith("promo:apply:"))
async def promo_apply_start(callback: CallbackQuery):
    product_id = callback.data.split(":", 2)[2]
    product = get_product(product_id)
    if not product:
        await callback.answer("Товар не найден.", show_alert=True)
        return
    pending_inputs[callback.from_user.id] = {"mode": "promo_code", "product_id": product_id}
    await show_page(
        callback,
        f"🎟️ <b>Промокод</b>\n\nТовар: <b>{html.escape(product['name'])}</b>\nВведи код скидки. Чтобы вернуться без скидки, отправь /cancel.",
        back_keyboard(f"product:{product_id}"),
    )


@dp.callback_query(F.data.startswith("review:"))
async def review_start(callback: CallbackQuery):
    raw_id = callback.data.split(":", 1)[1]
    if not raw_id.isdigit():
        await callback.answer("Некорректный заказ.", show_alert=True)
        return
    order = get_order(int(raw_id))
    if not order or int(order["user_id"]) != callback.from_user.id or order["status"] != "completed":
        await callback.answer("Оставить отзыв можно только о выполненном заказе.", show_alert=True)
        return
    with connect_db() as db:
        existing = db.execute("SELECT id FROM reviews WHERE order_id = ?", (int(raw_id),)).fetchone()
    if existing:
        await callback.answer("Отзыв по этому заказу уже отправлен.", show_alert=True)
        return
    pending_inputs[callback.from_user.id] = {"mode": "review_rating", "order_id": int(raw_id)}
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [button("⭐ 1", f"reviewrate:{raw_id}:1"), button("⭐ 2", f"reviewrate:{raw_id}:2"), button("⭐ 3", f"reviewrate:{raw_id}:3"), button("⭐ 4", f"reviewrate:{raw_id}:4"), button("⭐ 5", f"reviewrate:{raw_id}:5")],
        [button("Отмена", "home")],
    ])
    await show_page(callback, f"⭐ <b>Оценка заказа №{raw_id}</b>\n\nВыбери оценку от 1 до 5. Отзыв будет отмечен как проверенная покупка и опубликован после модерации.", keyboard)


@dp.callback_query(F.data.startswith("reviewrate:"))
async def review_set_rating(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await callback.answer("Некорректная оценка.", show_alert=True)
        return
    order_id, rating = int(parts[1]), int(parts[2])
    state = pending_inputs.get(callback.from_user.id, {})
    order = get_order(order_id)
    if state.get("mode") != "review_rating" or state.get("order_id") != order_id:
        await callback.answer("Начни отзыв заново из сообщения о выполнении заказа.", show_alert=True)
        return
    if rating not in range(1, 6) or not order or order["user_id"] != callback.from_user.id or order["status"] != "completed":
        await callback.answer("Оставить отзыв можно только о выполненном заказе.", show_alert=True)
        return
    pending_inputs[callback.from_user.id] = {"mode": "review_comment", "order_id": order_id, "rating": rating}
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[button("Пропустить комментарий", f"review_skip:{order_id}")]])
    await show_page(callback, f"⭐ Оценка: {'⭐' * rating}\n\nНапиши комментарий к покупке. Отправлять фото или личные данные не нужно.", keyboard)


@dp.callback_query(F.data.startswith("review_skip:"))
async def review_skip_comment(callback: CallbackQuery):
    raw_id = callback.data.split(":", 1)[1]
    state = pending_inputs.get(callback.from_user.id, {})
    if not raw_id.isdigit() or state.get("mode") != "review_comment" or state.get("order_id") != int(raw_id):
        await callback.answer("Начни отзыв заново.", show_alert=True)
        return
    await save_review(callback.from_user.id, int(raw_id), int(state["rating"]), "")
    pending_inputs.pop(callback.from_user.id, None)
    await show_page(callback, "✅ <b>Спасибо за отзыв!</b>\n\nОн отправлен на проверку и будет опубликован после модерации.", main_keyboard(), banner_key="order_completed")


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
        "<code>/disable ID</code> — выключить товар\n"
        "<code>/ordersadmin</code> — последние заказы\n"
        "<code>/reply USER_ID ТЕКСТ</code> — ответить клиенту\n\n"
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




@dp.message(Command("ordersadmin"))
async def admin_orders(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    with connect_db() as db:
        rows = db.execute("SELECT id,user_id,product_name,price_rub,status,created_at FROM orders ORDER BY id DESC LIMIT 15").fetchall()
    if not rows:
        await message.answer("Заказов пока нет.")
        return
    for row in rows:
        await message.answer(
            f"🧾 <b>Заказ №{row['id']}</b>\n"
            f"👤 <code>{row['user_id']}</code>\n"
            f"🛍 {html.escape(row['product_name'])}\n"
            f"💰 {row['price_rub']:g} ₽\n"
            f"📌 {html.escape(ORDER_STATUS_LABELS.get(row['status'], row['status']))}\n"
            f"🗓 {html.escape(str(row['created_at'] or '—'))}"
        )

@dp.message(Command("cancel"))
async def cancel_pending(message: Message):
    pending_inputs.pop(message.from_user.id, None)
    user_promos.pop(message.from_user.id, None)
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

    if mode in {"checkout_gift_recipient", "checkout_self_username"}:
        recipient = raw
        if recipient.startswith("https://t.me/"):
            recipient = "@" + recipient.rstrip("/").split("/")[-1]
        elif not recipient.startswith("@"):
            recipient = "@" + recipient
        username = recipient[1:]
        if not 5 <= len(username) <= 32 or not all(ch.isalnum() or ch == "_" for ch in username):
            await message.answer("Не получилось распознать username. Введи в формате <code>@username</code>.")
            return
        product = get_product(state.get("product_id", ""))
        if not product:
            pending_inputs.pop(user_id, None)
            await message.answer("Товар не найден. Начни оформление заново.", reply_markup=main_keyboard())
            return
        is_gift = mode == "checkout_gift_recipient"
        pending_inputs[user_id] = {"mode": "checkout_payment", "product_id": product["product_id"], "recipient": recipient, "is_gift": is_gift}
        await message.answer(
            f"{'🎁 Получатель' if is_gift else '👤 Аккаунт для пополнения'}: <b>{html.escape(recipient)}</b>\n\nВыбери способ оплаты:",
            reply_markup=checkout_payment_keyboard(),
        )
        return

    if mode == "promo_code":
        product_id = state.get("product_id")
        product = get_product(product_id)
        if not product:
            pending_inputs.pop(user_id, None)
            await message.answer("Товар не найден. Начни оформление заново.", reply_markup=main_keyboard())
            return
        promo, error = validate_promo(raw, user_id, product["category"])
        if error:
            await message.answer(f"❌ {html.escape(error)}\nПопробуй ещё раз или отправь /cancel.")
            return
        user_promos[user_id] = {"code": promo["code"], "product_id": product_id}
        pending_inputs.pop(user_id, None)
        if product["price_rub"] is None:
            await message.answer("✅ Промокод проверен. Но цена товара ещё не настроена; скидка применится после настройки цены.", reply_markup=product_keyboard(product))
        else:
            if promo["discount_type"] == "percent":
                discount = round(float(product["price_rub"]) * float(promo["discount_value"]) / 100, 2)
            else:
                discount = min(float(product["price_rub"]), float(promo["discount_value"]))
            await message.answer(
                f"✅ <b>Промокод применён</b>\n\n🎟 Код: <code>{html.escape(promo['code'])}</code>\n"
                f"💸 Скидка: <b>{discount:.2f} ₽</b>\n"
                f"🛍 Товар: {html.escape(product['name'])}\n"
                f"💰 Цена после скидки: <b>{max(0.01, float(product['price_rub']) - discount):.2f} ₽</b>\n\n"
                "Нажми «Оформить заявку», чтобы зарезервировать скидку.",
                reply_markup=product_keyboard(product),
            )
        log_activity(user_id, "promo_validated", "promo", promo["code"], f"product={product_id}")
        return

    if mode == "review_comment":
        order_id = int(state["order_id"])
        rating = int(state["rating"])
        if len(raw) > 1500:
            await message.answer("Комментарий слишком длинный. Максимум 1500 символов.")
            return
        saved = save_review(user_id, order_id, rating, raw)
        pending_inputs.pop(user_id, None)
        await message.answer(
            "✅ <b>Спасибо за отзыв!</b>\n\nОн отправлен на модерацию. После проверки появится в разделе отзывов.",
            reply_markup=main_keyboard(),
        )
        if not saved:
            await message.answer("Если отзыв по этому заказу уже был отправлен, повторно добавить его нельзя.")
        return

    if mode == "support_message":
        if not raw:
            await message.answer("Напиши обращение текстом.")
            return
        pending_inputs.pop(user_id, None)
        with connect_db() as db:
            ticket = db.execute("INSERT INTO support_tickets(user_id,subject,status) VALUES(?, 'Обращение в поддержку', 'new')", (user_id,))
            ticket_id = ticket.lastrowid
            db.execute("INSERT INTO support_messages(ticket_id,user_id,actor,body) VALUES(?,?,?,?)", (ticket_id, user_id, str(user_id), raw))
        log_activity(user_id, "support_ticket_created", "ticket", ticket_id, raw[:200])
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id,
                    f"📩 <b>Обращение №{ticket_id}</b>\n\n👤 {html.escape(message.from_user.full_name)}\nID: <code>{user_id}</code>\n\n{html.escape(raw)}\n\nОтветить: <code>/reply {user_id} Текст ответа</code>")
            except TelegramAPIError as error:
                print(f"GGSTAR: ошибка уведомления поддержки: {error}")
        await message.answer("✅ Обращение передано в поддержку. Ответ придёт сюда в Telegram.", reply_markup=main_keyboard())
        return

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

        product = upsert_custom_stars(amount)
        product_id = product["product_id"]

        if mode == "gift_custom_amount":
            recipient = state["recipient"]
            if not product["is_active"] or product["price_rub"] is None:
                pending_inputs.pop(user_id, None)
                await message.answer(
                    f"🎁 <b>Подарок для {html.escape(recipient)}</b>\n\n"
                    f"Количество: <b>{amount} Stars</b>\n\n"
                    "Цена пока не настроена. Сначала установи стоимость 100 Stars в админ-панели — цена произвольного номинала будет рассчитываться пропорционально.",
                    reply_markup=main_keyboard(),
                )
                return
            pending_inputs[user_id] = {"mode": "checkout_payment", "product_id": product_id, "recipient": recipient, "is_gift": True}
            await message.answer(
                f"🎁 <b>Подарок для {html.escape(recipient)}</b>\n\n"
                f"Количество: <b>{amount} Stars</b>\n"
                f"Цена: <b>{product['price_rub']:g} ₽</b>\n\nВыбери способ оплаты:",
                reply_markup=checkout_payment_keyboard(),
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
    migrate_extended_db()

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
