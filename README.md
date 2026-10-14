# StoreSense: Retail Data Warehouse & Market Basket Analysis

DMDW (Data Mining & Data Warehousing) course project, KIIT.

StoreSense builds a star-schema data warehouse from the Instacart grocery dataset and mines it to find:
- which products are bought together (Apriori and FP-Growth)
- what kinds of customers exist (K-Means segmentation)
- when and what people buy (OLAP)

The results are shown in a Streamlit dashboard.

The full project brief is in [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md).
How the team works on this repo is in [CONTRIBUTING.md](CONTRIBUTING.md).

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

## Team

| # | Role | Member | GitHub |
|---|---|---|---|
| 1 | Data & ETL Lead | Manish Sarkar | [@maxlovesher](https://github.com/maxlovesher) |
| 2 | Warehouse & OLAP | Kavya | [@Kavya-025](https://github.com/Kavya-025) |
| 3 | Association Rules | _name_ | [@KB-0141](https://github.com/KB-0141) |
| 4 | Customer Segmentation | Manish Dey | [@foresto-dreamer](https://github.com/foresto-dreamer) |
| 5 | Reorder Prediction & Evaluation | Animesh Prakash | [@DIO4699](https://github.com/DIO4699) |
| 6 | Dashboard & Integration | Rohit Gupta | [@rohitguptanit7070-lab](https://github.com/rohitguptanit7070-lab) |

## 1. Setup

You need Python 3.11 or newer.

```bash
git clone https://github.com/maxlovesher/StoreSense.git
cd StoreSense
python -m venv .venv
```

Activate the environment:
- Windows: `.venv\Scripts\activate`
- macOS / Linux: `source .venv/bin/activate`

Then install the dependencies:

```bash
pip install -r requirements.txt
pip install -e .
```

The second command (run once) lets every script import the shared helpers in `common/`, wherever it is run from.

## 2. Get the data

The dataset is **Instacart Market Basket Analysis** on Kaggle. It is about 700 MB unzipped and is **not** stored in this repo.

1. Sign in to Kaggle, open the [competition data page](https://www.kaggle.com/competitions/instacart-market-basket-analysis/data), and accept the competition rules. You must do this once with your own account, or the download is refused.
2. Download the files, either:
   - from the **Download All** button on that page, or
   - with the Kaggle CLI (`pip install kaggle`, with your API token in `~/.kaggle/kaggle.json`):
     ```bash
     kaggle competitions download -c instacart-market-basket-analysis -p data/raw
     ```
3. Unzip everything so these six files sit directly in `data/raw/`:

```
data/raw/orders.csv
data/raw/order_products__prior.csv
data/raw/order_products__train.csv
data/raw/products.csv
data/raw/aisles.csv
data/raw/departments.csv
```

`data/raw/` and `data/warehouse/` are gitignored. Never commit CSVs or the `.duckdb` file.

## 3. Run the pipeline

Run every command from the project root. Each script can be run on its own.

| Step | Command | Phase |
|---|---|---|
| Extract | `python etl/extract.py` | 2 |
| Transform | `python etl/transform.py` | 2 |
| Load into DuckDB | `python etl/load.py` | 2 |
| Validate warehouse | `python etl/validate.py` | 2 |
| Tests | `pytest` | 2 |
| Association rules | `python mining/association_rules.py` | 4 |
| Apriori vs FP-Growth benchmark | `python mining/benchmark.py` | 4 |
| Customer segmentation | `python mining/segmentation.py` | 4 |
| Reorder model (stretch) | `python mining/reorder_model.py` | 4 |
| Dashboard | `streamlit run dashboard/app.py` | 5 |
| Assemble the report | `python reports/build_report.py` | 6 |

The OLAP demo queries are in `sql/olap_queries.sql`. The mining result files the dashboard reads are in `reports/results/` (committed), the assembled report is `reports/StoreSense_report.md`, and the demo script is [docs/DEMO_FLOW.md](docs/DEMO_FLOW.md).

## 4. Repository layout

```
data/raw/            Kaggle CSVs (gitignored)
data/warehouse/      storesense.duckdb (gitignored)
common/              shared paths and DuckDB connection helper (used by every module)
etl/                 extract, transform, load, validate
sql/                 schema.sql, olap_queries.sql
mining/              association rules, benchmark, segmentation, reorder model
dashboard/           Streamlit app and pages
notebooks/           EDA notebook
reports/figures/     saved charts for the report
tests/               ETL row-count and key-integrity tests
docs/                project brief
```

## 5. Dataset limitations

- **No prices.** Basket size (items per order) is used in place of the "monetary" part of RFM.
- **No calendar dates.** There is only day-of-week, hour, and days since the previous order, and that last value is capped at 30.
- **Day-of-week coding is undocumented.** We assume `order_dow = 0` means Sunday.
