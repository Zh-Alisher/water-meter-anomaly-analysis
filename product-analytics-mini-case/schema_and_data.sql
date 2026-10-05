-- Mini Product Analytics Case
-- PostgreSQL
-- Synthetic payment funnel data

DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    user_id INT PRIMARY KEY,
    signup_date DATE NOT NULL,
    platform VARCHAR(20) NOT NULL
);

CREATE TABLE events (
    event_id INT PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id),
    event_time TIMESTAMP NOT NULL,
    event_name VARCHAR(50) NOT NULL
);

CREATE TABLE payments (
    payment_id INT PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    payment_method VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL
);

INSERT INTO users (user_id, signup_date, platform) VALUES
    (1, '2026-09-01', 'iOS'),
    (2, '2026-09-01', 'Android'),
    (3, '2026-09-02', 'iOS'),
    (4, '2026-09-02', 'Android'),
    (5, '2026-09-03', 'Android'),
    (6, '2026-09-03', 'iOS'),
    (7, '2026-09-04', 'iOS'),
    (8, '2026-09-04', 'Android');

INSERT INTO events (event_id, user_id, event_time, event_name) VALUES
    (1, 1, '2026-09-10 10:00:00', 'payment_screen'),
    (2, 1, '2026-09-10 10:01:00', 'payment_started'),
    (3, 1, '2026-09-10 10:02:00', 'payment_success'),

    (4, 2, '2026-09-10 11:00:00', 'payment_screen'),
    (5, 2, '2026-09-10 11:01:00', 'payment_started'),
    (6, 2, '2026-09-10 11:02:00', 'payment_failed'),
    (7, 2, '2026-09-10 11:04:00', 'payment_failed'),
    (8, 2, '2026-09-10 11:06:00', 'payment_success'),

    (9, 3, '2026-09-10 12:00:00', 'payment_screen'),
    (10, 3, '2026-09-10 12:01:00', 'payment_started'),
    (11, 3, '2026-09-10 12:02:00', 'payment_failed'),

    (12, 4, '2026-09-10 13:00:00', 'payment_screen'),
    (13, 4, '2026-09-10 13:01:00', 'payment_started'),
    (14, 4, '2026-09-10 13:02:00', 'payment_success'),

    (15, 5, '2026-09-10 14:00:00', 'payment_screen'),
    (16, 5, '2026-09-10 14:01:00', 'payment_started'),
    (17, 5, '2026-09-10 14:02:00', 'payment_success'),

    (18, 6, '2026-09-10 15:00:00', 'payment_screen'),
    (19, 6, '2026-09-10 15:01:00', 'payment_started'),
    (20, 6, '2026-09-10 15:02:00', 'payment_failed'),
    (21, 6, '2026-09-10 15:04:00', 'payment_failed'),

    (22, 7, '2026-09-10 16:00:00', 'payment_screen'),

    (23, 8, '2026-09-10 17:00:00', 'payment_screen'),
    (24, 8, '2026-09-10 17:01:00', 'payment_started'),
    (25, 8, '2026-09-10 17:02:00', 'payment_success');

INSERT INTO payments (
    payment_id,
    user_id,
    created_at,
    amount,
    payment_method,
    status
) VALUES
    (1, 1, '2026-09-10 10:02:00', 12000.00, 'card', 'success'),

    (2, 2, '2026-09-10 11:02:00', 8500.00, 'card', 'failed'),
    (3, 2, '2026-09-10 11:04:00', 8500.00, 'card', 'failed'),
    (4, 2, '2026-09-10 11:06:00', 8500.00, 'card', 'success'),

    (5, 3, '2026-09-10 12:02:00', 4200.00, 'bank_transfer', 'failed'),

    (6, 4, '2026-09-10 13:02:00', 15700.00, 'card', 'success'),
    (7, 5, '2026-09-10 14:02:00', 6300.00, 'bank_transfer', 'success'),

    (8, 6, '2026-09-10 15:02:00', 9100.00, 'bank_transfer', 'failed'),
    (9, 6, '2026-09-10 15:04:00', 9100.00, 'bank_transfer', 'failed'),

    (10, 8, '2026-09-10 17:02:00', 22000.00, 'card', 'success');
