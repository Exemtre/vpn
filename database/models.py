import datetime
import sqlite3
import os
import uuid

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vpn_bot.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT UNIQUE NOT NULL,
        full_name TEXT,
        username TEXT,
        referrer_id TEXT,
        sub_expires TEXT,
        plan TEXT,
        vpn_key TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        bonus_days INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        plan TEXT NOT NULL,
        price INTEGER NOT NULL,
        started_at TEXT DEFAULT (datetime('now')),
        expires_at TEXT,
        payment_method TEXT DEFAULT 'stars',
        gift_from TEXT
    );

    CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        label TEXT NOT NULL,
        days INTEGER NOT NULL,
        max_devices INTEGER DEFAULT 5,
        price_rub INTEGER NOT NULL,
        price_stars INTEGER NOT NULL,
        vpn_link TEXT DEFAULT 'Ссылка не задана',
        is_active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS promo_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        value INTEGER NOT NULL,
        uses_left INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS gifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT UNIQUE NOT NULL,
        from_user_id TEXT,
        plan_code TEXT,
        days INTEGER,
        price INTEGER,
        claimed_by TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS bot_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)

    count = conn.execute("SELECT COUNT(*) as c FROM plans").fetchone()["c"]
    if count == 0:
        defaults = [
            ("plan_free", "Бесплатный (Швеция)", 36500, 5, 0, 0, "https://t.me/your_free_vpn_link", 1),
            ("plan_30", "1 месяц", 30, 5, 299, 150, "https://t.me/your_paid_vpn_link", 2),
            ("plan_90", "3 месяца", 90, 5, 799, 400, "https://t.me/your_paid_vpn_link", 3),
            ("plan_180", "6 месяцев", 180, 5, 1499, 750, "https://t.me/your_paid_vpn_link", 4),
            ("plan_365", "12 месяцев", 365, 5, 2799, 1400, "https://t.me/your_paid_vpn_link", 5),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO plans (code,label,days,max_devices,price_rub,price_stars,vpn_link,sort_order) VALUES (?,?,?,?,?,?,?,?)",
            defaults)

    # Миграция: добавить колонку plan_instruction если её нет
    try:
        conn.execute("ALTER TABLE plans ADD COLUMN plan_instruction TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    # Миграция: таблица подключённых устройств (ИСПРАВЛЕНО - убран DEFAULT)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS vpn_devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        device_name TEXT NOT NULL,
        connected_at TEXT
    )
    """)

    # Таблица отправленных уведомлений (для защиты от дублирования)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS notifications_sent (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        notif_key TEXT NOT NULL,
        sent_at TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, notif_key)
    )
    """)

    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_conn()
    u = conn.execute("SELECT * FROM users WHERE user_id=?", (str(user_id),)).fetchone()
    conn.close()
    return dict(u) if u else None


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_user(user_id, full_name, username, referrer_id=None):
    conn = get_conn()
    existing = conn.execute("SELECT user_id FROM users WHERE user_id=?", (str(user_id),)).fetchone()
    if not existing:
        conn.execute("INSERT OR IGNORE INTO users (user_id, full_name, username, referrer_id) VALUES (?,?,?,?)",
                     (str(user_id), full_name, username or "", str(referrer_id) if referrer_id else None))
        conn.commit()
    conn.close()


def update_user_balance(user_id, amount):
    conn = get_conn()
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, str(user_id)))
    conn.commit()
    conn.close()


def toggle_ban_user(user_id):
    conn = get_conn()
    u = conn.execute("SELECT is_banned FROM users WHERE user_id=?", (str(user_id),)).fetchone()
    if u:
        new_status = 0 if u['is_banned'] == 1 else 1
        conn.execute("UPDATE users SET is_banned=? WHERE user_id=?", (new_status, str(user_id)))
        conn.commit()
        conn.close()
        return new_status
    conn.close()
    return None


