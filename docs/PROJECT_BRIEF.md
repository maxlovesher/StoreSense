# StoreSense: Retail Data Warehouse & Market Basket Analysis

> DMDW (Data Mining & Data Warehousing) course project, KIIT. Team of 6.
> This file is the project brief. Read it fully before writing any code.

## 1. Problem Statement

Design a retail data warehouse from real grocery transaction data and mine it to discover:
- which products are bought together (product associations)
- what types of customers exist (customer segments)
- when and what people buy (OLAP analysis)

All results are presented through an interactive dashboard.

## 2. Objectives

1. Build an **ETL pipeline** that turns raw CSVs into a clean **star-schema data warehouse**.
2. Support **OLAP operations**: roll-up, drill-down, slice, dice and pivot.
3. Mine **association rules** with **Apriori** and **FP-Growth**, and compare the two.
4. Perform **customer segmentation** with **K-Means** on RFM-style features.
5. *(Stretch)* Predict whether a customer will **reorder** a product, using classification.
6. Present everything in an **interactive dashboard**, with clear business insights.

## 3. Dataset

**Instacart Market Basket Analysis** (Kaggle). It has roughly 3.4M orders from about 206K users and about 50K products, organised into 134 aisles and 21 departments.

| File | Contents |
|---|---|
| `orders.csv` | One row per order: order_id, user_id, eval_set, order_number, order_dow, order_hour_of_day, days_since_prior_order |
| `order_products__prior.csv` | Products in prior orders (~32M rows): order_id, product_id, add_to_cart_order, reordered |
| `order_products__train.csv` | Products in each user's latest order (~1.4M rows), same columns |
| `products.csv` | product_id, product_name, aisle_id, department_id |
| `aisles.csv` | aisle_id, aisle |
| `departments.csv` | department_id, department |

**Known limitations** (state these openly in the report):
- **No prices.** Use basket size (items per order) as a stand-in for the "monetary" part of RFM.
- **No calendar dates.** There is only day-of-week, hour, and days since the previous order. The `days_since_prior_order` value is capped at 30.
- **Day-of-week coding is undocumented.** Treat `order_dow` as a day index from 0 to 6, and note the assumption that 0 means Sunday.

## 4. Architecture

```
Raw CSVs ──► ETL (Python) ──► DuckDB warehouse (star schema)
                                   │
          ┌────────────────────────┼─────────────────────────┐
          ▼                        ▼                         ▼
   OLAP queries            Association rules           Segmentation
 (ROLLUP / CUBE)          (Apriori vs FP-Growth)       (K-Means, RFM)
          └────────────────────────┼─────────────────────────┘
                                   ▼
                        Streamlit dashboard
```

## 5. Warehouse Design (Star Schema)

**Fact tables**
- `fact_order_line`: one row per product in an order. This is the main fact table.
  - Columns: order_id, product_key, user_key, time_key, add_to_cart_order, reordered
- `fact_order`: one row per order. This is an aggregate fact table for faster order-level analysis.
  - Columns: order_id, user_key, time_key, order_number, days_since_prior, basket_size, reordered_items

**Dimension tables**
- `dim_product`: product_key, product_name, aisle_id, aisle, department_id, department
  - Hierarchy: department → aisle → product
- `dim_user`: user_key, total_orders, avg_basket_size, avg_days_between_orders, reorder_ratio, segment
  - `segment` is filled in after clustering.
- `dim_time`: time_key, order_dow, day_name, is_weekend, order_hour_of_day, hour_band
  - Hierarchy: time of day (Morning / Afternoon / Evening / Night) → hour.

## 6. Modules

