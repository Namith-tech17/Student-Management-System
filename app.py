from dotenv import load_dotenv
load_dotenv()

import csv
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3
import datetime
import pandas as pd
import bcrypt
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "secret123")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_ENABLED = True

# Track emails already sent today to avoid spamming students
email_sent_today = set()  # stores (student_id, date) tuples


# 🔥 EMAIL FUNCTION
def send_email(to_email, subject, message):
    if not EMAIL_ENABLED or not to_email:
        return

    try:
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = EMAIL_USER
        msg['To'] = to_email

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()

        print(f"Email sent to {to_email}")
    except Exception as e:
        print("Email error:", e)


# 🔹 DATABASE
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            usn TEXT,
            email TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            date TEXT,
            status TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password BLOB
        )
    ''')

    conn.commit()
    conn.close()


# 🔹 IMPORT STUDENTS CSV
def import_students():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM students")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    try:
        with open('students.csv', 'r') as file:
            reader = csv.DictReader(file)

            for row in reader:
                cursor.execute(
                    "INSERT INTO students (name, usn, email) VALUES (?, ?, ?)",
                    (row.get('name'), row.get('usn'), row.get('email'))
                )

        conn.commit()

    except Exception as e:
        print("Student CSV Error:", e)

    conn.close()


# 🔥 IMPORT ATTENDANCE CSV (NEW)
def import_attendance():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM attendance")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    try:
        with open('attendance.csv', 'r') as file:
            reader = csv.DictReader(file)

            for row in reader:
                cursor.execute(
                    "INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)",
                    (row.get('student_id'), row.get('date'), row.get('status'))
                )

        conn.commit()

    except Exception as e:
        print("Attendance CSV Error:", e)

    conn.close()


# 🔹 DEFAULT USERS
def create_admin():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    users = [
        ("admin",     "1234"),
        ("teacher",   "teach1234"),
        ("professor", "prof1234"),
    ]

    for username, password in users:
        cursor.execute("SELECT * FROM users WHERE username=?", (username,))
        if not cursor.fetchone():
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))

    conn.commit()
    conn.close()


# 🔥 CORRECT EXECUTION ORDER
init_db()
create_admin()
import_students()
import_attendance()


# 🔹 REGISTER
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        try:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('login.html', error="Username already exists ❌")

        conn.close()
        return redirect('/')

    return render_template('register.html')


# 🔹 LOGIN
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect('/dashboard')

    error = None

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        cursor.execute("SELECT password FROM users WHERE username=?", (username,))
        user = cursor.fetchone()

        conn.close()

        if user and bcrypt.checkpw(password.encode('utf-8'), user[0]):
            session['user'] = username
            return redirect('/dashboard')
        else:
            error = "Wrong Username or Password ❌"

    return render_template('login.html', error=error)


# 🔹 DASHBOARD
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user' not in session:
        return redirect('/')

    selected_date = request.form.get('date') or str(datetime.date.today())

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM attendance WHERE date=? AND status='Present'", (selected_date,))
    present = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM attendance WHERE date=? AND status='Absent'", (selected_date,))
    absent = cursor.fetchone()[0]

    student_data = []
    at_risk_students = []

    for s in students:
        student_id, name, usn, email = s

        cursor.execute("SELECT COUNT(*) FROM attendance WHERE student_id=?", (student_id,))
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM attendance WHERE student_id=? AND status='Present'", (student_id,))
        present_count = cursor.fetchone()[0]

        percent = round((present_count / total) * 100, 2) if total > 0 else 0

        if percent < 75:
            risk = "⚠️ At Risk"
            at_risk_students.append((name, percent))

            # 🔥 EMAIL — only once per student per day (not on every page load)
            email_key = (student_id, selected_date)
            if email_key not in email_sent_today:
                email_sent_today.add(email_key)
                send_email(
                    email,
                    "Low Attendance Warning ⚠️",
                    f"Your attendance is {percent}%.\nMinimum required is 75%.\nPlease improve."
                )
        else:
            risk = "✅ Good"

        student_data.append((student_id, name, usn, percent, risk))

    conn.close()

    return render_template(
        'index.html',
        students=student_data,
        selected_date=selected_date,
        present=present,
        absent=absent,
        at_risk=at_risk_students
    )


# 🔹 ADD STUDENT
@app.route('/add_student', methods=['POST'])
def add_student():
    if 'user' not in session:
        return redirect('/')

    name = request.form['name']
    usn = request.form['usn']
    email = request.form.get('email')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO students (name, usn, email) VALUES (?, ?, ?)",
        (name, usn, email)
    )

    conn.commit()
    conn.close()

    return redirect('/dashboard')


# 🔥 ABSENT + EMAIL
@app.route('/absent/<int:id>/<date>')
def absent(id, date):
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM attendance WHERE student_id=? AND date=?", (id, date))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("UPDATE attendance SET status='Absent' WHERE student_id=? AND date=?", (id, date))
    else:
        cursor.execute("INSERT INTO attendance (student_id, date, status) VALUES (?, ?, 'Absent')", (id, date))

    cursor.execute("SELECT name, email FROM students WHERE id=?", (id,))
    student = cursor.fetchone()

    if student:
        name, email = student

        send_email(
            email,
            "Attendance Alert ❌",
            f"Dear {name},\n\nYou were marked ABSENT on {date}.\nPlease attend regularly.\n\n- System"
        )

    conn.commit()
    conn.close()

    return redirect('/dashboard')


# 🔹 ADD STUDENT PAGE
@app.route('/add')
def add():
    if 'user' not in session:
        return redirect('/')
    return render_template('add.html')


# 🔹 PRESENT
@app.route('/present/<int:id>/<date>')
def present(id, date):
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM attendance WHERE student_id=? AND date=?", (id, date))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("UPDATE attendance SET status='Present' WHERE student_id=? AND date=?", (id, date))
    else:
        cursor.execute("INSERT INTO attendance (student_id, date, status) VALUES (?, ?, 'Present')", (id, date))

    conn.commit()
    conn.close()
    return redirect('/dashboard')


# 🔹 EDIT STUDENT PAGE
@app.route('/edit/<int:id>')
def edit(id):
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE id=?", (id,))
    student = cursor.fetchone()
    conn.close()

    return render_template('edit.html', student=student)


# 🔹 UPDATE STUDENT
@app.route('/update/<int:id>', methods=['POST'])
def update(id):
    if 'user' not in session:
        return redirect('/')

    name = request.form['name']
    usn = request.form['usn']
    email = request.form.get('email')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE students SET name=?, usn=?, email=? WHERE id=?",
        (name, usn, email, id)
    )
    conn.commit()
    conn.close()

    return redirect('/dashboard')


# 🔹 DELETE STUDENT
@app.route('/delete/<int:id>')
def delete(id):
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE id=?", (id,))
    cursor.execute("DELETE FROM attendance WHERE student_id=?", (id,))
    conn.commit()
    conn.close()

    return redirect('/dashboard')


# 🔹 EXPORT ATTENDANCE AS EXCEL
@app.route('/export')
def export():
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')

    df_students = pd.read_sql_query("SELECT * FROM students", conn)
    df_attendance = pd.read_sql_query("SELECT * FROM attendance", conn)
    conn.close()

    df = pd.merge(df_attendance, df_students, left_on='student_id', right_on='id', suffixes=('_att', '_stu'))
    df = df[['name', 'usn', 'email', 'date', 'status']]
    df.columns = ['Name', 'USN', 'Email', 'Date', 'Status']

    file_path = 'attendance_export.xlsx'
    df.to_excel(file_path, index=False)

    return send_file(file_path, as_attachment=True)


# 🔹 LOGOUT
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


if __name__ == "__main__":
    app.run(debug=True)