def set_subscription(user_id, plan_code, days, price):
    import datetime as dt
    conn = get_conn()
    now = dt.datetime.utcnow()
    u = conn.execute("SELECT sub_expires FROM users WHERE user_id=?", (str(user_id),)).fetchone()
    current_expires = dt.datetime.fromisoformat(u['sub_expires']) if u and u['sub_expires'] else now
    if current_expires < now:
        current_expires = now
    expires = current_expires + dt.timedelta(days=days)
    conn.execute("UPDATE users SET sub_expires=?, plan=? WHERE user_id=?",
                 (expires.isoformat(), plan_code, str(user_id)))
    conn.execute("INSERT INTO subscriptions (user_id, plan, price, started_at, expires_at) VALUES (?,?,?,?,?)",
                 (str(user_id), plan_code, price, now.isoformat(), expires.isoformat()))
    conn.commit()
    conn.close()


def revoke_subscription(user_id):
    conn = get_conn()
    conn.execute("UPDATE users SET sub_expires=NULL, plan=NULL WHERE user_id=?", (str(user_id),))
    conn.commit()
    conn.close()


def get_promo(code):
    conn = get_conn()
    r = conn.execute("SELECT * FROM promo_codes WHERE code=? AND uses_left>0", (code.upper(),)).fetchone()
    conn.close()
    return dict(r) if r else None


def use_promo(code):
    conn = get_conn()
    conn.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code=?", (code.upper(),))
    conn.commit()
    conn.close()


def create_promo(code, value, uses):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO promo_codes (code, value, uses_left) VALUES (?,?,?)",
                 (code.upper(), value, uses))
    conn.commit()
    conn.close()


def get_all_promos():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM promo_codes ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_bot_settings():
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM bot_settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def set_bot_setting(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT INTO bot_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value))
    conn.commit()
    conn.close()


def get_all_plans():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM plans WHERE is_active=1 ORDER BY sort_order, id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_plan(plan_code):
    conn = get_conn()
    r = conn.execute("SELECT * FROM plans WHERE code=?", (plan_code,)).fetchone()
    conn.close()
    return dict(r) if r else None


def update_plan_price(plan_id, new_price_rub):
    conn = get_conn()
    conn.execute("UPDATE plans SET price_rub=?, price_stars=? WHERE id=?",
                 (new_price_rub, int(new_price_rub / 2), plan_id))
    conn.commit()
    conn.close()


def update_plan_link(plan_id, new_link):
    conn = get_conn()
    conn.execute("UPDATE plans SET vpn_link=? WHERE id=?", (new_link, plan_id))
    conn.commit()
    conn.close()


def update_plan_instruction(plan_id, instruction):
    conn = get_conn()
    conn.execute("UPDATE plans SET plan_instruction=? WHERE id=?", (instruction, plan_id))
    conn.commit()
    conn.close()


def create_gift(from_user_id, plan_code, days, price):
    conn = get_conn()
    token = str(uuid.uuid4())[:12]
    conn.execute("INSERT INTO gifts (token, from_user_id, plan_code, days, price) VALUES (?,?,?,?,?)",
                 (token, str(from_user_id), plan_code, days, price))
    conn.commit()
    conn.close()
    return token


def get_gift(token):
    conn = get_conn()
    r = conn.execute("SELECT * FROM gifts WHERE token=? AND claimed_by IS NULL", (token,)).fetchone()
    conn.close()
    return dict(r) if r else None


def claim_gift(token, user_id):
    conn = get_conn()
    conn.execute("UPDATE gifts SET claimed_by=? WHERE token=?", (str(user_id), token))
    conn.commit()
    conn.close()


def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    active = conn.execute("SELECT COUNT(*) as c FROM users WHERE sub_expires > datetime('now')").fetchone()["c"]
    revenue = conn.execute("SELECT COALESCE(SUM(price),0) as s FROM subscriptions").fetchone()["s"]
    today = conn.execute("SELECT COUNT(*) as c FROM users WHERE date(created_at) = date('now')").fetchone()["c"]
    conn.close()
    return {"total_users": total, "active_subs": active, "total_revenue": revenue, "today_users": today}


