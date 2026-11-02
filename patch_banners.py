from pathlib import Path
import re
import shutil

path = Path("bot.py")
source = path.read_text(encoding="utf-8-sig")

if "BANNER_DIR" in source or "get_banner" in source:
    raise SystemExit(
        "Подключение баннеров уже частично существует. "
        "Не изменяю файл повторно."
    )

old_import = "from aiogram.types import ("
if old_import not in source:
    raise SystemExit("Не найден блок импортов. Файл не изменён.")

source = source.replace(
    old_import,
    "from aiogram.types import FSInputFile\n" + old_import,
    1,
)

old_db = 'DB_PATH = BASE_DIR / "ggstar.db"'
if old_db not in source:
    raise SystemExit("Не найден DB_PATH. Файл не изменён.")

source = source.replace(
    old_db,
    old_db + '\nBANNER_DIR = BASE_DIR / "assets"',
    1,
)

new_function = '''def get_banner(key):
    if key is None:
        return None

    for extension in ("jpg", "png", "jpeg"):
        file_path = BANNER_DIR / f"{key}.{extension}"
        if file_path.is_file():
            return file_path

    return None


async def show_page(target, text, reply_markup, banner_key=None):
    banner = get_banner(banner_key)

    if isinstance(target, CallbackQuery):
        await target.answer()
        message = target.message

        if banner is not None:
            try:
                await message.delete()
            except TelegramAPIError:
                pass

            await message.answer_photo(
                photo=FSInputFile(str(banner)),
                caption=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
            return

        if message.photo:
            try:
                await message.delete()
            except TelegramAPIError:
                pass
            await message.answer(text, reply_markup=reply_markup)
            return

        try:
            await message.edit_text(text, reply_markup=reply_markup)
        except TelegramAPIError:
            await message.answer(text, reply_markup=reply_markup)

    elif banner is not None:
        await target.answer_photo(
            photo=FSInputFile(str(banner)),
            caption=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    else:
        await target.answer(text, reply_markup=reply_markup)
'''

pattern = (
    r'async def show_page\(target, text, reply_markup\):'
    r'.*?(?=\n# --------------------------------------------------\n# СТАРТ И ГЛАВНОЕ МЕНЮ)'
)

source, count = re.subn(
    pattern,
    lambda _: new_function,
    source,
    count=1,
    flags=re.S,
)

if count != 1:
    raise SystemExit("Не найдена старая функция show_page. Файл не изменён.")

start_pattern = re.compile(
    r'@dp\.message\(CommandStart\(\)\)\s*'
    r'async def start\(message: Message\):.*?'
    r'(?=\n@dp\.callback_query\(F\.data == "home"\))',
    re.S,
)

new_start = '''@dp.message(CommandStart())
async def start(message: Message):
    user = message.from_user
    save_user(user.id, user.username, user.full_name)
    await show_page(message, WELCOME, main_keyboard(), banner_key="main")
'''

source, count = start_pattern.subn(
    lambda _: new_start,
    source,
    count=1,
)

if count != 1:
    raise SystemExit("Не найден обработчик /start. Файл не изменён.")

def replace_once(old, new, description):
    global source
    if source.count(old) != 1:
        raise SystemExit(
            f"Не удалось найти блок «{description}». Файл не изменён."
        )
    source = source.replace(old, new, 1)

replace_once(
    'await show_page(callback, WELCOME, main_keyboard())',
    'await show_page(callback, WELCOME, main_keyboard(), banner_key="main")',
    "главное меню",
)

replace_once(
    '            games_keyboard(),\n        )',
    '            games_keyboard(),\n            banner_key="games",\n        )',
    "каталог игр",
)

replace_once(
    '        products_keyboard(category, products),\n    )',
    '        products_keyboard(category, products),\n'
    '        banner_key=category,\n    )',
    "категория товаров",
)

replace_once(
    '        products_keyboard(game_id, products),\n    )',
    '        products_keyboard(game_id, products),\n'
    '        banner_key=game_id,\n    )',
    "страница игры",
)

replace_once(
    '        product_keyboard(product),\n    )',
    '        product_keyboard(product),\n'
    '        banner_key=product["category"],\n    )',
    "страница товара",
)

compile(source, str(path), "exec")

backup = Path("bot_backup_before_banners.py")
if not backup.exists():
    shutil.copy2(path, backup)

path.write_text(source, encoding="utf-8")
print("Готово: баннеры подключены к коду.")
print("Создана резервная копия bot_backup_before_banners.py")
