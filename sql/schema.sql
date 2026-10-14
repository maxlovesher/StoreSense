-- StoreSense star schema (DuckDB)
-- Owner: Member 2 (Warehouse & OLAP)
-- Spec:  docs/PROJECT_BRIEF.md, section 5
--
-- Fact tables:      fact_order_line, fact_order
-- Dimension tables: dim_product, dim_user, dim_time
--
--                      dim_time              dim_product
--                         |  time_key            |  product_key
--                         |                      |
--   dim_user ---- fact_order_line ----------------+
--      |  user_key   (order_id, product_key,
--      |              user_key, time_key)
--      |
--      +--------- fact_order  ---- dim_time (time_key)
--
-- etl/load.py runs this file on an empty database and then fills the tables
-- with INSERT INTO <table> (<column list>) SELECT ..., so every table and
-- column name below must match the brief exactly.
--
-- Design notes
--  * Whole numbers (keys, counts) are integers; names and labels are VARCHAR;
--    averages and ratios are DOUBLE; is_weekend is BOOLEAN.
--  * Narrow integer types are only used where the whole range is known
--    (time_key is 0..167, so it needs SMALLINT: a TINYINT stops at 127).
--  * PRIMARY KEYs are declared on the four tables that have a single-column
--    key. fact_order_line has none: its natural key is (order_id, product_key),
--    but we measured a PRIMARY KEY (order_id, product_key) on the full data:
--    the table load went from 2.6 s to 56.1 s (whole warehouse 13.8 s to
--    61.8 s) and the .duckdb file from 0.23 GB to 1.81 GB. etl/validate.py
--    already checks key uniqueness instead.
--  * No FOREIGN KEY constraints. We tried them, and the ETL load fails at once:
--    load.py fills fact_order_line BEFORE fact_order and dim_user (fact_order
--    counts its basket sizes from the loaded order lines), so the order lines
--    would point at parent rows that do not exist yet. Changing the load order
--    is Member 1's code, and etl/validate.py already checks every key for
--    orphans after the load.

-- ---------------------------------------------------------------------------
-- dim_time: one row per day-of-week x hour slot (7 x 24 = 168 rows).
-- time_key = order_dow * 24 + order_hour_of_day.
-- Hierarchy: hour_band (Morning / Afternoon / Evening / Night) -> hour.
-- order_dow is 0..6 and we ASSUME 0 = Sunday (the dataset does not say).
-- ---------------------------------------------------------------------------
CREATE TABLE dim_time (
    time_key           SMALLINT PRIMARY KEY,
    order_dow          SMALLINT NOT NULL CHECK (order_dow BETWEEN 0 AND 6),
    day_name           VARCHAR  NOT NULL,
    is_weekend         BOOLEAN  NOT NULL,
    order_hour_of_day  SMALLINT NOT NULL CHECK (order_hour_of_day BETWEEN 0 AND 23),
    hour_band          VARCHAR  NOT NULL
);

-- ---------------------------------------------------------------------------
-- dim_product: one row per product, with its aisle and department.
-- Hierarchy: department -> aisle -> product.
-- aisle / department stay nullable: the ETL uses LEFT JOINs, and validate.py
-- reports any product whose lookup failed instead of the load crashing.
-- ---------------------------------------------------------------------------
CREATE TABLE dim_product (
    product_key    INTEGER PRIMARY KEY,
    product_name   VARCHAR NOT NULL,
    aisle_id       INTEGER NOT NULL,
    aisle          VARCHAR,
    department_id  INTEGER NOT NULL,
    department     VARCHAR
);

-- ---------------------------------------------------------------------------
-- dim_user: one row per customer, with order-history aggregates.
-- The three averages and the ratio can be NULL (a user with a single order has
-- no gap between orders; a user with only empty test orders has no basket).
-- segment is NULL until the clustering step (Member 4) fills it in.
-- ---------------------------------------------------------------------------
CREATE TABLE dim_user (
    user_key                 INTEGER PRIMARY KEY,
    total_orders             INTEGER NOT NULL,
    avg_basket_size          DOUBLE,
    avg_days_between_orders  DOUBLE,
    reorder_ratio            DOUBLE,
    segment                  VARCHAR
);

-- ---------------------------------------------------------------------------
-- fact_order: one row per order (~3.4M). Aggregate fact table for faster
-- order-level analysis. Grain: one order.
-- days_since_prior is NULL on a user's first order, so it is NOT "NOT NULL".
-- Test orders (no products) are kept here with basket_size = 0.
-- ---------------------------------------------------------------------------
CREATE TABLE fact_order (
    order_id          INTEGER PRIMARY KEY,
    user_key          INTEGER  NOT NULL,   -- -> dim_user.user_key
    time_key          SMALLINT NOT NULL,   -- -> dim_time.time_key
    order_number      INTEGER  NOT NULL,   -- 1 = the user's first order
    days_since_prior  INTEGER,             -- NULL on the first order; capped at 30
    basket_size       INTEGER  NOT NULL,   -- items in the order
    reordered_items   INTEGER  NOT NULL    -- how many of them were reorders
);

-- ---------------------------------------------------------------------------
-- fact_order_line: one row per product in an order (~33.8M). The main fact
-- table. Grain: one product in one order. user_key and time_key are copied
-- from the order, so a query can reach those dimensions without joining
-- fact_order.
-- ---------------------------------------------------------------------------
CREATE TABLE fact_order_line (
    order_id           INTEGER  NOT NULL,  -- -> fact_order.order_id
    product_key        INTEGER  NOT NULL,  -- -> dim_product.product_key
    user_key           INTEGER  NOT NULL,  -- -> dim_user.user_key
    time_key           SMALLINT NOT NULL,  -- -> dim_time.time_key
    add_to_cart_order  SMALLINT NOT NULL,  -- position in the cart (1 = first)
    reordered          TINYINT  NOT NULL   -- 1 if the user bought it before, else 0
);