### 6.1 ETL
- **Extract:** read the CSVs with DuckDB, which handles the 32M-row file comfortably.
- **Transform:**
  - clean nulls (`days_since_prior_order` is null for each user's first order)
  - join the product, aisle and department hierarchy
  - build the time dimension
  - compute user-level aggregates
- **Load:** create the tables in `data/warehouse/storesense.duckdb` from `sql/schema.sql`.
- **Validate:** check row counts, check that every foreign key has a matching dimension row, and confirm there are no orphan keys.

### 6.2 OLAP
Use DuckDB `GROUP BY ROLLUP / CUBE` and save the queries in `sql/olap_queries.sql`. Each operation needs a demo query:
- **Roll-up / drill-down:** department → aisle → product sales counts
- **Slice:** for example, weekend orders only
- **Dice:** for example, the Produce and Dairy departments in evening hours only
- **Pivot:** department × day-of-week matrix

### 6.3 Association Rule Mining
- **Algorithms:** Apriori and FP-Growth (mlxtend), at two levels:
  - **Aisle level:** 134 items, so the full dataset is feasible.
  - **Product level:** restrict to the top ~1,000–2,000 products and/or a sample of orders, to keep memory under control.
- **Metrics:** support, confidence and lift. Filter rules to lift > 1.
- **Benchmark:** compare runtime and memory of Apriori vs FP-Growth across several min_support values, and plot the results.
- **Output:**
  - top rules with plain-English interpretation
  - a "frequently bought together" lookup for any product

### 6.4 Customer Segmentation
- **Features per user:**
  - recency: days_since_prior of the user's last order
  - frequency: total orders
  - monetary proxy: average basket size
  - reorder ratio
- **Preprocessing:** standardise all features.
- **Choosing k:** use the elbow method plus silhouette score.
- **Clustering:** K-Means. Profile each cluster and give it a human-readable name (for example "Loyal weekly stock-up", "Occasional small basket").
- **Write back:** store each user's segment in `dim_user.segment`.

### 6.5 Reorder Prediction *(stretch goal)*
- **Target:** whether a user/product pair from prior orders appears in that user's train order.
- **Features:** user features, product features (overall reorder rate, popularity), and user×product features (times bought, last bought).
- **Models:** Logistic Regression as the baseline, then Random Forest or LightGBM.
- **Evaluation:** precision, recall, F1 and ROC-AUC. Accuracy is misleading here because the classes are imbalanced.

### 6.6 Dashboard (Streamlit)
Pages:
1. **Overview:** KPIs (orders, users, products, average basket size, reorder rate)
2. **OLAP Explorer:** pick a dimension and level; roll-up, drill-down and slice with filters; pivot heatmap
3. **Basket Rules:** a searchable rules table, product recommendations, and the Apriori vs FP-Growth benchmark chart
4. **Customer Segments:** cluster scatter/PCA plot, segment profiles, segment sizes
5. **Reorder Model** *(if built):* metrics and feature importance

## 7. Tech Stack

- **Language:** Python 3.11+
- **Warehouse / query engine:** DuckDB
- **Data handling:** pandas (polars optional for speed)
- **Mining:** mlxtend (Apriori, FP-Growth), scikit-learn (K-Means, classifiers)
- **Visualisation:** Plotly
- **Dashboard:** Streamlit
- **Diagrams:** dbdiagram.io or draw.io for the star schema

## 8. Repository Structure

```
storesense/
├── data/
│   ├── raw/                 # Kaggle CSVs (gitignored)
│   └── warehouse/           # storesense.duckdb (gitignored)
├── etl/
│   ├── extract.py
│   ├── transform.py
│   ├── load.py
│   └── validate.py
├── sql/
│   ├── schema.sql
│   └── olap_queries.sql
├── mining/
│   ├── association_rules.py
│   ├── benchmark.py
│   ├── segmentation.py
│   └── reorder_model.py
├── dashboard/
│   ├── app.py
│   └── views/               # the other pages (named views/, not pages/, so that st.navigation is used)
├── notebooks/
│   └── eda.ipynb
├── reports/figures/
├── tests/
├── requirements.txt
└── README.md
```

## 9. Team Roles (6 members)

| # | Role | Owns |
|---|---|---|
| 1 | Data & ETL Lead | Extract/transform/load scripts, data validation, EDA notebook |
| 2 | Warehouse & OLAP | Star schema, `schema.sql`, OLAP queries, schema diagram |
| 3 | Association Rules | Apriori + FP-Growth, rule interpretation, benchmark |
| 4 | Customer Segmentation | Feature engineering, K-Means, cluster profiling |
| 5 | Reorder Prediction & Evaluation | Classification model, metrics, model comparison |
| 6 | Dashboard & Integration | Streamlit app, connecting all modules, final demo flow |

Everyone contributes slides for their own module to the final presentation and report.

## 10. Build Phases

1. **Setup:** repo, environment, `requirements.txt`, data download instructions in the README
2. **ETL + Warehouse:** star schema built and validated in DuckDB
3. **OLAP:** all five operations demonstrated with saved queries
4. **Mining:** association rules + benchmark, then segmentation, then (stretch) reorder model
5. **Dashboard:** all pages working off the warehouse
6. **Report & Presentation:** diagrams, results, insights, limitations

## 11. Presentation Deliverables

- Problem statement and objectives
- Dataset overview and its limitations
- Star schema diagram and ETL flow diagram
- Live OLAP demo (roll-up, drill-down, slice, dice, pivot)
- Top association rules with business interpretation
- Apriori vs FP-Growth benchmark chart
- Customer segment profiles
- Key business insights (5–8 clear findings)
- Limitations and future scope
