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
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_arkonix_key"
socketio = SocketIO(app, cors_allowed_origins="*")


UPLOAD_FOLDER = "uploads/contracts"
STAFF_DOCUMENTS_FOLDER = "uploads/staff_documents"
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "jpg", "jpeg", "png"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["STAFF_DOCUMENTS_FOLDER"] = STAFF_DOCUMENTS_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STAFF_DOCUMENTS_FOLDER, exist_ok=True)

CHAT_ATTACHMENTS_FOLDER = "uploads/chat_attachments"
app.config["CHAT_ATTACHMENTS_FOLDER"] = CHAT_ATTACHMENTS_FOLDER
os.makedirs(CHAT_ATTACHMENTS_FOLDER, exist_ok=True)


ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "svg",
    "bmp",
    "pdf",
    "doc",
    "docx",
    "txt",
    "rtf",
    "odt",
    "xls",
    "xlsx",
    "csv",
    "ppt",
    "pptx",
    "mp4",
    "avi",
    "mov",
    "wmv",
    "flv",
    "mkv",
    "webm",
    "mp3",
    "wav",
    "ogg",
    "m4a",
    "flac",
    "zip",
    "rar",
    "7z",
    "tar",
    "gz",
}


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

 
        user = db.execute(
            "SELECT id, username, role FROM users WHERE username=? AND password=? AND role='staff'",
            (username, password),
        ).fetchone()

        if user:

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
                
                member = db.execute(
                    "SELECT id FROM team_members WHERE username=?", (username,)
                ).fetchone()
                if member:
                    session["staff_member_id"] = member["id"]
                return redirect("/staff/profile")
            else:
                return redirect("/")

     
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



@app.route("/staff/document/view/<doc_id>")
def staff_view_document(doc_id):
    if "staff_member_id" not in session:
        return "Доступ запрещён", 403


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



@app.route("/staff/document/download/<doc_id>")
def staff_download_document(doc_id):
    if "staff_member_id" not in session:
        return "Доступ запрещён", 403



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


        payment_stats = db.execute("""
            SELECT 
                COUNT(*) as total_payments,
                SUM(amount) as total_amount
            FROM payments
            WHERE status = 'completed'
        """).fetchone()

   
        staff_total = db.execute("""
            SELECT COALESCE(SUM(total_earned), 0) as total_earned
            FROM team_members
            WHERE status = 'approved'
        """).fetchone()

        db.close()

        return render_template(
            "admin_board.html",
            chats=chats,
            payment_stats=payment_stats,
            staff_total_earned=staff_total["total_earned"] if staff_total else 0,
        )


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





@socketio.on("join")
def join(data):
    join_room(f"chat_{data['chat_id']}")










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
















 










@socketio.on("send_message")
def send_message(data):
    if "user_id" not in session:
        return

    chat_id = data["chat_id"]
    text = data["text"]
    sender_id = session["user_id"]
    sender_role = session.get("role")

    db = get_db()


    cursor = db.execute(
        "INSERT INTO messages (chat_id, sender_id, text) VALUES (?,?,?)",
        (chat_id, sender_id, text),
    )
    message_id = cursor.lastrowid


    chat_info = db.execute(
        "SELECT status, client_id FROM chats WHERE id=?", (chat_id,)
    ).fetchone()


    if (
        sender_role in ["admin", "staff"]
        and chat_info
        and chat_info["status"] == "waiting"
    ):
        db.execute("UPDATE chats SET status=? WHERE id=?", ("in_progress", chat_id))

    db.commit()


    message_time = db.execute(
        "SELECT created_at FROM messages WHERE id=?", (message_id,)
    ).fetchone()

    db.close()


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

    
    
    card_data = db.execute(
        "SELECT card_number, card_holder FROM admin_payment_card WHERE admin_id=?",
        (session["user_id"],),
    ).fetchone()

    db.close()

    return render_template("admin_payment_settings.html", card_data=card_data)



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


    admin_card = db.execute(
        "SELECT card_number FROM admin_payment_card LIMIT 1"
    ).fetchone()

    if not admin_card:
        db.close()
        flash("❌ Карта для оплаты не настроена")
        return redirect(f"/chat/{chat_id}")

    try:
      
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



@app.route("/admin/payments")
def admin_payments():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён")
        return redirect("/login")

    db = get_db()


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



