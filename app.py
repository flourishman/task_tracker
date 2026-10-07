from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)

# Helper function to connect to our database and create the table if it doesn't exist
def init_db():
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Initialize the database when the app starts
init_db()

@app.route("/")
def home():
    # Fetch all tasks from the database to display them
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks")
    database_tasks = cursor.fetchall()  # This returns a list of tuples like [(1, 'Buy milk'), (2, 'Code')]
    conn.close()
    
    return render_template("index.html", tasks=database_tasks)

@app.route("/add", methods=["POST"])
def add_task():
    # Get the text input from the HTML form
    task_title = request.form.get("task")
    
    if task_title:
        # Insert the new task into our SQLite database
        conn = sqlite3.connect("tasks.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tasks (title) VALUES (?)", (task_title,))
        conn.commit()
        conn.close()

@app.route("/delete/<int:task_id>", methods=["POST"])
def delete_task(task_id):
    # Connect to database and delete the task matching this ID
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
        
    # Redirect back to the homepage to refresh the list
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)
