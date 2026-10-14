# 6. Dashboard

*Author: Member 6 (Dashboard & Integration). This is one section of the single project report; `reports/build_report.py` assembles all sections into one file.*

## 6.1 What it shows

The dashboard is a **Streamlit** app with five pages. It is the one place where the warehouse and the results of all mining modules are visible together.

| Page | What it shows | Where the data comes from |
|---|---|---|
| **Overview** | Five headline numbers (3,421,083 orders, 206,209 users, 49,688 products, an average basket of 10.11 items, a 59.0% reorder rate), orders by hour for each day, the ten biggest departments, and four findings computed from the same numbers | live queries on the warehouse |
| **OLAP Explorer** | *Roll-up and drill-down* along the product hierarchy (department, aisle, product) or the time hierarchy (hour band, hour), with subtotals and a grand total. *Slice and dice* with filters for department, aisle, day, hour band and weekend. A *pivot heatmap* of any two dimensions | live queries on the warehouse |
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
dashboard/pages/          the four other pages, which only draw charts and tables
dashboard/ui.py           cached versions of the queries, and the "missing file" message
dashboard/data.py         ALL the SQL and file reading (no Streamlit inside, so it can be tested)
reports/results/*.csv     result files written by the mining scripts and committed to git
```

The pages contain no SQL. They call functions in `dashboard/data.py`, which can be tested without a browser.

**Design decisions**

- **A query builder, not five fixed queries.** The OLAP Explorer lets the user choose dimensions and filters, so the SQL is built from a small whitelist of columns, and every value the user picks (a department name, a day) is passed to DuckDB as a **parameter**, never pasted into the SQL text. A test sends the text `x'; DROP TABLE dim_product; --` as a department and checks that nothing is dropped.
- **Mining results are read from files, not recomputed.** Following the shared contract (`handoff/PHASE4_SHARED_CONTRACT.md`), each mining script saves a small result file in `reports/results/`, and these are committed. So the Basket Rules, Segments and Reorder pages work on any teammate's laptop without running any mining, and they need no database.
- **The warehouse is opened read-only for each query and closed again.** DuckDB allows only one writer at a time, and the segmentation script writes `dim_user.segment`. Because the dashboard never keeps the file open, it does not block that script.
- **Caching.** Each query result is cached by Streamlit, so moving a slider or opening a tab again does not query 33.8M rows twice. Result files are cached for 60 seconds, so a re-run of a mining script shows up within a minute.
- **Friendly errors.** If the warehouse or a result file is missing, the page says what is missing and which command creates it (for example `python mining/segmentation.py`), instead of showing a stack trace.
- **The numbers are the same as in the report.** For example the OLAP Explorer's roll-up reproduces the department totals of section 2 (produce 9,888,378 order lines, grand total 33,819,106), and a query takes 0.1 to 0.3 seconds on the full data.

## 6.3 How it was tested

`tests/test_dashboard.py` has two parts:

1. **The data layer on a tiny made-up warehouse** (7 order lines, 4 products) with answers worked out by hand: the roll-up has detail rows, subtotals and a grand total that add up; a slice (weekend) and a dice (dairy eggs in the evening) give the hand-counted numbers; a pivot keeps the days in week order and fills empty cells with 0; a filter on a time column works even when the grouping does not use the time table; and the injection test above.
2. **Every page run headless on the real data** with Streamlit's `AppTest`: no page raises an error, the Overview shows 3,421,083 orders, 206,209 users and a 59.0% reorder rate, a filter changes the OLAP page without an error, the rules search works, and the segments page lists the segments by name. A further test checks that the columns of every committed result file match the shared contract, so a mining script that changes its output format makes a test fail before it breaks the dashboard.

We also opened each page in a browser and looked at it.

## 6.4 Limitations

- **It needs the built warehouse** (about 0.23 GB, built by `python etl/load.py` in about 15 seconds) for the Overview and OLAP pages. The other three pages work from the committed result files alone.
- **The results are a snapshot.** The dashboard shows what the mining scripts last saved. If someone rebuilds the warehouse, the segments must be recomputed (`python mining/segmentation.py`), as `etl/load.py --force` erases them.
- **No user accounts, and no live data.** It is a single-user analysis tool, not a production application.
- **Product-level views are limited on purpose.** A product-level roll-up has about 50,000 rows, so the page asks the user to pick a department or an aisle first.
- **The "what a store would do" texts are written by us** for the four segment names the segmentation produced. A different clustering would need new texts (the page says so for a segment without one).
- **Tested headless and by eye.** `AppTest` checks that pages run and show the right numbers, not how they look on every screen size.
