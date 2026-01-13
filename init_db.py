import sqlite3
import os

DB_NAME = "database.db"


def init_db():
    # Удаляем старую базу если она есть
    if os.path.exists(DB_NAME):
        print(f"⚠️ Удаляю старую базу данных {DB_NAME}...")
        os.remove(DB_NAME)
        print("✅ Старая база удалена")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("⏳ Создаю новую базу данных...")

    # ================= USERS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        email TEXT,
        role TEXT DEFAULT 'client'
    )
    """)
    print("✅ Таблица users создана")

    # ================= REVIEWS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name TEXT NOT NULL,
        rating INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    print("✅ Таблица reviews создана")

    # ================= REQUESTS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        service TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'new',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)
    print("✅ Таблица requests создана")

    # ================= CHATS =================
    # ВАЖНО: payment_status может быть:
    # - 'pending' (ожидает установки цены)
    # - 'awaiting_confirmation' (клиент подтвердил, ждёт админа)
    # - 'paid' (админ подтвердил оплату)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        staff_id INTEGER,
        service_name TEXT,
        status TEXT DEFAULT 'waiting',
        order_price REAL,
        payment_status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES users(id),
        FOREIGN KEY (staff_id) REFERENCES users(id)
    )
    """)
    print("✅ Таблица chats создана")

    # ================= MESSAGES =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats(id),
        FOREIGN KEY (sender_id) REFERENCES users(id)
    )
    """)
    print("✅ Таблица messages создана")

    # ================= PAYMENTS =================
    # ВАЖНО: status может быть:
    # - 'pending' (ожидает подтверждения админом)
    # - 'completed' (подтверждено админом)
    # - 'rejected' (отклонено админом)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        client_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        card_number TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats(id),
        FOREIGN KEY (client_id) REFERENCES users(id)
    )
    """)
    print("✅ Таблица payments создана")

    # ================= ADMIN BALANCE =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_balance (
        admin_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (admin_id) REFERENCES users(id)
    )
    """)
    print("✅ Таблица admin_balance создана")

    # ================= ADMIN PAYMENT CARD =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_payment_card (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER UNIQUE,
        card_number TEXT NOT NULL,
        card_holder TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (admin_id) REFERENCES users(id)
    )
    """)
    print("✅ Таблица admin_payment_card создана")

    # ================= PAYOUT CARDS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payout_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER UNIQUE NOT NULL,
        card_number TEXT NOT NULL,
        card_holder TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (admin_id) REFERENCES users(id)
    )
    """)
    print("✅ Таблица payout_cards создана")

    # ================= TEAM =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS team_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        position TEXT NOT NULL,
        contract_filename TEXT NOT NULL,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        email TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    print("✅ Таблица team_members создана")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS staff_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER NOT NULL,
        document_name TEXT NOT NULL,
        document_type TEXT NOT NULL,
        filename TEXT NOT NULL,
        description TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (member_id) REFERENCES team_members(id)
    )
    """)
    print("✅ Таблица staff_documents создана")

    # ================= DEFAULT USERS =================
    print("\n⏳ Создаю пользователей по умолчанию...")
    users = [
        ("admin", "admin123", "admin@arkonix.com", "admin"),
        ("staff", "staff123", "staff@arkonix.com", "staff"),
        ("client", "client123", "client@example.com", "client"),
    ]

    for u in users:
        try:
            cursor.execute(
                "INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)",
                u,
            )
            print(f"  ✅ Создан пользователь: {u[0]} (роль: {u[3]})")
        except sqlite3.IntegrityError:
            print(f"  ⚠️ Пользователь {u[0]} уже существует")

    # Создаём баланс для админа
    cursor.execute("SELECT id FROM users WHERE role='admin'")
    admin = cursor.fetchone()
    if admin:
        cursor.execute(
            "INSERT OR IGNORE INTO admin_balance (admin_id, balance) VALUES (?, 0)",
            (admin[0],),
        )
        print("  ✅ Создан баланс для администратора")

    conn.commit()
    conn.close()

    print("\n" + "=" * 50)
    print("🎉 База данных успешно создана!")
    print("=" * 50)
    print("\n📝 Данные для входа:")
    print("  Администратор:")
    print("    Логин: admin")
    print("    Пароль: admin123")
    print("\n  Клиент:")
    print("    Логин: client")
    print("    Пароль: client123")
    print("\n  Сотрудник:")
    print("    Логин: staff")
    print("    Пароль: staff123")
    print("\n💡 Важная информация:")
    print("  📊 Таблица payments: хранит все платежи")
    print("     - status: pending | completed | rejected")
    print("  💰 Таблица chats.payment_status:")
    print("     - pending: ожидает установки цены")
    print("     - awaiting_confirmation: клиент подтвердил, ждёт админа")
    print("     - paid: админ подтвердил оплату")
    print("=" * 50)


if __name__ == "__main__":
    init_db()
