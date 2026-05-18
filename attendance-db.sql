
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