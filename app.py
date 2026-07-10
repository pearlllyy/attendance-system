import os
import json
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
from config import Config
import pymysql
from datetime import date, datetime, time, timedelta
import csv
import io
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import find_dotenv, load_dotenv, set_key

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
    if hasattr(td, 'seconds'):
        total = int(td.total_seconds())
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f'{h:02d}:{m:02d}:{s:02d}'
    return str(td)


def serialize_backup_value(value):
    if isinstance(value, timedelta):
        return td_to_str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def serialize_backup_rows(rows):
    return [
        {key: serialize_backup_value(value) for key, value in row.items()}
        for row in rows
    ]


def fetch_backup_rows(cursor, table, order_by):
    cursor.execute(f"SELECT * FROM {table} ORDER BY {order_by}")
    return cursor.fetchall()


def upsert_backup_rows(cursor, table, columns, pk_column, rows):
    if not rows:
        return 0

    column_list = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))
    updates = ', '.join(
        f"{column} = VALUES({column})"
        for column in columns
        if column != pk_column
    )

    sql = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"
    if updates:
        sql += f" ON DUPLICATE KEY UPDATE {updates}"

    for row in rows:
        cursor.execute(sql, [row.get(column) for column in columns])

    return len(rows)


def save_admin_password(new_password):
    env_path = find_dotenv(usecwd=True)
    if not env_path:
        env_path = os.path.join(os.getcwd(), '.env')

    hashed_password = generate_password_hash(new_password)
    set_key(env_path, 'ADMIN_PASSWORD', hashed_password)
    load_dotenv(env_path, override=True)
    app.config['ADMIN_PASSWORD'] = hashed_password


def admin_password_matches(candidate_password):
    stored_password = (app.config.get('ADMIN_PASSWORD') or '').strip()

    if not stored_password:
        return False

    if stored_password.startswith('pbkdf2:') or stored_password.startswith('scrypt:'):
        try:
            return check_password_hash(stored_password, candidate_password)
        except ValueError:
            return False

    return candidate_password == stored_password


def build_backup_payload():
    db = get_db()
    cursor = db.cursor()
    try:
        payload = {
            'version': 1,
            'generated_at': datetime.now().isoformat(timespec='seconds'),
            'colleges': serialize_backup_rows(fetch_backup_rows(cursor, 'colleges', 'college_id')),
            'courses': serialize_backup_rows(fetch_backup_rows(cursor, 'courses', 'course_id')),
            'students': serialize_backup_rows(fetch_backup_rows(cursor, 'students', 'student_id')),
            'stations': serialize_backup_rows(fetch_backup_rows(cursor, 'stations', 'station_id')),
            'events': serialize_backup_rows(fetch_backup_rows(cursor, 'events', 'event_id')),
            'attendance_logs': serialize_backup_rows(fetch_backup_rows(cursor, 'attendance_logs', 'log_id')),
        }
        return payload
    finally:
        cursor.close()
        db.close()


def import_backup_payload(payload):
    db = get_db()
    cursor = db.cursor()

    table_specs = [
        ('colleges', ['college_id', 'college_code', 'college_name'], 'college_id'),
        ('courses', ['course_id', 'course_code', 'course_name', 'major', 'college_id'], 'course_id'),
        ('students', ['student_id', 'full_name', 'course_id', 'year_level', 'section'], 'student_id'),
        ('stations', ['station_id', 'station_name', 'course_id'], 'station_id'),
        ('events', ['event_id', 'event_name', 'event_date', 'time_in_cutoff', 'time_out_start', 'is_active'], 'event_id'),
        ('attendance_logs', ['log_id', 'student_id', 'event_id', 'station_id', 'time_in', 'time_out', 'status'], 'log_id'),
    ]

    try:
        counts = {}
        for table, columns, pk_column in table_specs:
            rows = payload.get(table, [])
            if rows is None:
                rows = []
            if not isinstance(rows, list):
                raise ValueError(f"'{table}' must be a list.")
            counts[table] = upsert_backup_rows(cursor, table, columns, pk_column, rows)

        db.commit()
        return counts
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()
        db.close()

# NOTE: The following code is a Flask application that manages student attendance for events. It includes routes for station login, scanning student IDs, and admin functionalities such as managing events, students, and viewing reports. The application uses a MySQL database to store data and provides JSON APIs for various operations. 

