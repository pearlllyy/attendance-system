-- -- NEW SCHEMA DESIGN ----------

-- -- Courses Table
-- CREATE TABLE courses (
--     course_id INT AUTO_INCREMENT PRIMARY KEY,
--     course_code VARCHAR(20) NOT NULL,
--     course_name VARCHAR(100) NOT NULL
-- );

-- -- Students Table
-- CREATE TABLE students (
--     student_id VARCHAR(20) PRIMARY KEY,
--     full_name VARCHAR(100) NOT NULL,
--     course_id INT NOT NULL,
--     year_level INT NOT NULL,
--     section VARCHAR(10) NOT NULL,
--     FOREIGN KEY (course_id) REFERENCES courses(course_id)
-- );

-- -- Events Table
-- CREATE TABLE events (
--     event_id INT AUTO_INCREMENT PRIMARY KEY,
--     event_name VARCHAR(100) NOT NULL,
--     event_date DATE NOT NULL,
--     time_in_cutoff TIME NOT NULL,
--     time_out_start TIME NOT NULL,
--     course_id INT DEFAULT NULL,
--     is_active TINYINT DEFAULT 0,
--     FOREIGN KEY (course_id) REFERENCES courses(course_id)
-- );

-- -- Stations Table
-- CREATE TABLE stations (
--     station_id INT AUTO_INCREMENT PRIMARY KEY,
--     station_name VARCHAR(50) NOT NULL,
--     course_id INT NOT NULL,
--     FOREIGN KEY (course_id) REFERENCES courses(course_id)
-- );

-- -- Attendance Logs Table
-- CREATE TABLE attendance_logs (
--     log_id INT AUTO_INCREMENT PRIMARY KEY,
--     student_id VARCHAR(20) NOT NULL,
--     event_id INT NOT NULL,
--     station_id INT NOT NULL,
--     time_in TIME DEFAULT NULL,
--     time_out TIME DEFAULT NULL,
--     status ENUM('Present', 'Late', 'Absent') NOT NULL DEFAULT 'Present',
--     FOREIGN KEY (student_id) REFERENCES students(student_id),
--     FOREIGN KEY (event_id) REFERENCES events(event_id),
--     FOREIGN KEY (station_id) REFERENCES stations(station_id)
-- );

-- -- - Indexing for Performance -------------
-- ALTER TABLE students ADD INDEX (course_id);
-- ALTER TABLE attendance_logs ADD INDEX (student_id, event_id);
-- ALTER TABLE events ADD INDEX (is_active);

-- ----------- Sample Data Insertion -----------
-- -- Courses
-- INSERT INTO courses (course_code, course_name) VALUES
-- ('BSIT', 'Bachelor of Science in Information Technology'),
-- ('BSCS', 'Bachelor of Science in Computer Science'),
-- ('BSBA', 'Bachelor of Science in Business Administration');

-- -- Students
-- INSERT INTO students (student_id, full_name, course_id, year_level, section) VALUES
-- ('2023-0001', 'Juan Dela Cruz', 1, 2, 'A'),
-- ('2023-0002', 'Maria Santos', 1, 2, 'A'),
-- ('2023-0003', 'Pedro Reyes', 2, 1, 'B'),
-- ('2023-0004', 'Ana Garcia', 1, 3, 'B'),
-- ('2023-0005', 'Jose Rizal', 2, 2, 'A');

-- -- Stations
-- INSERT INTO stations (station_name, course_id) VALUES
-- ('BSIT Station', 1),
-- ('BSCS Station', 2),
-- ('BSBA Station', 3);

-- -- Sample Event
-- INSERT INTO events (event_name, event_date, time_in_cutoff, time_out_start, course_id, is_active) VALUES
-- ('Foundation Day', '2026-05-18', '08:00:00', '17:00:00', NULL, 1);


-- Create and use database
CREATE DATABASE attendance_db;
USE attendance_db;

-- ─── Colleges ─────────────────────────────────────────────
CREATE TABLE colleges (
    college_id   INT AUTO_INCREMENT PRIMARY KEY,
    college_code VARCHAR(20)  NOT NULL,
    college_name VARCHAR(100) NOT NULL
);

