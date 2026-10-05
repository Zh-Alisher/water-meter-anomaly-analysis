-- Mini Product Analytics Case
-- PostgreSQL

-- 1. Payment funnel by unique users
WITH counts AS (
    SELECT
        COUNT(DISTINCT CASE
            WHEN event_name = 'payment_screen' THEN user_id
        END) AS screen_users,
        COUNT(DISTINCT CASE
            WHEN event_name = 'payment_started' THEN user_id
        END) AS started_users,
        COUNT(DISTINCT CASE
            WHEN event_name = 'payment_success' THEN user_id
        END) AS success_users
    FROM events
),
funnel AS (
    SELECT 1 AS step, 'payment_screen' AS stage, screen_users AS users, screen_users AS base
    FROM counts

    UNION ALL

    SELECT 2, 'payment_started', started_users, screen_users
    FROM counts

    UNION ALL

    SELECT 3, 'payment_success', success_users, screen_users
    FROM counts
)
SELECT
    stage,
    users,
    ROUND(100.0 * users / NULLIF(base, 0), 1) AS conversion_from_screen_pct
FROM funnel
ORDER BY step;


-- 1.1 Step conversion: payment_started -> payment_success
WITH counts AS (
    SELECT
        COUNT(DISTINCT CASE
            WHEN event_name = 'payment_started' THEN user_id
        END) AS started_users,
        COUNT(DISTINCT CASE
            WHEN event_name = 'payment_success' THEN user_id
        END) AS success_users
    FROM events
)
SELECT
    started_users,
    success_users,
    ROUND(
        100.0 * success_users / NULLIF(started_users, 0),
        1
    ) AS started_to_success_pct
FROM counts;


-- 2. Success Rate by platform
SELECT
    u.platform,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (WHERE p.status = 'success') AS successful_transactions,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE p.status = 'success')
        / NULLIF(COUNT(*), 0),
        1
    ) AS success_rate_pct
FROM payments p
JOIN users u
    ON u.user_id = p.user_id
GROUP BY u.platform
ORDER BY success_rate_pct DESC;


-- 3. Success Rate by payment method
SELECT
    payment_method,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (WHERE status = 'success') AS successful_transactions,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'success')
        / NULLIF(COUNT(*), 0),
        1
    ) AS success_rate_pct
FROM payments
GROUP BY payment_method
ORDER BY success_rate_pct DESC;


-- 4. Cross-segment check:
-- Is the problem really the platform, or a specific platform + method pair?
SELECT
    u.platform,
    p.payment_method,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (WHERE p.status = 'success') AS successful_transactions,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE p.status = 'success')
        / NULLIF(COUNT(*), 0),
        1
    ) AS success_rate_pct
FROM payments p
JOIN users u
    ON u.user_id = p.user_id
GROUP BY
    u.platform,
    p.payment_method
ORDER BY
    u.platform,
    p.payment_method;


-- 5. Users with repeated failed attempts on the same day
SELECT
    user_id,
    created_at::date AS payment_date,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_attempts,
    BOOL_OR(status = 'success') AS had_success_same_day
FROM payments
GROUP BY
    user_id,
    created_at::date
HAVING COUNT(*) FILTER (WHERE status = 'failed') >= 2
ORDER BY
    failed_attempts DESC,
    user_id;