# ─── Authentication ──────────────────────────────────────────────────────────
def login_required(f): # Function decorator to check if admin is logged in
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/admin/login', methods=['GET', 'POST']) # Admin login route
def admin_login(): # Admin login function
    setup_mode = not (app.config.get('ADMIN_PASSWORD') or '').strip()

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        password = data.get('password') or ''

        if setup_mode:
            confirm_password = data.get('confirm_password') or ''

            if not password.strip():
                return jsonify({'success': False, 'message': 'Please enter a new admin password.'})
            if password != confirm_password:
                return jsonify({'success': False, 'message': 'Passwords do not match.'})

            try:
                save_admin_password(password)
            except Exception:
                return jsonify({'success': False, 'message': 'Unable to save the admin password. Please check your .env file permissions.'})

            session['admin_logged_in'] = True
            return jsonify({'success': True, 'setup': True, 'message': 'Admin password saved successfully.'})

        if admin_password_matches(password):
            stored_password = (app.config.get('ADMIN_PASSWORD') or '').strip()
            if stored_password and not (stored_password.startswith('pbkdf2:') or stored_password.startswith('scrypt:')):
                try:
                    save_admin_password(password)
                except Exception:
                    pass
            session['admin_logged_in'] = True
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Incorrect password'})
    return render_template('admin_login.html', setup_mode=setup_mode)

@app.route('/admin/logout') # Admin logout route
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

# ─── Station Routes (no login required) ───────────────────────────
@app.route('/') # Home route (landing page)
def index():
    return render_template('index.html')

@app.route('/station/login', methods=['POST']) # Station login route
def station_login(): # Station login function
    data = request.get_json()
    session['station_id']   = data['station_id']
    session['station_name'] = data['station_name']
    session['course_id']    = data['course_id']
    return jsonify({'success': True})

@app.route('/scanner') # Scanner route (for scanning student IDs)
def scanner():  # Scanner function
    if 'station_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM events WHERE is_active = 1 LIMIT 1")
    event = cursor.fetchone()
    cursor.close()
    db.close()
    return render_template('scanner.html',
        station_name=session['station_name'],
        event=event
    )

