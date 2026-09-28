import os
import json
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
from config import Config
import pymysql
from dbutils.pooled_db import PooledDB
from datetime import date, datetime, time, timedelta
import csv
import io
import random
import string
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import find_dotenv, load_dotenv, set_key
from datetime import timezone

app = Flask(__name__)
app.config.from_object(Config)


def get_app_timezone():
    try:
        offset_hours = int(os.getenv('APP_TIMEZONE_OFFSET_HOURS', '8'))
    except ValueError:
        offset_hours = 8
    return timezone(timedelta(hours=offset_hours))


APP_TIMEZONE = get_app_timezone()


def local_now():
    return datetime.now(APP_TIMEZONE)


def get_lan_ips():
    ip_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server-ip.txt')
    try:
        with open(ip_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

# ─── Database Connection Pool ──────────────────────────────────────
# A pool avoids opening a brand-new TCP + MySQL auth handshake on every
# single request. Connections are created lazily (up to maxconnections)
# and reused, which matters a lot for the /scan route during rapid
# back-to-back scans across stations.
db_pool = PooledDB(
    creator=pymysql,
    mincached=app.config['DB_POOL_MINCACHED'],
    maxcached=app.config['DB_POOL_MAXCACHED'],
    maxconnections=app.config['DB_POOL_MAXCONNECTIONS'],
    maxusage=app.config['DB_POOL_MAXUSAGE'],
    blocking=True,
    ping=1,
    host=app.config['MYSQL_HOST'],
    user=app.config['MYSQL_USER'],
    password=app.config['MYSQL_PASSWORD'],
    db=app.config['MYSQL_DB'],
    port=app.config['MYSQL_PORT'],
    connect_timeout=app.config['DB_POOL_CONNECT_TIMEOUT'],
    read_timeout=app.config['DB_POOL_READ_TIMEOUT'],
    write_timeout=app.config['DB_POOL_WRITE_TIMEOUT'],
    charset='utf8mb4',
    autocommit=False,
    cursorclass=pymysql.cursors.DictCursor
)


def get_db():
    return db_pool.connection()

def get_direct_db():
    """Dedicated connection for long transactions (no pool recycling)."""
    return pymysql.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        db=app.config['MYSQL_DB'],
        port=app.config['MYSQL_PORT'],
        charset='utf8mb4',
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )

def ensure_events_course_column(cursor):
    cursor.execute("SHOW COLUMNS FROM events LIKE 'course_id'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE events ADD COLUMN course_id INT NULL AFTER time_out_start")
        cursor.execute("ALTER TABLE events ADD INDEX (course_id)")


def ensure_stations_college_column(cursor):
    cursor.execute("SHOW COLUMNS FROM stations LIKE 'college_id'")
    if cursor.fetchone():
        return

    cursor.execute("ALTER TABLE stations ADD COLUMN college_id INT NULL AFTER station_name")
    cursor.execute("UPDATE stations st JOIN courses c ON st.course_id = c.course_id SET st.college_id = c.college_id WHERE st.college_id IS NULL")
    cursor.execute("ALTER TABLE stations ADD INDEX (college_id)")


def ensure_scanners_table(cursor):
    cursor.execute("SHOW TABLES LIKE 'scanners'")
    if cursor.fetchone():
        return
    cursor.execute("""
        CREATE TABLE scanners (
            scanner_id INT AUTO_INCREMENT PRIMARY KEY,
            full_name  VARCHAR(100) NOT NULL,
            scan_code  VARCHAR(20)  NOT NULL UNIQUE,
            is_active  TINYINT      DEFAULT 1,
            created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
    """)


def ensure_attendance_scanner_columns(cursor):
    # Who scanned the student IN
    cursor.execute("SHOW COLUMNS FROM attendance_logs LIKE 'scanner_id'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE attendance_logs ADD COLUMN scanner_id INT NULL AFTER station_id")
        cursor.execute("ALTER TABLE attendance_logs ADD INDEX (scanner_id)")
    # Who scanned the student OUT (may be a different person)
    cursor.execute("SHOW COLUMNS FROM attendance_logs LIKE 'time_out_scanner_id'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE attendance_logs ADD COLUMN time_out_scanner_id INT NULL AFTER time_out")
        cursor.execute("ALTER TABLE attendance_logs ADD INDEX (time_out_scanner_id)")


