from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,
    jsonify,
    abort
)
from flask_socketio import SocketIO, emit, join_room
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime, timezone, timedelta
import os

app = Flask(__name__)
app.secret_key = "super_secret_arkonix_key"
socketio = SocketIO(app, cors_allowed_origins="*")


UPLOAD_FOLDER = "uploads/contracts"
STAFF_DOCUMENTS_FOLDER = "uploads/staff_documents"
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "jpg", "jpeg", "png"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["STAFF_DOCUMENTS_FOLDER"] = STAFF_DOCUMENTS_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STAFF_DOCUMENTS_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        email TEXT,
        role TEXT DEFAULT 'client'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name TEXT NOT NULL,
        rating INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        staff_id INTEGER,
        service_name TEXT,
        status TEXT DEFAULT 'waiting',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES users(id),
        FOREIGN KEY (staff_id) REFERENCES users(id)
    )
    """)

    # Добавляем новые столбцы для системы оплаты
    try:
        cursor.execute("PRAGMA table_info(chats)")
        columns = [column[1] for column in cursor.fetchall()]

        if "order_price" not in columns:
            cursor.execute("ALTER TABLE chats ADD COLUMN order_price REAL DEFAULT NULL")
            print("✅ Добавлен столбец order_price")

        if "payment_status" not in columns:
            cursor.execute(
                "ALTER TABLE chats ADD COLUMN payment_status TEXT DEFAULT 'pending'"
            )
            print("✅ Добавлен столбец payment_status")
    except Exception as e:
        print(f"⚠️ Ошибка при добавлении столбцов: {e}")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        sender_id INTEGER,
        text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats(id),
        FOREIGN KEY (sender_id) REFERENCES users(id)
    )
    """)

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

    # Новая таблица для дополнительных документов сотрудников
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

    try:
        cursor.execute(
            "INSERT INTO users (username, password, email, role) VALUES ('admin', 'admin123', 'admin@arkonix.com', 'admin')"
        )
        print("✅ Создан админ: username='admin', password='admin123'")
    except sqlite3.IntegrityError:
        pass

    conn.commit()
    conn.close()


init_db()


def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def main():
    db = get_db()
    reviews = db.execute(
        "SELECT user_name, rating, text, created_at FROM reviews ORDER BY id DESC"
    ).fetchall()
    db.close()
    return render_template("index.html", reviews=reviews)


@app.route("/add_review", methods=["POST"])
def add_review():
    db = get_db()
    db.execute(
        "INSERT INTO reviews(user_name,rating,text) VALUES(?,?,?)",
        (request.form["name"], request.form["rating"], request.form["comment"]),
    )
    db.commit()
    db.close()
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        email = request.form.get("email", "")

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password, email, role) VALUES (?,?,?,?)",
                (username, password, email, "client"),
            )
            db.commit()

            user = db.execute(
                "SELECT id, username FROM users WHERE username=?", (username,)
            ).fetchone()
            db.close()

            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = "client"

            return redirect("/")

        except sqlite3.IntegrityError:
            db.close()
            flash("Пользователь уже существует")
            return redirect("/register")

    return render_template("auth/register.html")


@app.route("/staff/register", methods=["GET", "POST"])
def staff_register():
    SECRET_CODE = "ARKONIX2025"

    if request.method == "POST":
        entered_code = request.form.get("secret_code", "")
        if entered_code != SECRET_CODE:
            flash(
                "❌ Неверный секретный код! Обратитесь к администратору для получения кода."
            )
            return redirect("/staff/register")

        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        position = request.form.get("position")
        username = request.form.get("username")
        password = request.form.get("password")
        email = request.form.get("email", "")

        if "contract" not in request.files:
            flash("Необходимо загрузить договор")
            return redirect("/staff/register")

        file = request.files["contract"]

        if file.filename == "":
            flash("Файл не выбран")
            return redirect("/staff/register")

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_filename = f"{timestamp}_{username}_{filename}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
            file.save(filepath)

            db = get_db()
            try:
                existing = db.execute(
                    "SELECT username FROM team_members WHERE username=?", (username,)
                ).fetchone()

                if existing:
                    flash("Пользователь с таким логином уже существует")
                    db.close()
                    return redirect("/staff/register")

                cursor = db.execute(
                    """
                    INSERT INTO team_members 
                    (first_name, last_name, position, contract_filename, username, password, email, status) 
                    VALUES (?,?,?,?,?,?,?,?)
                """,
                    (
                        first_name,
                        last_name,
                        position,
                        unique_filename,
                        username,
                        password,
                        email,
                        "pending",
                    ),
                )

                member_id = cursor.lastrowid

                db.commit()
                db.close()

                # Сохраняем в сессию ID сотрудника для авторизации
                session["staff_member_id"] = member_id
                session["username"] = username
                session["role"] = "staff_pending"

                flash("✅ Регистрация успешна! Ожидайте одобрения администратора.")
                return redirect("/staff/profile")

            except Exception as e:
                db.close()
                flash(f"Ошибка при регистрации: {str(e)}")
                return redirect("/staff/register")
        else:
            flash("Недопустимый формат файла. Разрешены: PDF, DOC, DOCX, JPG, PNG")
            return redirect("/staff/register")

    return render_template("auth/staff_register.html")