@app.route('/scan', methods=['POST']) # Scan route (for processing student ID scans)
def scan(): # Scan function
    if 'station_id' not in session:
        return jsonify({'success': False, 'message': 'No station logged in'})

    data       = request.get_json()
    student_id = data.get('student_id', '').strip()
    scan_mode  = data.get('scan_mode', 'IN')

    if not student_id:
        return jsonify({'success': False, 'message': 'No student ID received'})

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("SELECT * FROM events WHERE is_active = 1 LIMIT 1")
        event = cursor.fetchone()

        if not event:
            return jsonify({'success': False, 'message': 'No active event. Please contact admin.'})

        cursor.execute("""
            SELECT s.student_id, s.full_name, s.course_id, s.section,
                   s.year_level, c.course_code, col.college_code, col.college_name
            FROM students s
            JOIN courses c    ON s.course_id  = c.course_id
            JOIN colleges col ON c.college_id = col.college_id
            WHERE s.student_id = %s
        """, (student_id,))
        student = cursor.fetchone()

        if not student:
            return jsonify({'success': False, 'message': 'Student not found'})

        if student['course_id'] != session['course_id']:
            return jsonify({'success': False,
                'message': f"Wrong station! This student belongs to {student['course_code']}"
            })

        now          = datetime.now()
        current_time = now.strftime('%H:%M:%S')

        cursor.execute("""
            SELECT * FROM attendance_logs
            WHERE student_id = %s AND event_id = %s
        """, (student_id, event['event_id']))
        existing = cursor.fetchone()

        if not existing and scan_mode == 'OUT':
            return jsonify({'success': False,
                'message': f"{student['full_name']} did not scanned IN yet"
                })

        if existing:
            if scan_mode == 'IN':
                return jsonify({'success': False,
                    'message': f"{student['full_name']} already scanned IN"
                })
            if existing['time_out']:
                return jsonify({'success': False,
                    'message': f"{student['full_name']} already scanned IN and OUT"
                })
            time_out_start = td_to_str(event['time_out_start'])
            if current_time < time_out_start:
                return jsonify({'success': False,
                    'message': f"Time out scanning starts at {time_out_start}"
                })
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

        time_in_cutoff = td_to_str(event['time_in_cutoff'])
        status = 'Present' if current_time <= time_in_cutoff else 'Late'

        cursor.execute("""
            INSERT INTO attendance_logs
            (student_id, event_id, station_id, time_in, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            student_id, event['event_id'],
            session['station_id'], current_time, status
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
    cursor.execute("""
        SELECT st.station_id, st.station_name, st.course_id,
               c.course_code, col.college_code, col.college_name
        FROM stations st
        JOIN courses c    ON st.course_id  = c.course_id
        JOIN colleges col ON c.college_id  = col.college_id
        ORDER BY col.college_id, c.course_id
    """)
    stations = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(stations)

# ─── Admin Routes (login required) ────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT event_id, event_name, event_date FROM events ORDER BY event_date DESC")
    events = cursor.fetchall()
    cursor.execute("SELECT * FROM colleges ORDER BY college_code")
    colleges = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) AS total FROM students")
    students_total = cursor.fetchone()['total']
    cursor.execute("""
        SELECT s.student_id, s.full_name, s.section, s.year_level,
               c.course_code, col.college_code
        FROM students s
        JOIN courses c    ON s.course_id = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
    """)
    students = cursor.fetchall()
    cursor.execute("""
        SELECT a.log_id, s.full_name, s.student_id, s.section, s.year_level,
               c.course_code, col.college_code,
               e.event_name, e.event_date,
               a.time_in, a.time_out, a.status
        FROM attendance_logs a
        JOIN students s   ON a.student_id = s.student_id
        JOIN courses c    ON s.course_id  = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        JOIN events e     ON a.event_id   = e.event_id
        ORDER BY e.event_date DESC, a.time_in DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('dashboard.html', logs=logs, events=events, colleges=colleges,
                           students_total=students_total, students=students)

@app.route('/api/dashboard')
@login_required
def dashboard_api():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT a.log_id, s.full_name, s.student_id, s.section, s.year_level,
               c.course_code, col.college_code,
               e.event_name, e.event_date,
               TIME_FORMAT(a.time_in,  '%H:%i:%s') as time_in,
               TIME_FORMAT(a.time_out, '%H:%i:%s') as time_out,
               a.status
        FROM attendance_logs a
        JOIN students s   ON a.student_id = s.student_id
        JOIN courses c    ON s.course_id  = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        JOIN events e     ON a.event_id   = e.event_id
        ORDER BY e.event_date DESC, a.time_in DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(logs)

@app.route('/absences')
@login_required
def absences():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT event_id, event_name, event_date FROM events ORDER BY event_date DESC")
    events = cursor.fetchall()
    cursor.execute("SELECT * FROM colleges ORDER BY college_code")
    colleges = cursor.fetchall()
    cursor.execute("""
        SELECT c.*, col.college_code
        FROM courses c
        JOIN colleges col ON c.college_id = col.college_id
        ORDER BY col.college_id, c.course_id
    """)
    courses = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('absences.html', events=events, colleges=colleges, courses=courses)

@app.route('/api/absences')
@login_required
def absences_api():
    event_id   = request.args.get('event_id')
    college_id = request.args.get('college_id')
    course_id  = request.args.get('course_id')
    section    = request.args.get('section')
    year_level = request.args.get('year_level')

    if not event_id:
        return jsonify([])

    db = get_db()
    cursor = db.cursor()

    query = """
        SELECT s.student_id, s.full_name, s.section, s.year_level,
               c.course_code, col.college_code
        FROM students s
        JOIN courses c    ON s.course_id  = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        WHERE s.student_id NOT IN (
            SELECT student_id FROM attendance_logs WHERE event_id = %s
        )
    """
    params = [event_id]

    if college_id:
        query += " AND col.college_id = %s"
        params.append(college_id)
    if course_id:
        query += " AND c.course_id = %s"
        params.append(course_id)
    if section:
        query += " AND s.section = %s"
        params.append(section)
    if year_level:
        query += " AND s.year_level = %s"
        params.append(year_level)

    query += " ORDER BY col.college_code, c.course_code, s.section, s.full_name"

    cursor.execute(query, params)
    absent_students = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(absent_students)

@app.route('/api/absence-summary')
@login_required
def absence_summary():
    college_id = request.args.get('college_id')
    course_id  = request.args.get('course_id')
    section    = request.args.get('section')
    year_level = request.args.get('year_level')

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM events")
    total_events = cursor.fetchone()['total']

    query = """
        SELECT s.student_id, s.full_name, s.section, s.year_level,
               c.course_code, col.college_code,
               COUNT(a.log_id) as attended,
               %s - COUNT(a.log_id) as absences,
               %s as total_events
        FROM students s
        JOIN courses c    ON s.course_id  = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        LEFT JOIN attendance_logs a ON s.student_id = a.student_id
        WHERE 1=1
    """
    params = [total_events, total_events]

    if college_id:
        query += " AND col.college_id = %s"
        params.append(college_id)
    if course_id:
        query += " AND c.course_id = %s"
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

    return jsonify({'total_events': total_events, 'students': students})



@app.route('/backup')
@login_required
def backup():
    db = get_db()
    cursor = db.cursor()
    colleges_total = courses_total = students_total = stations_total = events_total = logs_total = 0
    try:
        cursor.execute("SELECT COUNT(*) as total FROM colleges")
        colleges_total = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total FROM courses")
        courses_total = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total FROM students")
        students_total = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total FROM stations")
        stations_total = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total FROM events")
        events_total = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total FROM attendance_logs")
        logs_total = cursor.fetchone()['total']
    except Exception:
        raise
    finally:
        cursor.close()
        db.close()

    return render_template(
        'backup.html',
        colleges_total=colleges_total,
        courses_total=courses_total,
        students_total=students_total,
        stations_total=stations_total,
        events_total=events_total,
        logs_total=logs_total,
    )


@app.route('/api/backup/export')
@login_required
def export_backup():
    payload = build_backup_payload()
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode('utf-8')
    filename = f"attendance_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return send_file(
        io.BytesIO(data),
        mimetype='application/json',
        as_attachment=True,
        download_name=filename,
    )