def ensure_attendance_entry_method_columns(cursor):
    # How the IN scan was captured: camera 'scan' vs typed-in 'manual' entry
    cursor.execute("SHOW COLUMNS FROM attendance_logs LIKE 'entry_method'")
    if not cursor.fetchone():
        cursor.execute("""
            ALTER TABLE attendance_logs
            ADD COLUMN entry_method ENUM('scan', 'manual') NOT NULL DEFAULT 'scan' AFTER scanner_id
        """)
    # Same, but for the OUT side, since IN and OUT can be done by different
    # people in different ways (e.g. camera IN, manual OUT after a jam)
    cursor.execute("SHOW COLUMNS FROM attendance_logs LIKE 'time_out_entry_method'")
    if not cursor.fetchone():
        cursor.execute("""
            ALTER TABLE attendance_logs
            ADD COLUMN time_out_entry_method ENUM('scan', 'manual') NOT NULL DEFAULT 'scan' AFTER time_out_scanner_id
        """)


def ensure_attendance_updated_at_column(cursor):
    cursor.execute("SHOW COLUMNS FROM attendance_logs LIKE 'updated_at'")
    column = cursor.fetchone()
    if not column:
        cursor.execute("""
            ALTER TABLE attendance_logs
            ADD COLUMN updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6) AFTER status
        """)
    elif 'timestamp(6)' not in column.get('Type', '').lower():
        cursor.execute("""
            ALTER TABLE attendance_logs
            MODIFY COLUMN updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6)
        """)

    cursor.execute("SHOW INDEX FROM attendance_logs WHERE Key_name = 'idx_attendance_updated_at'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE attendance_logs ADD INDEX idx_attendance_updated_at (updated_at)")


def ensure_attendance_unique_student_event(cursor):
    cursor.execute("SHOW INDEX FROM attendance_logs WHERE Key_name = 'uq_attendance_student_event'")
    if cursor.fetchone():
        return

    cursor.execute("""
        SELECT student_id, event_id, COUNT(*) AS duplicate_count
        FROM attendance_logs
        GROUP BY student_id, event_id
        HAVING duplicate_count > 1
        LIMIT 1
    """)
    duplicate = cursor.fetchone()
    if duplicate:
        raise RuntimeError(
            "Cannot add unique attendance constraint because duplicate "
            f"records exist for student_id={duplicate['student_id']} "
            f"and event_id={duplicate['event_id']}."
        )

    cursor.execute("""
        ALTER TABLE attendance_logs
        ADD UNIQUE KEY uq_attendance_student_event (student_id, event_id)
    """)


def ensure_attendance_event_log_index(cursor):
    cursor.execute("SHOW INDEX FROM attendance_logs WHERE Key_name = 'idx_attendance_event_log'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE attendance_logs ADD INDEX idx_attendance_event_log (event_id, log_id)")


def generate_scanner_code(cursor, length=6):
    """Generate a unique numeric code not already assigned to a scanner."""
    while True:
        code = ''.join(random.choices(string.digits, k=length))
        cursor.execute("SELECT scanner_id FROM scanners WHERE scan_code = %s", (code,))
        if not cursor.fetchone():
            return code


def run_startup_migrations():
    """One-time schema check/migration, run once when the app boots instead
    of on every /scan, /dashboard, /events, etc. request."""
    conn = db_pool.connection()
    cursor = conn.cursor()
    try:
        ensure_events_course_column(cursor)
        ensure_stations_college_column(cursor)
        ensure_scanners_table(cursor)
        ensure_attendance_scanner_columns(cursor)
        ensure_attendance_entry_method_columns(cursor)
        ensure_attendance_updated_at_column(cursor)
        ensure_attendance_unique_student_event(cursor)
        ensure_attendance_event_log_index(cursor)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


