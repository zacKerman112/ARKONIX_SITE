from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,
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
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "jpg", "jpeg", "png"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max


os.makedirs(UPLOAD_FOLDER, exist_ok=True)


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

            
                db.execute(
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

                db.commit()
                db.close()

                flash(
                    "Заявка на регистрацию успешно отправлена! Ожидайте одобрения администратора."
                )
                return redirect("/login")

            except Exception as e:
                db.close()
                flash(f"Ошибка при регистрации: {str(e)}")
                return redirect("/staff/register")
        else:
            flash("Недопустимый формат файла. Разрешены: PDF, DOC, DOCX, JPG, PNG")
            return redirect("/staff/register")

    return render_template("auth/staff_register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = get_db()
        user = db.execute(
            "SELECT id, username, role FROM users WHERE username=? AND password=?",
            (request.form["username"], request.form["password"]),
        ).fetchone()
        db.close()

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]


            if user["role"] == "admin":
                return redirect("/profile")
            else:
                return redirect("/")
        else:
            flash("Неверные данные")
            return redirect("/login")

    return render_template("auth/login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


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
        db.close()
        return render_template("admin_board.html", chats=chats)

 
    chats = db.execute(
        "SELECT id, service_name, status FROM chats WHERE client_id=?",
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
    )


@socketio.on("join")
def join(data):
    join_room(f"chat_{data['chat_id']}")


@socketio.on("send_message")
def send_message(data):
    if "user_id" not in session:
        return

    chat_id = data["chat_id"]
    text = data["text"]
    sender_id = session["user_id"]
    sender_role = session.get("role")

    db = get_db()

    db.execute(
        "INSERT INTO messages (chat_id, sender_id, text) VALUES (?,?,?)",
        (chat_id, sender_id, text),
    )

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
    db.close()

    emit(
        "new_message",
        {"text": text, "sender_id": sender_id},
        room=f"chat_{chat_id}",
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

    # Отладочная информация
    upload_dir = os.path.abspath(UPLOAD_FOLDER)
    print(f"\n{'=' * 50}")
    print(f"📁 Папка с файлами: {upload_dir}")
    print(f"📁 Существует: {os.path.exists(upload_dir)}")
    if os.path.exists(upload_dir):
        files = os.listdir(upload_dir)
        print(f"📄 Файлов в папке: {len(files)}")
        for f in files:
            print(f"  - {f}")
    print(f"{'=' * 50}\n")

    return render_template("admin_team.html", team_members=team_members)


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

        # Обновляем статус в team_members
        db.execute("UPDATE team_members SET status='approved' WHERE id=?", (member_id,))

        db.commit()
        flash(f"Участник {member['first_name']} {member['last_name']} успешно одобрен!")
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

        # Отправляем файл из абсолютного пути
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


if __name__ == "__main__":
    socketio.run(app, port=5001, debug=True)
