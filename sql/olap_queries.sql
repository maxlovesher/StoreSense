-- StoreSense OLAP demo queries (DuckDB GROUP BY ROLLUP / CUBE)
-- Owner: Member 2 (Warehouse & OLAP)
-- Spec:  docs/PROJECT_BRIEF.md, section 6.2
--
-- One demo query each for: roll-up / drill-down, slice, dice, pivot
-- (plus two bonus queries that show CUBE and the fact_order table).
--
-- Conventions
--  * "Sales" means ORDER LINES: there are no prices, so a sale is one product
--    in one order, and we count rows of fact_order_line.
--  * Day of week: order_dow 0..6, ASSUMING 0 = Sunday (see dim_time.day_name).
--  * Department / aisle names in the data are lower case ('produce',
--    'dairy eggs'), so filters must use lower case.
--  * ROLLUP / CUBE put NULL in the subtotal rows. GROUPING(col) is 1 when
--    that NULL is a subtotal and 0 when it is a real value, so the queries
--    use GROUPING() to label the rows instead of testing for NULL.
--  * Every statement ends with a semicolon, and no comment contains one, so
--    the dashboard can split this file on semicolons and run the queries one
--    by one. Each query starts with a comment tag such as [Q1a] that names it.


-- ===========================================================================
-- [Q1a] ROLL-UP: department -> aisle -> grand total
-- Question: how many order lines does each aisle sell, and how do they add up
--           to the department and to the whole store?
-- ROLLUP (department, aisle) returns three levels in one pass:
--     (department, aisle)  one row per aisle
--     (department, NULL)   subtotal for each department
--     (NULL, NULL)         grand total
-- ORDER BY ... NULLS LAST puts each subtotal right after its detail rows.
-- ===========================================================================
SELECT
    CASE GROUPING(p.department, p.aisle)
        WHEN 0 THEN 'aisle'
        WHEN 1 THEN 'department total'
        ELSE        'grand total'
    END                                   AS level,
    p.department,
    p.aisle,
    COUNT(*)                              AS order_lines
FROM fact_order_line l
JOIN dim_product p ON l.product_key = p.product_key
GROUP BY ROLLUP (p.department, p.aisle)
ORDER BY p.department NULLS LAST, p.aisle NULLS LAST;


-- ===========================================================================
-- [Q1b] DRILL-DOWN: department -> aisle -> product (one aisle opened up)
-- Question: inside the 'yogurt' aisle of 'dairy eggs', which products sell
--           most, and what are the aisle and department totals above them?
-- Drill-down is the reverse of roll-up: start at the department total and
-- keep adding a lower level of the hierarchy. A full three-level ROLLUP over
-- every product would return ~50,000 rows, so the WHERE clause opens just one
-- aisle. Change the two names to drill into another one.
-- GROUPING() gives a bit mask: 0 = product row, 1 = aisle subtotal,
-- 3 = department subtotal, 7 = grand total.
-- ===========================================================================
SELECT
    CASE GROUPING(p.department, p.aisle, p.product_name)
        WHEN 0 THEN 'product'
        WHEN 1 THEN 'aisle total'
        WHEN 3 THEN 'department total'
        ELSE        'grand total'
    END                                   AS level,
    p.department,
    p.aisle,
    p.product_name,
    COUNT(*)                              AS order_lines
FROM fact_order_line l
JOIN dim_product p ON l.product_key = p.product_key
WHERE p.department = 'dairy eggs'
  AND p.aisle      = 'yogurt'
GROUP BY ROLLUP (p.department, p.aisle, p.product_name)
ORDER BY GROUPING(p.department, p.aisle, p.product_name) DESC, order_lines DESC
LIMIT 15;


-- ===========================================================================
-- [Q2] SLICE: weekend orders only
-- Question: what do customers buy on the weekend, department by department?
-- A slice fixes ONE dimension to ONE value: here dim_time.is_weekend = true
-- (Sunday and Saturday). The result is a smaller cube that is still cut by
-- department.
-- ===========================================================================
SELECT
    p.department,
    COUNT(*)                                          AS weekend_order_lines,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_weekend_lines