run_startup_migrations()


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
            'generated_at': local_now().isoformat(timespec='seconds'),
            'colleges': serialize_backup_rows(fetch_backup_rows(cursor, 'colleges', 'college_id')),
            'courses': serialize_backup_rows(fetch_backup_rows(cursor, 'courses', 'course_id')),
            'students': serialize_backup_rows(fetch_backup_rows(cursor, 'students', 'student_id')),
            'stations': serialize_backup_rows(fetch_backup_rows(cursor, 'stations', 'station_id')),
            'events': serialize_backup_rows(fetch_backup_rows(cursor, 'events', 'event_id')),
            'scanners': serialize_backup_rows(fetch_backup_rows(cursor, 'scanners', 'scanner_id')),
            'attendance_logs': serialize_backup_rows(fetch_backup_rows(cursor, 'attendance_logs', 'log_id')),
        }
        return payload
    finally:
        cursor.close()
        db.close()


def import_backup_payload(payload):
    db = get_direct_db()
    cursor = db.cursor()

    table_specs = [
        ('colleges', ['college_id', 'college_code', 'college_name'], 'college_id'),
        ('courses', ['course_id', 'course_code', 'course_name', 'major', 'college_id'], 'course_id'),
        ('students', ['student_id', 'full_name', 'course_id', 'year_level', 'section'], 'student_id'),
        ('stations', ['station_id', 'station_name', 'college_id', 'course_id'], 'station_id'),
        ('events', ['event_id', 'event_name', 'event_date', 'time_in_cutoff', 'time_out_start', 'course_id', 'is_active'], 'event_id'),
        ('scanners', ['scanner_id', 'full_name', 'scan_code', 'is_active', 'created_at'], 'scanner_id'),
        ('attendance_logs', ['log_id', 'student_id', 'event_id', 'station_id', 'scanner_id', 'entry_method', 'time_in', 'time_out', 'time_out_scanner_id', 'time_out_entry_method', 'status'], 'log_id'),
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

    college_id = data.get('college_id')
    course_id = data.get('course_id')

    if college_id is None and course_id is not None:
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                "SELECT c.college_id, col.college_code, col.college_name FROM courses c JOIN colleges col ON c.college_id = col.college_id WHERE c.course_id = %s",
                (course_id,)
            )
            course = cursor.fetchone()
            if course:
                college_id = course['college_id']
                session['college_code'] = course['college_code']
                session['college_name'] = course['college_name']
        finally:
            cursor.close()
            db.close()

    session['college_id'] = college_id
    session['course_id'] = course_id
    return jsonify({'success': True})

@app.route('/station/logout') # Fully clears the station + scanner session
def station_logout():
    for key in ('station_id', 'station_name', 'college_id', 'college_code',
                'college_name', 'course_id', 'scanner_id', 'scanner_name'):
        session.pop(key, None)
    return redirect(url_for('index'))

# ─── Scanner (person-in-charge) authentication ─────────────────────
@app.route('/scanner/login', methods=['GET', 'POST'])
def scanner_login():
    if 'station_id' not in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        code = (data.get('code') or '').strip()

        if not code:
            return jsonify({'success': False, 'message': 'Please enter your scanner code.'})

        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                "SELECT scanner_id, full_name, is_active FROM scanners WHERE scan_code = %s",
                (code,)
            )
            scanner_row = cursor.fetchone()
        finally:
            cursor.close()
            db.close()

        if not scanner_row or not scanner_row['is_active']:
            return jsonify({'success': False, 'message': 'Invalid or inactive scanner code.'})

        session['scanner_id']   = scanner_row['scanner_id']
        session['scanner_name'] = scanner_row['full_name']
        return jsonify({'success': True})

    return render_template('scanner_login.html', station_name=session.get('station_name'))

@app.route('/scanner/logout') # Lets a different person take over scanning without re-picking the station
def scanner_logout():
    session.pop('scanner_id', None)
    session.pop('scanner_name', None)
    return redirect(url_for('scanner_login'))

