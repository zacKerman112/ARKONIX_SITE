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
        role TEXT DEFAULT 'client',
        name TEXT,
        surname TEXT,
        handle TEXT UNIQUE
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

    # ================= MESSAGES (С ПОДДЕРЖКОЙ ФАЙЛОВ!) =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        text TEXT,
        attachment_type TEXT,
        attachment_filename TEXT,
        attachment_size INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats(id),
        FOREIGN KEY (sender_id) REFERENCES users(id)
    )
    """)
    print("✅ Таблица messages создана (с поддержкой файлов)")

    # ================= PAYMENTS (ПЛАТЕЖИ ОТ КЛИЕНТОВ) =================
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
    print("✅ Таблица payments создана (платежи от клиентов)")

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

    # ================= TEAM MEMBERS (С ЗАРАБОТКОМ) =================
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
        total_earned REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    print("✅ Таблица team_members создана (с total_earned)")

    # ================= STAFF DOCUMENTS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS staff_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER NOT NULL,
        document_name TEXT NOT NULL,
        document_type TEXT NOT NULL,
        filename TEXT NOT NULL,
        description TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (member_id) REFERENCES team_members(id) ON DELETE CASCADE
    )
    """)
    print("✅ Таблица staff_documents создана")

    # ================= STAFF PAYMENTS (ЗАЧИСЛЕНИЯ СОТРУДНИКАМ) =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS staff_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        description TEXT,
        paid_by INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (member_id) REFERENCES team_members(id) ON DELETE CASCADE,
        FOREIGN KEY (paid_by) REFERENCES users(id)
    )
    """)
    print("✅ Таблица staff_payments создана (зачисления сотрудникам)")

    # ================= COMPANY ARCHIVE =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS company_archive (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        category TEXT NOT NULL,
        filename TEXT NOT NULL,
        file_type TEXT,
        file_size INTEGER,
        uploaded_by INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_public INTEGER DEFAULT 1,
        FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL
    )
    """)
    print("✅ Таблица company_archive создана")

    # ================= GROUPS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        avatar TEXT,
        creator_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (creator_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    print("✅ Таблица groups создана")

    # ================= GROUP MEMBERS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS group_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT DEFAULT 'member',
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(group_id, user_id)
    )
    """)
    print("✅ Таблица group_members создана")

    # ================= GROUP MESSAGES =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS group_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        message TEXT,
        image TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_read INTEGER DEFAULT 0,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    print("✅ Таблица group_messages создана")

    # ================= PRIVATE MESSAGES =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS private_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        message TEXT,
        image TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_read INTEGER DEFAULT 0,
        FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    print("✅ Таблица private_messages создана")

    # ================= CONTACTS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        contact_id INTEGER NOT NULL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (contact_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(user_id, contact_id)
    )
    """)
    print("✅ Таблица contacts создана")

    # ================= ИНДЕКСЫ ДЛЯ ОПТИМИЗАЦИИ =================
    print("\n⏳ Создаю индексы для оптимизации...")

    # Индексы для чатов
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_client ON chats(client_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_status ON chats(status)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chats_payment ON chats(payment_status)"
    )

    # Индексы для сообщений
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)"
    )

    # Индексы для платежей
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_chat ON payments(chat_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")

    # Индексы для зачислений сотрудникам
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_staff_payments_member ON staff_payments(member_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_staff_payments_date ON staff_payments(created_at)"
    )

    # Индексы для документов
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_staff_docs_member ON staff_documents(member_id)"
    )

    # Индексы для архива
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_archive_category ON company_archive(category)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_archive_public ON company_archive(is_public)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_archive_date ON company_archive(created_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_archive_uploader ON company_archive(uploaded_by)"
    )

    # Индексы для групп и сообщений
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_group_messages_group ON group_messages(group_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_private_messages_sender ON private_messages(sender_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_private_messages_receiver ON private_messages(receiver_id)"
    )

    print("✅ Индексы созданы")

    # ================= DEFAULT USERS =================
    print("\n⏳ Создаю пользователей по умолчанию...")
    users = [
        (
            "admin",
            "admin123",
            "admin@arkonix.com",
            "admin",
            "Админ",
            "Администраторов",
            "admin_user",
        ),
        (
            "client",
            "client123",
            "client@example.com",
            "client",
            "Клиент",
            "Тестовый",
            "test_client",
        ),
    ]

    for u in users:
        try:
            cursor.execute(
                "INSERT INTO users (username, password, email, role, name, surname, handle) VALUES (?, ?, ?, ?, ?, ?, ?)",
                u,
            )
            print(f"  ✅ Создан пользователь: {u[0]} (роль: {u[3]})")
        except sqlite3.IntegrityError:
            print(f"  ⚠️ Пользователь {u[0]} уже существует")

    # ================= ADMIN BALANCE =================
    print("\n⏳ Инициализирую балансы и настройки...")
    cursor.execute("SELECT id FROM users WHERE role='admin'")
    admin = cursor.fetchone()
    if admin:
        cursor.execute(
            "INSERT OR IGNORE INTO admin_balance (admin_id, balance) VALUES (?, 0)",
            (admin[0],),
        )
        print("  ✅ Создан баланс для администратора")

    # ================= SAMPLE REVIEWS =================
    print("\n⏳ Создаю примеры отзывов...")
    sample_reviews = [
        ("Алексей К.", 5, "Отличная работа! Все сделано быстро и качественно."),
        ("Мария С.", 5, "Профессиональный подход, всем рекомендую!"),
        ("Дмитрий В.", 4, "Хорошая работа, небольшие задержки по срокам."),
    ]

    for review in sample_reviews:
        try:
            cursor.execute(
                "INSERT INTO reviews (user_name, rating, text) VALUES (?, ?, ?)", review
            )
        except:
            pass
    print("  ✅ Добавлены примеры отзывов")

    conn.commit()
    conn.close()

    print("\n" + "=" * 70)
    print("🎉 База данных успешно создана!")
    print("=" * 70)
    print("\n📝 Данные для входа:")
    print("  Администратор: admin / admin123")
    print("  Тестовый клиент: client / client123")
    print("\n💡 Все таблицы созданы:")
    print("  ✅ users - пользователи системы")
    print("  ✅ reviews - отзывы клиентов")
    print("  ✅ requests - заявки на услуги")
    print("  ✅ chats - чаты с клиентами")
    print("  ✅ messages - сообщения (с поддержкой файлов)")
    print("  ✅ payments - платежи от клиентов")
    print("  ✅ admin_balance - баланс администратора")
    print("  ✅ admin_payment_card - карта для оплаты")
    print("  ✅ payout_cards - карты для выплат")
    print("  ✅ team_members - команда сотрудников (с total_earned)")
    print("  ✅ staff_documents - документы сотрудников")
    print("  ✅ staff_payments - зачисления сотрудникам")
    print("  ✅ company_archive - архив документов компании")
    print("  ✅ groups - групповые чаты")
    print("  ✅ group_members - участники групп")
    print("  ✅ group_messages - сообщения в группах")
    print("  ✅ private_messages - личные сообщения")
    print("  ✅ contacts - контакты пользователей")
    print("\n🚀 Особенности:")
    print("  ✅ Поддержка файлов в сообщениях (изображения, видео, документы)")
    print("  ✅ Система зачислений сотрудникам (staff_payments)")
    print("  ✅ Отслеживание заработка (total_earned в team_members)")
    print("  ✅ Архив документов компании с категоризацией")
    print("  ✅ Индексы для быстрой работы с большими объемами данных")
    print("  ✅ БЕЗ тестовых сотрудников - только реальные регистрации")
    print("  ✅ Примеры отзывов для красоты главной страницы")
    print("\n📌 Важно:")
    print("  • Сотрудники регистрируются через /staff/register")
    print("  • После регистрации ожидают одобрения администратора")
    print("  • Одобренные сотрудники получают доступ к системе")
    print("  • Зачисления возможны только одобренным сотрудникам")
    print("  • Архив документов доступен только администраторам")
    print("=" * 70)


if __name__ == "__main__":
    init_db()
