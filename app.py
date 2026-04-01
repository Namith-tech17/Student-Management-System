from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3
import datetime
import pandas as pd

app = Flask(__name__)
app.secret_key = "secret123"


# 🔹 DATABASE
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            usn TEXT
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

    conn.commit()
    conn.close()

init_db()


# 🔹 LOGIN
@app.route('/', methods=['GET', 'POST'])
def login():

    if 'user' in session:
        return redirect('/dashboard')

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == "admin" and password == "1234":
            session['user'] = username
            return redirect('/dashboard')
        else:
            return "Wrong Username or Password ❌"

    return render_template('login.html')


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

    # 📊 COUNT
    cursor.execute("SELECT COUNT(*) FROM attendance WHERE date=? AND status='Present'", (selected_date,))
    present = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM attendance WHERE date=? AND status='Absent'", (selected_date,))
    absent = cursor.fetchone()[0]

    # 🔥 ATTENDANCE %
    student_data = []
    for s in students:
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE student_id=?", (s[0],))
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM attendance WHERE student_id=? AND status='Present'", (s[0],))
        pres = cursor.fetchone()[0]

        percent = round((pres / total) * 100, 2) if total > 0 else 0

        student_data.append((s[0], s[1], s[2], percent))

    conn.close()

    return render_template('index.html',
                           students=student_data,
                           selected_date=selected_date,
                           present=present,
                           absent=absent)


# 🔹 ADD PAGE
@app.route('/add')
def add():
    if 'user' not in session:
        return redirect('/')
    return render_template('add.html')


# 🔹 ADD STUDENT
@app.route('/add_student', methods=['POST'])
def add_student():
    if 'user' not in session:
        return redirect('/')

    name = request.form['name']
    usn = request.form['usn']

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("INSERT INTO students (name, usn) VALUES (?, ?)", (name, usn))

    conn.commit()
    conn.close()

    return redirect('/dashboard')


# 🔹 EDIT
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


# 🔹 UPDATE
@app.route('/update/<int:id>', methods=['POST'])
def update(id):
    if 'user' not in session:
        return redirect('/')

    name = request.form['name']
    usn = request.form['usn']

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("UPDATE students SET name=?, usn=? WHERE id=?", (name, usn, id))

    conn.commit()
    conn.close()

    return redirect('/dashboard')


# 🔥 FIX DUPLICATE (PRESENT)
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


# 🔥 FIX DUPLICATE (ABSENT)
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

    conn.commit()
    conn.close()

    return redirect('/dashboard')


# 🔹 DELETE
@app.route('/delete/<int:id>')
def delete(id):
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("DELETE FROM students WHERE id=?", (id,))

    conn.commit()
    conn.close()

    return redirect('/dashboard')


# 🔥 EXCEL DOWNLOAD
@app.route('/export')
def export():
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')

    df = pd.read_sql_query('''
        SELECT students.name, students.usn, attendance.date, attendance.status
        FROM attendance
        JOIN students ON students.id = attendance.student_id
    ''', conn)

    file = "attendance.xlsx"
    df.to_excel(file, index=False)

    conn.close()

    return send_file(file, as_attachment=True)


# 🔹 LOGOUT
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


app.run(debug=True)