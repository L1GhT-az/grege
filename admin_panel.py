from __future__ import annotations

import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template_string, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DB_PATH = Path(os.getenv("GGSTAR_DB_PATH", str(BASE_DIR / "ggstar.db"))).expanduser()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_PANEL_SECRET = os.getenv("ADMIN_PANEL_SECRET", "").strip()
ADMIN_PANEL_HOST = os.getenv("ADMIN_PANEL_HOST", "127.0.0.1")
ADMIN_PANEL_PORT = int(os.getenv("ADMIN_PANEL_PORT", "8765"))


def load_panel_users() -> dict[str, str]:
    raw = os.getenv("ADMIN_PANEL_USERS", "").strip()
    users: dict[str, str] = {}
    if raw:
        for item in raw.split(","):
            if ":" not in item:
                continue
            username, password = item.split(":", 1)
            username, password = username.strip(), password.strip()
            if username and password:
                users[username] = password
    legacy_user = os.getenv("ADMIN_PANEL_USER", "admin").strip() or "admin"
    legacy_password = os.getenv("ADMIN_PANEL_PASSWORD", "").strip()
    if not users and legacy_password:
        users[legacy_user] = legacy_password
    return users


PANEL_USERS = load_panel_users()
app = Flask(__name__)
app.secret_key = ADMIN_PANEL_SECRET
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("ADMIN_PANEL_HTTPS", "0") == "1",
    MAX_CONTENT_LENGTH=512 * 1024,
)

ORDER_STATUSES = {
    "pending": "🕓 Ожидает оплаты",
    "paid": "💳 Оплачен",
    "processing": "⚙️ В обработке",
    "delayed": "⏳ Задерживается",
    "completed": "✅ Выполнен",
    "problem": "⚠️ Проблема",
    "cancelled": "❌ Отменён",
    "refunded": "↩️ Возврат",
}
STATUS_COLORS = {
    "pending": "pending", "paid": "paid", "processing": "processing",
    "delayed": "delayed", "completed": "completed", "problem": "problem",
    "cancelled": "cancelled", "refunded": "refunded",
}
PAID_STATUSES = ("paid", "processing", "delayed", "completed")
PANEL_SCHEMA_READY = False

