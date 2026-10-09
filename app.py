import os
import sqlite3
from datetime import date, datetime

import psycopg2
from flask import Flask, redirect, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    pass

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "task-planner-secret-key")
app.config["DATABASE_INITIALIZED"] = False
DATABASE_URL = os.getenv("DATABASE_URL")
PASSWORD_RESET_CODE = os.getenv("PASSWORD_RESET_CODE", "reset123")
DB_PLACEHOLDER = "%s" if DATABASE_URL else "?"


def first_value(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def get_db_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

    conn = sqlite3.connect("tasks.db")
    conn.row_factory = sqlite3.Row
    return conn


def get_greeting():
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


@app.before_request
def require_login():
    allowed_routes = {"login", "register", "forgot_password", "health", "static"}
    if request.endpoint in allowed_routes:
        return None
    if not session.get("user_id"):
        return redirect(url_for("login"))


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    if DATABASE_URL:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                priority TEXT NOT NULL DEFAULT 'Medium',
                due_date TEXT,
                user_id INTEGER NOT NULL DEFAULT 1,
                CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        cursor.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 1")
    else:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                priority TEXT NOT NULL DEFAULT 'Medium',
                due_date TEXT,
                user_id INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )

        user_columns = [row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()]
        if "username" not in user_columns or "password" not in user_columns:
            cursor.execute("ALTER TABLE users RENAME TO users_old")
            cursor.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO users (id, username, password) SELECT id, username, password FROM users_old"
            )
            cursor.execute("DROP TABLE users_old")

        task_columns = [row[1] for row in cursor.execute("PRAGMA table_info(tasks)").fetchall()]
        if "user_id" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1")

    default_user_sql = "SELECT id FROM users WHERE username = " + DB_PLACEHOLDER
    cursor.execute(default_user_sql, ("default",))
    default_user = cursor.fetchone()
    if default_user is None:
        insert_user_sql = "INSERT INTO users (username, password) VALUES (" + DB_PLACEHOLDER + ", " + DB_PLACEHOLDER + ")"
        cursor.execute(insert_user_sql, ("default", generate_password_hash("default123")))
        cursor.execute(default_user_sql, ("default",))
        default_user = cursor.fetchone()

    default_user_id = first_value(default_user)
    update_tasks_sql = "UPDATE tasks SET user_id = " + DB_PLACEHOLDER + " WHERE user_id IS NULL OR user_id = 0"
    cursor.execute(update_tasks_sql, (default_user_id,))

    conn.commit()
    conn.close()


@app.before_request
def ensure_database_initialized():
    if request.endpoint in {"static", "health"} or app.config["DATABASE_INITIALIZED"]:
        return None

    init_db()
    app.config["DATABASE_INITIALIZED"] = True