@app.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()

        # Сначала проверяем в таблице users (для одобренных сотрудников)
        user = db.execute(
            "SELECT id, username, role FROM users WHERE username=? AND password=? AND role='staff'",
            (username, password),
        ).fetchone()

        if user:
            # Находим member_id
            member = db.execute(
                "SELECT id FROM team_members WHERE username=?", (username,)
            ).fetchone()

            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = "staff"
            if member:
                session["staff_member_id"] = member["id"]

            db.close()
            flash("✅ Вход выполнен успешно!")
            return redirect("/staff/profile")

        # Если не найдено в users, проверяем в team_members (для неодобренных)
        staff_member = db.execute(
            "SELECT id, username, status FROM team_members WHERE username=? AND password=?",
            (username, password),
        ).fetchone()

        db.close()

        if staff_member:
            session["staff_member_id"] = staff_member["id"]
            session["username"] = staff_member["username"]
            session["role"] = (
                "staff_pending" if staff_member["status"] == "pending" else "staff"
            )

            flash("✅ Вход выполнен успешно!")
            return redirect("/staff/profile")

        flash("❌ Неверный логин или пароль")
        return redirect("/staff/login")

    return render_template("staff_login.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()

        # Сначала проверяем в основной таблице users
        user = db.execute(
            "SELECT id, username, role FROM users WHERE username=? AND password=?",
            (username, password),
        ).fetchone()

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            db.close()

            if user["role"] == "admin":
                return redirect("/profile")
            elif user["role"] == "staff":
                # Для одобренных сотрудников находим их member_id
                member = db.execute(
                    "SELECT id FROM team_members WHERE username=?", (username,)
                ).fetchone()
                if member:
                    session["staff_member_id"] = member["id"]
                return redirect("/staff/profile")
            else:
                return redirect("/")

        # Если не найдено в users, проверяем в team_members (для неодобренных сотрудников)
        staff_member = db.execute(
            "SELECT id, username, status FROM team_members WHERE username=? AND password=?",
            (username, password),
        ).fetchone()

        db.close()

        if staff_member:
            session["staff_member_id"] = staff_member["id"]
            session["username"] = staff_member["username"]
            session["role"] = (
                "staff_pending" if staff_member["status"] == "pending" else "staff"
            )
            return redirect("/staff/profile")

        flash("Неверные данные")
        return redirect("/login")

    return render_template("auth/login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# Личный кабинет сотрудника
@app.route("/staff/profile")
def staff_profile():
    if "staff_member_id" not in session:
        flash("Требуется авторизация")
        return redirect("/login")

    db = get_db()

    # Получаем данные сотрудника
    member = db.execute(
        "SELECT * FROM team_members WHERE id=?", (session["staff_member_id"],)
    ).fetchone()

    if not member:
        db.close()
        flash("Участник не найден")
        return redirect("/logout")

    # Получаем все документы сотрудника
    documents = []

    # Добавляем договор как первый документ
    documents.append(
        {
            "id": f"contract_{member['id']}",
            "document_type": "contract",
            "document_name": "Договор о участии в команде",
            "filename": member["contract_filename"],
            "description": "Основной договор",
            "uploaded_at": member["created_at"],
        }
    )

    # Добавляем дополнительные документы
    additional_docs = db.execute(
        "SELECT * FROM staff_documents WHERE member_id=? ORDER BY uploaded_at DESC",
        (session["staff_member_id"],),
    ).fetchall()

    for doc in additional_docs:
        documents.append(dict(doc))

    db.close()

    return render_template(
        "staff_profile.html", member=dict(member), documents=documents
    )


# Загрузка нового документа сотрудником
@app.route("/staff/upload_document", methods=["POST"])
def staff_upload_document():
    if "staff_member_id" not in session:
        flash("Требуется авторизация")
        return redirect("/login")

    document_name = request.form.get("document_name")
    document_type = request.form.get("document_type")
    description = request.form.get("description", "")

    if "document" not in request.files:
        flash("Файл не выбран")
        return redirect("/staff/profile")

    file = request.files["document"]

    if file.filename == "":
        flash("Файл не выбран")
        return redirect("/staff/profile")

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{session['username']}_{filename}"
        filepath = os.path.join(app.config["STAFF_DOCUMENTS_FOLDER"], unique_filename)
        file.save(filepath)

        db = get_db()
        db.execute(
            """
            INSERT INTO staff_documents 
            (member_id, document_name, document_type, filename, description)
            VALUES (?,?,?,?,?)
            """,
            (
                session["staff_member_id"],
                document_name,
                document_type,
                unique_filename,
                description,
            ),
        )
        db.commit()
        db.close()

        flash("✅ Документ успешно загружен и отправлен администратору!")
        return redirect("/staff/profile")
    else:
        flash("Недопустимый формат файла")
        return redirect("/staff/profile")


# Просмотр документа сотрудника
@app.route("/staff/document/view/<doc_id>")
def staff_view_document(doc_id):
    if "staff_member_id" not in session:
        return "Доступ запрещён", 403

    # Обработка договора
    if doc_id.startswith("contract_"):
        member_id = int(doc_id.split("_")[1])
        if member_id != session["staff_member_id"]:
            return "Доступ запрещён", 403

        db = get_db()
        member = db.execute(
            "SELECT contract_filename FROM team_members WHERE id=?", (member_id,)
        ).fetchone()
        db.close()

        if not member:
            return "Файл не найден", 404

        return send_from_directory(
            os.path.abspath(UPLOAD_FOLDER),
            member["contract_filename"],
            as_attachment=False,
        )

    # Обработка дополнительных документов
    db = get_db()
    document = db.execute(
        "SELECT * FROM staff_documents WHERE id=? AND member_id=?",
        (doc_id, session["staff_member_id"]),
    ).fetchone()
    db.close()

    if not document:
        return "Файл не найден", 404

    return send_from_directory(
        os.path.abspath(STAFF_DOCUMENTS_FOLDER),
        document["filename"],
        as_attachment=False,
    )


# Скачивание документа сотрудника
@app.route("/staff/document/download/<doc_id>")
def staff_download_document(doc_id):
    if "staff_member_id" not in session:
        return "Доступ запрещён", 403

    # Обработка договора
    if doc_id.startswith("contract_"):
        member_id = int(doc_id.split("_")[1])
        if member_id != session["staff_member_id"]:
            return "Доступ запрещён", 403

        db = get_db()
        member = db.execute(
            "SELECT contract_filename FROM team_members WHERE id=?", (member_id,)
        ).fetchone()
        db.close()

        if not member:
            return "Файл не найден", 404

        return send_from_directory(
            os.path.abspath(UPLOAD_FOLDER),
            member["contract_filename"],
            as_attachment=True,
        )

    # Обработка дополнительных документов
    db = get_db()
    document = db.execute(
        "SELECT * FROM staff_documents WHERE id=? AND member_id=?",
        (doc_id, session["staff_member_id"]),
    ).fetchone()
    db.close()

    if not document:
        return "Файл не найден", 404

    return send_from_directory(
        os.path.abspath(STAFF_DOCUMENTS_FOLDER),
        document["filename"],
        as_attachment=True,
    )






@app.route("/admin/set_card", methods=["POST"])
def set_card():
    if session.get("role") != "admin":
        abort(403)

    card_number = request.form["card_number"]
    card_holder = request.form["card_holder"]

    db = get_db()
    db.execute(
        """
        INSERT INTO payout_cards (admin_id, card_number, card_holder)
        VALUES (?, ?, ?)
        ON CONFLICT(admin_id) DO UPDATE SET
            card_number=excluded.card_number,
            card_holder=excluded.card_holder
    """,
        (session["user_id"], card_number, card_holder),
    )

    db.commit()
    db.close()

    flash("Карта сохранена")
    return redirect("/profile")


@app.route("/admin/balance")
def admin_balance():
    if session["role"] != "admin":
        abort(403)

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT balance FROM admin_balance
        WHERE admin_id = ?
    """,
        (session["user_id"],),
    )

    balance = cur.fetchone()["balance"]
    conn.close()

    return f"Баланс админа: ${balance}"


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()

    if session["role"] == "admin":
        chats = db.execute("""
            SELECT 
                chats.id,
                chats.client_id,
                users.username, 
                users.email,
                chats.service_name, 
                chats.status,
                chats.order_price,
                chats.payment_status,
                chats.created_at,
                (SELECT COUNT(*) FROM messages WHERE chat_id = chats.id) as message_count,
                (SELECT text FROM messages WHERE chat_id = chats.id ORDER BY id DESC LIMIT 1) as last_message,
                (SELECT created_at FROM messages WHERE chat_id = chats.id ORDER BY id DESC LIMIT 1) as last_message_time
            FROM chats
            JOIN users ON users.id = chats.client_id
            ORDER BY 
                CASE 
                    WHEN chats.status = 'waiting' THEN 0
                    ELSE 1
                END,
                COALESCE(
                    (SELECT created_at FROM messages WHERE chat_id = chats.id ORDER BY id DESC LIMIT 1),
                    chats.created_at
                ) DESC
        """).fetchall()

        # ДОБАВИТЬ: Получаем статистику платежей
        payment_stats = db.execute("""
            SELECT 
                COUNT(*) as total_payments,
                SUM(amount) as total_amount
            FROM payments
            WHERE status = 'completed'
        """).fetchone()

        db.close()
        return render_template(
            "admin_board.html", chats=chats, payment_stats=payment_stats
        )

    # Для клиентов добавляем информацию об оплате
    chats = db.execute(
        "SELECT id, service_name, status, order_price, payment_status FROM chats WHERE client_id=?",
        (session["user_id"],),
    ).fetchall()
    db.close()
    return render_template("profile.html", chats=chats)

@app.route("/create_chat", methods=["POST"])
def create_chat():
    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "client":
        return redirect("/login")

    service = request.form["service"]
    description = request.form.get("description", "")

    db = get_db()

    cursor = db.execute(
        "INSERT INTO chats (client_id, service_name, status) VALUES (?,?,?)",
        (session["user_id"], service, "waiting"),
    )
    chat_id = cursor.lastrowid

    if description:
        db.execute(
            "INSERT INTO messages (chat_id, sender_id, text) VALUES (?,?,?)",
            (chat_id, session["user_id"], description),
        )

    db.commit()
    db.close()

    return redirect(f"/chat/{chat_id}")


@app.route("/chat/<int:chat_id>")
def chat(chat_id):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()

    chat_info = db.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()

    if not chat_info:
        db.close()
        return "Чат не найден", 404

    if session["role"] == "client" and chat_info["client_id"] != session["user_id"]:
        db.close()
        return "Доступ запрещен", 403

    messages_raw = db.execute(
        "SELECT text, sender_id, created_at FROM messages WHERE chat_id=? ORDER BY id",
        (chat_id,),
    ).fetchall()

    ukraine_tz = timezone(timedelta(hours=2))
    messages = []
    for msg in messages_raw:
        msg_dict = dict(msg)
        if msg_dict["created_at"]:
            try:
                utc_time = datetime.fromisoformat(
                    msg_dict["created_at"].replace("Z", "+00:00")
                )
                ukraine_time = utc_time.astimezone(ukraine_tz)
                msg_dict["created_at"] = ukraine_time.isoformat()
            except:
                msg_dict["created_at"] = msg_dict["created_at"]
        messages.append(msg_dict)

    if session["role"] == "client":
        sender_name = "Поддержка ARKONIX"
    else:
        client = db.execute(
            "SELECT username FROM users WHERE id=?", (chat_info["client_id"],)
        ).fetchone()
        sender_name = client["username"] if client else "Клиент"

    db.close()

    return render_template(
        "chat.html",
        chat_id=chat_id,
        messages=messages,
        user_id=session["user_id"],
        sender_name=sender_name,
        service_name=chat_info["service_name"],
        chat_status=chat_info["payment_status"]
        if chat_info["payment_status"] == "paid"
        else chat_info["status"],
        order_price=chat_info["order_price"],
        created_at=chat_info["created_at"],
    )


@socketio.on("join")
def join(data):
    join_room(f"chat_{data['chat_id']}")




@app.route("/admin/all_documents")
def admin_all_documents():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён. Требуются права администратора.")
        return redirect("/login")

    db = get_db()

    # Получаем всех участников
    members = db.execute("""
        SELECT * FROM team_members 
        ORDER BY 
            CASE status
                WHEN 'pending' THEN 1
                WHEN 'approved' THEN 2
                WHEN 'rejected' THEN 3
            END,
            created_at DESC
    """).fetchall()

    members_with_docs = []
    total_documents = 0
    total_contracts = 0
    total_additional = 0

    for member in members:
        member_dict = dict(member)
        documents = []

        # Добавляем договор
        documents.append(
            {
                "id": f"contract_{member['id']}",
                "type": "contract",
                "name": "Договор о участии в команде",
                "filename": member["contract_filename"],
                "description": "Основной договор",
                "uploaded_at": member["created_at"],
            }
        )
        total_contracts += 1

        # Добавляем дополнительные документы
        additional_docs = db.execute(
            "SELECT * FROM staff_documents WHERE member_id=? ORDER BY uploaded_at DESC",
            (member["id"],),
        ).fetchall()

        for doc in additional_docs:
            doc_dict = dict(doc)
            documents.append(
                {
                    "id": doc_dict["id"],
                    "type": doc_dict["document_type"],
                    "name": doc_dict["document_name"],
                    "filename": doc_dict["filename"],
                    "description": doc_dict.get("description", ""),
                    "uploaded_at": doc_dict["uploaded_at"],
                }
            )
            total_additional += 1

        total_documents += len(documents)

        members_with_docs.append({"member": member_dict, "documents": documents})

    db.close()

    return render_template(
        "admin_all_documents.html",
        members_with_docs=members_with_docs,
        total_members=len(members),
        total_documents=total_documents,
        total_contracts=total_contracts,
        total_additional=total_additional,
    )


@app.route("/admin/team", methods=["GET"])
def admin_team():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён. Требуются права администратора.")
        return redirect("/login")

    db = get_db()
    team_members = db.execute("""
        SELECT id, first_name, last_name, position, username, email, status, contract_filename, created_at
        FROM team_members
        ORDER BY 
            CASE status
                WHEN 'pending' THEN 1
                WHEN 'approved' THEN 2
                WHEN 'rejected' THEN 3
            END,
            created_at DESC
    """).fetchall()
    db.close()

    return render_template("admin_team.html", team_members=team_members)


# Админ - просмотр документов сотрудника
@app.route("/admin/staff/<int:member_id>/documents")
def admin_view_staff_documents(member_id):
    if "user_id" not in session or session.get("role") != "admin":
        return "Доступ запрещён", 403

    db = get_db()

    member = db.execute(
        "SELECT * FROM team_members WHERE id=?", (member_id,)
    ).fetchone()

    if not member:
        db.close()
        flash("Участник не найден")
        return redirect("/admin/team")

    documents = db.execute(
        "SELECT * FROM staff_documents WHERE member_id=? ORDER BY uploaded_at DESC",
        (member_id,),
    ).fetchall()

    db.close()

    return render_template(
        "admin_staff_documents.html", member=dict(member), documents=documents
    )


# Админ - скачивание документа сотрудника
@app.route("/admin/staff/document/download/<int:doc_id>")
def admin_download_staff_document(doc_id):
    if "user_id" not in session or session.get("role") != "admin":
        return "Доступ запрещён", 403

    db = get_db()
    document = db.execute(
        "SELECT * FROM staff_documents WHERE id=?", (doc_id,)
    ).fetchone()
    db.close()

    if not document:
        return "Файл не найден", 404

    return send_from_directory(
        os.path.abspath(STAFF_DOCUMENTS_FOLDER),
        document["filename"],
        as_attachment=True,
    )


@app.route("/admin/team/approve/<int:member_id>", methods=["POST"])
def approve_team_member(member_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    db = get_db()

    member = db.execute(
        "SELECT * FROM team_members WHERE id=?", (member_id,)
    ).fetchone()

    if not member:
        flash("Участник не найден")
        db.close()
        return redirect("/admin/team")

    try:
        db.execute(
            """
            INSERT INTO users (username, password, email, role)
            VALUES (?, ?, ?, 'staff')
        """,
            (member["username"], member["password"], member["email"]),
        )

        db.execute("UPDATE team_members SET status='approved' WHERE id=?", (member_id,))

        db.commit()
        flash(
            f"✅ Участник {member['first_name']} {member['last_name']} успешно одобрен!"
        )
    except sqlite3.IntegrityError:
        flash("Пользователь с таким логином уже существует в системе")
    except Exception as e:
        flash(f"Ошибка: {str(e)}")

    db.close()
    return redirect("/admin/team")


@app.route("/admin/team/reject/<int:member_id>", methods=["POST"])
def reject_team_member(member_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    db = get_db()
    db.execute("UPDATE team_members SET status='rejected' WHERE id=?", (member_id,))
    db.commit()
    db.close()

    flash("Заявка отклонена")
    return redirect("/admin/team")


@app.route("/admin/team/delete/<int:member_id>", methods=["POST"])
def delete_team_member(member_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    db = get_db()

    member = db.execute(
        "SELECT contract_filename FROM team_members WHERE id=?", (member_id,)
    ).fetchone()

    if member and member["contract_filename"]:
        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"], member["contract_filename"]
        )
        if os.path.exists(filepath):
            os.remove(filepath)

    # Удаляем дополнительные документы
    documents = db.execute(
        "SELECT filename FROM staff_documents WHERE member_id=?", (member_id,)
    ).fetchall()

    for doc in documents:
        filepath = os.path.join(app.config["STAFF_DOCUMENTS_FOLDER"], doc["filename"])
        if os.path.exists(filepath):
            os.remove(filepath)

    db.execute("DELETE FROM staff_documents WHERE member_id=?", (member_id,))
    db.execute("DELETE FROM team_members WHERE id=?", (member_id,))
    db.commit()
    db.close()

    flash("Участник удалён из базы")
    return redirect("/admin/team")


@app.route("/uploads/contracts/<filename>")
def download_contract(filename):
    if "user_id" not in session or session.get("role") != "admin":
        return "Доступ запрещён", 403

    try:
        upload_dir = os.path.abspath(UPLOAD_FOLDER)
        file_path = os.path.join(upload_dir, filename)

        if not os.path.exists(file_path):
            flash(f"Файл не найден: {filename}")
            return redirect("/admin/team")

        return send_from_directory(upload_dir, filename, as_attachment=True)
    except Exception as e:
        flash(f"Ошибка при скачивании: {str(e)}")
        return redirect("/admin/team")


@app.route("/view/contracts/<filename>")
def view_contract(filename):
    if "user_id" not in session or session.get("role") != "admin":
        return "Доступ запрещён", 403

    try:
        upload_dir = os.path.abspath(UPLOAD_FOLDER)
        file_path = os.path.join(upload_dir, filename)

        if not os.path.exists(file_path):
            flash(f"Файл не найден: {filename}")
            return redirect("/admin/team")

        return send_from_directory(upload_dir, filename, as_attachment=False)
    except Exception as e:
        flash(f"Ошибка при открытии файла: {str(e)}")
        return redirect("/admin/team")








@app.route("/api/set_price", methods=["POST"])
def set_price():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json()
    chat_id = data.get("chat_id")
    price = data.get("price")

    if not chat_id or price is None:
        return jsonify({"error": "Missing data"}), 400

    try:
        price = float(price)
        if price <= 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": "Invalid price"}), 400

    db = get_db()

    chat = db.execute(
        "SELECT payment_status, client_id FROM chats WHERE id=?", (chat_id,)
    ).fetchone()

    if not chat:
        db.close()
        return jsonify({"error": "Chat not found"}), 404

    if chat["payment_status"] == "paid":
        db.close()
        return jsonify({"error": "Already paid"}), 400

    db.execute(
        "UPDATE chats SET order_price=?, status='in_progress' WHERE id=?",
        (price, chat_id),
    )

    db.commit()
    db.close()

    # ВАЖНО: Отправляем обновление цены всем участникам чата
    socketio.emit(
        "price_updated", {"chat_id": chat_id, "price": price}, room=f"chat_{chat_id}"
    )

    return jsonify({"success": True, "price": price})

@app.route("/discussions")
def discussions():
    if "user_id" not in session:
        return redirect("/login")

    selected_service = request.args.get("service", "")

    return render_template("discussions.html", selected_service=selected_service)


@app.route("/services")
def services():
    return render_template("services.html")


@app.route("/team")
def team():
    return render_template("team.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/delete_review/<int:review_id>", methods=["POST"])
def delete_review(review_id):
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён. Требуются права администратора.")
        return redirect("/login")

    db = get_db()
    db.execute("DELETE FROM reviews WHERE id=?", (review_id,))
    db.commit()
    db.close()

    flash("Отзыв успешно удалён")
    return redirect("/admin/reviews")


@app.route("/admin/reviews")
def admin_reviews():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён. Требуются права администратора.")
        return redirect("/login")

    db = get_db()
    reviews = db.execute(
        "SELECT id, user_name, rating, text, created_at FROM reviews ORDER BY id DESC"
    ).fetchall()
    db.close()

    return render_template("admin_reviews.html", reviews=reviews)
















 







# 6. Исправленный обработчик Socket.IO для отправки сообщений


@socketio.on("send_message")
def send_message(data):
    if "user_id" not in session:
        return

    chat_id = data["chat_id"]
    text = data["text"]
    sender_id = session["user_id"]
    sender_role = session.get("role")

    db = get_db()

    # Сохраняем сообщение
    cursor = db.execute(
        "INSERT INTO messages (chat_id, sender_id, text) VALUES (?,?,?)",
        (chat_id, sender_id, text),
    )
    message_id = cursor.lastrowid

    # Получаем информацию о чате
    chat_info = db.execute(
        "SELECT status, client_id FROM chats WHERE id=?", (chat_id,)
    ).fetchone()

    # Если админ/сотрудник отвечает, меняем статус на "в процессе"
    if (
        sender_role in ["admin", "staff"]
        and chat_info
        and chat_info["status"] == "waiting"
    ):
        db.execute("UPDATE chats SET status=? WHERE id=?", ("in_progress", chat_id))

    db.commit()

    # Получаем время создания сообщения
    message_time = db.execute(
        "SELECT created_at FROM messages WHERE id=?", (message_id,)
    ).fetchone()

    db.close()

    # ВАЖНО: include_self=True чтобы отправитель тоже видел сообщение
    emit(
        "new_message",
        {
            "text": text,
            "sender_id": sender_id,
            "created_at": message_time["created_at"]
            if message_time
            else datetime.now().isoformat(),
        },
        room=f"chat_{chat_id}",
        include_self=True,
    )


@app.route("/admin/payment_settings", methods=["GET", "POST"])
def admin_payment_settings():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён")
        return redirect("/login")

    db = get_db()

    if request.method == "POST":
        card_number = request.form.get("card_number", "").strip()
        card_holder = request.form.get("card_holder", "").strip()

        if not card_number or not card_holder:
            flash("❌ Заполните все поля")
            db.close()
            return redirect("/admin/payment_settings")

        # Очищаем номер карты от пробелов
        card_number = card_number.replace(" ", "")

        try:
            existing = db.execute(
                "SELECT id FROM admin_payment_card WHERE admin_id=?",
                (session["user_id"],),
            ).fetchone()

            if existing:
                db.execute(
                    """UPDATE admin_payment_card 
                       SET card_number=?, card_holder=?, updated_at=CURRENT_TIMESTAMP 
                       WHERE admin_id=?""",
                    (card_number, card_holder, session["user_id"]),
                )
            else:
                db.execute(
                    """INSERT INTO admin_payment_card (admin_id, card_number, card_holder)
                       VALUES (?, ?, ?)""",
                    (session["user_id"], card_number, card_holder),
                )

            db.commit()
            flash("✅ Данные карты успешно сохранены!")
        except Exception as e:
            flash(f"❌ Ошибка: {str(e)}")

        db.close()
        return redirect("/admin/payment_settings")

    # GET запрос - показываем форму
    card_data = db.execute(
        "SELECT card_number, card_holder FROM admin_payment_card WHERE admin_id=?",
        (session["user_id"],),
    ).fetchone()

    db.close()

    return render_template("admin_payment_settings.html", card_data=card_data)


# Страница оплаты для клиента
@app.route("/payment/<int:chat_id>")
def payment_page(chat_id):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()

    chat = db.execute(
        "SELECT * FROM chats WHERE id=? AND client_id=?", (chat_id, session["user_id"])
    ).fetchone()

    if not chat:
        db.close()
        flash("Чат не найден")
        return redirect("/profile")

    if not chat["order_price"]:
        db.close()
        flash("Цена ещё не установлена")
        return redirect(f"/chat/{chat_id}")

    if chat["payment_status"] == "paid":
        db.close()
        flash("Заказ уже оплачен")
        return redirect(f"/chat/{chat_id}")

    # Получаем карту администратора
    admin_card = db.execute(
        "SELECT card_number, card_holder FROM admin_payment_card LIMIT 1"
    ).fetchone()

    db.close()

    return render_template(
        "payment.html",
        chat=dict(chat),
        admin_card=dict(admin_card) if admin_card else None,
    )











@app.route("/payment/confirm/<int:chat_id>", methods=["POST"])
def confirm_payment(chat_id):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()

    chat = db.execute(
        "SELECT * FROM chats WHERE id=? AND client_id=?", (chat_id, session["user_id"])
    ).fetchone()

    if not chat or chat["payment_status"] == "paid":
        db.close()
        flash("Невозможно выполнить оплату")
        return redirect("/profile")

    # Получаем карту администратора
    admin_card = db.execute(
        "SELECT card_number FROM admin_payment_card LIMIT 1"
    ).fetchone()

    if not admin_card:
        db.close()
        flash("❌ Карта для оплаты не настроена")
        return redirect(f"/chat/{chat_id}")

    try:
        # Сохраняем информацию о платеже со статусом "ожидает подтверждения"
        db.execute(
            """INSERT INTO payments (chat_id, client_id, amount, card_number, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (
                chat_id,
                session["user_id"],
                chat["order_price"],
                admin_card["card_number"],
            ),
        )

        # Обновляем статус оплаты в чате на "ожидает подтверждения"
        db.execute(
            "UPDATE chats SET payment_status='awaiting_confirmation' WHERE id=?",
            (chat_id,),
        )

        db.commit()
        db.close()

        flash("✅ Заявка на оплату отправлена! Ожидайте подтверждения администратора.")

        return redirect(f"/chat/{chat_id}")

    except Exception as e:
        db.close()
        flash(f"❌ Ошибка при обработке платежа: {str(e)}")
        return redirect(f"/payment/{chat_id}")


# Новый роут: История платежей для админа
@app.route("/admin/payments")
def admin_payments():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён")
        return redirect("/login")

    db = get_db()

    # Получаем все платежи с информацией о клиентах и чатах
    payments = db.execute("""
        SELECT 
            payments.*,
            users.username,
            users.email,
            chats.service_name,
            chats.payment_status as chat_payment_status
        FROM payments
        JOIN users ON users.id = payments.client_id
        JOIN chats ON chats.id = payments.chat_id
        ORDER BY payments.payment_date DESC
    """).fetchall()

    db.close()

    return render_template("admin_payments.html", payments=payments)


# Новый роут: Подтверждение оплаты администратором
@app.route("/admin/payment/approve/<int:payment_id>", methods=["POST"])
def admin_approve_payment(payment_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    db = get_db()

    # Получаем информацию о платеже
    payment = db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()

    if not payment:
        db.close()
        flash("Платёж не найден")
        return redirect("/admin/payments")

    try:
        # Обновляем статус платежа
        db.execute("UPDATE payments SET status='completed' WHERE id=?", (payment_id,))

        # Обновляем статус оплаты в чате
        db.execute(
            "UPDATE chats SET payment_status='paid' WHERE id=?", (payment["chat_id"],)
        )

        db.commit()
        db.close()

        flash("✅ Платёж подтверждён!")

        # Уведомляем через Socket.IO
        socketio.emit(
            "payment_completed",
            {"chat_id": payment["chat_id"]},
            room=f"chat_{payment['chat_id']}",
        )

        return redirect("/admin/payments")

    except Exception as e:
        db.close()
        flash(f"❌ Ошибка: {str(e)}")
        return redirect("/admin/payments")


# Новый роут: Отклонение оплаты администратором
@app.route("/admin/payment/reject/<int:payment_id>", methods=["POST"])
def admin_reject_payment(payment_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    db = get_db()

    payment = db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()

    if not payment:
        db.close()
        flash("Платёж не найден")
        return redirect("/admin/payments")

    try:
        # Обновляем статус платежа
        db.execute("UPDATE payments SET status='rejected' WHERE id=?", (payment_id,))

        # Возвращаем статус чата обратно
        db.execute(
            "UPDATE chats SET payment_status='pending' WHERE id=?",
            (payment["chat_id"],),
        )

        db.commit()
        db.close()

        flash("⚠️ Платёж отклонён")
        return redirect("/admin/payments")

    except Exception as e:
        db.close()
        flash(f"❌ Ошибка: {str(e)}")
        return redirect("/admin/payments")
































if __name__ == "__main__":
    socketio.run(app, port=5001, debug=True)