@app.route('/scanner') # Scanner route (for scanning student IDs)
def scanner():  # Scanner function
    if 'station_id' not in session:
        return redirect(url_for('index'))
    if 'scanner_id' not in session:
        return redirect(url_for('scanner_login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM events WHERE is_active = 1 LIMIT 1")
    event = cursor.fetchone()
    cursor.close()
    db.close()
    return render_template('scanner.html',
        station_name=session['station_name'],
        scanner_name=session.get('scanner_name'),
        event=event
    )

@app.route('/scan', methods=['POST']) # Scan route (for processing student ID scans)
def scan(): # Scan function
    if 'station_id' not in session:
        return jsonify({'success': False, 'message': 'No station logged in'})
    if 'scanner_id' not in session:
        return jsonify({'success': False, 'message': 'Scanner not verified. Please re-enter your scanner code.'})

    data          = request.get_json()
    student_id    = data.get('student_id', '').strip()
    scan_mode     = data.get('scan_mode', 'IN')
    # 'scan' = read by the camera, 'manual' = typed in by the scanner-in-charge
    # when the camera can't read a code. Anything unrecognized falls back to
    # 'scan' so a malformed/missing value can never masquerade as a manual
    # override on the record.
    entry_method  = data.get('entry_method', 'scan')
    if entry_method not in ('scan', 'manual'):
        entry_method = 'scan'

    if not student_id:
        return jsonify({'success': False, 'message': 'No student ID received'})

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("""
            SELECT e.*, c.course_code AS event_course_code
            FROM events e
            LEFT JOIN courses c ON e.course_id = c.course_id
            WHERE e.is_active = 1
            LIMIT 1
        """)
        event = cursor.fetchone()

        if not event:
            return jsonify({'success': False, 'message': 'No active event. Please contact admin.'})

        cursor.execute("""
             SELECT s.student_id, s.full_name, s.course_id, s.section,
                 s.year_level, c.course_code, c.college_id, col.college_code, col.college_name
            FROM students s
            JOIN courses c    ON s.course_id  = c.course_id
            JOIN colleges col ON c.college_id = col.college_id
            WHERE s.student_id = %s
        """, (student_id,))
        student = cursor.fetchone()

        if not student:
            return jsonify({'success': False, 'message': 'Student not found'})

        station_college_id = session.get('college_id')
        station_course_id = session.get('course_id')

        if station_college_id is not None:
            if student['college_id'] != station_college_id:
                return jsonify({'success': False,
                    'message': f"Wrong station! This student belongs to {student['college_code']}"
                })
        elif station_course_id is not None and student['course_id'] != station_course_id:
            return jsonify({'success': False,
                'message': f"Wrong station! This student belongs to {student['course_code']}"
            })

        if event.get('course_id') and student['course_id'] != event['course_id']:
            return jsonify({'success': False,
                'message': f"This event is only for {event['event_course_code']} students."
            })

        now          = local_now()
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
                SET time_out = %s, time_out_scanner_id = %s, time_out_entry_method = %s
                WHERE student_id = %s AND event_id = %s
            """, (current_time, session['scanner_id'], entry_method, student_id, event['event_id']))
            db.commit()
            return jsonify({
                'success': True,
                'scan_type': 'OUT',
                'student_name': student['full_name'],
                'status': existing['status'],
                'time': now.strftime('%I:%M %p'),
                'entry_method': entry_method
            })

        time_in_cutoff = td_to_str(event['time_in_cutoff'])
        status = 'Present' if current_time <= time_in_cutoff else 'Late'

        cursor.execute("""
            INSERT INTO attendance_logs
            (student_id, event_id, station_id, scanner_id, entry_method, time_in, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            student_id, event['event_id'],
            session['station_id'], session['scanner_id'], entry_method, current_time, status
        ))
        db.commit()

        return jsonify({
            'success': True,
            'scan_type': 'IN',
            'student_name': student['full_name'],
            'status': status,
            'time': now.strftime('%I:%M %p'),
            'entry_method': entry_method
        })

    except pymysql.err.IntegrityError as e:
        db.rollback()
        if e.args and e.args[0] == 1062:
            return jsonify({'success': False, 'message': 'Student already scanned for this event'})
        return jsonify({'success': False, 'message': str(e)})
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
        SELECT MIN(st.station_id) AS station_id,
               CONCAT(col.college_code, ' Department') AS station_name,
               col.college_id,
               col.college_code,
               col.college_name
        FROM stations st
        JOIN colleges col ON st.college_id = col.college_id
        GROUP BY col.college_id, col.college_code, col.college_name
        ORDER BY col.college_code
    """)
    stations = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(stations)

# ─── Admin Routes (login required) ────────────────────────────────
DASHBOARD_PAGE_SIZE = 50


def parse_positive_int(value, default=1):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def fetch_active_event(cursor):
    cursor.execute("""
        SELECT event_id, event_name, event_date, course_id
        FROM events
        WHERE is_active = 1
        ORDER BY event_id DESC
        LIMIT 1
    """)
    return cursor.fetchone()


def fetch_dashboard_logs(cursor, event_id, page=1, limit=DASHBOARD_PAGE_SIZE):
    if not event_id:
        return []

    offset = (page - 1) * limit
    query = """
        SELECT a.log_id, s.full_name, s.student_id, s.section, s.year_level,
               col.college_code,
               e.event_name,
               TIME_FORMAT(a.time_in,  '%%H:%%i:%%s') as time_in,
               TIME_FORMAT(a.time_out, '%%H:%%i:%%s') as time_out,
               a.status,
               sc_in.full_name  AS scanned_in_by,
               sc_out.full_name AS scanned_out_by,
               a.entry_method,
               a.time_out_entry_method,
               CAST(UNIX_TIMESTAMP(a.updated_at) AS DECIMAL(16, 6)) AS updated_at_ts
        FROM attendance_logs a
        JOIN students s   ON a.student_id = s.student_id
        JOIN courses c    ON s.course_id  = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        JOIN events e     ON a.event_id   = e.event_id
        LEFT JOIN scanners sc_in  ON a.scanner_id = sc_in.scanner_id
        LEFT JOIN scanners sc_out ON a.time_out_scanner_id = sc_out.scanner_id
        WHERE a.event_id = %s
        ORDER BY a.log_id DESC
        LIMIT %s OFFSET %s
    """
    cursor.execute(query, (event_id, limit, offset))
    return cursor.fetchall()


def fetch_dashboard_summary(cursor, active_event, colleges):
    college_stats = {
        college['college_code']: {'college_code': college['college_code'], 'expected': 0, 'scans': 0}
        for college in colleges
    }
    summary = {
        'expected_scans': 0,
        'total_logs': 0,
        'absent_scans': 0,
        'college_stats': list(college_stats.values()),
    }

    if not active_event:
        return summary

    student_where = ""
    student_params = []
    if active_event.get('course_id'):
        student_where = "WHERE s.course_id = %s"
        student_params.append(active_event['course_id'])

    cursor.execute(f"""
        SELECT col.college_code, COUNT(*) AS expected
        FROM students s
        JOIN courses c    ON s.course_id = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        {student_where}
        GROUP BY col.college_code
    """, student_params)
    for row in cursor.fetchall():
        if row['college_code'] in college_stats:
            college_stats[row['college_code']]['expected'] = row['expected']

    cursor.execute("""
        SELECT col.college_code, COUNT(a.log_id) AS scans
        FROM attendance_logs a
        JOIN students s   ON a.student_id = s.student_id
        JOIN courses c    ON s.course_id = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        WHERE a.event_id = %s
        GROUP BY col.college_code
    """, (active_event['event_id'],))
    for row in cursor.fetchall():
        if row['college_code'] in college_stats:
            college_stats[row['college_code']]['scans'] = row['scans']

    summary['expected_scans'] = sum(row['expected'] for row in college_stats.values())
    summary['total_logs'] = sum(row['scans'] for row in college_stats.values())
    summary['absent_scans'] = max(0, summary['expected_scans'] - summary['total_logs'])
    summary['college_stats'] = list(college_stats.values())
    return summary


@app.route('/dashboard')
@login_required
def dashboard():
    page = parse_positive_int(request.args.get('page'), 1)
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM colleges ORDER BY college_code")
    colleges = cursor.fetchall()
    active_event = fetch_active_event(cursor)
    summary = fetch_dashboard_summary(cursor, active_event, colleges)
    page_count = max(1, (summary['total_logs'] + DASHBOARD_PAGE_SIZE - 1) // DASHBOARD_PAGE_SIZE)
    if page > page_count:
        page = page_count
    logs = fetch_dashboard_logs(
        cursor,
        active_event['event_id'] if active_event else None,
        page=page,
        limit=DASHBOARD_PAGE_SIZE,
    )
    cursor.close()
    db.close()
    return render_template('dashboard.html', logs=logs, active_event=active_event, colleges=colleges,
                           expected_scans=summary['expected_scans'],
                           total_logs=summary['total_logs'],
                           absent_scans=summary['absent_scans'],
                           dashboard_college_stats=summary['college_stats'],
                           current_page=page,
                           page_count=page_count,
                           page_size=DASHBOARD_PAGE_SIZE,
                           has_prev=page > 1,
                           has_next=page < page_count,
                           lan_ips=get_lan_ips())

@app.route('/api/dashboard')
@login_required
def dashboard_api():
    page = parse_positive_int(request.args.get('page'), 1)
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT * FROM colleges ORDER BY college_code")
        colleges = cursor.fetchall()
        active_event = fetch_active_event(cursor)
        summary = fetch_dashboard_summary(cursor, active_event, colleges)
        page_count = max(1, (summary['total_logs'] + DASHBOARD_PAGE_SIZE - 1) // DASHBOARD_PAGE_SIZE)
        if page > page_count:
            page = page_count
        logs = fetch_dashboard_logs(
            cursor,
            active_event['event_id'] if active_event else None,
            page=page,
            limit=DASHBOARD_PAGE_SIZE,
        )
        return jsonify({
            'logs': logs,
            'active_event': active_event,
            'expected_scans': summary['expected_scans'],
            'total_logs': summary['total_logs'],
            'absent_scans': summary['absent_scans'],
            'college_stats': summary['college_stats'],
            'page': page,
            'page_count': page_count,
            'page_size': DASHBOARD_PAGE_SIZE,
            'has_prev': page > 1,
            'has_next': page < page_count,
        })
    finally:
        cursor.close()
        db.close()

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
    cursor.execute("""
        SELECT s.student_id, s.full_name, s.section, s.year_level,
               c.course_code, col.college_code
        FROM students s
        JOIN courses c    ON s.course_id  = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        ORDER BY s.full_name
    """)
    students = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('absences.html', events=events, colleges=colleges, courses=courses, students=students)

@app.route('/api/student-attendance')
@login_required
def student_attendance_api():
    student_id = request.args.get('student_id', '').strip()
    if not student_id:
        return jsonify({'student': None, 'records': []})

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT s.student_id, s.full_name, s.section, s.year_level,
                   c.course_id, c.course_code, col.college_code
            FROM students s
            JOIN courses c    ON s.course_id  = c.course_id
            JOIN colleges col ON c.college_id = col.college_id
            WHERE s.student_id = %s
        """, (student_id,))
        student = cursor.fetchone()

        if not student:
            return jsonify({'student': None, 'records': []})

        cursor.execute("""
            SELECT e.event_id, e.event_name, e.event_date,
                   TIME_FORMAT(a.time_in,  '%%H:%%i:%%s') AS time_in,
                   TIME_FORMAT(a.time_out, '%%H:%%i:%%s') AS time_out,
                   CASE WHEN a.log_id IS NULL THEN 'Absent' ELSE a.status END AS status,
                   sc_in.full_name  AS scanned_in_by,
                   sc_out.full_name AS scanned_out_by,
                   a.entry_method,
                   a.time_out_entry_method
            FROM events e
            LEFT JOIN attendance_logs a ON a.event_id = e.event_id AND a.student_id = %s
            LEFT JOIN scanners sc_in  ON a.scanner_id = sc_in.scanner_id
            LEFT JOIN scanners sc_out ON a.time_out_scanner_id = sc_out.scanner_id
            WHERE (e.course_id IS NULL OR e.course_id = %s)
            ORDER BY e.event_date DESC
        """, (student_id, student['course_id']))
        records = cursor.fetchall()

        return jsonify({'student': student, 'records': records})
    finally:
        cursor.close()
        db.close()

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
               c.course_code, col.college_code,
               CASE WHEN a.log_id IS NULL THEN 'Absent' ELSE 'Present' END as status,
               sc_in.full_name  AS scanned_in_by,
               sc_out.full_name AS scanned_out_by,
               a.entry_method,
               a.time_out_entry_method
        FROM students s
        JOIN courses c    ON s.course_id  = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        JOIN events e     ON e.event_id = %s
        LEFT JOIN attendance_logs a ON a.student_id = s.student_id
                                   AND a.event_id = e.event_id
        LEFT JOIN scanners sc_in  ON a.scanner_id = sc_in.scanner_id
        LEFT JOIN scanners sc_out ON a.time_out_scanner_id = sc_out.scanner_id
        WHERE (e.course_id IS NULL OR e.course_id = s.course_id)
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

    query = """
        SELECT s.student_id, s.full_name, s.section, s.year_level,
               c.course_code, col.college_code,
               COUNT(a.log_id) as attended,
               COUNT(e.event_id) - COUNT(a.log_id) as absences,
               COUNT(e.event_id) as total_events,
               COALESCE(
                   GROUP_CONCAT(
                       DISTINCT CASE WHEN a.log_id IS NULL THEN CONCAT(e.event_name, ' (', e.event_date, ')') END
                       ORDER BY e.event_date
                       SEPARATOR '\n'
                   ),
                   ''
               ) as absent_events
        FROM students s
        JOIN courses c    ON s.course_id  = c.course_id
        JOIN colleges col ON c.college_id = col.college_id
        LEFT JOIN events e ON e.course_id IS NULL OR e.course_id = s.course_id
        LEFT JOIN attendance_logs a ON s.student_id = a.student_id
                                  AND a.event_id = e.event_id
        WHERE 1=1
    """
    params = []

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
    total_events = students[0]['total_events'] if students else 0
    cursor.close()
    db.close()

    return jsonify({'total_events': total_events, 'students': students})