@app.errorhandler(psycopg2.OperationalError)
@app.errorhandler(psycopg2.InterfaceError)
def handle_database_unavailable(_error):
    return render_template("database_unavailable.html"), 503


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/login", methods=["GET", "POST"])
def login():
    message = request.args.get("message")
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if username and password:
            conn = get_db_connection()
            cursor = conn.cursor()
            user_sql = "SELECT * FROM users WHERE username = " + DB_PLACEHOLDER
            cursor.execute(user_sql, (username,))
            user = cursor.fetchone()
            conn.close()

            if user and check_password_hash(user["password"], password):
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                return redirect(url_for("home"))

        return render_template("login.html", error="Invalid username or password.")

    return render_template("login.html", message=message)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        reset_code = (request.form.get("reset_code") or "").strip()
        new_password = request.form.get("new_password") or ""

        if not username or not reset_code or not new_password:
            return render_template("forgot_password.html", error="Username, reset code, and new password are required.")

        if len(new_password) < 6:
            return render_template("forgot_password.html", error="New password must be at least 6 characters long.")

        if reset_code != PASSWORD_RESET_CODE:
            return render_template("forgot_password.html", error="Invalid reset code.")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = " + DB_PLACEHOLDER, (username,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return render_template("forgot_password.html", error="Username not found.")

        cursor.execute(
            "UPDATE users SET password = " + DB_PLACEHOLDER + " WHERE id = " + DB_PLACEHOLDER,
            (generate_password_hash(new_password), user["id"] if isinstance(user, dict) else user[0]),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("login", message="Password reset successful. Please log in."))

    return render_template("forgot_password.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            return render_template("register.html", error="Username and password are required.")

        if len(password) < 6:
            return render_template("register.html", error="Password must be at least 6 characters long.")

        conn = get_db_connection()
        cursor = conn.cursor()
        existing_sql = "SELECT id FROM users WHERE username = " + DB_PLACEHOLDER
        cursor.execute(existing_sql, (username,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return render_template("register.html", error="Username already exists.")

        insert_user_sql = "INSERT INTO users (username, password) VALUES (" + DB_PLACEHOLDER + ", " + DB_PLACEHOLDER + ")"
        cursor.execute(insert_user_sql, (username, generate_password_hash(password)))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE username = " + DB_PLACEHOLDER, (username,))
        user = cursor.fetchone()
        conn.close()

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("home"))

    return render_template("register.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/reset-password", methods=["POST"])
def reset_password():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    current_password = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if not current_password or not new_password or not confirm_password:
        return redirect(url_for("home", reset_error="Please fill in all password fields."))

    if len(new_password) < 6:
        return redirect(url_for("home", reset_error="New password must be at least 6 characters long."))

    if new_password != confirm_password:
        return redirect(url_for("home", reset_error="New password and confirmation do not match."))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE id = " + DB_PLACEHOLDER, (user_id,))
    stored_user = cursor.fetchone()
    conn.close()

    stored_hash = stored_user["password"] if isinstance(stored_user, dict) else stored_user[0]

    if not stored_user or not check_password_hash(stored_hash, current_password):
        return redirect(url_for("home", reset_error="Current password is incorrect."))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = " + DB_PLACEHOLDER + " WHERE id = " + DB_PLACEHOLDER,
        (generate_password_hash(new_password), user_id),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("home", reset_success="Password updated successfully."))


@app.route("/")
def home():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    filter_name = request.args.get("filter", "all")
    reset_error = request.args.get("reset_error")
    reset_success = request.args.get("reset_success")
    user_id = session["user_id"]
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM tasks WHERE user_id = " + DB_PLACEHOLDER
    params = [user_id]

    if filter_name == "pending":
        query += " AND completed = 0"
    elif filter_name == "completed":
        query += " AND completed = 1"
    elif filter_name == "today":
        query += " AND due_date = " + DB_PLACEHOLDER
        params.append(date.today().isoformat())

    query += " ORDER BY completed ASC, due_date IS NULL, due_date ASC, id DESC"
    cursor.execute(query, params)
    tasks = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = " + DB_PLACEHOLDER, (user_id,))
    total_tasks = first_value(cursor.fetchone())
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = " + DB_PLACEHOLDER + " AND completed = 0", (user_id,))
    pending_tasks = first_value(cursor.fetchone())
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = " + DB_PLACEHOLDER + " AND completed = 1", (user_id,))
    completed_tasks = first_value(cursor.fetchone())
    cursor.execute(
        "SELECT COUNT(*) FROM tasks WHERE user_id = " + DB_PLACEHOLDER + " AND due_date = " + DB_PLACEHOLDER + " AND completed = 0",
        (user_id, date.today().isoformat()),
    )
    today_count = first_value(cursor.fetchone())
    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = " + DB_PLACEHOLDER + " AND completed = 1 ORDER BY id DESC LIMIT 5",
        (user_id,),
    )
    completed_list = [dict(row) for row in cursor.fetchall()]
    task_to_edit = None
    conn.close()

    return render_template(
        "index.html",
        greeting=get_greeting(),
        username=session["username"],
        tasks=tasks,
        current_filter=filter_name,
        total_tasks=total_tasks,
        pending_tasks=pending_tasks,
        completed_tasks=completed_tasks,
        today_count=today_count,
        completed_list=completed_list,
        task_to_edit=task_to_edit,
        reset_error=reset_error,
        reset_success=reset_success,
    )