def get_referral_stats(user_id):
    """Получает статистику рефералов пользователя."""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) as c FROM users WHERE referrer_id=?", (str(user_id),)).fetchone()["c"]
    premium = conn.execute(
        "SELECT COUNT(*) as c FROM users WHERE referrer_id=? AND plan IS NOT NULL AND plan != 'plan_free'",
        (str(user_id),)).fetchone()["c"]
    trial = total - premium
    conn.close()
    return {"total": total, "premium": premium, "trial": trial}


def add_subscription_days(user_id, days):
    """Добавляет дни к существующей подписке."""
    conn = get_conn()
    from datetime import datetime, timedelta
    u = conn.execute("SELECT sub_expires, plan FROM users WHERE user_id=?", (str(user_id),)).fetchone()
    now = datetime.utcnow()
    if u and u['sub_expires']:
        try:
            current_expires = datetime.fromisoformat(u['sub_expires'])
        except:
            current_expires = now
        new_expires = max(current_expires, now) + timedelta(days=days)
    else:
        new_expires = now + timedelta(days=days)
    conn.execute("UPDATE users SET sub_expires=? WHERE user_id=?",
                 (new_expires.isoformat(), str(user_id)))
    conn.commit()
    conn.close()


def get_user_devices(user_id):
    """Получить список подключённых устройств пользователя."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM vpn_devices WHERE user_id=? ORDER BY connected_at DESC",
        (str(user_id),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_user_device(user_id, device_name):
    """Добавить устройство пользователю (из админки) с текущей датой."""
    conn = get_conn()
    now = datetime.datetime.utcnow().isoformat()  # Добавляем текущую дату/время
    conn.execute(
        "INSERT INTO vpn_devices (user_id, device_name, connected_at) VALUES (?,?,?)",
        (str(user_id), device_name, now)
    )
    conn.commit()
    conn.close()


def delete_user_device(device_id):
    """Удалить устройство по ID."""
    conn = get_conn()
    conn.execute("DELETE FROM vpn_devices WHERE id=?", (device_id,))
    conn.commit()
    conn.close()


def get_users_expiring_soon(hours_before: int):
    """Возвращает пользователей, у которых подписка истекает в окне (hours_before±1) ч от текущего времени."""
    import datetime as dt
    conn = get_conn()
    now = dt.datetime.utcnow()
    lower = (now + dt.timedelta(hours=hours_before - 1)).isoformat()
    upper = (now + dt.timedelta(hours=hours_before + 1)).isoformat()
    rows = conn.execute(
        "SELECT * FROM users WHERE is_banned=0 AND sub_expires BETWEEN ? AND ?",
        (lower, upper)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_users_not_connected(hours_after: int):
    """Возвращает пользователей, оформивших подписку (hours_after±1) ч назад, без подключённых устройств."""
    import datetime as dt
    conn = get_conn()
    now = dt.datetime.utcnow()
    lower = (now - dt.timedelta(hours=hours_after + 1)).isoformat()
    upper = (now - dt.timedelta(hours=hours_after - 1)).isoformat()
    rows = conn.execute(
        """SELECT u.user_id, u.is_banned, s.started_at FROM users u
           JOIN subscriptions s ON s.user_id = u.user_id
           WHERE u.is_banned = 0
           AND s.started_at BETWEEN ? AND ?
           AND NOT EXISTS (SELECT 1 FROM vpn_devices d WHERE d.user_id = u.user_id)
           GROUP BY u.user_id""",
        (lower, upper)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def check_notification_sent(user_id, notif_key):
    """Возвращает True, если уведомление уже было отправлено."""
    conn = get_conn()
    r = conn.execute(
        "SELECT 1 FROM notifications_sent WHERE user_id=? AND notif_key=?",
        (str(user_id), notif_key)
    ).fetchone()
    conn.close()
    return r is not None


def mark_notification_sent(user_id, notif_key):
    """Помечает уведомление как отправленное."""
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO notifications_sent (user_id, notif_key) VALUES (?,?)",
        (str(user_id), notif_key)
    )
    conn.commit()
    conn.close()