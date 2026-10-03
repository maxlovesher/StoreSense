# Contributing to StoreSense

Every team member must contribute to this repository from **their own GitHub account**. Each person writes, commits and pushes the code for their own module, so they can explain it in the viva.

## 1. One-time setup

1. Accept the collaborator invite. It arrives by email and also appears at https://github.com/notifications.
2. Clone the repo and set up the environment (see the README).
3. Tell git who you are. **The email must be one that is added to your GitHub account**, or your commits won't show as yours:

   ```bash
   git config user.name "Your Name"
   git config user.email "the-email-on-your-github-account@example.com"
   ```

   You can check or add emails at https://github.com/settings/emails.

## 2. Who owns what

| # | Role | Branch | Your files |
|---|---|---|---|
| 1 | Data & ETL Lead | `feature/etl` | `etl/*.py`, `notebooks/eda.ipynb`, `tests/` |
| 2 | Warehouse & OLAP | `feature/warehouse` | `sql/schema.sql`, `sql/olap_queries.sql`, schema diagram |
| 3 | Association Rules | `feature/association-rules` | `mining/association_rules.py`, `mining/benchmark.py` |
| 4 | Customer Segmentation | `feature/segmentation` | `mining/segmentation.py` |
| 5 | Reorder Prediction | `feature/reorder-model` | `mining/reorder_model.py` |
| 6 | Dashboard & Integration | `feature/dashboard` | `dashboard/app.py`, `dashboard/pages/` |

If you need to change a file someone else owns, tell them first.

## 3. Daily workflow

```bash
# start from the latest main
git checkout main
git pull

# create your branch (first time only; afterwards just `git checkout feature/...`)
git checkout -b feature/segmentation

# ...write code...

git add mining/segmentation.py
git commit -m "Add elbow and silhouette plots for choosing k"
git push -u origin feature/segmentation
```

Then open a **Pull Request** into `main` on GitHub:
- Describe what you changed and how you tested it.
- Ask **one other team member** to review it.
- The reviewer approves and merges it.

Rules:
- **Commit small and often**, with messages that say what changed. One big commit at the end looks bad and is hard to review.
- **Never commit data.** No CSVs and no `.duckdb` files (`.gitignore` blocks them; don't force-add them).
- **Don't push directly to `main`.** Always go through a Pull Request.
- If your branch falls behind `main`, run `git pull origin main` on your branch and fix any conflicts.

## 4. Build order

Modules depend on each other, so work happens in this order:

1. **Phase 2.** ETL (member 1) and the schema (member 2) come first. Everything else reads from the warehouse.
2. **Meanwhile:**
   - Members 3, 4 and 5 can prototype on a small sample of the CSVs, using the table and column names from `sql/schema.sql`.
   - Member 6 can build the dashboard pages with placeholder data.
3. **Phase 3 onwards.** Once the warehouse is merged, switch to reading from `data/warehouse/storesense.duckdb`.

## 5. Code style

- Keep every script runnable on its own from the project root (`python mining/segmentation.py`).
- Do heavy work in DuckDB SQL, not pandas. The prior-orders file has ~32M rows.
- Write clear comments. Readability matters more than cleverness, because you will explain this code in the viva.
- Save charts for the report in `reports/figures/`.
