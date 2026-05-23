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

def td_to_str(td):
    """Convert MySQL timedelta TIME value to HH:MM:SS string"""
    if hasattr(td, 'seconds'):  # it's a timedelta
        total = int(td.total_seconds())
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f'{h:02d}:{m:02d}:{s:02d}'
    return str(td)
# ─── Routes ───────────────────────────────────────────────────────

# Homepage — Station Login
@app.route('/')
def index():
    return render_template('index.html')

# Station Login
@app.route('/station/login', methods=['POST'])
def station_login():
    data = request.get_json()
    session['station_id'] = data['station_id']
    session['station_name'] = data['station_name']
    session['course_id'] = data['course_id']
    return jsonify({'success': True})

# Scanner Page
@app.route('/scanner')
def scanner():
    if 'station_id' not in session:
        return redirect(url_for('index'))

    db = get_db()
    cursor = db.cursor()

    # Get active event
    cursor.execute("""
        SELECT * FROM events WHERE is_active = 1 LIMIT 1
    """)
    event = cursor.fetchone()
    cursor.close()
    db.close()

    if not event:
        return render_template('scanner.html',
            station_name=session['station_name'],
            event=None
        )

    return render_template('scanner.html',
        station_name=session['station_name'],
        event=event
    )

# ─── Scan Endpoint ─────────────────────────────────────────────────
@app.route('/scan', methods=['POST'])
def scan():
    if 'station_id' not in session:
        return jsonify({'success': False, 'message': 'No station logged in'})

    data = request.get_json()
    student_id = data.get('student_id', '').strip()
    scan_mode = data.get('scan_mode', 'IN')

    if not student_id:
        return jsonify({'success': False, 'message': 'No student ID received'})

    db = get_db()
    cursor = db.cursor()

    try:
        # Get active event
        cursor.execute("SELECT * FROM events WHERE is_active = 1 LIMIT 1")
        event = cursor.fetchone()

        if not event:
            return jsonify({'success': False, 'message': 'No active event. Please contact admin.'})

        # Check student exists and belongs to this station
        cursor.execute("""
            SELECT s.student_id, s.full_name, s.course_id, s.section, 
                   s.year_level, c.course_code
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

        now = datetime.now()
        current_time = now.strftime('%H:%M:%S')

        # Check if student already has a log for this event
        cursor.execute("""
            SELECT * FROM attendance_logs
            WHERE student_id = %s AND event_id = %s
        """, (student_id, event['event_id']))
        existing = cursor.fetchone()

        # ── Time Out ───────────────────────────────────────────────
        # Time in is a must before scanning for out
        if not existing and scan_mode == 'OUT':
            return jsonify({'success': False,
                'message': f"{student['full_name']} did not scanned IN yet"
            })

        if existing:
            if scan_mode == 'IN':
                return jsonify({'success': False,
                    'message': f"{student['full_name']} already scanned IN"
                })

            # Already scanned in — check if time out is allowed
            if existing['time_out']:
                return jsonify({'success': False,
                    'message': f"{student['full_name']} already scanned IN and OUT"
                })

            # Check if time out window has started
            time_out_start = td_to_str(event['time_out_start'])
            if current_time < time_out_start:
                return jsonify({'success': False,
                    'message': f"Time out scanning starts at {event['time_out_start']}"
                })

            # Record time out
            cursor.execute("""
                UPDATE attendance_logs
                SET time_out = %s
                WHERE student_id = %s AND event_id = %s
            """, (current_time, student_id, event['event_id']))
            db.commit()

            return jsonify({
                'success': True,
                'scan_type': 'OUT',
                'student_name': student['full_name'],
                'status': existing['status'],
                'time': now.strftime('%I:%M %p')
            })

        # ── Time In ────────────────────────────────────────────────
        # Determine status based on cutoff
        time_in_cutoff = td_to_str(event['time_in_cutoff'])
        status = 'Present' if current_time <= time_in_cutoff else 'Late'

        cursor.execute("""
            INSERT INTO attendance_logs
            (student_id, event_id, station_id, time_in, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            student_id,
            event['event_id'],
            session['station_id'],
            current_time,
            status
        ))
        db.commit()

        return jsonify({
            'success': True,
            'scan_type': 'IN',
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

# ─── Stations API ──────────────────────────────────────────────────
@app.route('/api/stations')
def get_stations():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT station_id, station_name, course_id FROM stations")
    stations = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(stations)

# ─── Dashboard ─────────────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    db = get_db()
    cursor = db.cursor()

    # Get all events for filter dropdown
    cursor.execute("SELECT event_id, event_name, event_date FROM events ORDER BY event_date DESC")
    events = cursor.fetchall()

    # Get all logs
    cursor.execute("""
        SELECT a.log_id, s.full_name, s.student_id, s.section, s.year_level,
               c.course_code, e.event_name, e.event_date,
               a.time_in, a.time_out, a.status
        FROM attendance_logs a
        JOIN students s ON a.student_id = s.student_id
        JOIN courses c ON s.course_id = c.course_id
        JOIN events e ON a.event_id = e.event_id
        ORDER BY e.event_date DESC, a.time_in DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('dashboard.html', logs=logs, events=events)

# ─── Absences ──────────────────────────────────────────────────────
@app.route('/absences')
def absences():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT event_id, event_name, event_date FROM events ORDER BY event_date DESC")
    events = cursor.fetchall()

    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()

    cursor.close()
    db.close()
    return render_template('absences.html', events=events, courses=courses)

@app.route('/api/absences')
def absences_api():
    event_id   = request.args.get('event_id')
    course_id  = request.args.get('course_id')
    section    = request.args.get('section')
    year_level = request.args.get('year_level')

    if not event_id:
        return jsonify([])

    db = get_db()
    cursor = db.cursor()

    # Students who did NOT scan for this event
    query = """
        SELECT s.student_id, s.full_name, s.section, s.year_level, c.course_code
        FROM students s
        JOIN courses c ON s.course_id = c.course_id
        WHERE s.student_id NOT IN (
            SELECT student_id FROM attendance_logs WHERE event_id = %s
        )
    """
    params = [event_id]

    if course_id:
        query += " AND s.course_id = %s"
        params.append(course_id)
    if section:
        query += " AND s.section = %s"
        params.append(section)
    if year_level:
        query += " AND s.year_level = %s"
        params.append(year_level)

    query += " ORDER BY s.section, s.full_name"

    cursor.execute(query, params)
    absent_students = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(absent_students)

# ─── Reports ───────────────────────────────────────────────────────
@app.route('/reports')
def reports():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()
    cursor.execute("SELECT event_id, event_name, event_date FROM events ORDER BY event_date DESC")
    events = cursor.fetchall()
    cursor.execute("""
        SELECT a.log_id, s.full_name, s.student_id, s.section, s.year_level,
               c.course_code, e.event_name, e.event_date,
               a.time_in, a.time_out, a.status
        FROM attendance_logs a
        JOIN students s ON a.student_id = s.student_id
        JOIN courses c ON s.course_id = c.course_id
        JOIN events e ON a.event_id = e.event_id
        ORDER BY e.event_date DESC, a.time_in DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('reports.html', logs=logs, courses=courses, events=events)

@app.route('/api/reports')
def reports_api():
    event_id   = request.args.get('event_id')
    course_id  = request.args.get('course_id')
    status     = request.args.get('status')
    section    = request.args.get('section')
    year_level = request.args.get('year_level')

    query = """
        SELECT a.log_id, s.full_name, s.student_id, s.section, s.year_level,
               c.course_code, e.event_name,
               DATE_FORMAT(e.event_date, '%Y-%m-%d') as event_date,
               TIME_FORMAT(a.time_in, '%H:%i:%s') as time_in,
               TIME_FORMAT(a.time_out, '%H:%i:%s') as time_out,
               a.status
        FROM attendance_logs a
        JOIN students s ON a.student_id = s.student_id
        JOIN courses c ON s.course_id = c.course_id
        JOIN events e ON a.event_id = e.event_id
        WHERE 1=1
    """
    params = []

    if event_id:
        query += " AND a.event_id = %s"
        params.append(event_id)
    if course_id:
        query += " AND s.course_id = %s"
        params.append(course_id)
    if status:
        query += " AND a.status = %s"
        params.append(status)
    if section:
        query += " AND s.section = %s"
        params.append(section)
    if year_level:
        query += " AND s.year_level = %s"
        params.append(year_level)

    query += " ORDER BY e.event_date DESC, a.time_in DESC"

    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, params)
    logs = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(logs)

# ─── Events Management ─────────────────────────────────────────────
@app.route('/events')
def events():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT e.*, c.course_code FROM events e
        LEFT JOIN courses c ON e.course_id = c.course_id
        ORDER BY e.event_date DESC
    """)
    events = cursor.fetchall()
    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('events.html', events=events, courses=courses)

@app.route('/api/events/create', methods=['POST'])
def create_event():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO events (event_name, event_date, time_in_cutoff, time_out_start, course_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            data['event_name'],
            data['event_date'],
            data['time_in_cutoff'],
            data['time_out_start'],
            data.get('course_id') or None
        ))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/events/activate', methods=['POST'])
def activate_event():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    try:
        # Deactivate all events first
        cursor.execute("UPDATE events SET is_active = 0")
        # Activate selected event
        cursor.execute("UPDATE events SET is_active = 1 WHERE event_id = %s", (data['event_id'],))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/events/deactivate', methods=['POST'])
def deactivate_event():
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE events SET is_active = 0")
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/absence-summary')
def absence_summary():
    course_id  = request.args.get('course_id')
    section    = request.args.get('section')
    year_level = request.args.get('year_level')

    db = get_db()
    cursor = db.cursor()

    # Get total number of events
    cursor.execute("SELECT COUNT(*) as total FROM events")
    total_events = cursor.fetchone()['total']

    # Get all students with attendance count
    query = """
        SELECT s.student_id, s.full_name, s.section, s.year_level,
               c.course_code,
               COUNT(a.log_id) as attended,
               %s - COUNT(a.log_id) as absences,
               %s as total_events
        FROM students s
        JOIN courses c ON s.course_id = c.course_id
        LEFT JOIN attendance_logs a ON s.student_id = a.student_id
        WHERE 1=1
    """
    params = [total_events, total_events]

    if course_id:
        query += " AND s.course_id = %s"
        params.append(course_id)
    if section:
        query += " AND s.section = %s"
        params.append(section)
    if year_level:
        query += " AND s.year_level = %s"
        params.append(year_level)

    query += " GROUP BY s.student_id ORDER BY absences DESC"

    cursor.execute(query, params)
    students = cursor.fetchall()
    cursor.close()
    db.close()

    return jsonify({
        'total_events': total_events,
        'students': students
    })

@app.route('/api/dashboard')
def dashboard_api():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT a.log_id, s.full_name, s.student_id, s.section, s.year_level,
               c.course_code, e.event_name, e.event_date,
               TIME_FORMAT(a.time_in, '%H:%i:%s') as time_in,
               TIME_FORMAT(a.time_out, '%H:%i:%s') as time_out,
               a.status
        FROM attendance_logs a
        JOIN students s ON a.student_id = s.student_id
        JOIN courses c ON s.course_id = c.course_id
        JOIN events e ON a.event_id = e.event_id
        ORDER BY e.event_date DESC, a.time_in DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(logs)

@app.route('/api/events/delete', methods=['POST'])
def delete_event():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    try:
        # Delete attendance logs for this event first
        cursor.execute("DELETE FROM attendance_logs WHERE event_id = %s", (data['event_id'],))
        # Then delete the event
        cursor.execute("DELETE FROM events WHERE event_id = %s", (data['event_id'],))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/logs/delete', methods=['POST'])
def delete_log():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM attendance_logs WHERE log_id = %s", (data['log_id'],))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

import csv
import io

# Students Page
@app.route('/students')
def students():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT s.student_id, s.full_name, s.section, s.year_level,
               c.course_code, c.course_id
        FROM students s
        JOIN courses c ON s.course_id = c.course_id
        ORDER BY c.course_code, s.year_level, s.section, s.full_name
    """)
    students = cursor.fetchall()
    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('students.html', students=students, courses=courses)

# Add Single Student
@app.route('/api/students/add', methods=['POST'])
def add_student():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO students (student_id, full_name, course_id, year_level, section)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            data['student_id'].strip(),
            data['full_name'].strip(),
            data['course_id'],
            data['year_level'],
            data['section'].strip().upper()
        ))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