@app.route("/admin/payment/approve/<int:payment_id>", methods=["POST"])
def admin_approve_payment(payment_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    db = get_db()


    payment = db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()

    if not payment:
        db.close()
        flash("Платёж не найден")
        return redirect("/admin/payments")

    try:
    
        db.execute("UPDATE payments SET status='completed' WHERE id=?", (payment_id,))

   
        db.execute(
            "UPDATE chats SET payment_status='paid' WHERE id=?", (payment["chat_id"],)
        )

        db.commit()
        db.close()

        flash("✅ Платёж подтверждён!")

 
 
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
 
        db.execute("UPDATE payments SET status='rejected' WHERE id=?", (payment_id,))

     
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








@app.route("/admin/chat/complete/<int:chat_id>", methods=["POST"])
def complete_chat(chat_id):
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён")
        return redirect("/login")

    db = get_db()


    chat = db.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()

    if not chat:
        db.close()
        flash("❌ Чат не найден")
        return redirect("/profile")

    try:
     
        db.execute("UPDATE chats SET status='completed' WHERE id=?", (chat_id,))

        db.commit()
        db.close()

        flash("✅ Чат успешно завершён!")

  
        socketio.emit(
            "chat_completed",
            {"chat_id": chat_id, "message": "Администратор завершил чат"},
            room=f"chat_{chat_id}",
        )

        return redirect("/profile")

    except Exception as e:
        db.close()
        flash(f"❌ Ошибка при завершении чата: {str(e)}")
        return redirect("/profile")



@app.route("/admin/chat/update_status/<int:chat_id>", methods=["POST"])
def update_chat_status(chat_id):
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403

    new_status = request.form.get("status")

    if new_status not in ["waiting", "in_progress", "completed", "cancelled"]:
        return jsonify({"error": "Invalid status"}), 400

    db = get_db()

    try:
        db.execute("UPDATE chats SET status=? WHERE id=?", (new_status, chat_id))
        db.commit()
        db.close()

   
        socketio.emit(
            "status_updated",
            {"chat_id": chat_id, "new_status": new_status},
            room=f"chat_{chat_id}",
        )

        return jsonify({"success": True, "status": new_status})

    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 500



@app.route("/api/chat_stats")
def chat_stats():
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403

    db = get_db()

    stats = {
        "total": db.execute("SELECT COUNT(*) as count FROM chats").fetchone()["count"],
        "waiting": db.execute(
            "SELECT COUNT(*) as count FROM chats WHERE status='waiting'"
        ).fetchone()["count"],
        "in_progress": db.execute(
            "SELECT COUNT(*) as count FROM chats WHERE status='in_progress'"
        ).fetchone()["count"],
        "completed": db.execute(
            "SELECT COUNT(*) as count FROM chats WHERE status='completed'"
        ).fetchone()["count"],
        "paid": db.execute(
            "SELECT COUNT(*) as count FROM chats WHERE payment_status='paid'"
        ).fetchone()["count"],
        "awaiting_payment": db.execute(
            "SELECT COUNT(*) as count FROM chats WHERE payment_status='awaiting_confirmation'"
        ).fetchone()["count"],
    }

    db.close()

    return jsonify(stats)









def get_file_type(filename):

    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""

    image_extensions = {"jpg", "jpeg", "png", "gif", "webp", "svg", "bmp"}
    video_extensions = {"mp4", "avi", "mov", "wmv", "flv", "mkv", "webm"}

    if ext in image_extensions:
        return "image"
    elif ext in video_extensions:
        return "video"
    else:
        return "file"


def format_file_size(size_bytes):
 
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"



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
        """SELECT id, text, sender_id, created_at, 
                  attachment_type, attachment_filename, attachment_size 
           FROM messages 
           WHERE chat_id=? 
           ORDER BY id""",
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

   
        if msg_dict.get("attachment_size"):
            msg_dict["formatted_size"] = format_file_size(msg_dict["attachment_size"])

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



@app.route("/chat/<int:chat_id>/upload", methods=["POST"])
def upload_chat_file(chat_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()


    chat_info = db.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()

    if not chat_info:
        db.close()
        return jsonify({"error": "Chat not found"}), 404

    if session["role"] == "client" and chat_info["client_id"] != session["user_id"]:
        db.close()
        return jsonify({"error": "Access denied"}), 403


    if "file" not in request.files:
        db.close()
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    message_text = request.form.get("text", "").strip()

    if file.filename == "":
        db.close()
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        db.close()
        return jsonify({"error": "File type not allowed"}), 400

    try:
  
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{chat_id}_{session['user_id']}_{filename}"
        filepath = os.path.join(app.config["CHAT_ATTACHMENTS_FOLDER"], unique_filename)

        file.save(filepath)
        file_size = os.path.getsize(filepath)
        file_type = get_file_type(filename)

     
     
        cursor = db.execute(
            """INSERT INTO messages 
               (chat_id, sender_id, text, attachment_type, attachment_filename, attachment_size) 
               VALUES (?,?,?,?,?,?)""",
            (
                chat_id,
                session["user_id"],
                message_text or "",
                file_type,
                unique_filename,
                file_size,
            ),
        )
        message_id = cursor.lastrowid

      
        sender_role = session.get("role")
        if sender_role in ["admin", "staff"] and chat_info["status"] == "waiting":
            db.execute("UPDATE chats SET status=? WHERE id=?", ("in_progress", chat_id))

        db.commit()


        message_time = db.execute(
            "SELECT created_at FROM messages WHERE id=?", (message_id,)
        ).fetchone()

        db.close()


        socketio.emit(
            "new_message",
            {
                "id": message_id,
                "text": message_text or "",
                "sender_id": session["user_id"],
                "created_at": message_time["created_at"]
                if message_time
                else datetime.now().isoformat(),
                "attachment_type": file_type,
                "attachment_filename": unique_filename,
                "attachment_size": file_size,
                "formatted_size": format_file_size(file_size),
            },
            room=f"chat_{chat_id}",
        )

        return jsonify(
            {
                "success": True,
                "message_id": message_id,
                "filename": unique_filename,
                "file_type": file_type,
            }
        )

    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 500



@app.route("/chat/attachment/<filename>")
def download_chat_attachment(filename):
    if "user_id" not in session:
        return "Доступ запрещён", 403

    try:
        return send_from_directory(
            os.path.abspath(app.config["CHAT_ATTACHMENTS_FOLDER"]),
            filename,
            as_attachment=True,
        )
    except Exception as e:
        return f"Файл не найден: {str(e)}", 404



@app.route("/chat/attachment/view/<filename>")
def view_chat_attachment(filename):
    if "user_id" not in session:
        return "Доступ запрещён", 403

    try:
        return send_from_directory(
            os.path.abspath(app.config["CHAT_ATTACHMENTS_FOLDER"]),
            filename,
            as_attachment=False,
        )
    except Exception as e:
        return f"Файл не найден: {str(e)}", 404



@socketio.on("send_message")
def send_message(data):
    if "user_id" not in session:
        return

    chat_id = data["chat_id"]
    text = data["text"]
    sender_id = session["user_id"]
    sender_role = session.get("role")

    db = get_db()

    
    cursor = db.execute(
        "INSERT INTO messages (chat_id, sender_id, text) VALUES (?,?,?)",
        (chat_id, sender_id, text),
    )
    message_id = cursor.lastrowid

    chat_info = db.execute(
        "SELECT status, client_id FROM chats WHERE id=?", (chat_id,)
    ).fetchone()

  
    if (
        sender_role in ["admin", "staff"]
        and chat_info
        and chat_info["status"] == "waiting"
    ):
        db.execute("UPDATE chats SET status=? WHERE id=?", ("in_progress", chat_id))

    db.commit()


    message_time = db.execute(
        "SELECT created_at FROM messages WHERE id=?", (message_id,)
    ).fetchone()

    db.close()

    emit(
        "new_message",
        {
            "id": message_id,
            "text": text,
            "sender_id": sender_id,
            "created_at": message_time["created_at"]
            if message_time
            else datetime.now().isoformat(),
        },
        room=f"chat_{chat_id}",
        include_self=True,
    )








@app.route("/staff/profile")
def staff_profile():
    if "staff_member_id" not in session:
        flash("Требуется авторизация")
        return redirect("/login")

    db = get_db()

    member = db.execute(
        "SELECT * FROM team_members WHERE id=?", (session["staff_member_id"],)
    ).fetchone()

    if not member:
        db.close()
        flash("Участник не найден")
        return redirect("/logout")


    documents = []


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


    additional_docs = db.execute(
        "SELECT * FROM staff_documents WHERE member_id=? ORDER BY uploaded_at DESC",
        (session["staff_member_id"],),
    ).fetchall()

    for doc in additional_docs:
        documents.append(dict(doc))


    total_earned = member["total_earned"] if member["total_earned"] else 0

  
    recent_payments = db.execute(
        """
        SELECT amount, description, created_at 
        FROM staff_payments 
        WHERE member_id=? 
        ORDER BY created_at DESC 
        LIMIT 5
        """,
        (session["staff_member_id"],),
    ).fetchall()


    payment_count = db.execute(
        "SELECT COUNT(*) as count FROM staff_payments WHERE member_id=?",
        (session["staff_member_id"],),
    ).fetchone()["count"]

    db.close()

    return render_template(
        "staff_profile.html",
        member=dict(member),
        documents=documents,
        total_earned=total_earned,
        recent_payments=recent_payments,
        payment_count=payment_count,
    )



@app.route("/staff/payments")
def staff_payments():
    if "staff_member_id" not in session:
        flash("Требуется авторизация")
        return redirect("/login")

    db = get_db()


    member = db.execute(
        "SELECT first_name, last_name, total_earned FROM team_members WHERE id=?",
        (session["staff_member_id"],),
    ).fetchone()

    if not member:
        db.close()
        flash("Участник не найден")
        return redirect("/logout")


    payments = db.execute(
        """
        SELECT 
            sp.amount,
            sp.description,
            sp.created_at,
            u.username as admin_username
        FROM staff_payments sp
        JOIN users u ON u.id = sp.paid_by
        WHERE sp.member_id=?
        ORDER BY sp.created_at DESC
        """,
        (session["staff_member_id"],),
    ).fetchall()


    total_earned = member["total_earned"] if member["total_earned"] else 0
    total_payments = len(payments)
    average_payment = total_earned / total_payments if total_payments > 0 else 0

    db.close()

    return render_template(
        "staff_payments.html",
        member=dict(member),
        payments=payments,
        total_earned=total_earned,
        total_payments=total_payments,
        average_payment=average_payment,
    )




@app.route("/admin/payments/staff")
def admin_staff_payments_history():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён. Требуются права администратора.")
        return redirect("/login")

    db = get_db()


    payments = db.execute(
        """
        SELECT 
            sp.id,
            sp.amount,
            sp.description,
            sp.created_at,
            tm.first_name,
            tm.last_name,
            tm.position,
            tm.id as member_id,
            u.username as admin_username
        FROM staff_payments sp
        JOIN team_members tm ON tm.id = sp.member_id
        JOIN users u ON u.id = sp.paid_by
        ORDER BY sp.created_at DESC
        """
    ).fetchall()


    stats = db.execute(
        """
        SELECT 
            COUNT(*) as total_payments,
            SUM(amount) as total_amount,
            AVG(amount) as average_amount
        FROM staff_payments
        """
    ).fetchone()

    
    top_earners = db.execute(
        """
        SELECT 
            tm.first_name,
            tm.last_name,
            tm.position,
            tm.total_earned,
            tm.id
        FROM team_members tm
        WHERE tm.status = 'approved' AND tm.total_earned > 0
        ORDER BY tm.total_earned DESC
        LIMIT 5
        """
    ).fetchall()

 
    staff_members = db.execute(
        """
        SELECT 
            id, 
            first_name, 
            last_name, 
            position, 
            username,
            email,
            status,
            total_earned,
            created_at
        FROM team_members
        ORDER BY 
            CASE status
                WHEN 'approved' THEN 1
                WHEN 'pending' THEN 2
                WHEN 'rejected' THEN 3
            END,
            first_name, 
            last_name
        """
    ).fetchall()

    db.close()

    return render_template(
        "admin_staff_payments.html",
        payments=payments,
        stats=dict(stats) if stats else {},
        top_earners=top_earners,
        staff_members=staff_members,
    )



@app.route("/admin/staff/<int:member_id>/pay", methods=["GET", "POST"])
def admin_pay_staff(member_id):
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён")
        return redirect("/login")

    db = get_db()

    member = db.execute(
        "SELECT * FROM team_members WHERE id=?", (member_id,)
    ).fetchone()

    if not member:
        db.close()
        flash("Сотрудник не найден")
        return redirect("/admin/team")

    if request.method == "POST":
        amount = request.form.get("amount")
        description = request.form.get("description", "").strip()

        if not amount:
            flash("Укажите сумму")
            db.close()
            return redirect(f"/admin/staff/{member_id}/pay")

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError("Сумма должна быть больше нуля")
        except ValueError as e:
            flash(f"Некорректная сумма: {str(e)}")
            db.close()
            return redirect(f"/admin/staff/{member_id}/pay")

        try:

            db.execute(
                """
                INSERT INTO staff_payments (member_id, amount, description, paid_by)
                VALUES (?, ?, ?, ?)
                """,
                (member_id, amount, description, session["user_id"]),
            )

            db.execute(
                """
                UPDATE team_members 
                SET total_earned = COALESCE(total_earned, 0) + ?
                WHERE id = ?
                """,
                (amount, member_id),
            )

            db.commit()
            flash(
                f"✅ Успешно зачислено ${amount:.2f} для {member['first_name']} {member['last_name']}"
            )

            db.close()
            return redirect("/admin/payments/staff")

        except Exception as e:
            db.close()
            flash(f"Ошибка при зачислении: {str(e)}")
            return redirect(f"/admin/staff/{member_id}/pay")


    payment_history = db.execute(
        """
        SELECT amount, description, created_at, u.username as admin_username
        FROM staff_payments sp
        JOIN users u ON u.id = sp.paid_by
        WHERE sp.member_id = ?
        ORDER BY sp.created_at DESC
        LIMIT 10
        """,
        (member_id,),
    ).fetchall()

    db.close()

    return render_template(
        "admin_pay_staff.html", member=dict(member), payment_history=payment_history
    )



@app.route("/api/admin/staff/pay", methods=["POST"])
def api_pay_staff():
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json()
    member_id = data.get("member_id")
    amount = data.get("amount")
    description = data.get("description", "").strip()

    if not member_id or not amount:
        return jsonify({"error": "Missing data"}), 400

    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        return jsonify({"error": "Invalid amount"}), 400

    db = get_db()


    member = db.execute(
        "SELECT first_name, last_name FROM team_members WHERE id=? AND status='approved'",
        (member_id,),
    ).fetchone()

    if not member:
        db.close()
        return jsonify({"error": "Staff member not found"}), 404

    try:

        db.execute(
            """
            INSERT INTO staff_payments (member_id, amount, description, paid_by)
            VALUES (?, ?, ?, ?)
            """,
            (member_id, amount, description, session["user_id"]),
        )



        db.execute(
            """
            UPDATE team_members 
            SET total_earned = COALESCE(total_earned, 0) + ?
            WHERE id = ?
            """,
            (amount, member_id),
        )

        db.commit()



        updated_member = db.execute(
            "SELECT total_earned FROM team_members WHERE id=?", (member_id,)
        ).fetchone()

        db.close()

        return jsonify(

            {
                "success": True,
                "message": f"Зачислено ${amount:.2f} для {member['first_name']} {member['last_name']}",
                "total_earned": updated_member["total_earned"],
            }
        )

    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 500




@app.route("/admin/team", methods=["GET"])
def admin_team():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён. Требуются права администратора.")
        return redirect("/login")

    db = get_db()
    team_members = db.execute(
        """
        SELECT id, first_name, last_name, position, username, email, status, 
               contract_filename, created_at, total_earned
        FROM team_members
        ORDER BY 
            CASE status
                WHEN 'pending' THEN 1
                WHEN 'approved' THEN 2
                WHEN 'rejected' THEN 3
            END,
            created_at DESC
    """
    ).fetchall()
    db.close()

    return render_template("admin_team.html", team_members=team_members)




@app.route("/admin/all_documents")
def admin_all_documents():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён. Требуются права администратора.")
        return redirect("/login")

    db = get_db()



    members = db.execute(
        """
        SELECT * FROM team_members 
        ORDER BY 
            CASE status
                WHEN 'pending' THEN 1
                WHEN 'approved' THEN 2
                WHEN 'rejected' THEN 3
            END,
            created_at DESC
    """
    ).fetchall()

    members_with_docs = []
    total_documents = 0
    total_contracts = 0
    total_additional = 0

    for member in members:
        member_dict = dict(member)
        documents = []



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




@app.route("/admin/payment/delete/<int:payment_id>", methods=["POST"])
def admin_delete_payment(payment_id):
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403

    db = get_db()

    
    
    payment = db.execute(
        "SELECT member_id, amount FROM staff_payments WHERE id=?", (payment_id,)
    ).fetchone()

    if not payment:
        db.close()
        return jsonify({"error": "Payment not found"}), 404

    try:
       

        db.execute("DELETE FROM staff_payments WHERE id=?", (payment_id,))

        
        
        db.execute(
            """
            UPDATE team_members 
            SET total_earned = COALESCE(total_earned, 0) - ?
            WHERE id = ?
            """,
            (payment["amount"], payment["member_id"]),
        )

        db.commit()
        db.close()

        flash("✅ Запись о зачислении удалена")
        return redirect("/admin/payments/staff")

    except Exception as e:
        db.close()
        flash(f"❌ Ошибка при удалении: {str(e)}")
        return redirect("/admin/payments/staff")




# Добавить в app.py после инициализации других UPLOAD_FOLDER'ов:

COMPANY_ARCHIVE_FOLDER = "uploads/company_archive"
app.config["COMPANY_ARCHIVE_FOLDER"] = COMPANY_ARCHIVE_FOLDER
os.makedirs(COMPANY_ARCHIVE_FOLDER, exist_ok=True)

# Категории документов архива
ARCHIVE_CATEGORIES = [
    "Устав и правила",
    "Финансовые документы",
    "Договоры",
    "Отчёты",
    "Процедуры",
    "Политики",
    "Другое",
]


# ==================== АРХИВ КОМПАНИИ ====================


@app.route("/admin/archive")
def admin_archive():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён")
        return redirect("/login")

    db = get_db()

    category_filter = request.args.get("category", "")

    if category_filter:
        documents = db.execute(
            """
            SELECT 
                ca.*,
                users.username as uploader_name
            FROM company_archive ca
            JOIN users ON users.id = ca.uploaded_by
            WHERE ca.category = ? AND ca.is_public = 1
            ORDER BY ca.created_at DESC
        """,
            (category_filter,),
        ).fetchall()
    else:
        documents = db.execute("""
            SELECT 
                ca.*,
                users.username as uploader_name
            FROM company_archive ca
            JOIN users ON users.id = ca.uploaded_by
            WHERE ca.is_public = 1
            ORDER BY ca.created_at DESC
        """).fetchall()

    # Статистика
    stats = db.execute("""
        SELECT 
            COUNT(*) as total_docs,
            COUNT(DISTINCT category) as total_categories,
            SUM(file_size) as total_size
        FROM company_archive
        WHERE is_public = 1
    """).fetchone()

    db.close()

    return render_template(
        "admin_archive.html",
        documents=documents,
        categories=ARCHIVE_CATEGORIES,
        selected_category=category_filter,
        stats=dict(stats) if stats else {},
    )


@app.route("/admin/archive/upload", methods=["POST"])
def archive_upload_document():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён")
        return redirect("/login")

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "").strip()

    if not title or not category:
        flash("Заполните название и категорию")
        return redirect("/admin/archive")

    if category not in ARCHIVE_CATEGORIES:
        flash("Невалидная категория")
        return redirect("/admin/archive")

    if "file" not in request.files:
        flash("Файл не выбран")
        return redirect("/admin/archive")

    file = request.files["file"]

    if file.filename == "":
        flash("Файл не выбран")
        return redirect("/admin/archive")

    if not allowed_file(file.filename):
        flash("Недопустимый формат файла")
        return redirect("/admin/archive")

    try:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{session['user_id']}_{filename}"
        filepath = os.path.join(app.config["COMPANY_ARCHIVE_FOLDER"], unique_filename)

        file.save(filepath)
        file_size = os.path.getsize(filepath)
        file_ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""

        db = get_db()
        db.execute(
            """
            INSERT INTO company_archive 
            (title, description, category, filename, file_type, file_size, uploaded_by, is_public)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """,
            (
                title,
                description,
                category,
                unique_filename,
                file_ext,
                file_size,
                session["user_id"],
            ),
        )

        db.commit()
        db.close()

        flash("✅ Документ успешно добавлен в архив!")
        return redirect("/admin/archive")

    except Exception as e:
        flash(f"Ошибка при загрузке: {str(e)}")
        return redirect("/admin/archive")


@app.route("/admin/archive/download/<int:doc_id>")
def archive_download_document(doc_id):
    if "user_id" not in session or session.get("role") != "admin":
        return "Доступ запрещён", 403

    db = get_db()
    document = db.execute(
        "SELECT * FROM company_archive WHERE id = ?", (doc_id,)
    ).fetchone()
    db.close()

    if not document:
        flash("Документ не найден")
        return redirect("/admin/archive")

    try:
        return send_from_directory(
            os.path.abspath(app.config["COMPANY_ARCHIVE_FOLDER"]),
            document["filename"],
            as_attachment=True,
        )
    except Exception as e:
        flash(f"Ошибка при скачивании: {str(e)}")
        return redirect("/admin/archive")


@app.route("/admin/archive/view/<int:doc_id>")
def archive_view_document(doc_id):
    if "user_id" not in session or session.get("role") != "admin":
        return "Доступ запрещён", 403

    db = get_db()
    document = db.execute(
        "SELECT * FROM company_archive WHERE id = ?", (doc_id,)
    ).fetchone()
    db.close()

    if not document:
        flash("Документ не найден")
        return redirect("/admin/archive")

    try:
        return send_from_directory(
            os.path.abspath(app.config["COMPANY_ARCHIVE_FOLDER"]),
            document["filename"],
            as_attachment=False,
        )
    except Exception as e:
        flash(f"Ошибка при открытии: {str(e)}")
        return redirect("/admin/archive")


@app.route("/admin/archive/delete/<int:doc_id>", methods=["POST"])
def archive_delete_document(doc_id):
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён")
        return redirect("/login")

    db = get_db()
    document = db.execute(
        "SELECT * FROM company_archive WHERE id = ?", (doc_id,)
    ).fetchone()

    if not document:
        db.close()
        flash("Документ не найден")
        return redirect("/admin/archive")

    try:
        # Удаляем файл
        filepath = os.path.join(
            app.config["COMPANY_ARCHIVE_FOLDER"], document["filename"]
        )
        if os.path.exists(filepath):
            os.remove(filepath)

        # Удаляем из БД
        db.execute("DELETE FROM company_archive WHERE id = ?", (doc_id,))
        db.commit()
        db.close()

        flash("✅ Документ удален из архива")
        return redirect("/admin/archive")

    except Exception as e:
        db.close()
        flash(f"Ошибка при удалении: {str(e)}")
        return redirect("/admin/archive")


@app.route("/admin/archive/edit/<int:doc_id>", methods=["POST"])
def archive_edit_document(doc_id):
    if "user_id" not in session or session.get("role") != "admin":
        flash("Доступ запрещён")
        return redirect("/login")

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "").strip()

    if not title or not category:
        flash("Заполните все поля")
        return redirect("/admin/archive")

    if category not in ARCHIVE_CATEGORIES:
        flash("Невалидная категория")
        return redirect("/admin/archive")

    db = get_db()

    try:
        db.execute(
            """
            UPDATE company_archive 
            SET title = ?, description = ?, category = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (title, description, category, doc_id),
        )

        db.commit()
        db.close()

        flash("✅ Документ обновлен")
    except Exception as e:
        db.close()
        flash(f"Ошибка: {str(e)}")

    return redirect("/admin/archive")


@app.route("/api/archive/stats")
def archive_stats():
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403

    db = get_db()

    total_size = (
        db.execute(
            "SELECT SUM(file_size) as size FROM company_archive WHERE is_public = 1"
        ).fetchone()["size"]
        or 0
    )

    by_category = db.execute("""
        SELECT category, COUNT(*) as count
        FROM company_archive
        WHERE is_public = 1
        GROUP BY category
        ORDER BY count DESC
    """).fetchall()

    stats = {
        "total_documents": db.execute(
            "SELECT COUNT(*) as count FROM company_archive WHERE is_public = 1"
        ).fetchone()["count"],
        "total_size": total_size,
        "by_category": [dict(cat) for cat in by_category],
    }

    db.close()
    return jsonify(stats)











# ==================== ДОБАВИТЬ В app.py ====================

# ВАЖНО: Добавить ВСЕ эти роуты в app.py


# ==================== ПРОСМОТР PDF В БРАУЗЕРЕ ====================


@app.route("/staff/document/preview/<doc_id>")
def staff_preview_document(doc_id):
    """Просмотр документа в браузере (встроенный просмотр)"""
    if "staff_member_id" not in session:
        return "Доступ запрещён", 403

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


# ==================== АРХИВ: ПРОСМОТР ФАЙЛОВ ====================


@app.route("/admin/archive/preview/<int:doc_id>")
def archive_preview_document(doc_id):
    """Просмотр архивного документа в браузере"""
    if "user_id" not in session or session.get("role") != "admin":
        return "Доступ запрещён", 403

    db = get_db()
    document = db.execute(
        "SELECT * FROM company_archive WHERE id = ?", (doc_id,)
    ).fetchone()
    db.close()

    if not document:
        return "Файл не найден", 404

    return send_from_directory(
        os.path.abspath(app.config["COMPANY_ARCHIVE_FOLDER"]),
        document["filename"],
        as_attachment=False,
    )


# ==================== ЧАТЫ: ПРОСМОТР ВЛОЖЕНИЙ ====================


@app.route("/chat/attachment/preview/<filename>")
def preview_chat_attachment(filename):
    """Просмотр вложения чата в браузере"""
    if "user_id" not in session:
        return "Доступ запрещён", 403

    try:
        return send_from_directory(
            os.path.abspath(app.config["CHAT_ATTACHMENTS_FOLDER"]),
            filename,
            as_attachment=False,
        )
    except Exception as e:
        return f"Файл не найден: {str(e)}", 404


# ==================== УНИВЕРСАЛЬНЫЙ ПРОСМОТР С IFRAME ====================


@app.route("/preview/file/<path:filename>")
def preview_file(filename):
    """
    Универсальный просмотр файла (подходит для PDF, изображений, видео)
    Использует встроенные возможности браузера
    """
    if "user_id" not in session:
        return "Доступ запрещён", 403

    folder = request.args.get("folder", "chat_attachments")

    valid_folders = {
        "chat_attachments": CHAT_ATTACHMENTS_FOLDER,
        "staff_documents": STAFF_DOCUMENTS_FOLDER,
        "contracts": UPLOAD_FOLDER,
        "company_archive": COMPANY_ARCHIVE_FOLDER,
    }

    if folder not in valid_folders:
        return "Невалидная папка", 403

    folder_path = valid_folders[folder]

    try:
        return send_from_directory(
            os.path.abspath(folder_path),
            filename,
            as_attachment=False,
        )
    except Exception as e:
        return f"Файл не найден: {str(e)}", 404




TRANSLATIONS = {
    "uk": {  # Украинский (по умолчанию)
        "welcome_title": "ARKONIX — створюємо цифрові рішення, які приносять результат",
        "welcome_subtitle": "Ми розробляємо ботів, AI-системи, веб-додатки та сайти, які автоматизують бізнес, скорочують витрати та прискорюють зростання.",
        "welcome_tagline": "Не просто код — продумані технології під реальні завдання.",
        "about_title": "Про нас",
        "services": "Послуги",
        "team": "Команда",
        "discussions": "Обговорення",
        "login": "Вхід",
        "register": "Реєстрація",
        "logout": "Вихід",
        "profile": "Особистий кабінет",
        "admin_panel": "Адмін-панель",
        "reviews_title": "Відгуки клієнтів",
        "leave_review": "Залишити відгук",
        "achievements_title": "Наші досягнення",
        "telegram_bots": "Telegram-ботів",
        "ai_solutions": "AI-рішень",
        "applications": "Додатків",
        "websites": "Сайтів",
        "contacts": "Контакти",
        "social_networks": "Соцмережі",
        "terms": "Умови використання",
        "privacy": "Політика та правила",
        "rights_reserved": "Всі права захищені",
        "main": "Головна",
        "no_reviews": "Поки відгуків немає.",
        "name": "Ім'я",
        "rating": "Оцінка",
        "select_rating": "⭐ Оберіть оцінку",
        "excellent": "⭐⭐⭐⭐⭐ Відмінно!",
        "good": "⭐⭐⭐⭐ Добре",
        "normal": "⭐⭐⭐ Нормально",
        "bad": "⭐⭐ Погано",
        "terrible": "⭐ Жахливо",
        "your_review": "Ваш відгук",
        "submit": "Відправити",
    },
    "ru": {  # Русский
        "welcome_title": "ARKONIX — создаём цифровые решения, которые приносят результат",
        "welcome_subtitle": "Мы разрабатываем ботов, AI-системы, веб-приложения и сайты, которые автоматизируют бизнес, сокращают издержки и ускоряют рост.",
        "welcome_tagline": "Не просто код — продуманные технологии под реальные задачи.",
        "about_title": "О нас",
        "services": "Услуги",
        "team": "Команда",
        "discussions": "Обсуждения",
        "login": "Вход",
        "register": "Регистрация",
        "logout": "Выход",
        "profile": "Личный кабинет",
        "admin_panel": "Админ-панель",
        "reviews_title": "Отзывы клиентов",
        "leave_review": "Оставить отзыв",
        "achievements_title": "Наши достижения",
        "telegram_bots": "Telegram-ботов",
        "ai_solutions": "AI-решений",
        "applications": "Приложений",
        "websites": "Сайтов",
        "contacts": "Контакты",
        "social_networks": "Соцсети",
        "terms": "Условия использования",
        "privacy": "Политика и правила",
        "rights_reserved": "Все права защищены",
        "main": "Главная",
        "no_reviews": "Пока отзывов нет.",
        "name": "Имя",
        "rating": "Оценка",
        "select_rating": "⭐ Выберите оценку",
        "excellent": "⭐⭐⭐⭐⭐ Отлично!",
        "good": "⭐⭐⭐⭐ Хорошо",
        "normal": "⭐⭐⭐ Нормально",
        "bad": "⭐⭐ Плохо",
        "terrible": "⭐ Ужасно",
        "your_review": "Ваш отзыв",
        "submit": "Отправить",
    },
    "en": {  # English
        "welcome_title": "ARKONIX — creating digital solutions that deliver results",
        "welcome_subtitle": "We develop bots, AI systems, web applications and websites that automate business, reduce costs and accelerate growth.",
        "welcome_tagline": "Not just code — thoughtful technologies for real tasks.",
        "about_title": "About us",
        "services": "Services",
        "team": "Team",
        "discussions": "Discussions",
        "login": "Login",
        "register": "Register",
        "logout": "Logout",
        "profile": "Profile",
        "admin_panel": "Admin Panel",
        "reviews_title": "Client Reviews",
        "leave_review": "Leave a Review",
        "achievements_title": "Our Achievements",
        "telegram_bots": "Telegram Bots",
        "ai_solutions": "AI Solutions",
        "applications": "Applications",
        "websites": "Websites",
        "contacts": "Contacts",
        "social_networks": "Social Networks",
        "terms": "Terms of Use",
        "privacy": "Privacy Policy",
        "rights_reserved": "All rights reserved",
        "main": "Home",
        "no_reviews": "No reviews yet.",
        "name": "Name",
        "rating": "Rating",
        "select_rating": "⭐ Select rating",
        "excellent": "⭐⭐⭐⭐⭐ Excellent!",
        "good": "⭐⭐⭐⭐ Good",
        "normal": "⭐⭐⭐ Normal",
        "bad": "⭐⭐ Bad",
        "terrible": "⭐ Terrible",
        "your_review": "Your review",
        "submit": "Submit",
    },
    "de": {  # Deutsch (Немецкий)
        "welcome_title": "ARKONIX — wir schaffen digitale Lösungen, die Ergebnisse liefern",
        "welcome_subtitle": "Wir entwickeln Bots, KI-Systeme, Webanwendungen und Websites, die Geschäftsprozesse automatisieren, Kosten senken und Wachstum beschleunigen.",
        "welcome_tagline": "Nicht nur Code — durchdachte Technologien für echte Aufgaben.",
        "about_title": "Über uns",
        "services": "Dienstleistungen",
        "team": "Team",
        "discussions": "Diskussionen",
        "login": "Anmelden",
        "register": "Registrieren",
        "logout": "Abmelden",
        "profile": "Profil",
        "admin_panel": "Admin-Panel",
        "reviews_title": "Kundenbewertungen",
        "leave_review": "Bewertung hinterlassen",
        "achievements_title": "Unsere Erfolge",
        "telegram_bots": "Telegram-Bots",
        "ai_solutions": "KI-Lösungen",
        "applications": "Anwendungen",
        "websites": "Websites",
        "contacts": "Kontakte",
        "social_networks": "Soziale Netzwerke",
        "terms": "Nutzungsbedingungen",
        "privacy": "Datenschutzrichtlinie",
        "rights_reserved": "Alle Rechte vorbehalten",
        "main": "Startseite",
        "no_reviews": "Noch keine Bewertungen.",
        "name": "Name",
        "rating": "Bewertung",
        "select_rating": "⭐ Bewertung wählen",
        "excellent": "⭐⭐⭐⭐⭐ Ausgezeichnet!",
        "good": "⭐⭐⭐⭐ Gut",
        "normal": "⭐⭐⭐ Normal",
        "bad": "⭐⭐ Schlecht",
        "terrible": "⭐ Schrecklich",
        "your_review": "Ihre Bewertung",
        "submit": "Senden",
    },
    "it": {  # Italiano
        "welcome_title": "ARKONIX — creiamo soluzioni digitali che portano risultati",
        "welcome_subtitle": "Sviluppiamo bot, sistemi AI, applicazioni web e siti che automatizzano il business, riducono i costi e accelerano la crescita.",
        "welcome_tagline": "Non solo codice — tecnologie pensate per compiti reali.",
        "about_title": "Chi siamo",
        "services": "Servizi",
        "team": "Team",
        "discussions": "Discussioni",
        "login": "Accedi",
        "register": "Registrati",
        "logout": "Esci",
        "profile": "Profilo",
        "admin_panel": "Pannello Admin",
        "reviews_title": "Recensioni dei clienti",
        "leave_review": "Lascia una recensione",
        "achievements_title": "I nostri risultati",
        "telegram_bots": "Bot Telegram",
        "ai_solutions": "Soluzioni AI",
        "applications": "Applicazioni",
        "websites": "Siti web",
        "contacts": "Contatti",
        "social_networks": "Social Network",
        "terms": "Termini di utilizzo",
        "privacy": "Privacy Policy",
        "rights_reserved": "Tutti i diritti riservati",
        "main": "Home",
        "no_reviews": "Nessuna recensione ancora.",
        "name": "Nome",
        "rating": "Valutazione",
        "select_rating": "⭐ Seleziona valutazione",
        "excellent": "⭐⭐⭐⭐⭐ Eccellente!",
        "good": "⭐⭐⭐⭐ Buono",
        "normal": "⭐⭐⭐ Normale",
        "bad": "⭐⭐ Cattivo",
        "terrible": "⭐ Terribile",
        "your_review": "La tua recensione",
        "submit": "Invia",
    },
    "fr": {  # Français
        "welcome_title": "ARKONIX — créons des solutions numériques qui donnent des résultats",
        "welcome_subtitle": "Nous développons des bots, des systèmes IA, des applications web et des sites qui automatisent les affaires, réduisent les coûts et accélèrent la croissance.",
        "welcome_tagline": "Pas seulement du code — des technologies réfléchies pour des tâches réelles.",
        "about_title": "À propos de nous",
        "services": "Services",
        "team": "Équipe",
        "discussions": "Discussions",
        "login": "Connexion",
        "register": "Inscription",
        "logout": "Déconnexion",
        "profile": "Profil",
        "admin_panel": "Panneau Admin",
        "reviews_title": "Avis des clients",
        "leave_review": "Laisser un avis",
        "achievements_title": "Nos réalisations",
        "telegram_bots": "Bots Telegram",
        "ai_solutions": "Solutions IA",
        "applications": "Applications",
        "websites": "Sites web",
        "contacts": "Contacts",
        "social_networks": "Réseaux sociaux",
        "terms": "Conditions d'utilisation",
        "privacy": "Politique de confidentialité",
        "rights_reserved": "Tous droits réservés",
        "main": "Accueil",
        "no_reviews": "Pas encore d'avis.",
        "name": "Nom",
        "rating": "Évaluation",
        "select_rating": "⭐ Sélectionner l'évaluation",
        "excellent": "⭐⭐⭐⭐⭐ Excellent!",
        "good": "⭐⭐⭐⭐ Bien",
        "normal": "⭐⭐⭐ Normal",
        "bad": "⭐⭐ Mauvais",
        "terrible": "⭐ Terrible",
        "your_review": "Votre avis",
        "submit": "Envoyer",
    },
    "zh": {  # 中文
        "welcome_title": "ARKONIX — 创造带来成果的数字解决方案",
        "welcome_subtitle": "我们开发机器人、AI系统、网络应用程序和网站，自动化业务、降低成本并加速增长。",
        "welcome_tagline": "不仅仅是代码 — 针对实际任务的周到技术。",
        "about_title": "关于我们",
        "services": "服务",
        "team": "团队",
        "discussions": "讨论",
        "login": "登录",
        "register": "注册",
        "logout": "退出",
        "profile": "个人资料",
        "admin_panel": "管理面板",
        "reviews_title": "客户评价",
        "leave_review": "留下评价",
        "achievements_title": "我们的成就",
        "telegram_bots": "Telegram机器人",
        "ai_solutions": "AI解决方案",
        "applications": "应用程序",
        "websites": "网站",
        "contacts": "联系方式",
        "social_networks": "社交网络",
        "terms": "使用条款",
        "privacy": "隐私政策",
        "rights_reserved": "版权所有",
        "main": "主页",
        "no_reviews": "暂无评价。",
        "name": "姓名",
        "rating": "评分",
        "select_rating": "⭐ 选择评分",
        "excellent": "⭐⭐⭐⭐⭐ 优秀！",
        "good": "⭐⭐⭐⭐ 好",
        "normal": "⭐⭐⭐ 一般",
        "bad": "⭐⭐ 差",
        "terrible": "⭐ 很差",
        "your_review": "您的评价",
        "submit": "提交",
    },
}


# Функция для получения переводов
def get_translation(key, lang=None):
    """Получить перевод по ключу"""
    if lang is None:
        lang = session.get("language", "uk")

    if lang not in TRANSLATIONS:
        lang = "uk"

    return TRANSLATIONS[lang].get(key, TRANSLATIONS["uk"].get(key, key))


# Функция для получения всех переводов для текущего языка
def get_all_translations():
    """Получить все переводы для текущего языка"""
    lang = session.get("language", "uk")
    if lang not in TRANSLATIONS:
        lang = "uk"
    return TRANSLATIONS[lang]


# Регистрируем функцию в Jinja2
app.jinja_env.globals.update(t=get_translation, translations=get_all_translations)


# Роут для смены языка
@app.route("/set_language/<lang>")
def set_language(lang):
    """Установить язык интерфейса"""
    if lang in TRANSLATIONS:
        session["language"] = lang
        flash(f"✅ Язык изменён на {lang.upper()}")
    else:
        flash("❌ Неподдерживаемый язык")

    # Возвращаемся на предыдущую страницу или на главную
    referrer = request.referrer
    if referrer:
        return redirect(referrer)
    return redirect("/")


@app.before_request
def set_default_language():
    """Установить украинский язык по умолчанию, если не выбран"""
    if "language" not in session:
        session["language"] = "uk"


@app.route("/offer")
def offer():
    return render_template("offer.html")






















if __name__ == "__main__":
    socketio.run(app, port=5001, debug=True)
