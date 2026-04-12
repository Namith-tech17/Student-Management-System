from flask import Blueprint, render_template, session, redirect
import sqlite3

history_bp = Blueprint('history', __name__)

@history_bp.route('/history')
def history():
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT students.name, students.usn, attendance.date, attendance.status
        FROM attendance
        JOIN students ON students.id = attendance.student_id
        ORDER BY attendance.date DESC
    ''')

    data = cursor.fetchall()
    conn.close()

    return render_template('history.html', data=data)