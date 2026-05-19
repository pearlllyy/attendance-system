CREATE DATABASE attendance_db;
USE attendance_db;

-- Pwede ja halin diya asta sa dalom i copy paste para isa lang --
CREATE TABLE courses (
    course_id INT AUTO_INCREMENT PRIMARY KEY,
    course_code VARCHAR(20) NOT NULL,
    course_name VARCHAR(100) NOT NULL
);

CREATE TABLE students (
    student_id VARCHAR(20) PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    course_id INT NOT NULL,
    year_level INT NOT NULL,
    section VARCHAR(10) NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

CREATE TABLE stations (
    station_id INT AUTO_INCREMENT PRIMARY KEY,
    station_name VARCHAR(50) NOT NULL,
    course_id INT NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

CREATE TABLE attendance_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    station_id INT NOT NULL,
    scan_date DATE NOT NULL,
    scan_time TIME NOT NULL,
    status ENUM('Present', 'Late') NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
);

ALTER TABLE students ADD INDEX (course_id);
ALTER TABLE attendance_logs ADD INDEX (student_id, scan_date);
-- asta di--

-- lain nga code block naman ja --
INSERT INTO courses (course_code, course_name) VALUES
('BSIT', 'Bachelor of Science in Information Technology'),
('BSCS', 'Bachelor of Science in Computer Science'),
('BSBA', 'Bachelor of Science in Business Administration');

INSERT INTO stations (station_name, course_id) VALUES
('BSIT Station', 1),
('BSCS Station', 2),
('BSBA Station', 3);

INSERT INTO students (student_id, full_name, course_id, year_level, section) VALUES
('2023-0001', 'Juan Dela Cruz', 1, 2, 'A'),
('2023-0002', 'Maria Santos', 1, 2, 'A'),
('2023-0003', 'Pedro Reyes', 2, 1, 'B');
-- asta di --



---------- NEW SCHEMA DESIGN ----------

-- Courses Table
CREATE TABLE courses (
    course_id INT AUTO_INCREMENT PRIMARY KEY,
    course_code VARCHAR(20) NOT NULL,
    course_name VARCHAR(100) NOT NULL
);

-- Students Table
CREATE TABLE students (
    student_id VARCHAR(20) PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    course_id INT NOT NULL,
    year_level INT NOT NULL,
    section VARCHAR(10) NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

-- Events Table
CREATE TABLE events (
    event_id INT AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(100) NOT NULL,
    event_date DATE NOT NULL,
    time_in_cutoff TIME NOT NULL,
    time_out_start TIME NOT NULL,
    course_id INT DEFAULT NULL,
    is_active TINYINT DEFAULT 0,
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

-- Stations Table
CREATE TABLE stations (
    station_id INT AUTO_INCREMENT PRIMARY KEY,
    station_name VARCHAR(50) NOT NULL,
    course_id INT NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

-- Attendance Logs Table
CREATE TABLE attendance_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    event_id INT NOT NULL,
    station_id INT NOT NULL,
    time_in TIME DEFAULT NULL,
    time_out TIME DEFAULT NULL,
    status ENUM('Present', 'Late', 'Absent') NOT NULL DEFAULT 'Present',
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
);

------------- Indexing for Performance -------------
ALTER TABLE students ADD INDEX (course_id);
ALTER TABLE attendance_logs ADD INDEX (student_id, event_id);
ALTER TABLE events ADD INDEX (is_active);

----------- Sample Data Insertion -----------
-- Courses
INSERT INTO courses (course_code, course_name) VALUES
('BSIT', 'Bachelor of Science in Information Technology'),
('BSCS', 'Bachelor of Science in Computer Science'),
('BSBA', 'Bachelor of Science in Business Administration');

-- Students
INSERT INTO students (student_id, full_name, course_id, year_level, section) VALUES
('2023-0001', 'Juan Dela Cruz', 1, 2, 'A'),
('2023-0002', 'Maria Santos', 1, 2, 'A'),
('2023-0003', 'Pedro Reyes', 2, 1, 'B'),
('2023-0004', 'Ana Garcia', 1, 3, 'B'),
('2023-0005', 'Jose Rizal', 2, 2, 'A');

-- Stations
INSERT INTO stations (station_name, course_id) VALUES
('BSIT Station', 1),
('BSCS Station', 2),
('BSBA Station', 3);

-- Sample Event
INSERT INTO events (event_name, event_date, time_in_cutoff, time_out_start, course_id, is_active) VALUES
('Foundation Day', '2026-05-18', '08:00:00', '17:00:00', NULL, 1);