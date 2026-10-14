# StoreSense: Retail Data Warehouse and Market Basket Analysis

*DMDW (Data Mining & Data Warehousing) course project, KIIT*

## Contents

1. [Introduction](#introduction)
2. [1. Data and ETL](#1-data-and-etl)
3. [2. Warehouse and OLAP](#2-warehouse-and-olap)
4. [3. Association rules](#3-association-rules)
5. [4. Customer segmentation](#4-customer-segmentation)
6. [5. Reorder prediction](#5-reorder-prediction)
7. [6. Dashboard](#6-dashboard)
8. [7. Insights, limitations and future work](#7-insights-limitations-and-future-work)

---

# Introduction

*Author: Member 6 (Dashboard & Integration), who assembles the sections of the team into this one report.*

## Problem statement

A grocery retailer has millions of baskets and little idea what they say. StoreSense turns the order history of the **Instacart** online grocery service into a **star-schema data warehouse** and mines it to answer three business questions:

- **When and what do people buy?** (OLAP analysis of the warehouse)
- **Which products are bought together?** (association rules, Apriori and FP-Growth)
- **What kinds of customers are there?** (K-Means segmentation)

A stretch goal asks a fourth question: **will a customer buy a product again?** (reorder prediction). All results are shown in an interactive Streamlit dashboard.

## Objectives

1. Build an **ETL pipeline** that turns the raw CSV files into a clean warehouse (section 1).
2. Design a **star schema** and demonstrate the OLAP operations roll-up, drill-down, slice, dice and pivot (section 2).
3. Mine **association rules** with Apriori and FP-Growth and compare the two algorithms (section 3).
4. **Segment customers** with K-Means on RFM-style features (section 4).
5. *(Stretch)* **Predict reorders** with classification, evaluated without data leakage (section 5).
6. Present everything in an **interactive dashboard** (section 6) and draw the business insights together (section 7).

## The data

The dataset is **Instacart Market Basket Analysis** (Kaggle): **3,421,083 orders** from **206,209 users**, **33,819,106 order lines**, **49,688 products** in **134 aisles** and **21 departments**. Section 1 describes the files in detail.

It has three limits that shape every result in this report:

- **No prices.** A "sale" is one order line (one product in one order), and basket size stands in for spending.
- **No calendar dates.** There are only the day of the week, the hour, and the number of days since the previous order (capped at 30).
- **Day-of-week coding is undocumented.** We assume 0 means Sunday.

## Architecture

```
Raw CSVs ──► ETL (Python + DuckDB) ──► DuckDB warehouse (star schema)
                                            │
          ┌─────────────────────────────────┼──────────────────────────┐
          ▼                                 ▼                          ▼
    OLAP queries                    Association rules            Segmentation
  (ROLLUP / CUBE)                 (Apriori vs FP-Growth)         (K-Means, RFM)
          │                                 │                          │
          │                       Reorder prediction (stretch)         │
          └─────────────────────────────────┼──────────────────────────┘
                                            ▼
                                 Streamlit dashboard
```

The warehouse holds two fact tables (`fact_order_line`, `fact_order`) and three dimensions (`dim_product`, `dim_user`, `dim_time`). The mining modules read it and save small result files, which the dashboard shows.

## The team and the sections

| Section | Topic | Member |
|---|---|---|
| 1 | Data and ETL | Member 1, Data & ETL Lead |
| 2 | Warehouse and OLAP | Member 2, Warehouse & OLAP |
| 3 | Association rules | Member 3, Association Rules |
| 4 | Customer segmentation | Member 4, Customer Segmentation |
| 5 | Reorder prediction | Member 5, Reorder Prediction & Evaluation |
| 6 | Dashboard | Member 6, Dashboard & Integration |
| 7 | Insights, limitations and future work | Member 6 |

The code, the tests and the instructions to reproduce each result are in the repository (`README.md`).

---

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

---

# 2. Warehouse and OLAP

*Author: Member 2 (Warehouse & OLAP). This is one section of the single project report; Member 6 assembles the final document.*

## 2.1 The star schema

![StoreSense star schema](figures/star_schema.png)

The warehouse has **two fact tables** and **three dimension tables**. The tables are created by `sql/schema.sql`, and the ETL then fills them (section 1).

| Table | Kind | Grain (one row is...) | Rows |
|---|---|---|---|
| `fact_order_line` | fact | one product in one order | 33,819,106 |
| `fact_order` | fact | one order | 3,421,083 |
| `dim_product` | dimension | one product (with its aisle and department) | 49,688 |
| `dim_user` | dimension | one customer (with order-history aggregates) | 206,209 |
| `dim_time` | dimension | one day-of-week x hour slot | 168 |

`fact_order_line` is the main fact table. Its only measure is the row itself: with no prices in the data, a "sale" is one order line, so the basic measure is `COUNT(*)`. It carries `user_key` and `time_key` copied from its order, so a query reaches the user and time dimensions without joining `fact_order` first.

`fact_order` is an **aggregate fact table**. It holds one row per order, with the measures `basket_size` and `reordered_items` already counted. Order-level questions (average basket per day) then read 3.4M rows instead of 33.8M.

### Why a star schema, and not one big table?

A single flat table would repeat the product name, aisle and department on every one of the 33.8M order lines, and the day name and hour band on each of them too. A star schema stores each of those facts once in a small dimension table and keeps only integer keys in the large fact table. This gives three benefits:

- **Less space.** The fact table holds six small numbers per row. The whole warehouse file is about 0.23 GB.
- **One place to change a label.** Fixing a department name is a one-row update.
- **Simple, fast queries.** Every OLAP question has the same shape: join the fact table to the dimensions it needs, filter, and `GROUP BY` the dimension columns. Dimensions are small, so these joins are cheap.

### Column types

Keys and counts are integers, names and labels are `VARCHAR`, `is_weekend` is `BOOLEAN`, and averages and ratios are `DOUBLE`. `time_key` is a `SMALLINT` because it runs 0 to 167, and a `TINYINT` stops at 127. `days_since_prior` is the one nullable fact column (NULL on every user's first order), and `dim_user.segment` starts NULL until the segmentation step fills it.

### Keys and constraints

Each dimension has a primary key, and so does `fact_order` (`order_id`). `fact_order_line` has **no** primary key and there are **no** foreign keys. We tested both on the full data instead of guessing:

| Variant | Result on the full data |
|---|---|
| **Chosen:** primary keys on the dimensions and `fact_order`; nothing on `fact_order_line` | `fact_order_line` loads in 2.6 s; whole warehouse in 13.8 s; file 0.23 GB |
| Add `PRIMARY KEY (order_id, product_key)` to `fact_order_line` | that table loads in **56.1 s**; whole warehouse 61.8 s; file **1.81 GB** |
| Add `FOREIGN KEY` constraints to the fact tables | the load **fails after 2.4 s**: `Violates foreign key constraint because key "order_id: 2" does not exist in the referenced table` |

The foreign keys fail because of the ETL's load order. `fact_order_line` is loaded before `fact_order` (which counts its basket sizes from the loaded order lines) and before `dim_user`, so the order lines reference parents that do not exist yet. Instead of constraints, `etl/validate.py` checks every key for orphans after the load, and it passes all 23 checks on this schema.

## 2.2 Dimension hierarchies

A hierarchy is the ordered list of levels along which we roll up or drill down.

```
dim_product:   department (21)  ->  aisle (134)  ->  product (49,688)
dim_time:      hour_band (4)    ->  hour (24)     ->  (day x hour slot, 168)
```

- **Product hierarchy.** Instacart groups products into 21 departments, 134 aisles and 49,688 products, all stored in `dim_product`. Two departments are not real shelves: `missing` and `other` (115,482 order lines, 0.34% of all lines), which hold products without a proper category.
- **Time hierarchy.** The hour bands are Morning (05:00 to 11:59, 7 hours), Afternoon (12:00 to 16:59, 5 hours), Evening (17:00 to 20:59, 4 hours) and Night (21:00 to 04:59, 8 hours). `dim_time` also has the day of the week above the hour, which gives 7 x 24 = **168 rows**.
- **`time_key`** is `order_dow * 24 + order_hour_of_day`, a number from 0 (Sunday midnight) to 167 (Saturday 23:00). That is why `dim_time` has 168 rows: one for every possible day-and-hour slot of a week. The data has no calendar dates, so a week is the only time unit that exists.

## 2.3 OLAP operations

All queries are in `sql/olap_queries.sql`, each with a comment saying what it answers. "Sales" means order lines, as the data has no prices. On the full data each query ran in 0.4 s or less.

### Roll-up: department, then aisle, then grand total (Q1a)

```sql
SELECT CASE GROUPING(p.department, p.aisle)
           WHEN 0 THEN 'aisle' WHEN 1 THEN 'department total' ELSE 'grand total' END AS level,
       p.department, p.aisle, COUNT(*) AS order_lines
FROM fact_order_line l
JOIN dim_product p ON l.product_key = p.product_key
GROUP BY ROLLUP (p.department, p.aisle)
ORDER BY p.department NULLS LAST, p.aisle NULLS LAST;
```

`ROLLUP (department, aisle)` produces the detail rows, a subtotal for each department, and a grand total, all in one scan (156 rows). `GROUPING()` is 1 when a NULL is a subtotal marker rather than a real value. Results:

| Department | Order lines | Share of all lines |
|---|---|---|
| produce | 9,888,378 | 29.2% |
| dairy eggs | 5,631,067 | 16.7% |
| snacks | 3,006,412 | 8.9% |
| beverages | 2,804,175 | 8.3% |
| frozen | 2,336,858 | 6.9% |
| **grand total** | **33,819,106** | 100% |

Produce and dairy eggs alone make up **45.9%** of everything sold. The largest aisles are fresh fruits (3,792,661), fresh vegetables (3,568,630), packaged vegetables fruits (1,843,806) and yogurt (1,507,583). The grand total equals the number of rows in `fact_order_line`, which confirms that nothing was dropped.

### Drill-down: opening one aisle down to its products (Q1b)

Drill-down is the same hierarchy read in the other direction: start from a department total and add the next level beneath it. A three-level `ROLLUP (department, aisle, product_name)` over every product would return about 50,000 rows, so the query fixes `department = 'dairy eggs'` and `aisle = 'yogurt'` and shows the product level of just that aisle, with the aisle and department totals above it. The aisle total is 1,507,583 lines, and the best-selling product in it is *Total 2% with Strawberry Lowfat Greek Strained Yogurt* (30,866 lines). Changing the two names drills into any other aisle.

### Slice: weekend orders only (Q2)

```sql
SELECT p.department, COUNT(*) AS weekend_order_lines, ...
FROM fact_order_line l
JOIN dim_product p ON l.product_key = p.product_key
JOIN dim_time    t ON l.time_key    = t.time_key
WHERE t.is_weekend
GROUP BY p.department
ORDER BY weekend_order_lines DESC;
```

A slice fixes **one** dimension to **one** value (`dim_time.is_weekend = true`, meaning Sunday and Saturday). The weekend holds **11,241,275 lines, or 33.2%** of all sales, although it is only 2 of 7 days (28.6%). Within the weekend, produce is 30.8% of lines, against 28.5% on weekdays.

### Dice: Produce and Dairy Eggs in the evening (Q3)

```sql
WHERE p.department IN ('produce', 'dairy eggs')
  AND t.hour_band = 'Evening'
GROUP BY p.department, t.order_hour_of_day
```

A dice fixes **several** dimensions at once, here two departments (from `dim_product`) and one hour band (from `dim_time`). The result has 8 rows:

| Hour | produce | dairy eggs |
|---|---|---|
| 17 | 622,014 | 355,685 |
| 18 | 483,307 | 280,786 |
| 19 | 371,953 | 216,548 |
| 20 | 299,865 | 170,442 |

Both departments **fall by about 52% between 17:00 and 20:00** (produce -51.8%, dairy eggs -52.1%), and produce sells about 1.75 times as much as dairy eggs in every hour. The evening is 18.0% of produce and dairy sales, close to its 18.4% share of all sales.

### Pivot: department by day of week (Q4)

```sql
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
```

A pivot turns the day of week from rows into columns, giving a 21 x 7 matrix. The `IN` list fixes the column order to Sunday through Saturday (the default would be alphabetical). Totals per day over all departments:

| Sun | Mon | Tue | Wed | Thu | Fri | Sat |
|---|---|---|---|---|---|---|
| 6,533,692 | 5,871,834 | 4,378,360 | 3,998,498 | 3,942,696 | 4,386,443 | 4,707,583 |

Sunday is the busiest day and Thursday the quietest, a ratio of 1.66. The gap is larger for produce (2,057,869 on Sunday against 1,095,847 on Thursday, 1.88x). Alcohol is the clear exception: it peaks on **Friday** (28,465) and is lowest on Sunday (18,150).

### Bonus: `CUBE` and the order-level table (Q5 and Q6)

- **Q5** uses `CUBE (department, hour_band)`. `ROLLUP (a, b)` gives the groups (a, b), (a) and the grand total. `CUBE (a, b)` also gives (b) alone, which here is the total for each time of day across all departments: Afternoon 13,749,997, Morning 11,388,324, Evening 6,236,388 and Night 2,444,397. `ROLLUP` cannot produce those because it only follows one hierarchy from the left.
- **Q6** reads `fact_order` and applies `CUBE (day_name, hour_band)` to the average basket size. It filters `basket_size > 0`, because the 75,000 test orders have no products and would pull the average down. That leaves 3,346,083 real orders with an average basket of **10.11 items**. Sunday baskets are the largest (11.16) and Wednesday baskets the smallest (9.34).

## 2.4 What we learned

- **The shape of demand is very uneven.** Two of the 21 departments sell 45.9% of all order lines, and the weekend (2 days) sells 33.2%.
- **Time of day matters.** The busiest hours are 10:00 (2,874,905 lines), 11:00 and 14:00. Evening sales drop by about half between 17:00 and 20:00 in both produce and dairy.
- **Constraints are a real design cost, not a default.** A primary key on the 33.8M-row table made its load about 21 times slower (2.6 s to 56.1 s) and the file about 8 times larger (0.23 GB to 1.81 GB). Foreign keys could not be used at all with this load order. Validation queries give the same safety at no load cost.
- **`ROLLUP` against `CUBE`.** `ROLLUP` gives subtotals along one hierarchy and is the right tool for department, aisle, product. `CUBE` gives every combination and suits two independent dimensions, such as department and time of day.
- **A star schema keeps the queries short.** Every OLAP query is one fact join to one or two small dimensions, and all of them ran in under half a second on 33.8M rows.

## 2.5 Limitations

- **No prices.** "Sales" counts order lines, so a cheap item and an expensive item weigh the same. Rankings by revenue could differ from the ones above.
- **No calendar dates.** The only time information is day of week and hour, so there is no month, season or trend analysis.
- **Day-of-week coding is an assumption.** We treat 0 as Sunday, as the dataset does not say. If 0 were another day, the day names in Q2 and Q4 would shift (the weekend slice in particular), but the numeric patterns would not change.
- **Test orders.** 75,000 orders have no products. They appear in `fact_order` (`basket_size = 0`) but not in `fact_order_line`, so order-level statistics must filter `basket_size > 0`.
- **Not every product is categorised.** The `missing` and `other` departments hold 0.34% of order lines.

## 2.6 How to reproduce

```bash
python etl/load.py --force      # builds the warehouse from sql/schema.sql (about 14 s)
python etl/validate.py          # 23/23 checks passed
```

Then run any query from `sql/olap_queries.sql`, for example from Python:

```python
from common.db import query_df
print(query_df(open("sql/olap_queries.sql").read().split(";")[3]))   # the dice query, Q3
```

---

# 3. Association rules

*Author: Member 3 (Association Rules). This is one section of the single project report; Member 6 assembles the final document.*

## 3.1 Method

We look for items that are bought together. An **order is a basket** and each **aisle or product is an item**. Baskets are read from `fact_order_line` and joined to `dim_product`. Only orders with **2 or more items** are used, because a single item cannot form a rule (3,182,490 orders qualify).

Three measures describe a rule `A -> B`:

| Measure | Meaning | Formula |
|---|---|---|
| **Support** | the share of baskets that contain A and B | `count(A and B) / baskets` |
| **Confidence** | of the baskets with A, the share that also have B | `support(A and B) / support(A)` |
| **Lift** | how much more often B is bought with A than by chance | `confidence / support(B)` |

A lift of 1 means A and B are independent (A tells us nothing about B). A lift of 3 means B is three times as likely in baskets with A as in a typical basket. We keep only rules with **lift > 1**.

We mine the frequent itemsets with both **Apriori** and **FP-Growth** (`mlxtend`), then build rules from them. Both algorithms must find exactly the same itemsets for the same `min_support`; `mining/association_rules.py` stops with an error if they do not, and a test checks this on a hand-worked example. Because they agree, the rule files hold the rules once, labelled `fpgrowth`.

### The two levels and the exact filters

| | Aisle level | Product level |
|---|---|---|
| Items | 132 aisles (the `missing` and `other` aisles removed) | the **1,000 most popular products** (by order lines, whole warehouse) |
| Orders | random sample of **500,000** orders (seed 42) out of the 3,182,490 | the same 500,000 orders |
| Baskets used | **492,350** (orders with 2+ distinct aisles) | **418,175** (orders with 2+ of the top 1,000 products) |
| `min_support` | **0.01** (at least 4,924 baskets) | **0.0015** (at least 627 baskets) |
| Largest itemset | 3 items | 3 items |
| Frequent itemsets | 2,344 (96 single aisles, 894 pairs, 1,354 triples) | 2,527 |
| Rules with lift > 1 | 9,730; the **top 5,000 by lift** are kept (lift 1.42 and above) | 3,410 (all kept) |

`min_support` is different for each level because the items are different. Aisles are common (a few percent of baskets each), so 0.01 is a sensible floor. A single product is rare: the 1,000th most popular has 5,677 order lines in 3.18M orders, so a floor of 0.0015 is already low for products.

The 1,000 products make up **53.9%** of all order lines, so the product rules describe the popular half of the shop, and a product outside the top 1,000 cannot appear in any rule.

### Memory

One row per order and one column per item would be a large table, so the baskets are stored as a **sparse** table (only the True cells are stored). With its default settings, Apriori still failed on the product baskets: mlxtend built a table of baskets x candidate itemsets and asked for **81.6 GiB** of memory. So `mine_itemsets()` runs Apriori with `low_memory=True`, which counts one candidate at a time. FP-Growth needs no such setting. The 500,000-order sample and the top-1,000 filter are the other memory controls; the whole script runs in about 2 minutes.

### Checking a rule by hand

The top product rule is *Icelandic Style Skyr Blueberry Non-fat Yogurt -> Non Fat Acai & Mixed Berries Yogurt*. We counted it with SQL on the **whole warehouse** (not the sample), using the same top-1,000 filter. Of 2,663,388 baskets, 19,850 contain the Blueberry skyr, 9,004 contain the Acai yogurt, and **4,094 contain both**.

| | In the 500,000-order sample (the rule file) | On the whole warehouse (SQL) |
|---|---|---|
| Confidence | 22.1% | 20.6% |
| Lift | 63.1 | 61.0 |

The sample gives almost the same answer as the full data, within about 7%.

## 3.2 Top rules and what a store could do with them

All rule files are in `reports/results/`, each with a plain-English `interpretation` column.

### Aisle level

| Rule | Support | Confidence | Lift |
|---|---|---|---|
| pasta sauce -> dry pasta + packaged cheese | 1.03% | 15.6% | 4.80 |
| dry pasta -> pasta sauce | 2.08% | 27.6% | 4.17 |
| canned jarred vegetables -> canned meals beans | 1.94% | 24.8% | 3.36 |
| frozen meals -> frozen pizza | 1.07% | 13.6% | 2.95 |
| frozen appetizers sides -> frozen meals | 1.14% | 20.3% | 2.58 |
| fresh herbs -> fresh vegetables | 8.44% | 84.7% | 1.80 |

- **Pasta dinner.** Dry pasta, pasta sauce and packaged cheese form the strongest group. A store could place them close together, or sell a "pasta night" bundle. When a customer has dry pasta in the cart, a pasta sauce suggestion is a good one (27.6% already buy it).
- **Pantry cooking.** Canned vegetables go with canned meals and beans, spices and soup. These are good aisles for a joint promotion.
- **Frozen aisles.** Frozen meals, frozen pizza and frozen appetizers are bought together, which suggests one "easy dinner" mission across the freezer.
- **High confidence is not high lift.** 84.7% of baskets with fresh herbs also contain fresh vegetables, but fresh vegetables are in about 47% of all baskets anyway, so the lift is only 1.8. The lift is the better guide to a *special* link. The confidence mostly reflects that fresh vegetables are popular.

### Product level

| Rule | Support | Confidence | Lift |
|---|---|---|---|
| Icelandic Style Skyr Blueberry Non-fat Yogurt -> Non Fat Acai & Mixed Berries Yogurt | 0.16% | 22.1% | 63.1 |
| Icelandic Style Skyr Blueberry Non-fat Yogurt -> Non Fat Raspberry Yogurt | 0.27% | 36.6% | 58.0 |
| Zero Calorie Cola -> Soda | 0.16% | 53.4% | 46.9 |
| Organic Yellow Squash -> Organic Zucchini | 0.20% | 47.8% | 11.8 |
| Bartlett Pears -> Banana | 0.54% | 39.0% | 2.17 |

- **The strongest product links are flavours of one line.** Customers who buy one skyr yogurt buy other flavours too, which looks like stocking up on variety. A store could sell a mixed-flavour multipack, and when one flavour is out of stock, recommend the other flavours.
- **Drinks.** Over half of the baskets with Zero Calorie Cola also have Soda. This could be a cross-promotion, or customers buying two kinds of soda for different people. The data cannot tell us which.
- **Fresh produce.** Squash and zucchini, which are similar vegetables, are bought together (47.8%). A produce display could put them side by side.
- **The dashboard lookup.** `frequently_bought_together("Banana")` reads `rules_product.csv` and returns the products most often bought with it. The dashboard uses this for a "customers also bought" box.

Rules show **association, not cause**: they say that two items appear in the same baskets, not that buying one makes a customer buy the other.

## 3.3 Benchmark: Apriori against FP-Growth

`mining/benchmark.py` times only the mining step, on a **100,000-order sample** (98,508 aisle baskets and 83,658 product baskets), with itemsets capped at 3 items. For each `min_support`, runtime and memory are measured in **separate runs**, because the memory tracer (`tracemalloc`) slows Python down and would distort the times. Memory is the **peak extra memory** used while mining. Each setting was run once. Apriori used `low_memory=True`, as in section 3.1.

| Level | `min_support` | Itemsets | Apriori time | FP-Growth time | Apriori memory | FP-Growth memory |
|---|---|---|---|---|---|---|
| aisle | 0.05 | 170 | 0.18 s | 1.69 s | 18 MB | 69 MB |
| aisle | 0.01 | 2,329 | 1.14 s | 4.31 s | 26 MB | 134 MB |
| aisle | 0.005 | 6,142 | 2.32 s | 7.15 s | 30 MB | 147 MB |
| product | 0.01 | 159 | 0.42 s | 1.15 s | 26 MB | 83 MB |
| product | 0.003 | 1,078 | 5.80 s | 2.12 s | 109 MB | 104 MB |
| product | 0.0015 | 2,516 | 10.80 s | 3.51 s | 165 MB | 130 MB |

(The full table, with five `min_support` values per level, is `reports/results/benchmark.csv`.)

![Runtime of the mining step](figures/benchmark_runtime.png)

![Peak memory of the mining step](figures/benchmark_memory.png)

What the benchmark shows:

- **At product level, FP-Growth is faster once `min_support` is low.** The two are level at `min_support` 0.005 (about 1.6 s each). At 0.0015 FP-Growth takes 3.5 s and Apriori 10.8 s, a ratio of about 3. Apriori's time grows quickly with the number of itemsets, while FP-Growth's grows slowly. Apriori has to test every candidate pair and triple against the baskets again; FP-Growth reads the baskets into a compact tree once and finds the itemsets from the tree without more passes over the data. From 0.003 downwards FP-Growth also uses less memory (130 MB against 165 MB at 0.0015).
- **At aisle level, Apriori was faster and used less memory at every `min_support` we tried.** FP-Growth was about 3 to 9 times slower here, and used about 4 to 5 times as much memory. This is the opposite of the textbook result. Our explanation (we did not test it) is that there are only 132 aisle items and we cap itemsets at 3, so Apriori has few candidates to check, while the `mlxtend` FP-Growth builds its tree in Python and pays a fixed cost for it however few itemsets there are. The cost shows even at the highest `min_support`.
- **Lower `min_support` costs more for both**, as expected: the number of itemsets grows, and so does the time. Apriori's growth is the steeper one at product level.
- **Both found the same itemsets** at every setting (the script stops if they differ).

So the usual advice "FP-Growth is faster" is true for **many items and low support** (the product level), not for **few items**. The right choice depends on the data, and the benchmark is how to find out.

## 3.4 Limitations

- **Sampling.** The rules come from 500,000 of 3.18M orders (15.7%), and the benchmark from 100,000. The check in section 3.1 shows the sample is close to the full data for the top rule, but a rare rule can differ more. We did not repeat the check for every rule.
- **Only the top 1,000 products.** They cover 53.9% of order lines. Rules for the long tail of rare products are missing, and a niche product cannot get a recommendation.
- **Short itemsets and a cap on rules.** Itemsets stop at 3 items. At aisle level we keep the top 5,000 of 9,730 rules by lift, so the aisle file leaves out the weakest lift > 1 rules (lift below 1.42). Many aisle rules are the same group of aisles read in different directions, so the number of rules overstates the number of ideas.
- **No prices.** Every item counts the same. A strong link between two cheap items may matter less to revenue than a weaker link between expensive ones. With prices we would rank rules by the money they bring, not by lift.
- **One basket is one order.** The data does not show who bought for whom, and repeat purchases are included: customers who reorder the same items every week make those items look strongly linked.
- **Association is not cause**, and a high lift on a rare pair (support 0.16%) rests on a few hundred baskets.
- **Benchmark scope.** One run per setting, on one laptop, with `mlxtend`'s implementations, `max_len = 3`, and Apriori in its low-memory mode. A different library or settings could change which algorithm wins at aisle level.

## 3.5 How to reproduce

```bash
python mining/association_rules.py   # writes rules_aisle.csv and rules_product.csv (about 2 minutes)
python mining/benchmark.py           # writes benchmark.csv and the two charts (about 4 minutes)
pytest tests/test_rules.py           # hand-worked 5-basket example
```

```python
from mining.association_rules import frequently_bought_together
print(frequently_bought_together("Banana", top_n=5))
```

---

# 4. Customer segmentation

*Author: Member 4 (Customer Segmentation). This is one section of the single project report; Member 6 assembles the final document.*

## 4.1 Features

We group the **206,209 users** with K-Means on four features taken from the warehouse. They follow the classic RFM idea (recency, frequency, monetary value), adapted to a dataset with no prices and no dates, plus the reorder ratio.

| Feature | Source | Stands for |
|---|---|---|
| `recency_days` | `fact_order.days_since_prior` of the user's **last** order (highest `order_number`) | Recency |
| `total_orders` | `dim_user.total_orders` | Frequency |
| `avg_basket_size` | `dim_user.avg_basket_size` | Monetary value (a proxy: there are no prices) |
| `reorder_ratio` | `dim_user.reorder_ratio` | Loyalty to the same products |

**The recency caveat.** The data has no calendar dates, so we cannot say how long ago a user last ordered. `days_since_prior` on the last order is the gap *before* that order, so it measures how long the user waited between their last two orders. It is the best proxy available, but a user with a short last gap may still have left a long time ago. 30.6% of users have the value 30, which is the cap in the data ("30 days or more"). 75,000 users have a test order as their last order. It has no items, but it does have a valid gap, so recency still works for them; we never use its `basket_size`.

`avg_days_between_orders` is also in `dim_user`. It is *not* a clustering feature (it overlaps with recency and frequency); it is only shown in the profile table.

## 4.2 Scaling

K-Means uses distances, so a feature measured in large numbers would dominate one measured in small numbers (orders run to 100, the reorder ratio only from 0 to 1). We therefore **standardise** every feature to mean 0 and standard deviation 1.

Before that we looked at each feature's shape:

| Feature | Mean | Median | Skew | Skew after `log(1 + x)` |
|---|---|---|---|---|
| `recency_days` | 17.1 | 15 | 0.04 | |
| `total_orders` | 16.6 | 10 | **2.40** | 0.65 |
| `avg_basket_size` | 10.0 | 9 | **1.22** | -0.33 |
| `reorder_ratio` | 0.44 | 0.44 | 0.02 | |

`total_orders` and `avg_basket_size` have long right tails: a few users have 100 orders or 60-item baskets. Without a transform those few users would stretch the scale and squeeze everyone else together. We apply **`log(1 + x)` to these two features** and leave recency and the reorder ratio alone (they are already symmetric).

## 4.3 Choosing k

We ran K-Means (`n_init = 10`, `random_state = 42`) for k = 2 to 10 on all users. The silhouette score compares every pair of points, so it is computed on a **fixed random sample of 20,000 users**.

| k | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|
| Inertia (thousands) | 542 | 439 | 371 | 322 | 290 | 261 | 241 | 225 | 212 |
| Silhouette | **0.309** | 0.276 | 0.274 | 0.274 | 0.258 | 0.255 | 0.242 | 0.234 | 0.231 |

![Elbow curve](figures/segmentation_elbow.png)

![Silhouette score](figures/segmentation_silhouette.png)

- **The elbow is not sharp.** The inertia falls steadily, with no clear bend. The drops get smaller after k = 5.
- **k = 2 has the best silhouette** (0.309), but it only splits frequent from infrequent users, which is too coarse to act on, so we only consider k = 4 or more.
- **k = 3, 4 and 5 are about equal** (0.276, 0.274, 0.274). Differences of 0.002 are inside the noise of a 20,000-user sample, so the silhouette cannot rank them. At k = 3 the small-basket shoppers are absorbed into other groups: none of the three segments has a small basket.
- **We chose k = 4**, the smallest k among the ties. It has fewer segments than k = 5 for the same silhouette score, and each of the four can be described in one sentence (section 4.4). At k = 5 two of the clusters had similar averages and were harder to tell apart.

The rule is in `choose_k()`: among k = 4 to 8, take the best silhouette rounded to 3 decimals, and the smallest k if several tie.

## 4.4 The four segments

Names were written *after* looking at the averages, and `name_segment()` gives each name by a rule on those averages. All figures are the mean per segment (`reports/results/segment_profiles.csv`).

| Segment | Users | Share | Orders | Items per basket | Days between orders | Reorder ratio | Last gap (days) |
|---|---|---|---|---|---|---|---|
| **Loyal frequent shopper** | 60,586 | 29.4% | 35.1 | 10.7 | 9.7 | 66% | 9.4 |
| **Infrequent big-basket shopper** | 57,005 | 27.6% | 8.9 | 12.8 | 20.3 | 36% | 28.1 |
| **Regular mid-frequency shopper** | 51,657 | 25.1% | 8.7 | 10.5 | 13.9 | 33% | 8.4 |
| **Occasional small basket** | 36,961 | 17.9% | 9.1 | 3.8 | 19.6 | 38% | 24.7 |
| All users | 206,209 | 100% | 16.6 | 10.0 | 15.5 | 44% | 17.1 |

![The four segments, projected to 2 components](figures/segmentation_clusters.png)

The first two PCA components keep 50% and 25% of the variance. The picture shows that frequent users (orange) are well apart from the rest, and that the small-basket group (green) sits at the bottom, but the two middle groups overlap heavily (see the limitations).

**The loyal frequent shoppers are 29% of users, but they place about 62% of all orders and buy about 65% of all items.** The other three segments are about equal in order count (9 each); they differ in rhythm and basket size.

### What a store would do for each

- **Loyal frequent shopper.** The most valuable group: an order every 10 days, and two thirds of each basket is repeat items. Protect them: a "buy it again" list, a subscription or standing order, a loyalty reward, and no stock-outs on their usual items. The cost of losing one of them is high.
- **Infrequent big-basket shopper.** They shop about every 20 days but buy the most per visit (12.8 items), and their last gap was long (28 days). They are a bigger basket waiting to be won back: a reminder or offer around the 3-week mark, free delivery above a basket value, and bulk or multipack deals suit them.
- **Regular mid-frequency shopper.** Active recently (last gap 8 days), ordering about every two weeks with a typical basket, but only a third of their items are repeats, so they still explore. Cross-sell with recommendations (the association rules in section 3) and make them more regular, for example by suggesting a weekly list.
- **Occasional small basket.** They order every 20 days and buy only 3.8 items, 38% of the average basket. They are 17.9% of users but buy only about 3.6% of all items. Use low-cost actions: a minimum-order incentive or a suggestion to add one more item to the cart. A small basket may also mean a top-up from a different store.

## 4.5 Writing the result back

`python mining/segmentation.py` prints the chosen k, the silhouette score and the profile table, and then writes the segment name into **`dim_user.segment`** with one set-based `UPDATE ... FROM` over a registered table, instead of 206,209 single updates. After the run, `dim_user` has **206,209 users with a segment and 0 NULL**, and the four segment sizes add up to 206,209.

It also writes `segment_profiles.csv`, `segment_pca_sample.csv` (a random sample of 10,000 users with their two PCA coordinates, for the dashboard scatter plot), and the three charts above. `python etl/load.py --force` erases `segment`, so after any rebuild of the warehouse, run the script again.

## 4.6 Limitations

- **The segments overlap.** The silhouette score is 0.27, which means weak to moderate structure. Shoppers are a continuum, and K-Means cuts it into pieces; a user near the border of two segments could easily belong to the other. The picture of the first two components shows this.
- **K-Means assumes round clusters of similar size.** It uses straight-line distance to a centre, so it cannot find long, curved or very different-sized groups, and it is sensitive to the choice of k and to the starting centres (we fix the seed and use `n_init = 10`).
- **No prices.** Basket size counts items, so a basket of three expensive items looks smaller than a basket of ten cheap ones. The "monetary" feature is a proxy, and a segment called "big basket" may not be the biggest spender.
- **No calendar dates.** Recency is the gap before the last order, not the time since it (section 4.1), and 30.6% of users sit at the cap of 30 days. We cannot tell which users have left.
- **Users with few orders.** Every user has at least 4 orders, so we cannot segment new customers, and the averages of someone with 4 orders are noisy.
- **A snapshot.** The segments describe each user's whole history in one label. A shopper who changes habits keeps the old segment until the script is run again.
- **Silhouette on a sample.** The scores use 20,000 of the 206,209 users. Differences of 0.002 between k values are not meaningful.

## 4.7 How to reproduce

```bash
python mining/segmentation.py       # about 1 minute; close the dashboard and notebooks first (DuckDB allows one writer)
pytest tests/test_segmentation.py   # made-up users in 3 clear groups
```

```sql
SELECT segment, COUNT(*) AS users FROM dim_user GROUP BY segment ORDER BY users DESC;
```

---

# 5. Reorder prediction

*Author: Member 5 (Reorder Prediction & Evaluation), a stretch goal. This is one section of the single project report; Member 6 assembles the final document.*

## 5.1 The problem, the label and the features

**Question:** for a product a user has bought before, will they buy it again in their latest order?

- **Label.** Each user with a "train" order has a list of products they bought in their *prior* orders. For every user x product pair on that list, the label is **1 if the product is in the user's train order, and 0 if not**. The train order is the answer; it is used for the label and for nothing else.
- **Who can be used.** Only the 131,209 users with a train order have a label. The other 75,000 users' last order is a test order with no products.
- **Scale.** On the full data there are about 8.5 million such pairs, and about 9.8% are positive. We use a **random sample of 30,000 users** (fixed seed 42): **1,951,532 pairs, 9.7% positive**.

Every feature is built from **prior orders only**, in DuckDB SQL (`FEATURE_SQL` in `mining/reorder_model.py`), and only the finished table is brought into pandas.

| Group | Feature | Meaning |
|---|---|---|
| User | `u_orders` | number of prior orders |
| | `u_avg_basket` | average items per prior order |
| | `u_reorder_ratio` | share of the user's prior order lines that were reorders |
| | `u_avg_days_between` | average gap between the user's prior orders (days) |
| | `u_distinct_products` | different products the user has bought |
| Product | `p_orders` | popularity: prior order lines of the product, over all users |
| | `p_reorder_rate` | share of those lines that were reorders |
| | `p_users` | different users who bought it before |
| User x product | `up_times_bought` | how many prior orders contain the product |
| | `up_share` | `up_times_bought / u_orders` |
| | `up_orders_since_last` | orders since the user last bought it (0 = in the last prior order) |
| | `up_days_since_last` | days since the user last bought it (sum of the gaps after that order) |
| | `up_avg_cart_pos` | average position in the cart (early items are the habits) |

## 5.2 Avoiding leakage

**Data leakage** is when information from the answer slips into the inputs, so a model looks excellent in testing and fails in real use. Here the danger is the train order: if any feature used it, even indirectly (a product's "reorder rate" that counts the train order, or a user's "average basket" that includes it), the model would partly be reading the answer.

How we prevented it:

1. **The warehouse does not store which order is prior or train**, so `eval_set` is read from the raw `orders.csv` (through `etl.extract.register_raw_views`) into a small `order_eval` table.
2. **Every feature query filters on `eval_set = 'prior'`.** This includes the product features (`p_orders`, `p_reorder_rate`, `p_users`), which are calculated over *all users' prior orders only*.
3. **The train order appears in exactly one place:** the `train_labels` part of the query, which supplies the label after all the features are built. The candidate pairs also come only from prior orders, so a product that was bought for the first time in the train order is not a row.
4. **The train-order columns that are not a product list** (its day of week, hour, and gap since the previous order) are also left out, even though they would be known at order time, so that "prior orders only" is strictly true.
5. **A test checks it.** In `tests/test_reorder.py` the train orders are replaced with completely different baskets, with different `reordered` flags: the candidate pairs and every feature stay exactly the same, and only the labels change.

As a sanity check, the best ROC-AUC we found is 0.83. A value above about 0.95 would have been a warning sign of leakage.

## 5.3 Splitting and imbalance

**The split is by user, not by row.** Rows of the same user are alike (the same habits), so a row-level split would put almost-copies of a user in both training and test and flatter the score. We split the 30,000 users into **60% train (18,000 users), 20% validation (6,000) and 20% test (6,000)**, and a test checks that no user is in two sets.

| Set | Users | Rows | Positive |
|---|---|---|---|
| Train | 18,000 | 1,161,258 | 9.79% |
| Validation | 6,000 | 401,666 | 9.62% |
| Test | 6,000 | 388,608 | 9.69% |

**Why not accuracy.** Only about 1 pair in 10 is positive. A model that always answers "no" has an accuracy of **90.3%** on the test users and finds no reorder at all. Our models have *lower* accuracy (86.7% and 86.9%) while being far more useful, so accuracy would point to the wrong model. We use:

- **Precision:** of the products we predict will be reordered, the share that really are.
- **Recall:** of the products that really are reordered, the share we find.
- **F1:** the harmonic mean of precision and recall.
- **ROC-AUC:** the chance that a random reordered product gets a higher score than a random non-reordered one. 0.5 is random guessing and 1.0 is perfect. It does not depend on a threshold.

**Handling the imbalance.** Logistic Regression uses `class_weight = "balanced"`. LightGBM uses no class weights. For both, the **probability threshold is chosen on the validation users** (the one with the highest F1) and then used unchanged on the test users, so the test set is never used to tune anything. The threshold is a column in `reorder_metrics.csv`.

## 5.4 Results

All numbers are on the **6,000 test users (388,608 pairs, 37,664 of them positive)**.

| Model | Precision | Recall | F1 | ROC-AUC | Threshold |
|---|---|---|---|---|---|
| Logistic Regression (baseline) | 0.363 | 0.496 | 0.419 | 0.822 | 0.675 |
| **LightGBM** | **0.371** | **0.509** | **0.429** | **0.829** | 0.213 |

![ROC curves on the test users](figures/reorder_roc.png)

At its threshold, LightGBM predicts 51,663 reorders: **19,178 right, 32,485 wrong, and it misses 18,486** that did happen.

- **Both models are far above guessing** (ROC-AUC 0.5), and far above "always no" on F1 (which is 0).
- **We chose LightGBM** because it has the better ROC-AUC on the *validation* users (the choice is made there, not on the test set), and it also wins on every test metric.
- **But the gain is small:** 0.007 of ROC-AUC and 0.010 of F1. A simple, explainable Logistic Regression is almost as good. We did not tune LightGBM's settings, and we ran one split, so we cannot say how stable such a small gap is.
- **Precision is low: only about 37% of our "will reorder" predictions are right.** Whether someone reorders an item on a given trip has a lot of chance in it, and prices and dates might help. The model is a ranking aid ("which items to put on a reorder list first") more than an exact prediction.

## 5.5 What matters most

Importance of the 13 features in LightGBM (share of the total split gain):

![Feature importance](figures/reorder_feature_importance.png)

| Feature | Importance |
|---|---|
| `up_orders_since_last` | 31.2% |
| `up_share` | 26.6% |
| `up_times_bought` | 10.3% |
| `up_days_since_last` | 9.7% |
| `p_reorder_rate` | 7.6% |
| the other 8 features | 14.6% in total |

What it says about shopping habits:

- **Recency and habit decide it.** The two top features, how recently the user bought the product and how large a share of their orders contain it, make up 58% of the importance. The raw data agrees: **27.9% of products bought in the user's last prior order are bought again, against 2.8% of products last bought 5 or more orders ago.**
- **A product bought once is rarely bought again.** 60% of all pairs are products bought a single time, and only 4.7% of those come back in the next order. For a product bought 6 times it is 23.1%.
- **What the user buys matters more than who the user is.** All five user features together give about 11% of the importance, and the three product features about 10%, while the five user-and-product features give about 79%.
- **Some products are reordered by many users.** `p_reorder_rate` is fifth (7.6%): products that many users keep reordering (usually staples) are more likely to come back than one-off items.

For a store this suggests a "buy it again" list built from what the customer bought most recently and most often, with the list ordered by the model's score.

## 5.6 Limitations

- **A sample of users.** We train on 30,000 of the 131,209 users with a train order (22.9%), to keep the run to about 20 seconds. The results on the full set could be slightly different.
- **Only products the user has bought before.** The candidates are prior purchases, so the model cannot predict a first-time purchase in the train order. Those are missed by design.
- **No prices and no calendar dates.** The "days since last" feature is a sum of day gaps, not a date, and a price change or promotion cannot be a feature. Gaps are also capped at 30 days in the data.
- **Left-out information.** We did not use the day or hour of the train order, or its gap since the previous order. They would be available at order time and would probably help; we left them out to keep "prior orders only" strict.
- **The threshold reflects one choice.** Maximising F1 treats a missed reorder and a wrong prediction as equally bad. A store with a different cost would pick another threshold.
- **One split and no tuning.** We did not run cross-validation or search for better settings, so the small LightGBM gain is not proven.
- **Product statistics use other users' prior orders**, including users in our test set. These are not labels, and a real system would have that data too, so we do not count it as leakage, but it means a product's statistics were not computed from the training users alone.

## 5.7 How to reproduce

```bash
python mining/reorder_model.py     # about 20 seconds: prints both models' metrics, writes the two CSVs and two charts
pytest tests/test_reorder.py       # a tiny database with answers worked out by hand, and the leakage check
```

It needs the raw CSVs in `data/raw/` (for `eval_set`) and the built warehouse. The results are in `reports/results/reorder_metrics.csv` and `reorder_feature_importance.csv`.

---

# 6. Dashboard

*Author: Member 6 (Dashboard & Integration). This is one section of the single project report; `reports/build_report.py` assembles all sections into one file.*

## 6.1 What it shows

The dashboard is a **Streamlit** app with five pages. It is the one place where the warehouse and the results of all mining modules are visible together.

| Page | What it shows | Where the data comes from |
|---|---|---|
| **Overview** | Five headline numbers (3,421,083 orders, 206,209 users, 49,688 products, an average basket of 10.11 items, a 59.0% reorder rate), orders by hour for each day, the ten biggest departments, and four findings computed from the same numbers | live queries on the warehouse |
| **OLAP Explorer** | *Roll-up and drill-down* along the product hierarchy (department, aisle, product) or the time hierarchy (hour band, hour), with subtotals and a grand total. *Slice and dice* with filters for department, aisle, day, hour band and weekend. A *pivot heatmap* of any two dimensions. A rotatable **3-D cube** of any three dimensions (one ball per cell, size and colour = order lines), in which picking values on one axis highlights a slice and on several axes a dice | live queries on the warehouse |
| **Basket Rules** | A searchable table of the association rules at aisle and product level (filters for lift and confidence, CSV download), *product recommendations* from `frequently_bought_together()`, and the Apriori vs FP-Growth benchmark | `rules_aisle.csv`, `rules_product.csv`, `benchmark.csv` |
| **Customer Segments** | Segment sizes, how each segment differs from the average user, a 2-D (PCA) scatter plot of 10,000 users, the profile table and a store idea for each segment | `segment_profiles.csv`, `segment_pca_sample.csv` |
| **Reorder Model** | Precision, recall, F1 and ROC-AUC of both models, feature importance of the better one, the ROC curve, and a note on how to read the numbers | `reorder_metrics.csv`, `reorder_feature_importance.csv` |

To start it, from the project root:

```bash
streamlit run dashboard/app.py
```

## 6.2 How it is built

```
dashboard/app.py          entry point: the Overview page and the page menu (st.navigation)
dashboard/views/          the four other pages, which only draw charts and tables
dashboard/ui.py           cached versions of the queries, and the "missing file" message
dashboard/data.py         ALL the SQL and file reading (no Streamlit inside, so it can be tested)
reports/results/*.csv     result files written by the mining scripts and committed to git
```

The pages contain no SQL. They call functions in `dashboard/data.py`, which can be tested without a browser. The page folder is called `views/` rather than Streamlit's usual `pages/`: Streamlit treats a `pages/` folder as its older automatic page list, and a link straight to a page then skipped our page menu (the first entry showed as "app" instead of "Overview").

**Design decisions**

- **A query builder, not five fixed queries.** The OLAP Explorer lets the user choose dimensions and filters, so the SQL is built from a small whitelist of columns, and every value the user picks (a department name, a day) is passed to DuckDB as a **parameter**, never pasted into the SQL text. A test sends the text `x'; DROP TABLE dim_product; --` as a department and checks that nothing is dropped.
- **Mining results are read from files, not recomputed.** Following the shared contract (`handoff/PHASE4_SHARED_CONTRACT.md`), each mining script saves a small result file in `reports/results/`, and these are committed. So the Basket Rules, Segments and Reorder pages work on any teammate's laptop without running any mining, and they need no database.
- **The warehouse is opened read-only for each query and closed again.** DuckDB allows only one writer at a time, and the segmentation script writes `dim_user.segment`. Because the dashboard never keeps the file open, it does not block that script.
- **Caching.** Each query result is cached by Streamlit, so moving a slider or opening a tab again does not query 33.8M rows twice. Result files are cached for 60 seconds, so a re-run of a mining script shows up within a minute.
- **Friendly errors.** If the warehouse or a result file is missing, the page says what is missing and which command creates it (for example `python mining/segmentation.py`), instead of showing a stack trace.
- **The numbers are the same as in the report.** For example the OLAP Explorer's roll-up reproduces the department totals of section 2 (produce 9,888,378 order lines, grand total 33,819,106), and a query takes 0.1 to 0.3 seconds on the full data.
- **A demo extract for hosting.** The warehouse is not in git, so a hosted copy (Streamlit Community Cloud, free, see `docs/DEPLOY.md`) would have no data. `dashboard/build_demo_data.py` writes a 4.3 MB extract to `data/demo/`: the 33.8M order lines counted per product and day-hour slot (3.0M rows), the product and time dimensions, and the five headline numbers. Every OLAP question in the dashboard groups or filters by product, aisle, department, day or hour, and none looks inside an order, so these counts answer all of them exactly. The queries count order lines as `SUM(n)`, where a warehouse row has n = 1 and an extract row holds the count, and the app uses the extract whenever the warehouse is missing. A test checks that both sources give identical tables. The extract has no orders, users or baskets.

## 6.3 How it was tested

`tests/test_dashboard.py` has two parts:

1. **The data layer on a tiny made-up warehouse** (7 order lines, 4 products) with answers worked out by hand: the roll-up has detail rows, subtotals and a grand total that add up; a slice (weekend) and a dice (dairy eggs in the evening) give the hand-counted numbers; a pivot keeps the days in week order and fills empty cells with 0; the 3-D cube has every cell, including empty ones as 0, and a slice or dice highlights the right cells; a filter on a time column works even when the grouping does not use the time table; and the injection test above.
2. **Every page run headless on the real data** with Streamlit's `AppTest`: no page raises an error, the Overview shows 3,421,083 orders, 206,209 users and a 59.0% reorder rate, a filter changes the OLAP page without an error, the cube has 588 cells (21 departments x 7 days x 4 hour bands) and a Sunday slice holds exactly the 6,533,692 Sunday order lines of section 2, the rules search works, and the segments page lists the segments by name. A further test checks that the columns of every committed result file match the shared contract, so a mining script that changes its output format makes a test fail before it breaks the dashboard.

We also opened each page in a browser and looked at it.

## 6.4 Limitations

- **The demo extract must be rebuilt when the warehouse changes** (`python dashboard/build_demo_data.py`); a test fails until it is. Without the warehouse, the app runs on the extract, and the other three pages work from the committed result files alone.
- **The results are a snapshot.** The dashboard shows what the mining scripts last saved. If someone rebuilds the warehouse, the segments must be recomputed (`python mining/segmentation.py`), as `etl/load.py --force` erases them.
- **No user accounts, and no live data.** It is a single-user analysis tool, not a production application.
- **Product-level views are limited on purpose.** A product-level roll-up has about 50,000 rows, so the page asks the user to pick a department or an aisle first.
- **The "what a store would do" texts are written by us** for the four segment names the segmentation produced. A different clustering would need new texts (the page says so for a segment without one).
- **Tested headless and by eye.** `AppTest` checks that pages run and show the right numbers, not how they look on every screen size.

---

# 7. Insights, limitations and future work

*Author: Member 6 (Dashboard & Integration). Every number below comes from sections 1 to 5 and can be found there with its method.*

## 7.1 Key business insights

1. **Two departments carry the store.** Produce and dairy eggs make up **45.9%** of all order lines (29.2% and 16.7%). Their availability and freshness matter more than any promotion on a small department. *(Section 2)*

2. **Demand is very uneven in time.** Sunday is the busiest day (6.5M order lines) and Thursday the quietest (3.9M), a ratio of **1.66**. The two weekend days carry **33.2%** of all sales, against 28.6% if the week were flat. Sunday baskets are also the largest (11.2 items against 9.3 on Wednesday). Staffing, stock and delivery slots should follow this rhythm, with the peak at **10:00**. *(Section 2)*

3. **Alcohol is the exception to the weekly pattern.** It peaks on **Friday** (28,465 lines) and is lowest on Sunday (18,150), while the store as a whole is busiest on Sunday. Weekend stock for this department may need to arrive earlier in the week. *(Section 2)*

4. **Customers shop for "missions", and the rules show them.** Dry pasta, pasta sauce and packaged cheese form the strongest aisle group (lift up to **4.8**): 27.6% of baskets with dry pasta also contain pasta sauce, against 6.6% by chance. A "pasta night" shelf or bundle is a direct use. Pantry canned goods and the frozen "easy dinner" aisles show the same pattern. *(Section 3)*

5. **At product level, flavours of one line are bought together.** The strongest product rules link flavours of the same skyr yogurt (lift above **60**, about 1 in 5 baskets with one flavour has another). Customers stock up on variety, so mixed-flavour multipacks, and recommending the other flavours when one is out of stock, fit this behaviour. *(Section 3)*

6. **Under a third of the customers produce almost two thirds of the orders.** The **loyal frequent shoppers** are 29.4% of users but place about **62%** of all orders and buy about 65% of all items. They order every 10 days and 66% of their basket is repeat items, so a "buy it again" list, a standing order or a loyalty reward protects the most value. *(Section 4)*

7. **Habit predicts a reorder much more than customer traits do.** 59% of all order lines are products the customer has bought before. In a model that predicts reorders (ROC-AUC 0.83), the most important features are how recently and how often the customer bought the product: **27.9%** of products bought in the last order are bought again, against **2.8%** of those last bought five or more orders ago. A product bought only once comes back in 4.7% of cases. *(Section 5)*

8. **The right algorithm depends on the data.** FP-Growth is the usual favourite, and at product level with a low `min_support` it is about **3 times faster** than Apriori. At aisle level (132 items) Apriori was faster and lighter at every setting we tried. Benchmarking on the real data, not the textbook, settled the choice. *(Section 3)*

## 7.2 Limitations

These apply to the whole project; each section lists its own in more detail.

- **No prices.** Sales are counted as order lines, so a cheap and an expensive item weigh the same. Rankings by revenue could be different, and "basket size" is only a proxy for spending (sections 2, 3 and 4).
- **No calendar dates.** We see the day of the week and hour, but no months, seasons or trends, and "recency" is the gap before the last order, not the time since it (sections 2 and 4).
- **The day-of-week coding is assumed.** If 0 is not Sunday, the day names shift, but the patterns stay the same (section 2).
- **Samples and filters.** Rules come from 500,000 of 3.18M baskets and the top 1,000 products (54% of order lines), and the reorder model from 30,000 of 131,209 users. For the top rule, the sample was within about 7% of the full data, but we did not check every rule (sections 3 and 5).
- **Association is not cause.** A rule or a feature importance says what goes together, not what makes it happen.
- **The segments overlap.** K-Means cuts a continuum of shoppers into four groups (silhouette 0.27), so the borders are soft (section 4).
- **Modest predictive power.** The reorder model finds about half of the real reorders, and only about 37% of its "will reorder" predictions are right. LightGBM beat the simple baseline by a small margin that we did not prove stable (section 5).
- **A snapshot.** The warehouse is built once from a fixed file; there is no live data.

## 7.3 Future work

- **Add prices** to rank rules, segments and recommendations by revenue instead of counts.
- **Add real dates** to study trends and seasons, and to make recency a true recency.
- **Longer and sequential rules.** Allow itemsets of more than 3 items, and look at what is bought *after* what across orders.
- **A richer reorder model.** Add the day, hour and gap of the order being predicted, tune the model, and validate with cross-validation. Extend the candidates beyond products bought before.
- **Refresh automatically.** Re-run the pipeline and the mining scripts on a schedule, and keep segments up to date as customers change habits.
- **Serve recommendations.** Put `frequently_bought_together` and the reorder scores behind an API for a shop front-end, and test them with an A/B experiment.

## 7.4 Conclusion

StoreSense takes a 3.4-million-order grocery history from raw files to a validated star schema, answers when and what people buy with OLAP, finds what is bought together with two mining algorithms and compares them, groups 206,209 customers into four understandable segments, and predicts reorders without leaking the answer. The dashboard puts all of it in one place. Its main limits are the missing prices and dates, and the rest of the report says where each result stands because of them.
