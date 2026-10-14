"""
ETL step 2: Transform.

Owner: Member 1 (Data & ETL Lead)
Spec:  docs/PROJECT_BRIEF.md, sections 5 and 6.1

Each constant below is ONE SELECT statement that produces the rows of one
warehouse table. Nothing runs here: load.py executes them as
`INSERT INTO <table> (<columns>) <SELECT>`, so the data stays inside DuckDB.

Design decisions (also written up in reports/sections/01_data_and_etl.md):

* Surrogate keys. product_key = product_id and user_key = user_id. The source
  ids are already unique integers, so a separate numbering would only make
  results harder to trace back to the raw files.

* time_key = order_dow * 24 + order_hour_of_day  (0..167).
  dim_time has one row for each day-of-week x hour combination: 7 x 24 = 168.

* Day-of-week coding is undocumented in the dataset. We ASSUME 0 = Sunday.

* Hour bands: Morning 05-11, Afternoon 12-16, Evening 17-20, Night 21-04.

* NULL handling. days_since_prior_order is empty only on a user's first
  order, because there is no earlier order. We keep it as NULL instead of
  inventing a 0 (which would wrongly say "ordered again the same day").
  AVG() ignores NULLs, so averages are correct. validate.py checks that the
  only NULLs are on order_number = 1.

* Test orders. ~75K orders have eval_set = 'test' and no products at all.
  They are kept in fact_order with basket_size = 0, so every order in
  orders.csv appears in the warehouse. Remember this when computing basket
  statistics: use `WHERE basket_size > 0` (dim_user already does).

* eval_set (prior / train / test) is NOT stored, because the brief's schema
  has no column for it.
"""

# ---------------------------------------------------------------------------
# dim_time: built from nothing, no source file needed.
# ---------------------------------------------------------------------------
DIM_TIME_SQL = """
SELECT
    d.dow * 24 + h.hr                                   AS time_key,
    d.dow                                               AS order_dow,
    CASE d.dow WHEN 0 THEN 'Sunday'    WHEN 1 THEN 'Monday'
               WHEN 2 THEN 'Tuesday'   WHEN 3 THEN 'Wednesday'
               WHEN 4 THEN 'Thursday'  WHEN 5 THEN 'Friday'
               WHEN 6 THEN 'Saturday' END               AS day_name,
    d.dow IN (0, 6)                                     AS is_weekend,
    h.hr                                                AS order_hour_of_day,
    CASE WHEN h.hr BETWEEN 5  AND 11 THEN 'Morning'
         WHEN h.hr BETWEEN 12 AND 16 THEN 'Afternoon'
         WHEN h.hr BETWEEN 17 AND 20 THEN 'Evening'
         ELSE 'Night' END                               AS hour_band
FROM range(7)  AS d(dow)
CROSS JOIN range(24) AS h(hr)
"""

# ---------------------------------------------------------------------------
# dim_product: product + aisle + department (hierarchy department > aisle > product).
# LEFT JOINs so a product is never silently dropped; validate.py reports any
# product whose aisle or department failed to join.
# ---------------------------------------------------------------------------
DIM_PRODUCT_SQL = """
SELECT
    p.product_id      AS product_key,
    p.product_name,
    p.aisle_id,
    a.aisle,
    p.department_id,
    d.department
FROM raw_products p
LEFT JOIN raw_aisles      a ON p.aisle_id      = a.aisle_id
LEFT JOIN raw_departments d ON p.department_id = d.department_id
"""

# ---------------------------------------------------------------------------
# fact_order_line: one row per product in an order (~33.8M rows).
# Prior and train order lines are stacked (UNION ALL), then each line gets the
# user and the time slot of its order by joining to the orders table.
# ---------------------------------------------------------------------------
FACT_ORDER_LINE_SQL = """
SELECT
    l.order_id,
    l.product_id                                    AS product_key,
    o.user_id                                       AS user_key,
    o.order_dow * 24 + o.order_hour_of_day          AS time_key,
    l.add_to_cart_order,
    l.reordered
FROM (
    SELECT * FROM raw_order_products_prior
    UNION ALL
    SELECT * FROM raw_order_products_train
) l
JOIN raw_orders o ON l.order_id = o.order_id
"""

# ---------------------------------------------------------------------------
# fact_order: one row per order (~3.4M rows). Reads the ALREADY LOADED
# fact_order_line table to count basket size, which is much faster than
# parsing the 32M-row CSV a second time. Orders with no lines (the test
# orders) get basket_size = 0 through the LEFT JOIN + COALESCE.
# ---------------------------------------------------------------------------
FACT_ORDER_SQL = """
SELECT
    o.order_id,
    o.user_id                                       AS user_key,
    o.order_dow * 24 + o.order_hour_of_day          AS time_key,
    o.order_number,
    CAST(o.days_since_prior_order AS INTEGER)       AS days_since_prior,
    COALESCE(b.basket_size, 0)                      AS basket_size,
    COALESCE(b.reordered_items, 0)                  AS reordered_items
FROM raw_orders o
LEFT JOIN (
    SELECT order_id,
           COUNT(*)       AS basket_size,
           SUM(reordered) AS reordered_items
    FROM fact_order_line
    GROUP BY order_id
) b ON o.order_id = b.order_id
"""

# ---------------------------------------------------------------------------
# dim_user: per-user aggregates (~206K rows). Reads the loaded fact_order.
#   total_orders             every order the user placed
#   avg_basket_size          items per order, ignoring the empty test orders
#   avg_days_between_orders  AVG ignores the NULL on the first order
#   reorder_ratio            share of all bought items that were reorders
# `segment` is not set here: the clustering step fills it in later.
# ---------------------------------------------------------------------------
DIM_USER_SQL = """
SELECT
    user_key,
    COUNT(*)                                                    AS total_orders,
    AVG(basket_size) FILTER (WHERE basket_size > 0)             AS avg_basket_size,
    AVG(days_since_prior)                                       AS avg_days_between_orders,
    SUM(reordered_items)::DOUBLE / NULLIF(SUM(basket_size), 0)  AS reorder_ratio
FROM fact_order
GROUP BY user_key
"""

# ---------------------------------------------------------------------------
# The order load.py follows: (table, its columns, the SELECT that fills it).
# Order matters: fact_order reads fact_order_line, and dim_user reads fact_order.
# The SELECT columns must be in the same order as the column list.
# ---------------------------------------------------------------------------
LOAD_STEPS = [
    ("dim_time",
     ["time_key", "order_dow", "day_name", "is_weekend", "order_hour_of_day", "hour_band"],
     DIM_TIME_SQL),
    ("dim_product",
     ["product_key", "product_name", "aisle_id", "aisle", "department_id", "department"],
     DIM_PRODUCT_SQL),
    ("fact_order_line",
     ["order_id", "product_key", "user_key", "time_key", "add_to_cart_order", "reordered"],
     FACT_ORDER_LINE_SQL),
    ("fact_order",
     ["order_id", "user_key", "time_key", "order_number", "days_since_prior",
      "basket_size", "reordered_items"],
     FACT_ORDER_SQL),
    ("dim_user",
     ["user_key", "total_orders", "avg_basket_size", "avg_days_between_orders", "reorder_ratio"],
     DIM_USER_SQL),
]