# Delete Student
@app.route('/api/students/delete', methods=['POST'])
def delete_student():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM attendance_logs WHERE student_id = %s", (data['student_id'],))
        cursor.execute("DELETE FROM students WHERE student_id = %s", (data['student_id'],))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

# -----------------------   CSV Import
@app.route('/api/students/import', methods=['POST'])
def import_students():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'})

    file = request.files['file']

    if not file.filename.endswith('.csv'):
        return jsonify({'success': False, 'message': 'File must be a .csv'})

    db = get_db()
    cursor = db.cursor()

    try:
        stream  = io.StringIO(file.stream.read().decode('UTF-8'))
        reader  = csv.DictReader(stream)
        inserted = 0
        skipped  = 0
        errors   = []

        for row in reader:
            try:
                cursor.execute("""
                    INSERT INTO students (student_id, full_name, course_id, year_level, section)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    row['student_id'].strip(),
                    row['full_name'].strip(),
                    int(row['course_id'].strip()),
                    int(row['year_level'].strip()),
                    row['section'].strip().upper()
                ))
                inserted += 1
            except Exception as e:
                skipped += 1
                errors.append(f"Row {inserted + skipped}: {str(e)}")

        db.commit()
        return jsonify({
            'success': True,
            'inserted': inserted,
            'skipped': skipped,
            'errors': errors
        })

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

# ─── Run ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, ssl_context='adhoc')