@app.route('/backup')
@login_required
def backup():
    db = get_db()
    cursor = db.cursor()
    colleges_total = courses_total = students_total = stations_total = events_total = scanners_total = logs_total = 0
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
        cursor.execute("SELECT COUNT(*) as total FROM scanners")
        scanners_total = cursor.fetchone()['total']
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
        scanners_total=scanners_total,
        logs_total=logs_total,
    )


@app.route('/api/backup/export')
@login_required
def export_backup():
    payload = build_backup_payload()
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode('utf-8')
    filename = f"attendance_backup_{local_now().strftime('%Y%m%d_%H%M%S')}.json"
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
    cursor.execute("""
        SELECT e.*, c.course_code
        FROM events e
        LEFT JOIN courses c ON e.course_id = c.course_id
        ORDER BY e.event_date DESC
    """)
    events = cursor.fetchall()
    cursor.execute("""
        SELECT c.course_id, c.course_code, col.college_code
        FROM courses c
        JOIN colleges col ON c.college_id = col.college_id
        ORDER BY col.college_code, c.course_code
    """)
    courses = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('events.html', events=events, courses=courses)

@app.route('/api/events/create', methods=['POST'])
@login_required
def create_event():
    data = request.get_json() or {}
    db = get_db()
    cursor = db.cursor()
    try:
        course_id = data.get('course_id') or None
        if course_id is not None:
            cursor.execute("SELECT course_id FROM courses WHERE course_id = %s", (course_id,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'message': 'Selected course was not found.'}), 400

        cursor.execute("""
            INSERT INTO events (event_name, event_date, time_in_cutoff, time_out_start, course_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            data['event_name'], data['event_date'],
            data['time_in_cutoff'], data['time_out_start'], course_id
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

@app.route('/scanners')
@login_required
def scanners():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT sc.scanner_id, sc.full_name, sc.scan_code, sc.is_active, sc.created_at,
               COUNT(a.log_id) AS scans_done,
               SUM(CASE WHEN a.scanner_id = sc.scanner_id AND a.entry_method = 'manual' THEN 1 ELSE 0 END)
             + SUM(CASE WHEN a.time_out_scanner_id = sc.scanner_id AND a.time_out_entry_method = 'manual' THEN 1 ELSE 0 END)
               AS manual_entries
        FROM scanners sc
        LEFT JOIN attendance_logs a
               ON a.scanner_id = sc.scanner_id OR a.time_out_scanner_id = sc.scanner_id
        GROUP BY sc.scanner_id, sc.full_name, sc.scan_code, sc.is_active, sc.created_at
        ORDER BY sc.full_name
    """)
    scanner_list = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('scanners.html', scanners=scanner_list)

