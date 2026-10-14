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

*To fill in after running the pipeline on the full dataset. These must be real numbers from the run, not estimates.*

| Item | Value |
|---|---|
| Rows in `fact_order_line` | |
| Rows in `fact_order` | |
| Rows in `dim_user` | |
| Rows in `dim_product` | |
| Test orders kept (basket size 0) | |
| Orders at the 30-day cap | |
| Full load time | |
| Validation | _ / 23 checks passed |

EDA findings (from `notebooks/eda.ipynb`, run on the full warehouse):

- *e.g. busiest day and hour:*
- *e.g. median and mean basket size:*
- *e.g. department with the highest reorder rate:*

## 1.6 How to reproduce

```bash
python etl/load.py        # build the warehouse
python etl/validate.py    # run the 23 checks
pytest                    # unit tests for the ETL
```
