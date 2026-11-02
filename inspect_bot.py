from pathlib import Path

p = Path("bot.py")
text = p.read_text(encoding="utf-8-sig")

for name in ["CATALOG", "GAMES", "products_keyboard", "product_keyboard", "catalog", "game_page"]:
    print(f"\n{'=' * 15} {name} {'=' * 15}")
    pos = text.find(name)
    if pos == -1:
        print("Не найдено")
    else:
        print(text[max(0, pos - 100):pos + 1800])