@app.route('/api/scanners/add', methods=['POST'])
@login_required
def add_scanner():
    data = request.get_json(silent=True) or {}
    full_name = (data.get('full_name') or '').strip()
    if not full_name:
        return jsonify({'success': False, 'message': 'Full name is required.'})

    db = get_db()
    cursor = db.cursor()
    try:
        code = generate_scanner_code(cursor)
        cursor.execute(
            "INSERT INTO scanners (full_name, scan_code) VALUES (%s, %s)",
            (full_name, code)
        )
        db.commit()
        return jsonify({'success': True, 'scanner_id': cursor.lastrowid,
                        'scan_code': code, 'full_name': full_name})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/scanners/update', methods=['POST'])
@login_required
def update_scanner():
    data = request.get_json(silent=True) or {}
    scanner_id = data.get('scanner_id')
    full_name  = (data.get('full_name') or '').strip()
    if not scanner_id or not full_name:
        return jsonify({'success': False, 'message': 'Scanner ID and full name are required.'})

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "UPDATE scanners SET full_name = %s WHERE scanner_id = %s",
            (full_name, scanner_id)
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/scanners/regenerate-code', methods=['POST'])
@login_required
def regenerate_scanner_code():
    data = request.get_json(silent=True) or {}
    scanner_id = data.get('scanner_id')
    if not scanner_id:
        return jsonify({'success': False, 'message': 'Scanner ID is required.'})

    db = get_db()
    cursor = db.cursor()
    try:
        code = generate_scanner_code(cursor)
        cursor.execute(
            "UPDATE scanners SET scan_code = %s WHERE scanner_id = %s",
            (code, scanner_id)
        )
        db.commit()
        return jsonify({'success': True, 'scan_code': code})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/scanners/toggle', methods=['POST'])
