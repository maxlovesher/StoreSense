# StoreSense: demo flow

About 10 minutes, five presenters. Each person shows their own module on the dashboard and answers questions about it. The numbers below are the real ones, so check them against the screen.

## Before the demo (5 minutes earlier)

```bash
git checkout main && git pull
python etl/validate.py          # 23 / 23 checks should pass
streamlit run dashboard/app.py  # then open http://localhost:8501
```

- Close any notebook that has the warehouse open (DuckDB allows one writer; the dashboard itself only reads).
- Open every page once so the queries are cached, and keep the browser at full screen.
- If the warehouse is missing, build it: `python etl/load.py` (about 15 seconds). The Basket Rules, Customer Segments and Reorder Model pages work without it.

## The flow

| Min | Page | Who | What to say and show |
|---|---|---|---|
| 0:00 | Slides | Member 6 | The problem (what do 3.4M grocery orders say?), the three limits of the data (no prices, no dates, day coding assumed), and the architecture diagram. |
| 1:30 | **Overview** | Member 1 | The five numbers: 3,421,083 orders, 206,209 users, 49,688 products, 10.11 items per basket, 59.0% reorder rate. Then the ETL flow in one sentence: raw CSVs, DuckDB views, transform, load, validate (23 checks pass). Point to "When do people shop?": the morning-to-afternoon hump, with Sunday on top. |
| 3:00 | **OLAP Explorer** | Member 2 | The star schema diagram first (2 facts, 3 dimensions). Then live: **roll-up** (department > aisle, grand total 33,819,106) and say "produce and dairy eggs are 45.9%"; **drill-down** (tick department *dairy eggs* and aisle *yogurt*, raise the level to Product); **slice** (Weekend only: 33.2% of lines from 2 of 7 days); **dice** (dairy eggs and produce, hour band Evening); **pivot** (Department by Day of week: alcohol is the one that peaks on Friday). |
| 5:00 | **Basket Rules** | Member 3 | Rules table at aisle level, search "pasta": dry pasta to pasta sauce, lift 4.2. Then Recommendations: pick a product and show what is bought with it. Then the benchmark: FP-Growth about 3 times faster at product level, Apriori faster at aisle level. Be ready to say why we think so and that we did not test it. |
| 6:30 | **Customer Segments** | Member 4 | The four segments and their sizes. "29% of users, about 62% of orders" for the loyal group. The scatter plot, and say honestly that the two middle groups overlap (silhouette 0.27). One idea per segment. |
| 8:00 | **Reorder Model** | Member 5 | ROC-AUC 0.83, precision 37%, recall 51%. Feature importance: recency and habit. Explain how leakage was avoided in one sentence: every feature comes from prior orders only, and a test proves that changing the train order changes no feature. |
| 9:00 | Slides | Member 6 | The key insights (report section 7) and the limitations, then questions. |

## If something goes wrong

- **A page shows a yellow message** ("... not found. Create it with: ..."): run the command in the message. The result files are normally committed, so this only happens on an old checkout.
- **"database is locked" or a connection error**: another program has the warehouse open for writing. Close it (a notebook, or a running `segmentation.py`) and reload the page.
- **A chart is slow the first time**: the first query on 33.8M rows takes up to a second. Open each page before the demo.
- **Port already in use**: `streamlit run dashboard/app.py --server.port 8502`.

## Questions to expect

| Topic | The answer to have ready |
|---|---|
| Why a star schema? | Dimensions stored once, small joins, fast `GROUP BY`. A primary key on the 33.8M-row fact table made the load 21 times slower, so we left it out and validate the keys instead (section 2). |
| Support, confidence, lift? | Share of baskets with both items; of baskets with A, the share with B; confidence divided by the support of B. Lift 1 means no link (section 3). |
| Why not accuracy for reorders? | "Always no" is 90.3% accurate and finds nothing (section 5). |
| How did you pick k? | Silhouette on a 20,000-user sample plus describability. k = 3, 4 and 5 tie, so we took the smallest that keeps the small-basket group (section 4). |
| What would change with prices? | Rank rules, segments and recommendations by revenue, not counts (section 7). |

The full report is `reports/StoreSense_report.md` (built with `python reports/build_report.py`).
