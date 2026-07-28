import os
from dotenv import load_dotenv

load_dotenv()  # reads variables from a local .env file into the environment


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    # Database settings
    MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'attendance_db')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))

    # Database connection pool settings
    DB_POOL_MINCACHED = env_int('DB_POOL_MINCACHED', 2)
    DB_POOL_MAXCACHED = env_int('DB_POOL_MAXCACHED', 10)
    DB_POOL_MAXCONNECTIONS = env_int('DB_POOL_MAXCONNECTIONS', 30)
    DB_POOL_MAXUSAGE = env_int('DB_POOL_MAXUSAGE', 1000)
    DB_POOL_CONNECT_TIMEOUT = env_int('DB_POOL_CONNECT_TIMEOUT', 5)
    DB_POOL_READ_TIMEOUT = env_int('DB_POOL_READ_TIMEOUT', 15)
    DB_POOL_WRITE_TIMEOUT = env_int('DB_POOL_WRITE_TIMEOUT', 15)

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