@app.route("/edit/<int:task_id>")
def edit_task(task_id):
    user_id = session["user_id"]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE id = " + DB_PLACEHOLDER + " AND user_id = " + DB_PLACEHOLDER,
        (task_id, user_id),
    )
    task = cursor.fetchone()
    if task is None:
        conn.close()
        return redirect(url_for("home"))

    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = " + DB_PLACEHOLDER + " ORDER BY completed ASC, due_date IS NULL, due_date ASC, id DESC",
        (user_id,),
    )
    tasks = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = " + DB_PLACEHOLDER, (user_id,))
    total_tasks = first_value(cursor.fetchone())
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = " + DB_PLACEHOLDER + " AND completed = 0", (user_id,))
    pending_tasks = first_value(cursor.fetchone())
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = " + DB_PLACEHOLDER + " AND completed = 1", (user_id,))
    completed_tasks = first_value(cursor.fetchone())
    cursor.execute(
        "SELECT COUNT(*) FROM tasks WHERE user_id = " + DB_PLACEHOLDER + " AND due_date = " + DB_PLACEHOLDER + " AND completed = 0",
        (user_id, date.today().isoformat()),
    )
    today_count = first_value(cursor.fetchone())
    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = " + DB_PLACEHOLDER + " AND completed = 1 ORDER BY id DESC LIMIT 5",
        (user_id,),
    )
    completed_list = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return render_template(
        "index.html",
        greeting=get_greeting(),
        username=session["username"],
        tasks=tasks,
        current_filter=request.args.get("filter", "all"),
        total_tasks=total_tasks,
        pending_tasks=pending_tasks,
        completed_tasks=completed_tasks,
        today_count=today_count,
        completed_list=completed_list,
        task_to_edit=dict(task),
        reset_error=request.args.get("reset_error"),
        reset_success=request.args.get("reset_success"),
    )


@app.route("/add", methods=["POST"])
def add_task():
    user_id = session["user_id"]
    task_title = (request.form.get("task") or "").strip()
    due_date = request.form.get("due_date") or None
    priority = request.form.get("priority", "Medium")

    if task_title:
        conn = get_db_connection()
        cursor = conn.cursor()
        insert_task_sql = "INSERT INTO tasks (title, due_date, priority, user_id) VALUES (" + DB_PLACEHOLDER + ", " + DB_PLACEHOLDER + ", " + DB_PLACEHOLDER + ", " + DB_PLACEHOLDER + ")"
        cursor.execute(insert_task_sql, (task_title, due_date, priority, user_id))
        conn.commit()
        conn.close()

    return redirect(url_for("home"))


@app.route("/toggle/<int:task_id>", methods=["POST"])
def toggle_task(task_id):
    user_id = session["user_id"]
    conn = get_db_connection()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute(
            "UPDATE tasks SET completed = CASE WHEN completed = 1 THEN 0 ELSE 1 END WHERE id = %s AND user_id = %s",
            (task_id, user_id),
        )
    else:
        cursor.execute(
            "UPDATE tasks SET completed = CASE WHEN completed = 1 THEN 0 ELSE 1 END WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


@app.route("/update/<int:task_id>", methods=["POST"])
def update_task(task_id):
    user_id = session["user_id"]
    task_title = (request.form.get("task") or "").strip()
    due_date = request.form.get("due_date") or None
    priority = request.form.get("priority", "Medium")

    if task_title:
        conn = get_db_connection()
        cursor = conn.cursor()
        update_task_sql = "UPDATE tasks SET title = " + DB_PLACEHOLDER + ", due_date = " + DB_PLACEHOLDER + ", priority = " + DB_PLACEHOLDER + " WHERE id = " + DB_PLACEHOLDER + " AND user_id = " + DB_PLACEHOLDER
        cursor.execute(update_task_sql, (task_title, due_date, priority, task_id, user_id))
        conn.commit()
        conn.close()

    return redirect(url_for("home"))


@app.route("/delete/<int:task_id>", methods=["POST"])
def delete_task(task_id):
    user_id = session["user_id"]
    conn = get_db_connection()
    cursor = conn.cursor()
    delete_task_sql = "DELETE FROM tasks WHERE id = " + DB_PLACEHOLDER + " AND user_id = " + DB_PLACEHOLDER
    cursor.execute(delete_task_sql, (task_id, user_id))
    conn.commit()
    conn.close()

    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