-- ─── Courses ──────────────────────────────────────────────
CREATE TABLE courses (
    course_id   INT AUTO_INCREMENT PRIMARY KEY,
    course_code VARCHAR(20)  NOT NULL,
    course_name VARCHAR(100) NOT NULL,
    major       VARCHAR(100) DEFAULT NULL,
    college_id  INT NOT NULL,
    FOREIGN KEY (college_id) REFERENCES colleges(college_id)
);

-- ─── Students ─────────────────────────────────────────────
CREATE TABLE students (
    student_id VARCHAR(20)  PRIMARY KEY,
    full_name  VARCHAR(100) NOT NULL,
    course_id  INT NOT NULL,
    year_level INT NOT NULL,
    section    VARCHAR(10)  NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

-- ─── Stations ─────────────────────────────────────────────
CREATE TABLE stations (
    station_id   INT AUTO_INCREMENT PRIMARY KEY,
    station_name VARCHAR(50) NOT NULL,
    course_id    INT NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

-- ─── Events ───────────────────────────────────────────────
CREATE TABLE events (
    event_id       INT AUTO_INCREMENT PRIMARY KEY,
    event_name     VARCHAR(100) NOT NULL,
    event_date     DATE         NOT NULL,
    time_in_cutoff TIME         NOT NULL,
    time_out_start TIME         NOT NULL,
    is_active      TINYINT      DEFAULT 0
);

-- ─── Attendance Logs ──────────────────────────────────────
CREATE TABLE attendance_logs (
    log_id     INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    event_id   INT         NOT NULL,
    station_id INT         NOT NULL,
    time_in    TIME        DEFAULT NULL,
    time_out   TIME        DEFAULT NULL,
    status     ENUM('Present', 'Late', 'Absent') NOT NULL DEFAULT 'Present',
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (event_id)   REFERENCES events(event_id),
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
);

-- ─── Indexes ──────────────────────────────────────────────
ALTER TABLE students       ADD INDEX (course_id);
ALTER TABLE courses        ADD INDEX (college_id);
ALTER TABLE attendance_logs ADD INDEX (student_id, event_id);
ALTER TABLE events         ADD INDEX (is_active);

-- ─── Colleges Data ────────────────────────────────────────
INSERT INTO colleges (college_code, college_name) VALUES
('SICT', 'School of Information and Communication Technology'),
('CBM',  'College of Business and Management'),
('COE',  'College of Education'),
('SOA',  'School of Agriculture');

-- ─── Courses Data ─────────────────────────────────────────
INSERT INTO courses (course_code, course_name, major, college_id) VALUES
-- SICT
('BSIT', 'Bachelor of Science in Information Technology', NULL, 1),
-- CBM
('BSHM', 'Bachelor of Science in Hospitality Management', NULL, 2),
('BSE',  'Bachelor of Science in Entrepreneurship',       NULL, 2),
('BSOA', 'Bachelor of Science in Office Administration',  NULL, 2),
-- COE
('BSEd', 'Bachelor of Secondary Education',               NULL, 3),
('BEEd', 'Bachelor of Elementary Education',              NULL, 3),
-- SOA
('BSA',  'Bachelor of Science in Agriculture',            NULL, 4);

-- ─── Stations Data ────────────────────────────────────────
INSERT INTO stations (station_name, course_id) VALUES
('BSIT Station', 1),
('BSHM Station', 2),
('BSE Station',  3),
('BSOA Station', 4),
('BSEd Station', 5),
('BEEd Station', 6),
('BSA Station',  7);

-- ─── Sample Event ─────────────────────────────────────────
INSERT INTO events (event_name, event_date, time_in_cutoff, time_out_start, is_active) VALUES
('Foundation Day', CURDATE(), '08:00:00', '17:00:00', 0);

-- ─── Sample Students ──────────────────────────────────────
INSERT INTO students (student_id, full_name, course_id, year_level, section) VALUES
('2023-0001', 'Juan Dela Cruz',  1, 2, 'A'),
('2023-0002', 'Maria Santos',    1, 2, 'A'),
('2023-0003', 'Pedro Reyes',     2, 1, 'B'),
('2023-0004', 'Ana Garcia',      3, 2, 'A'),
('2023-0005', 'Jose Rizal',      5, 1, 'A');