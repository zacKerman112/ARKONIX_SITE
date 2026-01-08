from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit, join_room
import sqlite3

app = Flask(__name__)
app.secret_key = "super_secret_arkonix_key"
socketio = SocketIO(app, cors_allowed_origins="*")


# ---------- DB ----------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


# ---------- Главная ----------
@app.route("/")
def main():
    db = get_db()
    reviews = db.execute(
        "SELECT user_name, rating, text, created_at FROM reviews ORDER BY id DESC"
    ).fetchall()
    db.close()
    return render_template("index.html", reviews=reviews)


# ---------- Добавить отзыв ----------
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


# ---------- РЕГИСТРАЦИЯ ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password, role) VALUES (?,?,?)",
                (username, password, "client"),
            )
            db.commit()

            # Получаем id нового пользователя
            user_id = db.execute(
                "SELECT id FROM users WHERE username=?", (username,)
            ).fetchone()["id"]
            db.close()

            # Сразу логиним пользователя
            session["user_id"] = user_id
            session["role"] = "client"

            # ПЕРЕНАПРАВЛЕНИЕ НА ГЛАВНУЮ
            return redirect("/")

        except sqlite3.IntegrityError:
            db.close()
            flash("Пользователь уже существует")
            return redirect("/register")

    return render_template("auth/register.html")


# ---------- ЛОГИН ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = get_db()
        user = db.execute(
            "SELECT id, role FROM users WHERE username=? AND password=?",
            (request.form["username"], request.form["password"]),
        ).fetchone()
        db.close()

        if user:
            session["user_id"] = user["id"]
            session["role"] = user["role"]

            # ПЕРЕНАПРАВЛЕНИЕ ПОСЛЕ УСПЕШНОГО ЛОГИНА
            if user["role"] in ["admin", "staff"]:
                return redirect("/profile")  # админ/сотрудник → профиль
            else:
                return redirect("/")  # клиент → главная
        else:
            flash("Неверные данные")
            return redirect("/login")

    return render_template("auth/login.html")


# ---------- ВЫХОД ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------- ПРОФИЛИ ----------
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()

    # ---------- ADMIN / STAFF ----------
    if session["role"] in ["admin", "staff"]:
        # Получаем все чаты с информацией о клиентах
        chats = db.execute("""
            SELECT 
                chats.id, 
                users.username, 
                chats.service_name, 
                chats.status,
                chats.created_at,
                (SELECT COUNT(*) FROM messages WHERE chat_id = chats.id) as message_count,
                (SELECT text FROM messages WHERE chat_id = chats.id ORDER BY id DESC LIMIT 1) as last_message
            FROM chats
            JOIN users ON users.id = chats.client_id
            ORDER BY chats.id DESC
        """).fetchall()
        db.close()
        return render_template("admin_board.html", chats=chats)

    # ---------- CLIENT ----------
    chats = db.execute(
        "SELECT id, service_name, status FROM chats WHERE client_id=?",
        (session["user_id"],),
    ).fetchall()
    db.close()
    return render_template("profile.html", chats=chats)


# ---------- СОЗДАНИЕ ЧАТА ----------
@app.route("/create_chat", methods=["POST"])
def create_chat():
    if session.get("role") != "client":
        return redirect("/login")

    service = request.form["service"]
    description = request.form.get("description", "")

    db = get_db()

    # Создаем чат
    cursor = db.execute(
        "INSERT INTO chats (client_id, service_name, status) VALUES (?,?,?)",
        (session["user_id"], service, "waiting"),
    )
    chat_id = cursor.lastrowid

    # Добавляем первое сообщение с описанием проекта
    if description:
        db.execute(
            "INSERT INTO messages (chat_id, sender_id, text) VALUES (?,?,?)",
            (chat_id, session["user_id"], description),
        )

    db.commit()
    db.close()

    # Перенаправляем сразу в чат
    return redirect(f"/chat/{chat_id}")


# ---------- ЧАТ ----------
@app.route("/chat/<int:chat_id>")
def chat(chat_id):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()

    chat_info = db.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()

    # Проверка доступа к чату
    if not chat_info:
        db.close()
        return "Чат не найден", 404

    # Проверка прав: клиент может видеть только свои чаты, admin/staff - все
    if session["role"] == "client" and chat_info["client_id"] != session["user_id"]:
        db.close()
        return "Доступ запрещен", 403

    messages = db.execute(
        "SELECT text, sender_id FROM messages WHERE chat_id=? ORDER BY id", (chat_id,)
    ).fetchall()

    db.close()

    return render_template(
        "chat.html", chat_id=chat_id, messages=messages, user_id=session["user_id"]
    )


# ---------- SOCKET.IO ----------
@socketio.on("join")
def join(data):
    join_room(f"chat_{data['chat_id']}")


@socketio.on("send_message")
def send_message(data):
    if "user_id" not in session:
        return

    chat_id = data["chat_id"]
    text = data["text"]

    db = get_db()
    db.execute(
        "INSERT INTO messages (chat_id, sender_id, text) VALUES (?,?,?)",
        (chat_id, session["user_id"], text),
    )
    db.commit()
    db.close()

    emit(
        "new_message",
        {"text": text, "sender_id": session["user_id"]},
        room=f"chat_{chat_id}",
    )


# ---------- ОБСУЖДЕНИЯ ----------
@app.route("/discussions")
def discussions():
    if "user_id" not in session:
        return redirect("/login")

    # Только для клиентов
    if session["role"] != "client":
        return redirect("/profile")

    return render_template("discussions.html")


# ---------- STATIC ----------
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
# Добавь эти роуты после роута add_review в твой app.py:


# ---------- Удалить отзыв (только для админа) ----------
@app.route("/delete_review/<int:review_id>", methods=["POST"])
def delete_review(review_id):
    if "user_id" not in session or session.get("role") not in ["admin", "staff"]:
        return redirect("/login")

    db = get_db()
    db.execute("DELETE FROM reviews WHERE id=?", (review_id,))
    db.commit()
    db.close()

    flash("Отзыв успешно удалён")
    return redirect("/admin/reviews")


# ---------- Страница управления отзывами (админ) ----------
@app.route("/admin/reviews")
def admin_reviews():
    if "user_id" not in session or session.get("role") not in ["admin", "staff"]:
        return redirect("/login")

    db = get_db()
    reviews = db.execute(
        "SELECT id, user_name, rating, text, created_at FROM reviews ORDER BY id DESC"
    ).fetchall()
    db.close()

    return render_template("admin_reviews.html", reviews=reviews)

# ---------- RUN ----------
if __name__ == "__main__":
    socketio.run(app, debug=True)
