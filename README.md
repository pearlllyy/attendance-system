# Attendance System

**Smart Attendance Monitoring System using Mobile Barcode Scanner**

A web-based attendance management system built with Flask and MySQL. Designed for educational institutions, it allows multiple scanning stations to efficiently record student attendance using mobile devices as barcode/QR code scanners.

## Features

- **Station-based Login** — Each course/department has its own scanning station
- **Mobile Barcode Scanning** — Use any mobile browser as a scanner (no extra apps needed)
- **Time In / Time Out** — Supports full session tracking with automatic validation
- **Late Detection** — Automatic "Present" / "Late" status based on cutoff time
- **Real-time Feedback** — Instant success/error messages with student name
- **Admin Dashboard** — View all attendance logs
- **Absences Report** — Identify students who didn't attend
- **Flexible Reports** — Filter by event, course, section, status, etc.
- **Multi-Event Support** — Manage multiple events with individual time settings

## Tech Stack

- **Backend**: Python + Flask
- **Database**: MySQL
- **Frontend**: HTML, CSS, JavaScript (with Barcode scanner support)
- **Others**: PyMySQL, Jinja2, XAMPP