BASE_HTML = r'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} · GGSTAR Admin</title>
<style>
:root{color-scheme:dark;--bg:#0d0f12;--panel:#16191e;--panel2:#1b1f26;--line:#2c313b;--text:#f1f3f5;--muted:#9ba3af;--gold:#e6bb5b;--green:#53c795;--red:#f07880;--blue:#82adff;--orange:#f0aa62}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,Segoe UI,Arial,sans-serif}a{color:inherit;text-decoration:none}button,input,select,textarea{font:inherit}button,.button{border:1px solid var(--line);border-radius:9px;background:#242a33;color:var(--text);padding:9px 12px;cursor:pointer;display:inline-block}button:hover,.button:hover{border-color:var(--gold)}button.primary,.button.primary{background:var(--gold);border-color:var(--gold);color:#151515;font-weight:750}button.danger{border-color:#69383c;color:#ffb2b7}.wrap{max-width:1520px;margin:auto;padding:20px}.top{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:22px;flex-wrap:wrap}.brand{font-size:20px;font-weight:850;letter-spacing:.4px}.brand b{color:var(--gold)}.muted{color:var(--muted)}.nav{display:flex;gap:7px;flex-wrap:wrap}.nav a{padding:8px 10px;border:1px solid var(--line);border-radius:9px;color:#d9dce3}.nav a.active,.nav a:hover{border-color:var(--gold);color:var(--gold)}h1{font-size:26px;margin:0 0 5px}h2{font-size:18px;margin:0 0 14px}h3{font-size:15px;margin:0 0 9px}.sub{color:var(--muted);margin-bottom:20px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:17px;min-width:0}.metric{font-size:27px;font-weight:800;margin-top:7px;overflow-wrap:anywhere}.metric.gold{color:var(--gold)}.metric.green{color:var(--green)}.section{margin-top:22px}.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}table{border-collapse:collapse;width:100%;min-width:740px}th,td{padding:11px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:650;font-size:11px;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}tr:last-child td{border-bottom:0}.small{font-size:12px;color:var(--muted)}.badge{display:inline-block;border-radius:99px;padding:4px 8px;font-size:12px;white-space:nowrap}.pending{background:#43361c;color:#ffdc8d}.paid{background:#183f35;color:#8ce7c1}.processing{background:#1c3155;color:#a9c8ff}.delayed{background:#523719;color:#ffd19a}.completed{background:#173b29;color:#91e9ad}.cancelled,.refunded{background:#48262a;color:#ffabb0}.problem{background:#4a2b44;color:#ffb1f2}.input{width:100%;min-width:90px;padding:9px 10px;border-radius:8px;border:1px solid var(--line);background:#101318;color:var(--text)}textarea.input{min-height:100px;resize:vertical}.inline-form{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:15px 0}.filters .input{width:auto;min-width:145px}.alert{padding:11px 13px;border:1px solid var(--line);background:var(--panel);border-radius:9px;margin:10px 0}.alert.success{border-color:#276d4f}.alert.error{border-color:#834348}.empty{text-align:center;padding:30px;color:var(--muted)}.login{max-width:420px;margin:10vh auto;padding:26px}.login .input{margin:8px 0 14px}.footer{margin-top:24px;color:var(--muted);font-size:12px}.actions{display:flex;gap:7px;flex-wrap:wrap}.actions form{margin:0}.product-name{font-weight:680}.nowrap{white-space:nowrap}.success-text{color:var(--green)}.danger-text{color:var(--red)}.field{margin-bottom:12px}.field label{display:block;color:#c6cbd4;font-size:12px;margin-bottom:5px}.field .input{width:100%}.form-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.bar-list{display:grid;gap:9px}.bar-row{display:grid;grid-template-columns:105px minmax(60px,1fr) 105px;gap:10px;align-items:center}.bar{height:9px;background:#292f39;border-radius:99px;overflow:hidden}.bar>span{display:block;height:100%;background:var(--gold);border-radius:99px}.note{padding:11px 13px;border-radius:9px;background:#20242b;color:#bfc5cf;font-size:12px}.tabs{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0}.code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.split{display:grid;grid-template-columns:1fr 1fr;gap:15px}.table-form .input{min-width:90px}
@media(max-width:1050px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.form-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.nav{order:3;width:100%}}
@media(max-width:600px){.wrap{padding:12px}.grid,.grid.two,.grid.three,.split{grid-template-columns:1fr}.form-grid{grid-template-columns:1fr}.metric{font-size:23px}.top{align-items:flex-start}h1{font-size:22px}.bar-row{grid-template-columns:75px minmax(35px,1fr) 80px}}
</style></head><body><div class="wrap">
{% if user %}<header class="top"><a class="brand" href="{{ url_for('dashboard') }}">★ <b>GGSTAR</b> Admin</a><nav class="nav">
<a class="{{ 'active' if section=='dashboard' else '' }}" href="{{ url_for('dashboard') }}">Главная</a>
<a class="{{ 'active' if section=='orders' else '' }}" href="{{ url_for('orders') }}">Заказы</a>
<a class="{{ 'active' if section=='products' else '' }}" href="{{ url_for('products') }}">Товары</a>
<a class="{{ 'active' if section=='clients' else '' }}" href="{{ url_for('clients') }}">Клиенты</a>
<a class="{{ 'active' if section=='support' else '' }}" href="{{ url_for('support') }}">Поддержка</a>
<a class="{{ 'active' if section=='marketing' else '' }}" href="{{ url_for('marketing') }}">Промо / рассылки</a>
<a class="{{ 'active' if section=='reviews' else '' }}" href="{{ url_for('reviews') }}">Отзывы</a>
<a class="{{ 'active' if section=='activity' else '' }}" href="{{ url_for('activity') }}">Активность</a>
<a class="{{ 'active' if section=='settings' else '' }}" href="{{ url_for('settings') }}">Настройки</a>
</nav><div class="muted">{{ user }} · <a href="{{ url_for('logout') }}">Выйти</a></div></header>{% endif %}
{% with messages = get_flashed_messages(with_categories=true) %}{% for category, message in messages %}<div class="alert {{ category }}">{{ message|safe }}</div>{% endfor %}{% endwith %}
{{ body|safe }}<div class="footer">GGSTAR Admin · {{ now }} · Все изменения записываются в журнал</div></div></body></html>'''


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def db_connect():
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Не найдена база данных: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=20000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_column(db, table: str, definition: str) -> None:
    column = definition.split()[0]
    existing = {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def ensure_panel_schema() -> None:
    global PANEL_SCHEMA_READY
    if PANEL_SCHEMA_READY or not DB_PATH.is_file():
        return
    with sqlite3.connect(DB_PATH, timeout=20) as db:
        db.execute("PRAGMA busy_timeout=20000")
        for definition in ("last_seen_at TEXT", "referral_code TEXT", "referred_by INTEGER", "marketing_opt_in INTEGER NOT NULL DEFAULT 0", "banned INTEGER NOT NULL DEFAULT 0", "notes TEXT"):
            ensure_column(db, "users", definition)
        for definition in ("price_usdt REAL", "purchase_cost_rub REAL", "purchase_cost_usdt REAL", "supplier TEXT", "updated_at TEXT"):
            ensure_column(db, "products", definition)
        for definition in ("price_usdt REAL", "purchase_cost_rub REAL", "purchase_cost_usdt REAL", "discount_amount_rub REAL NOT NULL DEFAULT 0", "promo_code TEXT", "payment_method TEXT", "paid_at TEXT", "completed_at TEXT", "delay_eta TEXT", "delay_message TEXT", "delay_promo_code TEXT", "responsible TEXT", "updated_at TEXT", "source TEXT"):
            ensure_column(db, "orders", definition)
        statements = [
            """CREATE TABLE IF NOT EXISTS activity_log(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL DEFAULT 'system',action TEXT NOT NULL,entity_type TEXT,entity_id TEXT,details TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS order_status_history(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL,actor TEXT NOT NULL DEFAULT 'system',old_status TEXT,new_status TEXT NOT NULL,note TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS promo_codes(code TEXT PRIMARY KEY,discount_type TEXT NOT NULL DEFAULT 'percent',discount_value REAL NOT NULL DEFAULT 0,usage_limit INTEGER,uses INTEGER NOT NULL DEFAULT 0,user_id INTEGER,category TEXT,starts_at TEXT,expires_at TEXT,active INTEGER NOT NULL DEFAULT 1,reason TEXT,created_by TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS promo_redemptions(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT NOT NULL,user_id INTEGER NOT NULL,order_id INTEGER NOT NULL,discount_amount_rub REAL NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'reserved',created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(code,user_id,order_id))""",
            """CREATE TABLE IF NOT EXISTS support_tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,subject TEXT NOT NULL DEFAULT 'Обращение в поддержку',status TEXT NOT NULL DEFAULT 'new',assigned_to TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS support_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id INTEGER NOT NULL,user_id INTEGER NOT NULL,actor TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS customer_notes(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,actor TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL UNIQUE,user_id INTEGER NOT NULL,product_id TEXT,product_name TEXT NOT NULL,rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),comment TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'pending',created_at TEXT DEFAULT CURRENT_TIMESTAMP,moderated_by TEXT,moderated_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS referrals(id INTEGER PRIMARY KEY AUTOINCREMENT,inviter_id INTEGER NOT NULL,referred_id INTEGER NOT NULL UNIQUE,first_order_id INTEGER,status TEXT NOT NULL DEFAULT 'registered',reward_code TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,converted_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS broadcast_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,message TEXT NOT NULL,audience TEXT NOT NULL,total_count INTEGER NOT NULL DEFAULT 0,sent_count INTEGER NOT NULL DEFAULT 0,failed_count INTEGER NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS broadcast_recipients(id INTEGER PRIMARY KEY AUTOINCREMENT,broadcast_id INTEGER NOT NULL,user_id INTEGER NOT NULL,status TEXT NOT NULL,error TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)""",
        ]
        for sql in statements:
            db.execute(sql)
        db.execute("UPDATE users SET referral_code='GG'||CAST(user_id AS TEXT) WHERE referral_code IS NULL OR referral_code='' ")
        db.execute("UPDATE users SET last_seen_at=COALESCE(last_seen_at,created_at,CURRENT_TIMESTAMP)")
        for key, value in (("tax_rate_percent", "6"), ("sbp_fee_percent", "3"), ("referral_reward_percent", "5"), ("usdt_rub_rate", "84"), ("delay_promo_percent", "5")):
            db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))
        db.commit()
    PANEL_SCHEMA_READY = True


def log_activity(actor: str, action: str, entity_type: str | None = None, entity_id: object | None = None, details: str | None = None) -> None:
    try:
        with db_connect() as db:
            db.execute("INSERT INTO activity_log(actor,action,entity_type,entity_id,details) VALUES(?,?,?,?,?)", (str(actor), action, entity_type, str(entity_id) if entity_id is not None else None, details))
    except (sqlite3.Error, FileNotFoundError):
        pass


def render_page(title: str, section: str, body: str):
    return render_template_string(BASE_HTML, title=title, section=section, body=body, user=session.get("panel_user"), now=datetime.now().strftime("%d.%m.%Y %H:%M"))


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_field() -> str:
    return f'<input type="hidden" name="csrf_token" value="{escape(csrf_token())}">'


def money(value) -> str:
    try:
        if value is None:
            return "—"
        return f"{float(value):,.2f} ₽".replace(",", " ").replace(".00 ₽", " ₽")
    except (ValueError, TypeError):
        return "—"


def setting(db, key: str, default: float = 0.0) -> float:
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    try:
        return float(row["value"]) if row else default
    except (TypeError, ValueError):
        return default


def save_setting(key: str, value: object) -> None:
    with db_connect() as db:
        db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def tg_api(method: str, payload: dict) -> tuple[bool, str, dict | None]:
    if not BOT_TOKEN:
        return False, "BOT_TOKEN не задан в .env", None
    data = dict(payload)
    for key, value in list(data.items()):
        if isinstance(value, (dict, list)):
            data[key] = json.dumps(value, ensure_ascii=False)
    req = Request(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", data=urlencode(data).encode("utf-8"), headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result.get("ok"):
            return True, "OK", result.get("result")
        return False, str(result.get("description", "Telegram API error")), result
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        return False, str(exc), None


def create_promo(code: str | None, discount_type: str, discount_value: float, usage_limit: int | None, user_id: int | None, category: str | None, expiry: str | None, reason: str, actor: str) -> str:
    if not code:
        code = "GG" + secrets.token_hex(4).upper()
    code = "".join(ch for ch in code.upper().strip() if ch.isalnum() or ch in "-_")[:32]
    if not code:
        raise ValueError("Промокод содержит недопустимые символы.")
    if discount_type not in {"percent", "fixed"} or discount_value <= 0:
        raise ValueError("Укажи корректный тип и размер скидки.")
    if discount_type == "percent" and discount_value > 100:
        raise ValueError("Процентная скидка не может быть больше 100%.")
    if usage_limit is not None and usage_limit < 1:
        raise ValueError("Лимит использований должен быть больше нуля.")
    expires_at = None
    if expiry:
        try:
            expires_at = datetime.strptime(expiry, "%Y-%m-%d").strftime("%Y-%m-%d 23:59:59")
        except ValueError as exc:
            raise ValueError("Некорректная дата окончания промокода.") from exc
    with db_connect() as db:
        db.execute("INSERT INTO promo_codes(code,discount_type,discount_value,usage_limit,user_id,category,expires_at,active,reason,created_by) VALUES(?,?,?,?,?,?,?,1,?,?)", (code, discount_type, discount_value, usage_limit, user_id, category, expires_at, reason[:300], actor))
    log_activity(actor, "promo_created", "promo", code, reason)
    return code


def notify_customer(user_id: int, order_id: int, product_name: str, status: str, delay_eta: str | None = None, delay_message: str | None = None, promo_code: str | None = None) -> tuple[bool, str]:
    label = ORDER_STATUSES.get(status, status)
    text = f"📦 <b>Обновление заказа №{order_id}</b>\n\n🛍 {escape(product_name)}\n📌 Статус: <b>{escape(label)}</b>"
    keyboard = None
    if status == "paid":
        text += "\n\nОплату подтвердили. Заказ передан на обработку."
    elif status == "processing":
        text += "\n\nЗаказ в работе. Сообщим, когда всё будет готово."
    elif status == "delayed":
        text = f"⏳ <b>Извините, заказ №{order_id} задерживается</b>\n\nМы столкнулись с задержкой при обработке заказа. Приносим извинения за ожидание."
        if delay_message:
            text += f"\n\n{escape(delay_message)}"
        if delay_eta:
            text += f"\n\n🕓 Ожидаемый срок: <b>{escape(delay_eta)}</b>"
        if promo_code:
            text += f"\n\n🎟 В качестве извинения дарим промокод <code>{escape(promo_code)}</code>. Он привязан к твоему аккаунту и действует на одну покупку."
        text += "\n\nСпасибо за терпение. Если срок изменится, мы сообщим отдельно."
    elif status == "completed":
        text += "\n\n🎉 <b>Заказ выполнен!</b> Спасибо за покупку в GGSTAR. Будем рады видеть тебя снова!\n\nЕсли всё прошло хорошо, оставь отзыв — он будет отмечен как подтверждённая покупка."
        keyboard = {"inline_keyboard": [[{"text": "⭐ Оставить отзыв", "callback_data": f"review:{order_id}"}], [{"text": "🏠 В магазин", "callback_data": "home"}]]}
    elif status == "cancelled":
        text += "\n\nЗаказ отменён. Если нужна помощь, напиши в поддержку GGSTAR."
    elif status == "refunded":
        text += "\n\nПо заказу отмечен возврат средств. Если у тебя остались вопросы, напиши в поддержку."
    elif status == "problem":
        text += "\n\nЗаказ требует дополнительной проверки. Мы сообщим, когда появятся новости."
    payload = {"chat_id": str(user_id), "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = keyboard
    ok, detail, _ = tg_api("sendMessage", payload)
    return ok, ("Уведомление отправлено." if ok else f"Уведомление не отправлено: {detail}")


def generate_delay_coupon(user_id: int, actor: str, order_id: int) -> str:
    with db_connect() as db:
        percent = setting(db, "delay_promo_percent", 5.0)
    code = create_promo(None, "percent", max(1, min(100, percent)), 1, user_id, None, (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"), f"Извинение за задержку заказа №{order_id}", actor)
    return code


def process_referral_conversion(user_id: int, order_id: int, actor: str) -> tuple[int | None, str | None]:
    with db_connect() as db:
        ref = db.execute("SELECT * FROM referrals WHERE referred_id = ? AND status = 'registered'", (user_id,)).fetchone()
        if not ref:
            return None, None
        percent = setting(db, "referral_reward_percent", 5.0)
    code = create_promo(None, "percent", max(1, min(100, percent)), 1, int(ref["inviter_id"]), None, (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"), "Бонус за приглашённого друга", actor)
    with db_connect() as db:
        db.execute("UPDATE referrals SET status='rewarded',first_order_id=?,reward_code=?,converted_at=CURRENT_TIMESTAMP WHERE id=?", (order_id, code, ref["id"]))
    message = f"🎉 <b>Твой друг совершил первую покупку в GGSTAR!</b>\n\nВ качестве благодарности дарим тебе промокод <code>{escape(code)}</code> на скидку {percent:g}%. Он привязан к твоему аккаунту и действует 30 дней."
    tg_api("sendMessage", {"chat_id": int(ref["inviter_id"]), "text": message, "parse_mode": "HTML"})
    log_activity(actor, "referral_converted", "referral", ref["id"], f"order={order_id}; reward={code}")
    return int(ref["inviter_id"]), code


LOGIN_ATTEMPTS: dict[str, list[float]] = {}


@app.before_request
def protect_pages():
    ensure_panel_schema()
    if request.endpoint in {"login", "login_post", "static"}:
        return None
    if not PANEL_USERS:
        return render_page("Нужен пароль", "", '<section class="card login"><h1>Настрой доступ</h1><p>В .env задай <code>ADMIN_PANEL_USERS=owner:длинный-пароль,friend:другой-пароль</code>, затем перезапусти панель.</p></section>'), 503
    if "panel_user" not in session:
        return redirect(url_for("login", next=request.path))
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not supplied or not expected or not hmac.compare_digest(supplied, expected):
            abort(400, description="Форма устарела. Обнови страницу и повтори действие.")
    return None


@app.get("/login")
def login():
    if not PANEL_USERS:
        return render_page("Настройка входа", "", '<section class="card login"><h1>Настрой вход</h1><p>Добавь в .env строку <code>ADMIN_PANEL_USERS=owner:пароль,friend:пароль</code> и перезапусти панель.</p></section>'), 503
    if "panel_user" in session:
        return redirect(url_for("dashboard"))
    token = csrf_token()
    body = f'''<section class="card login"><div class="brand">★ <b>GGSTAR</b> Admin</div><h1 style="margin-top:16px">Вход в панель</h1><p class="muted">Управление магазином, заказами и клиентами.</p><form method="post" action="{url_for('login_post')}">{csrf_field()}<div class="field"><label>Логин</label><input class="input" name="username" autocomplete="username" required autofocus></div><div class="field"><label>Пароль</label><input class="input" type="password" name="password" autocomplete="current-password" required></div><button class="primary" style="width:100%">Войти</button></form></section>'''
    return render_page("Вход", "", body)


@app.post("/login")
def login_post():
    ip = request.remote_addr or "unknown"
    ts = time.time()
    attempts = [x for x in LOGIN_ATTEMPTS.get(ip, []) if ts - x < 300]
    LOGIN_ATTEMPTS[ip] = attempts
    if len(attempts) >= 10:
        flash("Слишком много попыток. Подожди 5 минут.", "error")
        return redirect(url_for("login"))
    if not hmac.compare_digest(request.form.get("csrf_token", ""), session.get("csrf_token", "")):
        flash("Форма устарела. Обнови страницу и повтори.", "error")
        return redirect(url_for("login"))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    saved = PANEL_USERS.get(username)
    if saved is None or not hmac.compare_digest(password, saved):
        attempts.append(ts)
        LOGIN_ATTEMPTS[ip] = attempts
        flash("Неверный логин или пароль.", "error")
        return redirect(url_for("login"))
    LOGIN_ATTEMPTS.pop(ip, None)
    session.clear()
    session["panel_user"] = username
    csrf_token()
    log_activity(username, "panel_login", "user", username)
    flash(f"Добро пожаловать, {escape(username)}!", "success")
    next_url = request.args.get("next", "")
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect(url_for("dashboard"))


@app.get("/logout")
def logout():
    log_activity(session.get("panel_user", "unknown"), "panel_logout", "user", session.get("panel_user"))
    session.clear()
    return redirect(url_for("login"))


def period_bounds(period: str) -> tuple[str, str, str]:
    today = datetime.now().date()
    if period == "yesterday":
        start = today - timedelta(days=1)
        end = today
    elif period == "7d":
        start, end = today - timedelta(days=6), today + timedelta(days=1)
    elif period == "30d":
        start, end = today - timedelta(days=29), today + timedelta(days=1)
    elif period == "month":
        start, end = today.replace(day=1), today + timedelta(days=1)
    elif period == "prev_month":
        end = today.replace(day=1)
        start = (end - timedelta(days=1)).replace(day=1)
    else:
        start, end = today, today + timedelta(days=1)
        period = "today"
    return start.strftime("%Y-%m-%d 00:00:00"), end.strftime("%Y-%m-%d 00:00:00"), period


@app.get("/")
def dashboard():
    period = request.args.get("period", "today")
    start, end, period = period_bounds(period)
    paid_placeholders = ",".join("?" for _ in PAID_STATUSES)
    with db_connect() as db:
        products = db.execute("SELECT COUNT(*) total, SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) active FROM products").fetchone()
        users = db.execute("SELECT COUNT(*) total, SUM(CASE WHEN date(last_seen_at)=date('now','localtime') THEN 1 ELSE 0 END) active_today, SUM(CASE WHEN marketing_opt_in=1 THEN 1 ELSE 0 END) opted_in FROM users").fetchone()
        overall_orders = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        pending = db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        delayed = db.execute("SELECT COUNT(*) FROM orders WHERE status='delayed'").fetchone()[0]
        stats = db.execute(f"""SELECT COUNT(*) order_count,COALESCE(SUM(price_rub),0) revenue,COALESCE(SUM(CASE WHEN purchase_cost_rub IS NOT NULL THEN purchase_cost_rub WHEN purchase_cost_usdt IS NOT NULL THEN purchase_cost_usdt*? ELSE 0 END),0) costs, SUM(CASE WHEN purchase_cost_rub IS NULL AND purchase_cost_usdt IS NULL THEN 1 ELSE 0 END) missing_cost, COALESCE(SUM(CASE WHEN payment_method='sbp' THEN price_rub*? ELSE 0 END),0) sbp_fee FROM orders WHERE status IN ({paid_placeholders}) AND COALESCE(paid_at,created_at)>=? AND COALESCE(paid_at,created_at)<?""", (setting(db,"usdt_rub_rate",84),setting(db,"sbp_fee_percent",3)/100,*PAID_STATUSES,start,end)).fetchone()
        tax_rate = setting(db, "tax_rate_percent", 6.0)
        tax = float(stats["revenue"] or 0)*tax_rate/100
        profit = float(stats["revenue"] or 0)-float(stats["costs"] or 0)-float(stats["sbp_fee"] or 0)-tax
        recent = db.execute("SELECT id,user_id,product_name,price_rub,status,created_at FROM orders ORDER BY id DESC LIMIT 8").fetchall()
        trend = []
        for offset in range(13,-1,-1):
            day=(datetime.now().date()-timedelta(days=offset)).strftime("%Y-%m-%d")
            rev=db.execute(f"SELECT COALESCE(SUM(price_rub),0) FROM orders WHERE status IN ({paid_placeholders}) AND date(COALESCE(paid_at,created_at))=?",(*PAID_STATUSES,day)).fetchone()[0]
            trend.append((day[5:],float(rev or 0)))
        max_rev=max((x[1] for x in trend),default=0) or 1
        top_products=db.execute(f"SELECT product_name,COUNT(*) cnt,COALESCE(SUM(price_rub),0) revenue FROM orders WHERE status IN ({paid_placeholders}) GROUP BY product_name ORDER BY revenue DESC LIMIT 5",PAID_STATUSES).fetchall()
    body=f'''<div><h1>Обзор магазина</h1><div class="sub">Финансовые показатели за выбранный период и оперативная сводка GGSTAR.</div></div>
<form class="filters" method="get"><select class="input" name="period">'''
    labels={"today":"Сегодня","yesterday":"Вчера","7d":"Последние 7 дней","30d":"Последние 30 дней","month":"Текущий месяц","prev_month":"Предыдущий месяц"}
    for value,label in labels.items(): body+=f'<option value="{value}"{" selected" if period==value else ""}>{label}</option>'
    body+='''</select><button class="primary">Показать</button><a class="button" href="/">Сегодня</a></form>'''
    body+=f'''<div class="grid">
<div class="card"><div class="muted">Выручка</div><div class="metric gold">{money(stats['revenue'])}</div><div class="small">Оплаченные заказы за период</div></div>
<div class="card"><div class="muted">Расчётная прибыль</div><div class="metric {'green' if profit>=0 else ''}">{money(profit)}</div><div class="small">Доход − закупка − комиссии − налог</div></div>
<div class="card"><div class="muted">Заказы за период</div><div class="metric">{stats['order_count']}</div><div class="small">Всего в базе: {overall_orders}</div></div>
<div class="card"><div class="muted">Новые / ожидают</div><div class="metric">{pending}</div><div class="small">Задерживаются: {delayed}</div></div>
<div class="card"><div class="muted">Пользователи</div><div class="metric">{users['total'] or 0}</div><div class="small">Активны сегодня: {users['active_today'] or 0}</div></div>
<div class="card"><div class="muted">Подписаны на акции</div><div class="metric">{users['opted_in'] or 0}</div><div class="small">Получают рассылки по согласию</div></div>
<div class="card"><div class="muted">Себестоимость</div><div class="metric">{money(stats['costs'])}</div><div class="small">В заказах без закупочной цены: {stats['missing_cost'] or 0}</div></div>
<div class="card"><div class="muted">Товары</div><div class="metric">{products['active'] or 0} / {products['total'] or 0}</div><div class="small">Активных / всего</div></div>
</div>'''
    body+='<section class="section grid two"><div class="card"><h2>Выручка по дням · 14 дней</h2><div class="bar-list">'
    for day,rev in trend:
        width=int(rev/max_rev*100) if max_rev else 0
        body+=f'<div class="bar-row"><div class="small">{escape(day)}</div><div class="bar"><span style="width:{width}%"></span></div><div class="small" style="text-align:right">{money(rev)}</div></div>'
    body+='</div></div><div class="card"><h2>Топ товаров по выручке</h2><div class="table-wrap"><table><thead><tr><th>Товар</th><th>Заказы</th><th>Выручка</th></tr></thead><tbody>'
    if not top_products: body+='<tr><td colspan="3" class="empty">Пока нет оплаченных заказов</td></tr>'
    for row in top_products: body+=f'<tr><td>{escape(row["product_name"])}</td><td>{row["cnt"]}</td><td>{money(row["revenue"])}</td></tr>'
    body+='</tbody></table></div><p class="small">Прибыль точна только для заказов, в которых заполнена себестоимость. Платёжные интеграции пока не подключены.</p></div></section>'
    body+='<section class="section"><div class="top"><div><h2>Последние заказы</h2><div class="muted small">Быстрый доступ к обработке заказов</div></div><a class="button primary" href="/orders">Все заказы</a></div><div class="table-wrap"><table><thead><tr><th>№</th><th>Покупатель</th><th>Товар</th><th>Сумма</th><th>Статус</th><th>Создан</th></tr></thead><tbody>'
    for row in recent:
        status=row['status']; body+=f'<tr><td><a href="{url_for("order_detail",order_id=row["id"])}">#{row["id"]}</a></td><td><a href="{url_for("client_detail",user_id=row["user_id"])}">{row["user_id"]}</a></td><td>{escape(row["product_name"])}</td><td>{money(row["price_rub"])}</td><td><span class="badge {STATUS_COLORS.get(status,"pending")}">{escape(ORDER_STATUSES.get(status,status))}</span></td><td class="nowrap">{escape(str(row["created_at"] or "—"))}</td></tr>'
    if not recent: body+='<tr><td colspan="6" class="empty">Заказов пока нет</td></tr>'
    body+='</tbody></table></div></section>'
    return render_page("Главная", "dashboard", body)


@app.get("/products")
def products():
    q=request.args.get("q","").strip(); category=request.args.get("category","").strip(); status=request.args.get("status","").strip()
    where=[]; params=[]
    if q: where.append("(product_id LIKE ? OR name LIKE ?)"); params += [f"%{q}%", f"%{q}%"]
    if category: where.append("category=?"); params.append(category)
    if status=="active": where.append("is_active=1")
    elif status=="inactive": where.append("is_active=0")
    sql="SELECT product_id,category,name,price_rub,price_usdt,purchase_cost_rub,purchase_cost_usdt,supplier,is_active FROM products"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY category,rowid"
    with db_connect() as db:
        rows=db.execute(sql,params).fetchall(); categories=[r[0] for r in db.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()]
    body=f'''<div><div class="top"><div><h1>Товары</h1><div class="sub">Цена продажи, цена в USDT, себестоимость и поставщик. Изменения сохраняются в базе бота.</div></div><a class="button" href="/export/products.csv">Экспорт CSV</a></div>
<form class="filters" method="get"><input class="input" name="q" value="{escape(q)}" placeholder="Название или ID товара"><select class="input" name="category"><option value="">Все категории</option>'''
    for item in categories: body+=f'<option value="{escape(item)}"{" selected" if item==category else ""}>{escape(item)}</option>'
    body+=f'''</select><select class="input" name="status"><option value="">Любой статус</option><option value="active"{" selected" if status=="active" else ""}>Активные</option><option value="inactive"{" selected" if status=="inactive" else ""}>Выключенные</option></select><button class="primary">Фильтр</button><a class="button" href="/products">Сбросить</a></form>
<div class="table-wrap"><table class="table-form"><thead><tr><th>Товар / ID</th><th>Категория</th><th>Продажа ₽</th><th>Продажа USDT</th><th>Закупка ₽</th><th>Закупка USDT</th><th>Поставщик</th><th>Статус</th><th></th></tr></thead><tbody>'''
    for row in rows:
        fid="p"+str(row["product_id"]).replace("-","")
        def val(key): return "" if row[key] is None else str(row[key])
        body+=f'''<tr><td><div class="product-name">{escape(row['name'])}</div><div class="small code">{escape(row['product_id'])}</div></td><td>{escape(row['category'])}</td><td><form id="{fid}" method="post" action="/products/update">{csrf_field()}<input type="hidden" name="product_id" value="{escape(row['product_id'])}"></form><input form="{fid}" class="input" type="number" name="price_rub" min="0" step="0.01" value="{escape(val('price_rub'))}" placeholder="—"></td><td><input form="{fid}" class="input" type="number" name="price_usdt" min="0" step="0.0001" value="{escape(val('price_usdt'))}" placeholder="—"></td><td><input form="{fid}" class="input" type="number" name="purchase_cost_rub" min="0" step="0.01" value="{escape(val('purchase_cost_rub'))}" placeholder="—"></td><td><input form="{fid}" class="input" type="number" name="purchase_cost_usdt" min="0" step="0.0001" value="{escape(val('purchase_cost_usdt'))}" placeholder="—"></td><td><input form="{fid}" class="input" name="supplier" value="{escape(val('supplier'))}" placeholder="FazerCards"></td><td><label><input form="{fid}" type="checkbox" name="is_active" value="1"{' checked' if row['is_active'] else ''}> Активен</label></td><td><button form="{fid}" class="primary">Сохранить</button></td></tr>'''
    if not rows: body+='<tr><td colspan="9" class="empty">Товаров не найдено</td></tr>'
    body+='</tbody></table></div><p class="note">Пустая цена USDT не отключает товар в рублях. Для точной прибыли указывай закупочную цену. Смена прайса не меняет историческую цену уже созданных заказов.</p>'
    return render_page("Товары", "products", body)


@app.post("/products/update")
def product_update():
    product_id=request.form.get("product_id","").strip()
    fields={}
    for key in ("price_rub","price_usdt","purchase_cost_rub","purchase_cost_usdt"):
        raw=request.form.get(key,"").strip().replace(",",".")
        if not raw: fields[key]=None; continue
        try: value=float(raw)
        except ValueError: flash(f"Поле {key}: введи число.","error"); return redirect(url_for("products",q=product_id))
        if value<0 or value>100_000_000: flash("Числа должны быть неотрицательными и разумными.","error"); return redirect(url_for("products",q=product_id))
        fields[key]=value
    active=1 if request.form.get("is_active")=="1" else 0
    if active and (fields["price_rub"] is None or fields["price_rub"]<=0):
        flash("Для активности товара нужна положительная цена в рублях.","error"); return redirect(url_for("products",q=product_id))
    supplier=request.form.get("supplier","").strip()[:100]
    with db_connect() as db:
        old=db.execute("SELECT * FROM products WHERE product_id=?",(product_id,)).fetchone()
        if not old: flash("Товар не найден.","error"); return redirect(url_for("products"))
        db.execute("UPDATE products SET price_rub=?,price_usdt=?,purchase_cost_rub=?,purchase_cost_usdt=?,supplier=?,is_active=?,updated_at=CURRENT_TIMESTAMP WHERE product_id=?",(fields["price_rub"],fields["price_usdt"],fields["purchase_cost_rub"],fields["purchase_cost_usdt"],supplier,active,product_id))
    log_activity(session["panel_user"],"product_updated","product",product_id,json.dumps(fields,ensure_ascii=False))
    flash("Товар сохранён.","success")
    return redirect(url_for("products",q=product_id))


def order_query(where, params):
    sql="SELECT id,user_id,product_id,product_name,price_rub,price_usdt,purchase_cost_rub,payment_method,status,created_at,paid_at,delay_eta FROM orders"
    if where: sql += " WHERE " + " AND ".join(where)
    return sql+" ORDER BY id DESC LIMIT 300",params


@app.get("/orders")
def orders():
    q=request.args.get("q","").strip(); status_filter=request.args.get("status","").strip()
    where=[]; params=[]
    if q:
        where.append("(CAST(id AS TEXT)=? OR CAST(user_id AS TEXT)=? OR product_name LIKE ? OR COALESCE(payment_method,'') LIKE ?)")
        params += [q,q,f"%{q}%",f"%{q}%"]
    if status_filter in ORDER_STATUSES: where.append("status=?"); params.append(status_filter)
    sql,params=order_query(where,params)
    with db_connect() as db: rows=db.execute(sql,params).fetchall()
    body=f'''<div><div class="top"><div><h1>Заказы</h1><div class="sub">Открой заказ, проверь оплату и меняй статус. При задержке можно указать срок и автоматически выдать промокод.</div></div><a class="button" href="/export/orders.csv">Экспорт CSV</a></div>
<form class="filters" method="get"><input class="input" name="q" value="{escape(q)}" placeholder="№ заказа, ID клиента или товар"><select class="input" name="status"><option value="">Все статусы</option>'''
    for key,label in ORDER_STATUSES.items(): body+=f'<option value="{key}"{" selected" if status_filter==key else ""}>{escape(label)}</option>'
    body+='</select><button class="primary">Фильтр</button><a class="button" href="/orders">Сбросить</a></form><div class="table-wrap"><table><thead><tr><th>Заказ</th><th>Клиент</th><th>Товар</th><th>Сумма</th><th>Оплата</th><th>Статус</th><th>Дата</th><th></th></tr></thead><tbody>'
    for row in rows:
        status=row['status']; body+=f'<tr><td><b>#{row["id"]}</b></td><td><a href="{url_for("client_detail",user_id=row["user_id"])}">{row["user_id"]}</a></td><td>{escape(row["product_name"])}</td><td>{money(row["price_rub"])}</td><td>{escape(row["payment_method"] or "—")}</td><td><span class="badge {STATUS_COLORS.get(status,"pending")}">{escape(ORDER_STATUSES.get(status,status))}</span></td><td>{escape(str(row["created_at"] or "—"))}</td><td><a class="button" href="{url_for("order_detail",order_id=row["id"])}">Открыть</a></td></tr>'
    if not rows: body+='<tr><td colspan="8" class="empty">Заказов не найдено</td></tr>'
    body+='</tbody></table></div><p class="small">Показаны последние 300 совпадений. Не подтверждай оплату, пока фактически не проверишь поступление денег.</p>'
    return render_page("Заказы","orders",body)


@app.get("/orders/<int:order_id>")
def order_detail(order_id: int):
    with db_connect() as db:
        order=db.execute("SELECT * FROM orders WHERE id=?",(order_id,)).fetchone()
        history=db.execute("SELECT * FROM order_status_history WHERE order_id=? ORDER BY id DESC",(order_id,)).fetchall()
    if not order: abort(404)
    status=order["status"]
    body=f'''<div><a class="muted" href="/orders">← Все заказы</a><h1 style="margin-top:10px">Заказ №{order_id}</h1><div class="sub">Карточка заказа, статус, уведомление покупателю и служебная история.</div></div>
<div class="grid three"><div class="card"><div class="muted">Покупатель</div><div class="metric">{order['user_id']}</div><a class="small" href="{url_for('client_detail',user_id=order['user_id'])}">Открыть профиль</a></div><div class="card"><div class="muted">Сумма продажи</div><div class="metric gold">{money(order['price_rub'])}</div><div class="small">USDT: {escape(str(order['price_usdt'] or '—'))}</div></div><div class="card"><div class="muted">Статус</div><div class="metric">{escape(ORDER_STATUSES.get(status,status))}</div><div class="small">Создан: {escape(str(order['created_at'] or '—'))}</div></div></div>
<section class="section card"><h2>Данные заказа</h2><div class="grid two"><div><div class="muted small">Товар</div><b>{escape(order['product_name'])}</b><div class="muted small" style="margin-top:12px">ID товара</div><code>{escape(order['product_id'])}</code></div><div><div class="muted small">Способ оплаты</div><b>{escape(order['payment_method'] or 'Не указан')}</b><div class="muted small" style="margin-top:12px">Промокод</div><code>{escape(order['promo_code'] or '—')}</code></div></div></section>
<section class="section card"><h2>Обновить статус</h2><form method="post" action="/orders/update">{csrf_field()}<input type="hidden" name="order_id" value="{order_id}"><div class="form-grid"><div class="field"><label>Статус</label><select class="input" name="status">'''
    for key,label in ORDER_STATUSES.items(): body+=f'<option value="{key}"{" selected" if status==key else ""}>{escape(label)}</option>'
    body+=f'''</select></div><div class="field"><label>Срок при задержке (например, «30–60 минут», «завтра до 18:00»)</label><input class="input" name="delay_eta" value="{escape(order['delay_eta'] or '')}" placeholder="Ожидаемый срок"></div><div class="field"><label>Ответственный</label><input class="input" name="responsible" value="{escape(order['responsible'] or session['panel_user'])}"></div><div class="field"><label>Способ оплаты</label><select class="input" name="payment_method"><option value="">Не указан</option><option value="sbp"{" selected" if order['payment_method']=='sbp' else ""}>СБП</option><option value="usdt"{" selected" if order['payment_method']=='usdt' else ""}>USDT</option><option value="other"{" selected" if order['payment_method']=='other' else ""}>Другой</option></select></div></div><div class="field"><label>Комментарий покупателю / причина задержки</label><textarea class="input" name="delay_message" placeholder="Например: поставщик задержал обработку, мы уже решаем вопрос.">{escape(order['delay_message'] or '')}</textarea></div><div class="note">При статусе «Задерживается» панель автоматически выдаст персональный промокод на скидку, если он ещё не создан.</div><button class="primary">Сохранить статус и уведомить покупателя</button></form></section>
<section class="section card"><h2>История изменений</h2>'''
    if not history: body+='<p class="muted">История появится после изменения статуса через панель.</p>'
    for item in history: body+=f'<div class="alert"><b>{escape(item["actor"])}</b> · {escape(str(item["created_at"] or ""))}<br>{escape(str(item["old_status"] or "—"))} → {escape(item["new_status"])}<div class="small">{escape(item["note"] or "")}</div></div>'
    if order['delay_promo_code']: body+=f'<div class="note">Промокод за задержку уже выдан: <code>{escape(order["delay_promo_code"])}</code></div>'
    body+='</section>'
    return render_page(f"Заказ №{order_id}","orders",body)


@app.post("/orders/update")
def order_update():
    raw_id=request.form.get("order_id",""); status=request.form.get("status","")
    if not raw_id.isdigit() or status not in ORDER_STATUSES:
        flash("Некорректный заказ или статус.","error"); return redirect(url_for("orders"))
    order_id=int(raw_id); actor=session["panel_user"]
    eta=request.form.get("delay_eta","").strip()[:120]
    delay_message=request.form.get("delay_message","").strip()[:1500]
    responsible=request.form.get("responsible","").strip()[:80] or actor
    payment_method=request.form.get("payment_method","").strip().lower()
    if payment_method not in {"", "sbp", "usdt", "other"}: payment_method=""
    with db_connect() as db:
        order=db.execute("SELECT * FROM orders WHERE id=?",(order_id,)).fetchone()
        if not order: flash("Заказ не найден.","error"); return redirect(url_for("orders"))
        old_status=order["status"]
        if old_status==status and (status!="delayed" or (order["delay_eta"] or "")==eta and (order["delay_message"] or "")==delay_message):
            flash("Статус и комментарий не изменились; повторное уведомление не отправлено.","success")
            return redirect(url_for("order_detail",order_id=order_id))
        if status=="delayed" and not eta:
            flash("Для статуса «Задерживается» укажи ожидаемый срок.","error"); return redirect(url_for("order_detail",order_id=order_id))
        if status in {"processing", "delayed", "completed"} and order["paid_at"] is None and old_status not in {"paid", "processing", "delayed", "completed"}:
            flash("Сначала подтверди оплату: установи статус «Оплачен». Это защищает финансовую статистику от неоплаченных заказов.","error"); return redirect(url_for("order_detail",order_id=order_id))
        if status == "refunded" and order["paid_at"] is None and old_status not in {"paid", "processing", "delayed", "completed"}:
            flash("Нельзя оформить возврат у заказа без подтверждённой оплаты.","error"); return redirect(url_for("order_detail",order_id=order_id))
        db.execute("UPDATE orders SET status=?,delay_eta=?,delay_message=?,responsible=?,payment_method=?,updated_at=CURRENT_TIMESTAMP,paid_at=CASE WHEN ? IN ('paid','processing','delayed','completed') AND paid_at IS NULL THEN CURRENT_TIMESTAMP ELSE paid_at END,completed_at=CASE WHEN ?='completed' AND completed_at IS NULL THEN CURRENT_TIMESTAMP ELSE completed_at END WHERE id=?",(status,eta or None,delay_message or None,responsible,payment_method or None,status,status,order_id))
        db.execute("INSERT INTO order_status_history(order_id,actor,old_status,new_status,note) VALUES(?,?,?,?,?)",(order_id,actor,old_status,status,delay_message or (f"Срок: {eta}" if eta else None)))
    coupon=order["delay_promo_code"]
    if status=="delayed" and not coupon:
        try:
            coupon=generate_delay_coupon(int(order["user_id"]),actor,order_id)
            with db_connect() as db: db.execute("UPDATE orders SET delay_promo_code=? WHERE id=?",(coupon,order_id))
        except sqlite3.IntegrityError:
            coupon=None
    log_activity(actor,"order_status_changed","order",order_id,f"{old_status}->{status}; ETA={eta or '-'}")
    ok, detail=notify_customer(int(order["user_id"]),order_id,str(order["product_name"]),status,eta,delay_message,coupon if status=="delayed" else None)
    if status=="completed" and old_status!="completed":
        try: process_referral_conversion(int(order["user_id"]),order_id,actor)
        except Exception as exc: log_activity(actor,"referral_reward_error","order",order_id,str(exc)[:300])
        with db_connect() as db: db.execute("UPDATE promo_redemptions SET status='used' WHERE order_id=?",(order_id,))
    if status in {"cancelled","refunded"}:
        with db_connect() as db:
            reserved = db.execute("SELECT code,COUNT(*) n FROM promo_redemptions WHERE order_id=? AND status='reserved' GROUP BY code",(order_id,)).fetchall()
            db.execute("UPDATE promo_redemptions SET status='released' WHERE order_id=? AND status='reserved'",(order_id,))
            for item in reserved:
                db.execute("UPDATE promo_codes SET uses=MAX(0,uses-?) WHERE code=?",(item["n"],item["code"]))
    flash(f"Заказ №{order_id}: {ORDER_STATUSES[status]}. {detail}","success" if ok else "error")
    return redirect(url_for("order_detail",order_id=order_id))


@app.get("/clients")
def clients():
    q=request.args.get("q","").strip(); segment=request.args.get("segment","").strip()
    where=[]; params=[]
    if q:
        where.append("(CAST(u.user_id AS TEXT) LIKE ? OR COALESCE(u.username,'') LIKE ? OR COALESCE(u.full_name,'') LIKE ?)"); params += [f"%{q}%",f"%{q.lstrip('@')}%",f"%{q}%"]
    if segment=="opted": where.append("u.marketing_opt_in=1")
    elif segment=="repeat": where.append("(SELECT COUNT(*) FROM orders oo WHERE oo.user_id=u.user_id AND oo.status IN ('paid','processing','delayed','completed'))>=2")
    elif segment=="inactive": where.append("date(COALESCE(u.last_seen_at,u.created_at)) < date('now','localtime','-30 day')")
    sql=f'''SELECT u.user_id,u.username,u.full_name,u.created_at,u.last_seen_at,u.marketing_opt_in,u.banned,
    COUNT(o.id) order_count,COALESCE(SUM(CASE WHEN o.status IN ('paid','processing','delayed','completed') THEN o.price_rub ELSE 0 END),0) paid_total,
    MAX(o.created_at) last_order FROM users u LEFT JOIN orders o ON o.user_id=u.user_id
    {('WHERE '+ ' AND '.join(where)) if where else ''} GROUP BY u.user_id ORDER BY last_seen_at DESC LIMIT 500'''
    with db_connect() as db: rows=db.execute(sql,params).fetchall()
    body=f'''<div><div class="top"><div><h1>Клиенты</h1><div class="sub">Профили, история покупок, активность, подписка на рассылки и внутренние заметки.</div></div><a class="button" href="/export/clients.csv">Экспорт CSV</a></div><form class="filters" method="get"><input class="input" name="q" value="{escape(q)}" placeholder="Telegram ID, username или имя"><select class="input" name="segment"><option value="">Все клиенты</option><option value="opted"{' selected' if segment=='opted' else ''}>Подписаны на рассылки</option><option value="repeat"{' selected' if segment=='repeat' else ''}>Повторные покупатели</option><option value="inactive"{' selected' if segment=='inactive' else ''}>Неактивны 30+ дней</option></select><button class="primary">Фильтр</button><a class="button" href="/clients">Сбросить</a></form><div class="table-wrap"><table><thead><tr><th>Клиент</th><th>ID</th><th>Заказов</th><th>Оплачено</th><th>Последняя активность</th><th>Новости</th><th></th></tr></thead><tbody>'''
    for row in rows:
        body+=f'<tr><td><b>{escape(row["full_name"] or "Без имени")}</b><div class="small">{escape("@"+row["username"] if row["username"] else "без username")}</div></td><td><code>{row["user_id"]}</code></td><td>{row["order_count"]}</td><td>{money(row["paid_total"])}</td><td>{escape(str(row["last_seen_at"] or row["created_at"] or "—"))}</td><td>{"🔔 Да" if row["marketing_opt_in"] else "— Нет"}</td><td><a class="button" href="{url_for("client_detail",user_id=row["user_id"])}">Профиль</a></td></tr>'
    if not rows: body+='<tr><td colspan="7" class="empty">Клиенты не найдены</td></tr>'
    body+='</tbody></table></div>'
    return render_page("Клиенты","clients",body)


@app.get("/clients/<int:user_id>")
def client_detail(user_id: int):
    with db_connect() as db:
        user=db.execute("SELECT * FROM users WHERE user_id=?",(user_id,)).fetchone()
        orders_rows=db.execute("SELECT id,product_name,price_rub,status,created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 50",(user_id,)).fetchall()
        notes=db.execute("SELECT * FROM customer_notes WHERE user_id=? ORDER BY id DESC LIMIT 30",(user_id,)).fetchall()
        referral=db.execute("SELECT referral_code FROM users WHERE user_id=?",(user_id,)).fetchone()
    if not user: abort(404)
    username="@"+user["username"] if user["username"] else "не указан"
    body=f'''<a class="muted" href="/clients">← Все клиенты</a><h1 style="margin-top:10px">{escape(user['full_name'] or 'Без имени')}</h1><div class="sub">Профиль покупателя GGSTAR</div><div class="grid three"><div class="card"><div class="muted">Telegram ID</div><div class="metric">{user_id}</div><div class="small">{escape(username)}</div></div><div class="card"><div class="muted">Регистрация</div><div class="metric">{escape(str(user['created_at'] or '—')[:10])}</div><div class="small">Активность: {escape(str(user['last_seen_at'] or '—'))}</div></div><div class="card"><div class="muted">Уведомления</div><div class="metric">{'Включены' if user['marketing_opt_in'] else 'Выключены'}</div></div></div>
<section class="section card"><h2>Действия</h2><div class="split"><form method="post" action="/clients/{user_id}/message">{csrf_field()}<div class="field"><label>Отправить сообщение покупателю</label><textarea class="input" name="message" required maxlength="3000" placeholder="Сообщение"></textarea></div><button class="primary">Отправить в Telegram</button></form><form method="post" action="/clients/{user_id}/note">{csrf_field()}<div class="field"><label>Добавить внутреннюю заметку</label><textarea class="input" name="note" required maxlength="2000" placeholder="Например: предпочитает USDT"></textarea></div><button>Сохранить заметку</button></form></div></section>
<section class="section"><h2>История заказов</h2><div class="table-wrap"><table><thead><tr><th>Заказ</th><th>Товар</th><th>Сумма</th><th>Статус</th><th>Дата</th></tr></thead><tbody>'''
    for row in orders_rows: body+=f'<tr><td><a href="{url_for("order_detail",order_id=row["id"])}">#{row["id"]}</a></td><td>{escape(row["product_name"])}</td><td>{money(row["price_rub"])}</td><td><span class="badge {STATUS_COLORS.get(row["status"],"pending")}">{escape(ORDER_STATUSES.get(row["status"],row["status"]))}</span></td><td>{escape(str(row["created_at"] or "—"))}</td></tr>'
    if not orders_rows: body+='<tr><td colspan="5" class="empty">Заказов нет</td></tr>'
    body+='</tbody></table></div></section><section class="section card"><h2>Заметки команды</h2>'
    if not notes: body+='<p class="muted">Заметок пока нет.</p>'
    for row in notes: body+=f'<div class="alert">{escape(row["note"])}<div class="small">{escape(row["actor"])} · {escape(str(row["created_at"] or ""))}</div></div>'
    body+='</section>'
    return render_page("Клиент","clients",body)


@app.post("/clients/<int:user_id>/note")
def client_note(user_id: int):
    note=request.form.get("note","").strip()[:2000]
    if not note: flash("Заметка пустая.","error"); return redirect(url_for("client_detail",user_id=user_id))
    with db_connect() as db: db.execute("INSERT INTO customer_notes(user_id,actor,note) VALUES(?,?,?)",(user_id,session["panel_user"],note))
    log_activity(session["panel_user"],"client_note_added","user",user_id,note[:200]); flash("Заметка сохранена.","success")
    return redirect(url_for("client_detail",user_id=user_id))


@app.post("/clients/<int:user_id>/message")
def client_message(user_id: int):
    message=request.form.get("message","").strip()[:3000]
    if not message: flash("Сообщение пустое.","error"); return redirect(url_for("client_detail",user_id=user_id))
    ok,detail,_=tg_api("sendMessage",{"chat_id":user_id,"text":"💬 Сообщение от команды GGSTAR\n\n"+message})
    with db_connect() as db:
        ticket=db.execute("SELECT id FROM support_tickets WHERE user_id=? ORDER BY id DESC LIMIT 1",(user_id,)).fetchone()
        if ticket: db.execute("INSERT INTO support_messages(ticket_id,user_id,actor,body) VALUES(?,?,?,?)",(ticket["id"],user_id,session["panel_user"],message))
    log_activity(session["panel_user"],"client_message_sent" if ok else "client_message_failed","user",user_id,message[:200])
    flash("Сообщение отправлено." if ok else f"Не удалось отправить: {escape(detail)}","success" if ok else "error")
    return redirect(url_for("client_detail",user_id=user_id))


@app.get("/support")
def support():
    q=request.args.get("q","").strip(); status=request.args.get("status","").strip()
    where=[]; params=[]
    if q:
        where.append("(CAST(t.id AS TEXT)=? OR CAST(t.user_id AS TEXT)=? OR m.body LIKE ?)"); params += [q,q,f"%{q}%"]
    if status: where.append("t.status=?"); params.append(status)
    sql=f'''SELECT t.*,u.full_name,u.username,(SELECT body FROM support_messages m2 WHERE m2.ticket_id=t.id ORDER BY m2.id DESC LIMIT 1) last_message FROM support_tickets t LEFT JOIN users u ON u.user_id=t.user_id LEFT JOIN support_messages m ON m.ticket_id=t.id {('WHERE '+' AND '.join(where)) if where else ''} GROUP BY t.id ORDER BY t.updated_at DESC LIMIT 200'''
    with db_connect() as db: rows=db.execute(sql,params).fetchall()
    body=f'''<div><h1>Поддержка</h1><div class="sub">Обращения покупателей и история ответов.</div></div><form class="filters"><input class="input" name="q" value="{escape(q)}" placeholder="№ обращения, клиент или текст"><select class="input" name="status"><option value="">Все статусы</option><option value="new"{' selected' if status=='new' else ''}>Новое</option><option value="answered"{' selected' if status=='answered' else ''}>Ответили</option><option value="closed"{' selected' if status=='closed' else ''}>Закрыто</option></select><button class="primary">Фильтр</button><a class="button" href="/support">Сбросить</a></form><div class="table-wrap"><table><thead><tr><th>Обращение</th><th>Клиент</th><th>Статус</th><th>Последнее сообщение</th><th>Обновлено</th><th></th></tr></thead><tbody>'''
    for row in rows: body+=f'<tr><td>#{row["id"]}</td><td><a href="{url_for("client_detail",user_id=row["user_id"])}">{escape(row["full_name"] or str(row["user_id"]))}</a><div class="small">{row["user_id"]} · {escape("@"+row["username"] if row["username"] else "")}</div></td><td>{escape(row["status"])}</td><td>{escape(str(row["last_message"] or "—")[:180])}</td><td>{escape(str(row["updated_at"] or "—"))}</td><td><a class="button" href="{url_for("support_detail",ticket_id=row["id"])}">Открыть</a></td></tr>'
    if not rows: body+='<tr><td colspan="6" class="empty">Обращений пока нет</td></tr>'
    body+='</tbody></table></div>'
    return render_page("Поддержка","support",body)


@app.get("/support/<int:ticket_id>")
def support_detail(ticket_id: int):
    with db_connect() as db:
        ticket=db.execute("SELECT * FROM support_tickets WHERE id=?",(ticket_id,)).fetchone()
        messages=db.execute("SELECT * FROM support_messages WHERE ticket_id=? ORDER BY id",(ticket_id,)).fetchall()
        user=db.execute("SELECT full_name,username FROM users WHERE user_id=?",(ticket["user_id"],)).fetchone() if ticket else None
    if not ticket: abort(404)
    body=f'''<a class="muted" href="/support">← Все обращения</a><h1 style="margin-top:10px">Обращение №{ticket_id}</h1><div class="sub">Клиент: {escape((user['full_name'] if user else '') or str(ticket['user_id']))} · ID {ticket['user_id']}</div><section class="section card"><h2>Переписка</h2>'''
    if not messages: body+='<p class="muted">Нет сообщений.</p>'
    for msg in messages: body+=f'<div class="alert"><b>{escape(msg["actor"])}</b> <span class="small">{escape(str(msg["created_at"] or ""))}</span><div style="white-space:pre-wrap;margin-top:5px">{escape(msg["body"])}</div></div>'
    body+=f'''</section><section class="section card"><h2>Ответить</h2><form method="post" action="/support/{ticket_id}/reply">{csrf_field()}<div class="field"><textarea class="input" name="message" required maxlength="3000" placeholder="Ответ клиенту"></textarea></div><div class="actions"><button class="primary">Отправить ответ</button><button formaction="/support/{ticket_id}/close" formmethod="post">Закрыть обращение</button></div></form></section>'''
    return render_page(f"Обращение №{ticket_id}","support",body)


@app.post("/support/<int:ticket_id>/reply")
def support_reply(ticket_id: int):
    text=request.form.get("message","").strip()[:3000]
    with db_connect() as db: ticket=db.execute("SELECT * FROM support_tickets WHERE id=?",(ticket_id,)).fetchone()
    if not ticket: abort(404)
    if not text: flash("Сообщение пустое.","error"); return redirect(url_for("support_detail",ticket_id=ticket_id))
    ok,detail,_=tg_api("sendMessage",{"chat_id":int(ticket["user_id"]),"text":"💬 Ответ поддержки GGSTAR\n\n"+text})
    if ok:
        with db_connect() as db:
            db.execute("INSERT INTO support_messages(ticket_id,user_id,actor,body) VALUES(?,?,?,?)",(ticket_id,ticket["user_id"],session["panel_user"],text))
            db.execute("UPDATE support_tickets SET status='answered',updated_at=CURRENT_TIMESTAMP,assigned_to=? WHERE id=?",(session["panel_user"],ticket_id))
        log_activity(session["panel_user"],"support_reply_sent","ticket",ticket_id,text[:200]); flash("Ответ отправлен.","success")
    else: flash(f"Telegram не отправил сообщение: {escape(detail)}","error")
    return redirect(url_for("support_detail",ticket_id=ticket_id))


@app.post("/support/<int:ticket_id>/close")
def support_close(ticket_id: int):
    with db_connect() as db: db.execute("UPDATE support_tickets SET status='closed',updated_at=CURRENT_TIMESTAMP WHERE id=?",(ticket_id,))
    log_activity(session["panel_user"],"support_closed","ticket",ticket_id); flash("Обращение закрыто.","success")
    return redirect(url_for("support_detail",ticket_id=ticket_id))


@app.get("/marketing")
def marketing():
    with db_connect() as db:
        promos=db.execute("SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT 100").fetchall()
        broadcasts=db.execute("SELECT * FROM broadcast_logs ORDER BY id DESC LIMIT 20").fetchall()
        opt_count=db.execute("SELECT COUNT(*) FROM users WHERE marketing_opt_in=1").fetchone()[0]
        categories=db.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
    body=f'''<div><h1>Промокоды и рассылки</h1><div class="sub">Создавай купоны для акций, конкурсов и компенсаций за задержку. Рассылки отправляются пользователям, которые включили новости в боте.</div></div><div class="grid three"><div class="card"><div class="muted">Активные промокоды</div><div class="metric">{sum(1 for p in promos if p['active'])}</div></div><div class="card"><div class="muted">Подписаны на рассылку</div><div class="metric">{opt_count}</div></div><div class="card"><div class="muted">Рассылок в журнале</div><div class="metric">{len(broadcasts)}</div></div></div><section class="section grid two"><div class="card"><h2>Создать промокод</h2><form method="post" action="/marketing/promo">{csrf_field()}<div class="field"><label>Код (пусто = сгенерировать)</label><input class="input" name="code" maxlength="32" placeholder="GGSTAR10"></div><div class="form-grid"><div class="field"><label>Тип скидки</label><select class="input" name="discount_type"><option value="percent">Процент</option><option value="fixed">Фиксированная сумма, ₽</option></select></div><div class="field"><label>Размер</label><input class="input" name="discount_value" type="number" step="0.01" min="0.01" required></div><div class="field"><label>Лимит использований</label><input class="input" name="usage_limit" type="number" min="1" placeholder="Без лимита"></div></div><div class="form-grid"><div class="field"><label>Привязать к Telegram ID (необязательно)</label><input class="input" name="user_id" type="number" min="1"></div><div class="field"><label>Категория</label><select class="input" name="category"><option value="">Все товары</option>'''
    for cat in categories: body+=f'<option value="{escape(cat[0])}">{escape(cat[0])}</option>'
    body+=f'''</select></div><div class="field"><label>Действует до</label><input class="input" type="date" name="expires_at"></div></div><div class="field"><label>Причина / кампания</label><input class="input" name="reason" placeholder="Конкурс в канале, компенсация"></div><button class="primary">Создать промокод</button></form></div><div class="card"><h2>Рассылка</h2><p class="muted small">Промо-сообщения идут только тем, кто в боте включил «Новости и акции». Не отправляй спам; для клиента доступна отписка.</p><form method="post" action="/marketing/broadcast">{csrf_field()}<div class="field"><label>Аудитория</label><select class="input" name="audience"><option value="opted">Все подписанные на новости</option><option value="buyers">Подписанные покупатели</option><option value="inactive">Подписанные, неактивные 30+ дней</option></select></div><div class="field"><label>Текст сообщения</label><textarea class="input" name="message" maxlength="3500" required placeholder="Текст акции или объявления"></textarea></div><label><input type="checkbox" name="confirm" value="1" required> Проверил текст и аудиторию</label><div style="margin-top:12px"><button class="primary">Отправить рассылку</button></div></form></div></section><section class="section"><h2>Промокоды</h2><div class="table-wrap"><table><thead><tr><th>Код</th><th>Скидка</th><th>Использования</th><th>Получатель / категория</th><th>Срок</th><th>Причина</th><th>Статус</th><th></th></tr></thead><tbody>'''
    for p in promos:
        discount=f"{p['discount_value']:g}%" if p['discount_type']=='percent' else money(p['discount_value'])
        recipient=str(p['user_id']) if p['user_id'] else "все"
        category=p['category'] or "любая"
        limit=str(p['usage_limit']) if p['usage_limit'] else "∞"
        body+=f'<tr><td><code>{escape(p["code"])}</code></td><td>{discount}</td><td>{p["uses"]} / {limit}</td><td>{escape(recipient)}<div class="small">{escape(category)}</div></td><td>{escape(str(p["expires_at"] or "без срока"))}</td><td>{escape(p["reason"] or "—")}</td><td>{"Активен" if p["active"] else "Отключён"}</td><td>'
        if p['active']: body+=f'<form method="post" action="{url_for("promo_toggle",code=p["code"])}">{csrf_field()}<button class="danger">Отключить</button></form>'
        body+='</td></tr>'
    if not promos: body+='<tr><td colspan="8" class="empty">Промокодов пока нет</td></tr>'
    body+='</tbody></table></div></section><section class="section"><h2>История рассылок</h2><div class="table-wrap"><table><thead><tr><th>Дата</th><th>Автор</th><th>Аудитория</th><th>Отправлено</th><th>Ошибок</th><th>Текст</th></tr></thead><tbody>'
    for b in broadcasts: body+=f'<tr><td>{escape(str(b["created_at"] or ""))}</td><td>{escape(b["actor"])}</td><td>{escape(b["audience"])}</td><td>{b["sent_count"]}/{b["total_count"]}</td><td>{b["failed_count"]}</td><td>{escape(b["message"][:160])}</td></tr>'
    if not broadcasts: body+='<tr><td colspan="6" class="empty">Рассылок пока не было</td></tr>'
    body+='</tbody></table></div></section>'
    return render_page("Промокоды и рассылки","marketing",body)


@app.post("/marketing/promo")
def promo_create():
    code=request.form.get("code","").strip() or None
    discount_type=request.form.get("discount_type","percent")
    try:
        discount=float(request.form.get("discount_value","0").replace(",","."))
        limit_raw=request.form.get("usage_limit","").strip(); limit=int(limit_raw) if limit_raw else None
        user_raw=request.form.get("user_id","").strip(); user_id=int(user_raw) if user_raw else None
        category=request.form.get("category","").strip() or None
        expiry=request.form.get("expires_at","").strip() or None
        reason=request.form.get("reason","").strip()
        code=create_promo(code,discount_type,discount,limit,user_id,category,expiry,reason,session["panel_user"])
    except (ValueError, sqlite3.IntegrityError) as exc:
        flash(f"Не удалось создать промокод: {escape(str(exc))}","error"); return redirect(url_for("marketing"))
    flash(f"Промокод {escape(code)} создан.","success"); return redirect(url_for("marketing"))


@app.post("/marketing/promo/<code>/toggle")
def promo_toggle(code: str):
    with db_connect() as db:
        row=db.execute("SELECT active FROM promo_codes WHERE code=?",(code,)).fetchone()
        if not row: flash("Промокод не найден.","error"); return redirect(url_for("marketing"))
        new_value=0 if row["active"] else 1
        db.execute("UPDATE promo_codes SET active=? WHERE code=?",(new_value,code))
    log_activity(session["panel_user"],"promo_toggled","promo",code,str(new_value)); flash("Промокод включён." if new_value else "Промокод отключён.","success")
    return redirect(url_for("marketing"))


@app.post("/marketing/broadcast")
def broadcast_send():
    if request.form.get("confirm")!="1": flash("Подтверди отправку.","error"); return redirect(url_for("marketing"))
    message=request.form.get("message","").strip()[:3500]; audience=request.form.get("audience","opted")
    if not message: flash("Текст рассылки пустой.","error"); return redirect(url_for("marketing"))
    where=["marketing_opt_in=1"]; params=[]
    if audience=="buyers": where.append("user_id IN (SELECT DISTINCT user_id FROM orders WHERE status IN ('paid','processing','delayed','completed'))")
    elif audience=="inactive": where.append("date(COALESCE(last_seen_at,created_at)) < date('now','localtime','-30 day')")
    else: audience="opted"
    with db_connect() as db: recipients=[int(r[0]) for r in db.execute("SELECT user_id FROM users WHERE "+" AND ".join(where)+" AND banned=0 ORDER BY user_id LIMIT 3000").fetchall()]
    if not recipients: flash("Нет получателей, включивших новости.","error"); return redirect(url_for("marketing"))
    with db_connect() as db:
        cur=db.execute("INSERT INTO broadcast_logs(actor,message,audience,total_count) VALUES(?,?,?,?)",(session["panel_user"],message,audience,len(recipients))); broadcast_id=cur.lastrowid
    sent=failed=0
    for uid in recipients:
        ok,detail,_=tg_api("sendMessage",{"chat_id":uid,"text":"📣 GGSTAR — новости и акции\n\n"+message,"reply_markup":{"inline_keyboard":[[{"text":"🔕 Настроить уведомления","callback_data":"marketing"}]]}})
        sent+=int(ok); failed+=int(not ok)
        with db_connect() as db: db.execute("INSERT INTO broadcast_recipients(broadcast_id,user_id,status,error) VALUES(?,?,?,?)",(broadcast_id,uid,"sent" if ok else "failed",None if ok else detail[:300]))
        time.sleep(0.04)
    with db_connect() as db: db.execute("UPDATE broadcast_logs SET sent_count=?,failed_count=? WHERE id=?",(sent,failed,broadcast_id))
    log_activity(session["panel_user"],"broadcast_sent","broadcast",broadcast_id,f"sent={sent};failed={failed};audience={audience}")
    flash(f"Рассылка завершена: отправлено {sent}, ошибок {failed} из {len(recipients)}.","success" if failed==0 else "error")
    return redirect(url_for("marketing"))


@app.get("/reviews")
def reviews():
    status=request.args.get("status","pending")
    if status not in {"pending","approved","rejected","all"}: status="pending"
    sql="SELECT * FROM reviews"+(" WHERE status=?" if status!="all" else "")+" ORDER BY id DESC LIMIT 300"
    with db_connect() as db: rows=db.execute(sql,() if status=="all" else (status,)).fetchall()
    body=f'''<div><h1>Отзывы</h1><div class="sub">Оставить отзыв можно только по завершённому заказу. Один отзыв на заказ; публикация только после модерации.</div></div><form class="filters"><select class="input" name="status">'''
    for key,label in (("pending","На модерации"),("approved","Опубликованные"),("rejected","Отклонённые"),("all","Все")): body+=f'<option value="{key}"{" selected" if status==key else ""}>{label}</option>'
    body+='</select><button class="primary">Показать</button></form><div class="table-wrap"><table><thead><tr><th>Товар / заказ</th><th>Клиент</th><th>Оценка</th><th>Комментарий</th><th>Дата</th><th>Статус / действие</th></tr></thead><tbody>'
    for row in rows:
        body+=f'<tr><td>{escape(row["product_name"])}<div class="small">Заказ #{row["order_id"]}</div></td><td><a href="{url_for("client_detail",user_id=row["user_id"])}">{row["user_id"]}</a></td><td>{"⭐"*row["rating"]}</td><td>{escape(row["comment"] or "—")}</td><td>{escape(str(row["created_at"] or ""))}</td><td><span class="badge {"completed" if row["status"]=="approved" else "cancelled" if row["status"]=="rejected" else "pending"}">{escape(row["status"])}</span><div class="actions" style="margin-top:7px">'
        if row['status']!='approved': body+=f'<form method="post" action="/reviews/{row["id"]}">{csrf_field()}<input type="hidden" name="status" value="approved"><button class="primary">Опубликовать</button></form>'
        if row['status']!='rejected': body+=f'<form method="post" action="/reviews/{row["id"]}">{csrf_field()}<input type="hidden" name="status" value="rejected"><button class="danger">Отклонить</button></form>'
        body+='</div></td></tr>'
    if not rows: body+='<tr><td colspan="6" class="empty">Отзывов в этой категории нет</td></tr>'
    body+='</tbody></table></div>'
    return render_page("Отзывы","reviews",body)


@app.post("/reviews/<int:review_id>")
def review_update(review_id: int):
    status=request.form.get("status","")
    if status not in {"approved","rejected"}: flash("Некорректное действие.","error"); return redirect(url_for("reviews"))
    with db_connect() as db:
        row=db.execute("SELECT * FROM reviews WHERE id=?",(review_id,)).fetchone()
        if not row: flash("Отзыв не найден.","error"); return redirect(url_for("reviews"))
        db.execute("UPDATE reviews SET status=?,moderated_by=?,moderated_at=CURRENT_TIMESTAMP WHERE id=?",(status,session["panel_user"],review_id))
    log_activity(session["panel_user"],"review_moderated","review",review_id,status)
    if status=="approved":
        tg_api("sendMessage",{"chat_id":int(row["user_id"]),"text":"⭐ Спасибо! Твой отзыв о покупке в GGSTAR проверен и опубликован."})
    flash("Отзыв опубликован." if status=="approved" else "Отзыв отклонён.","success")
    return redirect(url_for("reviews",status=request.args.get("status","pending")))


@app.get("/activity")
def activity():
    q=request.args.get("q","").strip()
    with db_connect() as db:
        if q:
            rows=db.execute("SELECT * FROM activity_log WHERE actor LIKE ? OR action LIKE ? OR entity_id LIKE ? OR COALESCE(details,'') LIKE ? ORDER BY id DESC LIMIT 300",(f"%{q}%",f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
        else:
            rows=db.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT 300").fetchall()
    body=f'''<div><h1>Журнал активности</h1><div class="sub">Кто и когда изменил статус заказа, цену, промокод, отзыв или настройки.</div></div><form class="filters"><input class="input" name="q" value="{escape(q)}" placeholder="Пользователь, действие или запись"><button class="primary">Поиск</button><a class="button" href="/activity">Сбросить</a></form><div class="table-wrap"><table><thead><tr><th>Дата</th><th>Автор</th><th>Действие</th><th>Объект</th><th>Подробности</th></tr></thead><tbody>'''
    for row in rows: body+=f'<tr><td class="nowrap">{escape(str(row["created_at"] or ""))}</td><td>{escape(row["actor"])}</td><td>{escape(row["action"])}</td><td>{escape(str(row["entity_type"] or ""))} <code>{escape(str(row["entity_id"] or ""))}</code></td><td>{escape(str(row["details"] or "")[:500])}</td></tr>'
    if not rows: body+='<tr><td colspan="5" class="empty">Событий пока нет</td></tr>'
    body+='</tbody></table></div>'
    return render_page("Активность","activity",body)


@app.get("/settings")
def settings():
    with db_connect() as db:
        values={key: setting(db,key,default) for key,default in (("tax_rate_percent",6),("sbp_fee_percent",3),("referral_reward_percent",5),("usdt_rub_rate",84),("delay_promo_percent",5))}
    body=f'''<div><h1>Настройки магазина</h1><div class="sub">Параметры расчётной аналитики и бонусов. Изменение здесь не подключает платёжный шлюз.</div></div><section class="card"><form method="post" action="/settings">{csrf_field()}<div class="form-grid">'''
    for key,label,hint in (("tax_rate_percent","Налог, %","Для аналитики. Уточни фактический налоговый режим с бухгалтером."),("sbp_fee_percent","Комиссия СБП, %","Вычитается из расчётной прибыли только для заказов с payment_method=sbp."),("referral_reward_percent","Бонус за друга, %","Размер одноразового промокода приглашавшему клиенту."),("usdt_rub_rate","Курс USDT → ₽","Используется как ориентир в расчётах."),("delay_promo_percent","Промокод за задержку, %","Купон персональный, один раз, действует 30 дней.")):
        body+=f'<div class="field"><label>{label}</label><input class="input" type="number" step="0.01" min="0" max="100000" name="{key}" value="{values[key]:g}" required><div class="small">{hint}</div></div>'
    body+='''</div><button class="primary">Сохранить настройки</button></form></section><section class="section card"><h2>Безопасность</h2><p class="note">Панель использует отдельные логины из ADMIN_PANEL_USERS. Не публикуй её без HTTPS, firewall и ограниченного доступа. На время разработки используй Tailscale Serve/VPS с HTTPS. Не отправляй другу BOT_TOKEN или файл .env.</p></section>'''
    return render_page("Настройки","settings",body)


@app.post("/settings")
def settings_save():
    keys=("tax_rate_percent","sbp_fee_percent","referral_reward_percent","usdt_rub_rate","delay_promo_percent")
    values={}
    for key in keys:
        try: value=float(request.form.get(key,""))
        except ValueError: flash("Все настройки должны быть числами.","error"); return redirect(url_for("settings"))
        if value<0 or value>100000 or (key in {"tax_rate_percent","sbp_fee_percent","referral_reward_percent","delay_promo_percent"} and value>100): flash(f"Недопустимое значение для {key}.","error"); return redirect(url_for("settings"))
        values[key]=value
    for key,value in values.items(): save_setting(key,value)
    log_activity(session["panel_user"],"settings_updated","settings",None,json.dumps(values))
    flash("Настройки сохранены.","success")
    return redirect(url_for("settings"))


@app.get("/export/<kind>.csv")
def export_csv(kind: str):
    import csv
    from io import StringIO
    if kind not in {"orders","clients","products"}: abort(404)
    with db_connect() as db:
        if kind=="orders": rows=db.execute("SELECT id,user_id,product_id,product_name,price_rub,price_usdt,payment_method,status,created_at,paid_at,completed_at FROM orders ORDER BY id DESC LIMIT 10000").fetchall()
        elif kind=="clients": rows=db.execute("SELECT user_id,username,full_name,created_at,last_seen_at,marketing_opt_in FROM users ORDER BY user_id LIMIT 10000").fetchall()
        else: rows=db.execute("SELECT product_id,category,name,price_rub,price_usdt,purchase_cost_rub,purchase_cost_usdt,supplier,is_active FROM products ORDER BY category,product_id").fetchall()
    from flask import Response
    buff=StringIO(); writer=csv.writer(buff,delimiter=";")
    if rows:
        writer.writerow(rows[0].keys())
        for row in rows: writer.writerow([row[k] for k in row.keys()])
    else: writer.writerow(["empty"])
    content="\ufeff"+buff.getvalue()
    log_activity(session.get("panel_user","unknown"),"csv_export",kind,None,f"rows={len(rows)}")
    return Response(content,mimetype="text/csv; charset=utf-8",headers={"Content-Disposition":f"attachment; filename=ggstar_{kind}.csv"})


@app.errorhandler(400)
def bad_request(error):
    return render_page("Ошибка формы","",f'<section class="card"><h1>Форма устарела</h1><p>{escape(getattr(error,"description","Обнови страницу и попробуй ещё раз."))}</p><a class="button primary" href="{url_for("dashboard")}">На главную</a></section>'),400


@app.errorhandler(404)
def not_found(_error):
    return render_page("Не найдено","",f'<section class="card"><h1>Страница не найдена</h1><a class="button primary" href="{url_for("dashboard")}">На главную</a></section>'),404


if __name__ == "__main__":
    if not PANEL_USERS:
        print("GGSTAR Admin: добавь ADMIN_PANEL_USERS=owner:пароль,friend:пароль в .env")
        raise SystemExit(2)
    if not ADMIN_PANEL_SECRET:
        raise SystemExit("ADMIN_PANEL_SECRET не задан")
    ensure_panel_schema()
    if ADMIN_PANEL_HOST not in {"127.0.0.1", "localhost", "::1"}:
        print("ВНИМАНИЕ: панель слушает внешний интерфейс. Не открывай её в интернет без HTTPS и firewall.")
    print(f"GGSTAR Admin запускается: http://{ADMIN_PANEL_HOST}:{ADMIN_PANEL_PORT}")
    print(f"База данных: {DB_PATH}")
    app.run(host=ADMIN_PANEL_HOST, port=ADMIN_PANEL_PORT, debug=False)
