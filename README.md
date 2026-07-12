# Attendance System

**Smart Attendance Monitoring System using Mobile Barcode Scanning**

A web-based attendance management system built with Flask. The app lets instructors and staff run station-based scanners (mobile browsers) to record student attendance for events, classes, and other sessions.

**Quick summary**
- **Scanner:** Mobile browser-based scanner using the included `static/html5-qrcode.min.js`.
- **Backend:** Flask app in `app.py`.
- **Database:** MySQL (schema provided in `attendance-db.sql`).
- **Deployment:** Runs locally or via Docker using `Containerfile` / `compose.yaml`.

**Key features**
- **Station-based login:** Assign scanning stations per course or room.
- **Time In / Time Out:** Tracks session start/end with validation.
- **Absent detection with Penalty Calculation:** Marks entries as Present/Absent based on configured cutoff and automatically calculate absents' penalty/ies.
- **Real-time feedback:** Displays student name and status after a scan.
- **Admin dashboard & reports:** View attendance logs, absences, and filterable reports.

**Prerequisites**
- Python 3.10+ and `pip` for local runs, or Docker/Podman for containerized runs.
- MySQL or compatible server accessible to the app (or run the app against an existing DB).
``

**Configuration**
- Edit `config.py` to set database connection, secret keys, and environment-specific settings.
- Environment variables can be used by the containerized deployment (see `compose.yaml`).

**Database & Backup**
- The SQL schema is in `attendance-db.sql`.
- Use the provided `backup.html` UI or run a mysqldump to create backups.

**Project layout**
- `app.py`: Flask application entry point
- `config.py`: Application configuration (DB credentials, settings)
- `attendance-db.sql`: Database schema and initial SQL
- `requirements.txt`: Python dependencies
- `Containerfile`, `compose.yaml`, `entrypoint.sh`: Container deployment files
- `templates/`: HTML templates (dashboard, scanner, admin views)
- `static/`: JS/CSS and `html5-qrcode` scanner script

**Development notes**
- `static/script.js` contains scanner integration code using `html5-qrcode`.
- To add a new event or change cutoff rules, update the admin pages and DB records.

**Contributing**
- Open issues or pull requests describing changes. Keep changes focused and include tests where relevant.

**License**
All Rights Reserved © 2026 Pearl S. & Eui-jin B.

This project and all its source code, documentation, database scripts, and related files are the exclusive property of the copyright owners.

No part of this project may be copied, modified, distributed, sublicensed, or used in any form without the explicit written permission of the copyright owners.

For permission requests, please contact the owners directly.
