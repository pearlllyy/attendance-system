from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from config import Config
import pymysql
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

# ─── Database Connection ───────────────────────────────────────────
def get_db():
    return pymysql.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        db=app.config['MYSQL_DB'],
        port=app.config['MYSQL_PORT'],
        cursorclass=pymysql.cursors.DictCursor
    )

# ─── Routes ───────────────────────────────────────────────────────

# Homepage — Station Login
@app.route('/')
def index():
    return render_template('index.html')

# Station Login — sets which course this station handles
@app.route('/station/login', methods=['POST'])
def station_login():
    data = request.get_json()
    session['station_id'] = data['station_id']
    session['station_name'] = data['station_name']
    session['course_id'] = data['course_id']
    return jsonify({'success': True})

# Scanner Page — main scanning interface for phones
@app.route('/scanner')
def scanner():
    if 'station_id' not in session:
        return redirect(url_for('index'))
    return render_template('scanner.html', 
        station_name=session['station_name']
    )

# Scan Endpoint — called every time a barcode is scanned
@app.route('/scan', methods=['POST'])
def scan():
    if 'station_id' not in session:
        return jsonify({'success': False, 'message': 'No station logged in'})

    data = request.get_json()
    student_id = data.get('student_id', '').strip()

    if not student_id:
        return jsonify({'success': False, 'message': 'No student ID received'})

    db = get_db()
    cursor = db.cursor()

    try:
        # Check 1 — Does the student exist and belong to this station's course?
        cursor.execute("""
            SELECT s.student_id, s.full_name, s.course_id, c.course_code
            FROM students s
            JOIN courses c ON s.course_id = c.course_id
            WHERE s.student_id = %s
        """, (student_id,))
        student = cursor.fetchone()

        if not student:
            return jsonify({'success': False, 'message': 'Student not found'})

        if student['course_id'] != session['course_id']:
            return jsonify({'success': False, 
                'message': f"Wrong station! This student belongs to {student['course_code']}"
            })

        # Check 2 — Already scanned today?
        today = datetime.now().date()
        cursor.execute("""
            SELECT log_id FROM attendance_logs
            WHERE student_id = %s AND scan_date = %s
        """, (student_id, today))
        existing = cursor.fetchone()

        if existing:
            return jsonify({'success': False, 
                'message': f"{student['full_name']} already scanned today"
            })

        # Determine status based on cutoff time
        now = datetime.now()
        cutoff = now.replace(
            hour=app.config['CUTOFF_HOUR'],
            minute=app.config['CUTOFF_MINUTE'],
            second=0
        )
        status = 'Present' if now <= cutoff else 'Late'

        # Log attendance
        cursor.execute("""
            INSERT INTO attendance_logs 
            (student_id, station_id, scan_date, scan_time, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            student_id,
            session['station_id'],
            today,
            now.strftime('%H:%M:%S'),
            status
        ))
        db.commit()

        return jsonify({
            'success': True,
            'student_name': student['full_name'],
            'status': status,
            'time': now.strftime('%I:%M %p')
        })

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})

    finally:
        cursor.close()
        db.close()

# Dashboard — admin view
@app.route('/dashboard')
def dashboard():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT a.log_id, s.full_name, s.student_id, c.course_code,
               a.scan_date, a.scan_time, a.status
        FROM attendance_logs a
        JOIN students s ON a.student_id = s.student_id
        JOIN courses c ON s.course_id = c.course_id
        ORDER BY a.scan_date DESC, a.scan_time DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('dashboard.html', logs=logs)

@app.route('/api/stations')
def get_stations():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT station_id, station_name, course_id FROM stations")
    stations = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(stations)

# Reports page
@app.route('/reports')
def reports():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()
    cursor.execute("""
        SELECT a.log_id, s.full_name, s.student_id, c.course_code,
               a.scan_date, a.scan_time, a.status
        FROM attendance_logs a
        JOIN students s ON a.student_id = s.student_id
        JOIN courses c ON s.course_id = c.course_id
        ORDER BY a.scan_date DESC, a.scan_time DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('reports.html', logs=logs, courses=courses)

# Reports API — filtered results
@app.route('/api/reports')
def reports_api():
    course_id  = request.args.get('course_id')
    status     = request.args.get('status')
    date_from  = request.args.get('date_from')
    date_to    = request.args.get('date_to')

    query  = """
        SELECT a.log_id, s.full_name, s.student_id, c.course_code,
               DATE_FORMAT(a.scan_date, '%Y-%m-%d') as scan_date,
               TIME_FORMAT(a.scan_time, '%H:%i:%s') as scan_time, a.status
        FROM attendance_logs a
        JOIN students s ON a.student_id = s.student_id
        JOIN courses c ON s.course_id = c.course_id
        WHERE 1=1
    """
    params = []

    if course_id:
        query += " AND s.course_id = %s"
        params.append(course_id)
    if status:
        query += " AND a.status = %s"
        params.append(status)
    if date_from:
        query += " AND a.scan_date >= %s"
        params.append(date_from)
    if date_to:
        query += " AND a.scan_date <= %s"
        params.append(date_to)

    query += " ORDER BY a.scan_date DESC, a.scan_time DESC"

    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, params)
    logs = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(logs)

# ─── Run ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)