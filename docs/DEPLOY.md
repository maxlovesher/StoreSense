# Deploying the dashboard (free, Streamlit Community Cloud)

The dashboard is a Streamlit app, so it is hosted on **Streamlit Community Cloud**, which is free and deploys straight from this GitHub repository. (Vercel and similar hosts run static sites and short serverless functions; a Streamlit app needs a server that stays running, so it does not work there.)

## Why it works without the warehouse

The warehouse file (0.23 GB) is not in git. The hosted app uses the **demo extract** in `data/demo/` instead (4.3 MB, committed): the order lines already counted per product and day-hour slot, plus the product and time dimensions and the five headline numbers. The Overview and OLAP pages give exactly the same numbers from it (a test compares the two). The other three pages read the committed result files in `reports/results/`. The sidebar says which data source is in use.

The extract holds counts and product names only: no orders, users or baskets.

## One-time setup (about 5 minutes)

Do this from the GitHub account that owns the repository (`maxlovesher`), after the deploy pull request is merged into `main`.

1. Open https://share.streamlit.io and choose **Continue with GitHub**. Sign in, and allow Streamlit to see your repositories. The repository is private, so allow access to private repositories when asked.
2. Click **Create app**, then choose to deploy from a GitHub repository.
3. Fill in:
   - **Repository:** `maxlovesher/StoreSense`
   - **Branch:** `main`
   - **Main file path:** `dashboard/app.py`
   - **App URL:** pick a name, for example `storesense`
4. Open **Advanced settings** and choose **Python 3.11** or **3.12**.
5. Click **Deploy**. The first build installs the packages in `dashboard/requirements.txt` and takes a few minutes. Then the app opens at its URL.
6. Decide who may see it: in the app's **Share** settings, either invite the teammates and the examiner by email, or make it viewable by anyone with the link.

## After that

- **Every push to `main` redeploys the app** automatically.
- **If the warehouse changes** (for example a new ETL run), rebuild and commit the extract:
  ```bash
  python dashboard/build_demo_data.py
  ```
  The test `test_committed_demo_extract_matches_the_warehouse` fails until you do.
- **If a mining result changes**, commit the new file in `reports/results/` as usual.
- **To try the hosted setup locally**, force the demo extract:
  ```bash
  STORESENSE_DATA=demo streamlit run dashboard/app.py
  ```
  (In PowerShell: `$env:STORESENSE_DATA="demo"; streamlit run dashboard/app.py`.)

## If something goes wrong

- **The app shows an error page:** open **Manage app** (bottom right of the app) to see the build and run logs.
- **`ModuleNotFoundError`:** check that the main file path is exactly `dashboard/app.py`. The app adds the project folder to Python's import path itself, so no `pip install -e .` is needed.
- **The app is asleep:** free apps go to sleep after a while without visitors. Open it and click the button to wake it; it starts again in under a minute. Open it before a demo.