@login_required
def toggle_scanner():
    data = request.get_json(silent=True) or {}
    scanner_id = data.get('scanner_id')
    if not scanner_id:
        return jsonify({'success': False, 'message': 'Scanner ID is required.'})

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "UPDATE scanners SET is_active = NOT is_active WHERE scanner_id = %s",
            (scanner_id,)
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/api/scanners/delete', methods=['POST'])
@login_required
def delete_scanner():
    data = request.get_json(silent=True) or {}
    scanner_id = data.get('scanner_id')
    if not scanner_id:
        return jsonify({'success': False, 'message': 'Scanner ID is required.'})

    db = get_db()
    cursor = db.cursor()
    try:
        # Historical logs keep the numeric scanner_id even after the scanner
        # profile is deleted, so past "scanned by" records aren't lost —
        # they'll just show as "Unknown scanner" once the name is gone.
        cursor.execute("DELETE FROM scanners WHERE scanner_id = %s", (scanner_id,))
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

        for i, row in enumerate(reader, start=1):
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
                db.commit()
                inserted += 1
            except Exception as e:
                db.rollback()
                skipped += 1
                errors.append(f"Row {i}: {str(e)}")
                continue
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
    app.run(host='0.0.0.0', port=5000, ssl_context='adhoc', threaded=True)