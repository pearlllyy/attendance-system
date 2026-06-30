import os
from dotenv import load_dotenv

load_dotenv()  # reads variables from a local .env file into the environment


class Config:
    # Database settings
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'attendance_db')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))

    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # Attendance cutoff time (24hr format)
    # Students who scan after this time will be marked Late
    CUTOFF_HOUR = int(os.environ.get('CUTOFF_HOUR', 8))
    CUTOFF_MINUTE = int(os.environ.get('CUTOFF_MINUTE', 0))

    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')

    # Fail loudly if required secrets are missing, instead of running insecurely
    if not SECRET_KEY:
        raise RuntimeError('SECRET_KEY environment variable is not set. Check your .env file.')
