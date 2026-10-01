/*
PostgreSQL examples for the same logic used in analysis.py.
Important: only consecutive calendar days are treated as daily consumption.
*/

-- Base daily consumption ------------------------------------------------------
WITH lagged AS (
    SELECT
        anon_id,
        data,
        pokazanie,
        paketov_za_sutki,
        LAG(data) OVER (PARTITION BY anon_id ORDER BY data) AS prev_data,
        LAG(pokazanie) OVER (PARTITION BY anon_id ORDER BY data) AS prev_pokazanie
    FROM pokazaniya
)
SELECT
    anon_id,
    data,
    pokazanie - prev_pokazanie AS rashod
FROM lagged
WHERE data - prev_data = 1;

-- 1. Negative consumption: <= -0.001 m3/day ---------------------------------
WITH lagged AS (
    SELECT *,
           LAG(data) OVER (PARTITION BY anon_id ORDER BY data) AS prev_data,
           LAG(pokazanie) OVER (PARTITION BY anon_id ORDER BY data) AS prev_pokazanie
    FROM pokazaniya
), daily AS (
    SELECT anon_id, data, pokazanie, prev_pokazanie,
           pokazanie - prev_pokazanie AS rashod
    FROM lagged
    WHERE data - prev_data = 1
)
SELECT *
FROM daily
WHERE rashod <= -0.001
ORDER BY rashod;

-- 2a. Absolute spikes: > 1.5 m3/day -----------------------------------------
WITH lagged AS (
    SELECT *,
           LAG(data) OVER (PARTITION BY anon_id ORDER BY data) AS prev_data,
           LAG(pokazanie) OVER (PARTITION BY anon_id ORDER BY data) AS prev_pokazanie
    FROM pokazaniya
), daily AS (
    SELECT anon_id, data, pokazanie - prev_pokazanie AS rashod
    FROM lagged
    WHERE data - prev_data = 1
)
SELECT *
FROM daily
WHERE rashod > 1.5
ORDER BY rashod DESC;

-- 2b. Relative spikes: >= 5x meter median and > 0.5 m3/day -------------------
WITH lagged AS (
    SELECT *,
           LAG(data) OVER (PARTITION BY anon_id ORDER BY data) AS prev_data,
           LAG(pokazanie) OVER (PARTITION BY anon_id ORDER BY data) AS prev_pokazanie
    FROM pokazaniya
), daily AS (
    SELECT anon_id, data, pokazanie - prev_pokazanie AS rashod
    FROM lagged
    WHERE data - prev_data = 1
), baseline AS (
    SELECT
        anon_id,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY rashod) AS usual_rashod,
        COUNT(*) AS baseline_days
    FROM daily
    WHERE rashod > 0 AND rashod <= 10
    GROUP BY anon_id
    HAVING COUNT(*) >= 20
)
SELECT d.anon_id, d.data, d.rashod, b.usual_rashod,
       d.rashod / b.usual_rashod AS multiple
FROM daily d
JOIN baseline b USING (anon_id)
WHERE d.rashod > 0.5
  AND d.rashod >= 5 * b.usual_rashod
ORDER BY multiple DESC;

-- 3. Physically unrealistic values: > 20 m3/day ------------------------------
WITH lagged AS (
    SELECT *,
           LAG(data) OVER (PARTITION BY anon_id ORDER BY data) AS prev_data,
           LAG(pokazanie) OVER (PARTITION BY anon_id ORDER BY data) AS prev_pokazanie
    FROM pokazaniya
), daily AS (
    SELECT anon_id, data, pokazanie - prev_pokazanie AS rashod
    FROM lagged
    WHERE data - prev_data = 1
)
SELECT d.*, p.bs, p.tip, p.model
FROM daily d
LEFT JOIN pribory p USING (anon_id)
WHERE d.rashod > 20
ORDER BY d.rashod DESC;

-- 4. Leak candidates: >0.001 m3/day for >=90 consecutive days ----------------
WITH lagged AS (
    SELECT *,
           LAG(data) OVER (PARTITION BY anon_id ORDER BY data) AS prev_data,
           LAG(pokazanie) OVER (PARTITION BY anon_id ORDER BY data) AS prev_pokazanie
    FROM pokazaniya
), daily AS (
    SELECT anon_id, data, pokazanie - prev_pokazanie AS rashod
    FROM lagged
    WHERE data - prev_data = 1
), positive AS (
    SELECT *,
           data - (ROW_NUMBER() OVER (PARTITION BY anon_id ORDER BY data))::int AS grp
    FROM daily
    WHERE rashod > 0.001
), streaks AS (
    SELECT anon_id, grp, MIN(data) AS start_date, MAX(data) AS end_date, COUNT(*) AS days
    FROM positive
    GROUP BY anon_id, grp
)
SELECT anon_id, MAX(days) AS max_days
FROM streaks
GROUP BY anon_id
HAVING MAX(days) >= 90
ORDER BY max_days DESC;

-- 5. Zero consumption while packets are still received: >=30 days ------------
WITH lagged AS (
    SELECT *,
           LAG(data) OVER (PARTITION BY anon_id ORDER BY data) AS prev_data,
           LAG(pokazanie) OVER (PARTITION BY anon_id ORDER BY data) AS prev_pokazanie
    FROM pokazaniya
), daily AS (
    SELECT anon_id, data, paketov_za_sutki,
           pokazanie - prev_pokazanie AS rashod
    FROM lagged
    WHERE data - prev_data = 1
), zero_days AS (
    SELECT *,
           data - (ROW_NUMBER() OVER (PARTITION BY anon_id ORDER BY data))::int AS grp
    FROM daily
    WHERE rashod = 0 AND paketov_za_sutki > 0
), streaks AS (
    SELECT anon_id, grp, MIN(data) AS start_date, MAX(data) AS end_date, COUNT(*) AS days
    FROM zero_days
    GROUP BY anon_id, grp
)
SELECT anon_id, MAX(days) AS max_days
FROM streaks
GROUP BY anon_id
HAVING MAX(days) >= 30
ORDER BY max_days DESC;

-- Full reproducible logic for step changes and magnet analysis is kept in
-- analysis.py because the rolling median logic is clearer and easier to review
-- there. The CSV outputs in results/ contain every qualifying device/day.
