class Config:
    # Database settings
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = ''        # Leave empty if you haven't set a MySQL password
    MYSQL_DB = 'attendance_db'
    MYSQL_PORT = 3306

    # Flask settings
    SECRET_KEY = 'attendance-system-secret-key'

    # Attendance cutoff time (24hr format)
    # Students who scan after this time will be marked Late
    CUTOFF_HOUR = 8      # 8 AM
    CUTOFF_MINUTE = 0