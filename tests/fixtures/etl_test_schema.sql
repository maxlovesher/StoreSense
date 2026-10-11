-- Table layout used ONLY by the ETL tests (tests/test_etl.py).
--
-- It follows section 5 of docs/PROJECT_BRIEF.md. The real schema lives in
-- sql/schema.sql and is owned by Member 2; this copy exists so the ETL can be
-- tested before (and independently of) that file.

CREATE TABLE dim_time (
    time_key          INTEGER PRIMARY KEY,
    order_dow         INTEGER,
    day_name          VARCHAR,
    is_weekend        BOOLEAN,
    order_hour_of_day INTEGER,
    hour_band         VARCHAR
);

CREATE TABLE dim_product (
    product_key   INTEGER PRIMARY KEY,
    product_name  VARCHAR,
    aisle_id      INTEGER,
    aisle         VARCHAR,
    department_id INTEGER,
    department    VARCHAR
);

CREATE TABLE dim_user (
    user_key                INTEGER PRIMARY KEY,
    total_orders            INTEGER,
    avg_basket_size         DOUBLE,
    avg_days_between_orders DOUBLE,
    reorder_ratio           DOUBLE,
    segment                 VARCHAR
);

CREATE TABLE fact_order (
    order_id         INTEGER PRIMARY KEY,
    user_key         INTEGER,
    time_key         INTEGER,
    order_number     INTEGER,
    days_since_prior INTEGER,
    basket_size      INTEGER,
    reordered_items  INTEGER
);

CREATE TABLE fact_order_line (
    order_id          INTEGER,
    product_key       INTEGER,
    user_key          INTEGER,
    time_key          INTEGER,
    add_to_cart_order INTEGER,
    reordered         INTEGER
);