FROM fact_order_line l
JOIN dim_product p ON l.product_key = p.product_key
JOIN dim_time    t ON l.time_key    = t.time_key
WHERE t.is_weekend
GROUP BY p.department
ORDER BY weekend_order_lines DESC;


-- ===========================================================================
-- [Q3] DICE: Produce and Dairy-Eggs departments, in the evening hours only
-- Question: how do produce and dairy sales change hour by hour in the evening?
-- A dice fixes SEVERAL dimensions at once: two departments from dim_product
-- AND one hour band from dim_time (Evening = hours 17-20).
-- ===========================================================================
SELECT
    p.department,
    t.order_hour_of_day                    AS hour,
    COUNT(*)                               AS order_lines
FROM fact_order_line l
JOIN dim_product p ON l.product_key = p.product_key
JOIN dim_time    t ON l.time_key    = t.time_key
WHERE p.department IN ('produce', 'dairy eggs')
  AND t.hour_band = 'Evening'
GROUP BY p.department, t.order_hour_of_day
ORDER BY p.department, hour;


-- ===========================================================================
-- [Q4] PIVOT: department x day-of-week matrix
-- Question: which departments are busiest on which day?
-- A pivot rotates one dimension (day) from rows to columns. DuckDB's PIVOT
-- statement does it directly. The day names are listed after IN so the
-- columns come out Sunday..Saturday instead of alphabetically.
-- ===========================================================================
PIVOT (
    SELECT p.department, t.day_name, l.order_id
    FROM fact_order_line l
    JOIN dim_product p ON l.product_key = p.product_key
    JOIN dim_time    t ON l.time_key    = t.time_key
)
ON day_name IN ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')
USING COUNT(order_id)
GROUP BY department
ORDER BY department;


-- ===========================================================================
-- [Q5] BONUS - CUBE: department x hour band, every combination of subtotals
-- Question: sales by department and time of day, with the totals for each
--           department, for each time of day, and for the whole store.
-- ROLLUP (a, b) gives (a,b), (a), ().   CUBE (a, b) gives (a,b), (a), (b), ().
-- CUBE adds the "(b) only" subtotal, here the total for each hour band across
-- all departments, which ROLLUP cannot produce because it follows ONE
-- hierarchy from the left.
-- ===========================================================================
SELECT
    CASE WHEN GROUPING(p.department) = 1 THEN 'ALL departments' ELSE p.department END AS department,
    CASE WHEN GROUPING(t.hour_band)  = 1 THEN 'ALL day'         ELSE t.hour_band  END AS hour_band,
    COUNT(*)                               AS order_lines
FROM fact_order_line l
JOIN dim_product p ON l.product_key = p.product_key
JOIN dim_time    t ON l.time_key    = t.time_key
GROUP BY CUBE (p.department, t.hour_band)
ORDER BY GROUPING(p.department), p.department, GROUPING(t.hour_band), t.hour_band;


-- ===========================================================================
-- [Q6] BONUS - order-level analysis on fact_order: basket size by day and band
-- Question: on which days and at what time of day do customers buy the most
--           items per order?
-- fact_order holds test orders with basket_size = 0, which are not real
-- baskets, so basket statistics must filter basket_size > 0.
-- ===========================================================================
SELECT
    CASE WHEN GROUPING(t.day_name)  = 1 THEN 'ALL days' ELSE t.day_name  END AS day_name,
    CASE WHEN GROUPING(t.hour_band) = 1 THEN 'ALL day'  ELSE t.hour_band END AS hour_band,
    COUNT(*)                               AS orders,
    ROUND(AVG(o.basket_size), 2)           AS avg_basket_size
FROM fact_order o
JOIN dim_time t ON o.time_key = t.time_key
WHERE o.basket_size > 0
GROUP BY CUBE (t.day_name, t.hour_band)
ORDER BY GROUPING(t.day_name), MIN(t.order_dow), GROUPING(t.hour_band), t.hour_band;