@app.route('/api/backup/import', methods=['POST'])
@login_required
def import_backup():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No backup file uploaded.'})

    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith('.json'):
        return jsonify({'success': False, 'message': 'Backup file must be a .json file.'})

    try:
        payload = json.loads(file.stream.read().decode('utf-8'))
    except Exception:
        return jsonify({'success': False, 'message': 'Invalid backup file. Please upload a valid JSON backup.'})

    if not isinstance(payload, dict):
        return jsonify({'success': False, 'message': 'Invalid backup structure.'})

    try:
        counts = import_backup_payload(payload)
        return jsonify({
            'success': True,
            'message': 'Backup imported successfully.',
            'counts': counts
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/events')
@login_required
def events():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM events ORDER BY event_date DESC")
    events = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('events.html', events=events)

@app.route('/api/events/create', methods=['POST'])
@login_required
def create_event():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO events (event_name, event_date, time_in_cutoff, time_out_start)
            VALUES (%s, %s, %s, %s)
        """, (
            data['event_name'], data['event_date'],
            data['time_in_cutoff'], data['time_out_start']
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
@login_required
def activate_event():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE events SET is_active = 0")
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
@login_required
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

@app.route('/api/events/delete', methods=['POST'])
@login_required
def delete_event():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM attendance_logs WHERE event_id = %s", (data['event_id'],))
        cursor.execute("DELETE FROM events WHERE event_id = %s", (data['event_id'],))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/students')
@login_required
def students():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT s.student_id, s.full_name, s.section, s.year_level,
               c.course_code, c.course_id, col.college_code, col.college_id
        FROM students s
        JOIN courses c    ON s.course_id  = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        ORDER BY col.college_id, c.course_id, s.year_level, s.section, s.full_name
    """)
    students = cursor.fetchall()
    cursor.execute("""
        SELECT c.*, col.college_code, col.college_name
        FROM courses c
        JOIN colleges col ON c.college_id = col.college_id
        ORDER BY col.college_id, c.course_id
    """)
    courses = cursor.fetchall()
    cursor.execute("SELECT * FROM colleges ORDER BY college_id")
    colleges = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('students.html', students=students,
                           courses=courses, colleges=colleges)

@app.route('/api/students/add', methods=['POST'])
@login_required
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

@app.route('/api/students/update', methods=['POST'])
@login_required
def update_student():
    data = request.get_json()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE students
            SET full_name = %s,
                course_id = %s,
                year_level = %s,
                section = %s
            WHERE student_id = %s
        """, (
            data['full_name'].strip(),
            data['course_id'],
            data['year_level'],
            data['section'].strip().upper(),
            data['student_id'].strip()
        ))
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'Student not found'})
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/students/delete', methods=['POST'])
@login_required
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

@app.route('/api/students/delete-all', methods=['POST'])
@login_required
def delete_all_students():
    data = request.get_json(silent=True) or {}
    if not admin_password_matches(data.get('password') or ''):
        return jsonify({'success': False, 'message': 'Incorrect admin password.'}), 403

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM attendance_logs")
        cursor.execute("DELETE FROM students")
        deleted_students = cursor.rowcount
        db.commit()
        return jsonify({'success': True, 'deleted_students': deleted_students})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/students/import', methods=['POST'])
@login_required
def import_students():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'})
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({'success': False, 'message': 'File must be a .csv'})
    db = get_db()
    cursor = db.cursor()
    try:
        raw = file.stream.read()
        try:
            # Handles plain UTF-8 and UTF-8-with-BOM (utf-8-sig strips the BOM)
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Excel often saves CSVs as Windows-1252/ANSI instead of UTF-8.
            # cp1252 covers ñ, é, etc. and rarely raises, so it's a safe fallback.
            decoded = raw.decode("cp1252")
        stream = io.StringIO(decoded, newline=None)
        reader   = csv.DictReader(stream)
        inserted = 0
        skipped  = 0
        errors   = []
        for row in reader:
            try:
                cursor.execute("""
                    INSERT INTO students
                    (student_id, full_name, course_id, year_level, section)
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
        return jsonify({'success': True, 'inserted': inserted,
                        'skipped': skipped, 'errors': errors})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/logs/delete', methods=['POST'])
@login_required
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

# ─── Run ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, ssl_context='adhoc')
