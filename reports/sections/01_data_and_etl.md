# 1. Data and ETL

*Author: Member 1 (Data & ETL Lead). This is one section of the single project report; Member 6 assembles the final document.*

## 1.1 Dataset

We use the **Instacart Market Basket Analysis** dataset from Kaggle: roughly 3.4M grocery orders from about 206K users, covering about 50K products organised in 134 aisles and 21 departments.

| File | One row is... | Approx. rows |
|---|---|---|
| `orders.csv` | an order (user, day of week, hour, days since the user's previous order) | 3.4M |
| `order_products__prior.csv` | a product in a prior order | 32M |
| `order_products__train.csv` | a product in each user's latest order (train set) | 1.4M |
| `products.csv`, `aisles.csv`, `departments.csv` | the product / aisle / department lookup | 50K / 134 / 21 |

### Limitations of the data

- **No prices.** We use basket size (items per order) as the stand-in for the "monetary" part of RFM.
- **No calendar dates.** Only day of week, hour of day and the number of days since the previous order exist. That last value is **capped at 30**, so a value of 30 means "30 days or more".
- **Undocumented day-of-week coding.** We treat `order_dow` as a day index 0 to 6 and **assume 0 = Sunday**.
- **Test orders have no products.** About 75K orders are marked `test`; their products are hidden by the competition.

## 1.2 ETL flow

```
data/raw/*.csv
    |  extract.py    DuckDB reads the CSVs through views (nothing is copied into memory)
    v
raw_* views
    |  transform.py  one SELECT per warehouse table
    v
    |  load.py       sql/schema.sql creates the tables, then INSERT INTO ... SELECT fills them
    v
data/warehouse/storesense.duckdb   (star schema: 2 fact tables + 3 dimensions)
    |  validate.py   row counts, orphan keys, NULL / duplicate / range checks
    v
23 checks, all must pass
```

All the heavy work happens inside DuckDB SQL. The 32M-row prior-orders file is never loaded into pandas.

Load order matters: `dim_time`, `dim_product`, `fact_order_line`, then `fact_order` (which counts basket sizes from the already-loaded order lines instead of re-reading the CSV), then `dim_user` (aggregated from `fact_order`).

## 1.3 Design decisions

| Decision | What we did | Why |
|---|---|---|
| Keys | `product_key = product_id`, `user_key = user_id` | The source ids are already unique integers; keeping them makes every result traceable back to the raw files. |
| Time dimension | `time_key = order_dow * 24 + order_hour_of_day`, giving 168 rows (7 days x 24 hours) | One row per possible day-and-hour slot; the key is computed, so no lookup is needed while loading. |
| Hour bands | Morning 05-11, Afternoon 12-16, Evening 17-20, Night 21-04 | Gives the time-of-day level of the hierarchy used for roll-up and dice. |
| Weekend | Sunday and Saturday (day 0 and 6) | Follows from the 0 = Sunday assumption. |
| First orders | `days_since_prior` stays **NULL** | A 0 would wrongly mean "ordered again the same day". `AVG` ignores NULL, so averages stay correct. |
| Test orders | **Kept** in `fact_order` with `basket_size = 0` | Every order in `orders.csv` appears in the warehouse. Basket statistics must filter `basket_size > 0`; `dim_user` already does. |
| `eval_set` | **Not stored** | The agreed schema has no column for it. Anything that must separate prior from train orders (the reorder model) has to read `orders.csv` directly. |
| Product hierarchy | `LEFT JOIN` to aisles and departments | A product is never silently dropped; validation reports any product with a missing aisle or department. |
| Source types | Read `order_dow` and `order_hour_of_day` as `INTEGER` | An early version used `TINYINT`, and `6 * 24` overflowed. The automated tests caught this on synthetic data before it could fail on the full dataset. |

## 1.4 Validation

`etl/validate.py` runs 23 checks. Each is a SQL query that counts problems, and passing means 0 problems:

- **Row counts:** `dim_time` has 168 rows; `fact_order` equals the rows in `orders.csv`; `fact_order_line` equals prior + train rows; `dim_product` equals `products.csv`; the basket sizes add up to the number of order lines.
- **Foreign keys (no orphans):** every `product_key`, `user_key`, `time_key` and `order_id` in the fact tables has a matching dimension or parent row.
- **Keys:** unique in every dimension and in `fact_order`; no NULL keys.
- **NULL policy and ranges:** `days_since_prior` is NULL on every first order and only there; it is between 0 and 30; `reordered` is 0 or 1; `time_key` is between 0 and 167.

`tests/test_etl.py` runs the real pipeline on a tiny hand-checkable dataset and also **breaks the warehouse on purpose** (deleting a product, forcing a wrong NULL) to confirm that validation notices.

## 1.5 Results

The full Instacart data was loaded into DuckDB with `python etl/load.py` using the schema in `sql/schema.sql`, then checked with `python etl/validate.py`.

| Item | Value |
|---|---|
| Rows in `fact_order_line` | 33,819,106 (32,434,489 prior + 1,384,617 train) |
| Rows in `fact_order` | 3,421,083 (equal to `orders.csv`) |
| Rows in `dim_user` | 206,209 |
| Rows in `dim_product` | 49,688 (equal to `products.csv`) |
| Rows in `dim_time` | 168 |
| Test orders kept (basket size 0) | 75,000 |
| First orders (`days_since_prior` is NULL) | 206,209, one per user |
| Orders at the 30-day cap | 369,323 |
| Full load time | 8.6 seconds for all five tables (single machine, DuckDB) |
| Warehouse file size | about 0.23 GB |
| Validation | 23 / 23 checks passed |

EDA findings (from `notebooks/eda.ipynb` and queries on the full warehouse):

- **Users.** Every user has at least 4 orders. The mean is 16.6 and the median is 10, with a maximum of 100, so most users order a handful of times while a small group orders very often.
- **Basket size.** Across the 3,346,083 orders that contain items, the mean basket is 10.11 items, the median is 8 and the 95th percentile is 25. The largest basket has 145 items. The mean is above the median because a few very large baskets pull it up.
- **Reordering.** 59.0% of all order lines are reorders. The departments with the highest reorder rates are dairy eggs (67.0%), beverages (65.4%) and produce (65.1%).
- **When people order.** Counting all 3,421,083 orders, Sunday (600,905) and Monday (587,478) are the busiest days, followed by Tuesday (467,260). The busiest hours are 10:00 (288,418 orders), 11:00 (284,728) and 15:00 (283,639). The day names rely on our assumption that `order_dow = 0` is Sunday.
- **Best sellers.** Bananas lead with 491,291 order lines, followed by Bag of Organic Bananas (394,930) and Organic Strawberries (275,577).
- **The 30-day cap.** 369,323 orders sit exactly at 30 days since the previous order. Because the source caps this value, they stand for "30 days or more", which is why the histogram has a tall last bar.

Data quality notes:

- 1,258 products fall in the dataset's own `missing` department and aisle, and 548 are in the `other` department. They are kept, not dropped, and are worth excluding from any product-level business conclusions.
- The 75,000 test orders are real orders with unknown contents. They are kept with `basket_size = 0`, so any basket statistic filters `basket_size > 0`.

## 1.6 How to reproduce

```bash
python etl/load.py        # build the warehouse
python etl/validate.py    # run the 23 checks
pytest                    # unit tests for the ETL
```
