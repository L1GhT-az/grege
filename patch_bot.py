from pathlib import Path
import re

path = Path("bot.py")
source = path.read_text(encoding="utf-8-sig")

catalog = '''CATALOG = {
    "stars": {
        "title": "Telegram Stars",
        "emoji": "⭐",
        "description": "Звёзды Telegram",
        "products": [
            ("stars_50", "50 звёзд"),
            ("stars_100", "100 звёзд"),
            ("stars_200", "200 звёзд"),
            ("stars_250", "250 звёзд"),
            ("stars_500", "500 звёзд"),
            ("stars_750", "750 звёзд"),
            ("stars_1000", "1000 звёзд"),
            ("stars_1500", "1500 звёзд"),
            ("stars_2500", "2500 звёзд"),
            ("stars_5000", "5000 звёзд"),
        ],
    },
    "premium": {
        "title": "Telegram Premium",
        "emoji": "💎",
        "description": "Подписка Telegram Premium",
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
            ("steam_100", "100 ₽ на баланс"),
            ("steam_300", "300 ₽ на баланс"),
            ("steam_500", "500 ₽ на баланс"),
            ("steam_1000", "1000 ₽ на баланс"),
            ("steam_custom", "Другая сумма"),
        ],
    },
    "games": {
        "title": "Игры",
        "emoji": "🎮",
        "description": "Пополнение и подарочные карты",
        "products": [],
    },
}

GAMES = {
    "pubg": {
        "title": "PUBG Mobile",
        "emoji": "🎯",
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
        "products": [
            ("roblox_robux_400", "400 Robux"),
            ("roblox_robux_800", "800 Robux"),
            ("roblox_robux_1700", "1700 Robux"),
            ("roblox_robux_4500", "4500 Robux"),
            ("roblox_robux_10000", "10000 Robux"),
            ("roblox_giftcard", "Подарочная карта Roblox"),
        ],
    },
    "brawl": {
        "title": "Brawl Stars",
        "emoji": "⭐",
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
        "products": [
            ("mlbb_diamonds_86", "86 Diamonds"),
            ("mlbb_diamonds_172", "172 Diamonds"),
            ("mlbb_diamonds_257", "257 Diamonds"),
            ("mlbb_diamonds_706", "706 Diamonds"),
            ("mlbb_diamonds_1412", "1412 Diamonds"),
            ("mlbb_weekly", "Weekly Diamond Pass"),
        ],
    },
    "freefire": {
        "title": "Free Fire",
        "emoji": "🔥",
        "products": [
            ("freefire_gift_100", "Подарочная карта — 100"),
            ("freefire_gift_310", "Подарочная карта — 310"),
            ("freefire_gift_520", "Подарочная карта — 520"),
            ("freefire_gift_1060", "Подарочная карта — 1060"),
            ("freefire_gift_2180", "Подарочная карта — 2180"),
        ],
    },
    "valorant": {
        "title": "Valorant",
        "emoji": "🎯",
        "products": [
            ("valorant_gift_475", "Подарочная карта — 475 VP"),
            ("valorant_gift_1000", "Подарочная карта — 1000 VP"),
            ("valorant_gift_2050", "Подарочная карта — 2050 VP"),
            ("valorant_gift_3650", "Подарочная карта — 3650 VP"),
            ("valorant_gift_5350", "Подарочная карта — 5350 VP"),
        ],
    },
    "other": {
        "title": "Другие игры",
        "emoji": "🕹",
        "products": [
            ("other_request", "Запросить другую игру"),
        ],
    },
}'''

source, count = re.subn(
    r'CATALOG = \{.*?(?=\n# --------------------------------------------------\n# БАЗА ДАННЫХ)',
    catalog,
    source,
    count=1,
    flags=re.S,
)
if count != 1:
    raise RuntimeError("Не удалось заменить каталог. Исходный файл не сохранён.")

keyboard_code = '''def products_keyboard(category, products):
    rows = []
    row = []
    columns = 4 if category == "stars" else 2

    for product in products:
        if not product["is_active"] or product["price_rub"] is None:
            label = f'▫️ {product["name"]}'
        else:
            label = f'{product["name"]} · {product["price_rub"]:g} ₽'

        row.append(button(label[:64], f'product:{product["product_id"]}'))

        if len(row) == columns:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    if category == "stars":
        rows.append([
            button("⬅️ Назад", "home"),
            button("🎁 Подарить", "gift:stars"),
        ])
    else:
        back = f"game:{category}" if category in GAMES else "home"
        rows.append([button("⬅️ Назад", back)])

    rows.append([button("🏠 Главное меню", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_keyboard(product):
    rows = []

    if product["is_active"] and product["price_rub"] is not None:
        rows.append([
            button("🛒 Оставить заявку", f'order:{product["product_id"]}')
        ])
    else:
        rows.append([
            button("🔔 Уведомить о запуске", f'notify:{product["product_id"]}')
        ])

    category = product["category"]
    back = f"game:{category}" if category in GAMES else f"catalog:{category}"

    rows.append([button("⬅️ Назад", back)])
    rows.append([button("🏠 Главное меню", "home")])

    return InlineKeyboardMarkup(inline_keyboard=rows)
'''

source, count = re.subn(
    r'def products_keyboard\(category, products\):.*?(?=\nasync def show_page\()',
    keyboard_code + "\n\n",
    source,
    count=1,
    flags=re.S,
)
if count != 1:
    raise RuntimeError("Не удалось заменить клавиатуры. Исходный файл не сохранён.")

# Добавляем обработчик подарка, если его ещё нет.
if 'F.data == "gift:stars"' not in source:
    gift_handler = '''

@dp.callback_query(F.data == "gift:stars")
async def gift_stars(callback: CallbackQuery):
    await show_page(
        callback,
        "🎁 <b>Подарить Telegram Stars</b>\\\\n\\\\n"
        "Выбери номинал звёзд, затем укажи получателя.\\\\n"
        "Функция оформления подарка будет доступна после подключения поставщика.",
        back_keyboard("catalog:stars"),
    )

'''
    marker = '@dp.callback_query(F.data.startswith("product:"))'
    if marker not in source:
        raise RuntimeError("Не найден обработчик товаров. Исходный файл не сохранён.")
    source = source.replace(marker, gift_handler + marker, 1)

# Обновляем названия и категории существующих записей, сохраняя цены и статусы.
source = source.replace(
    '''                    ON CONFLICT(product_id) DO NOTHING
''',
    '''                    ON CONFLICT(product_id) DO UPDATE SET
                        category = excluded.category,
                        name = excluded.name
''',
)
source = source.replace(
    '''                    VALUES (?, ?, ?, NULL, 0)
                """, (product_id, category, name))''',
    '''                    VALUES (?, ?, ?, NULL, 0)
                    ON CONFLICT(product_id) DO UPDATE SET
                        category = excluded.category,
                        name = excluded.name
                """, (product_id, category, name))''',
)

path.write_text(source, encoding="utf-8")
print("Каталог и клавиатуры обновлены.")
