"""
Reorder prediction (stretch goal).

Owner: Member 5 (Reorder Prediction & Evaluation)
Spec:  docs/PROJECT_BRIEF.md, section 6.5

Predict whether a user/product pair seen in the user's PRIOR orders appears in
that user's train order (label 1) or not (label 0).

No leakage: every feature is built from prior orders only. The train order is
used for the label and nothing else. The warehouse does not store eval_set, so
it is read from the raw orders.csv (through etl.extract.register_raw_views).

Pipeline: sample users with a train order, build the features in DuckDB SQL,
split BY USER into train / validation / test, fit Logistic Regression (baseline)
and LightGBM, choose the probability threshold on the validation users, and
report precision, recall, F1 and ROC-AUC on the test users.

Writes reports/results/reorder_metrics.csv, reorder_feature_importance.csv,
reorder_threshold_curve.csv (for the dashboard's threshold slider) and two charts
in reports/figures/.

Run from the project root:
    python mining/reorder_model.py
"""
import duckdb
import matplotlib

matplotlib.use("Agg")   # draw to files, no window
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve, precision_score, recall_score, f1_score, roc_auc_score, roc_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common.db import FIGURES_DIR, PROJECT_ROOT, WAREHOUSE_PATH
from etl.extract import register_raw_views

SEED = 42
RESULTS_DIR = PROJECT_ROOT / "reports" / "results"
N_USERS = 30_000                     # users with a train order that we sample (of 131,209)
SPLIT = {"train": 0.6, "validation": 0.2, "test": 0.2}

USER_FEATURES = ["u_orders", "u_avg_basket", "u_reorder_ratio", "u_avg_days_between", "u_distinct_products"]
PRODUCT_FEATURES = ["p_orders", "p_reorder_rate", "p_users"]
USER_PRODUCT_FEATURES = ["up_times_bought", "up_share", "up_orders_since_last", "up_days_since_last", "up_avg_cart_pos"]
FEATURES = USER_FEATURES + PRODUCT_FEATURES + USER_PRODUCT_FEATURES


# ---------------------------------------------------------------------------
# 1. Data: one row per (user, product) pair from the prior orders
# ---------------------------------------------------------------------------
def connect(warehouse_path=WAREHOUSE_PATH) -> duckdb.DuckDBPyConnection:
    """
    An in-memory DuckDB with the two warehouse tables we need (as views on the
    read-only warehouse file) and order_eval (order_id, eval_set) from the raw CSV.
    """
    con = duckdb.connect()
    register_raw_views(con)
    con.execute(f"ATTACH '{warehouse_path.as_posix()}' AS wh (READ_ONLY)")
    for table in ("fact_order", "fact_order_line"):
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM wh.{table}")
    con.execute("CREATE TABLE order_eval AS SELECT order_id, eval_set FROM raw_orders")
    return con


def sample_train_users(con, n_users: int = N_USERS) -> np.ndarray:
    """A fixed random sample of users that have a train order (only they have a label)."""
    users = con.execute("""
        SELECT DISTINCT o.user_key
        FROM fact_order o JOIN order_eval e ON o.order_id = e.order_id
        WHERE e.eval_set = 'train' ORDER BY o.user_key
    """).df()["user_key"].to_numpy()
    if n_users < len(users):
        users = np.sort(np.random.default_rng(SEED).choice(users, n_users, replace=False))
    return users


# order_eval(order_id, eval_set) says which orders are prior and which is train.
# Features come from 'prior' orders only; the 'train' order is joined ONLY in the
# last step, to make the label.
FEATURE_SQL = """
WITH prior_orders AS (
    SELECT o.order_id, o.user_key, o.order_number, o.basket_size,
           SUM(COALESCE(o.days_since_prior, 0)) OVER (PARTITION BY o.user_key ORDER BY o.order_number) AS cum_days
    FROM fact_order o
    JOIN order_eval e ON o.order_id = e.order_id
    WHERE e.eval_set = 'prior' AND o.user_key IN (SELECT user_key FROM sample_users)
),
prior_lines AS (
    SELECT l.user_key, l.product_key, l.reordered, l.add_to_cart_order, po.order_number, po.cum_days
    FROM fact_order_line l
    JOIN prior_orders po ON l.order_id = po.order_id
),
user_orders AS (
    SELECT user_key, MAX(order_number) AS u_orders, AVG(basket_size) AS u_avg_basket, MAX(cum_days) AS total_days
    FROM prior_orders GROUP BY user_key
),
user_lines AS (
    SELECT user_key, AVG(reordered) AS u_reorder_ratio, COUNT(DISTINCT product_key) AS u_distinct_products
    FROM prior_lines GROUP BY user_key
),
product_stats AS (   -- popularity and reorder rate of each product, from every user's PRIOR orders
    SELECT l.product_key, COUNT(*) AS p_orders, AVG(l.reordered) AS p_reorder_rate,
           COUNT(DISTINCT l.user_key) AS p_users
    FROM fact_order_line l
    JOIN order_eval e ON l.order_id = e.order_id
    WHERE e.eval_set = 'prior'
    GROUP BY l.product_key
),
user_product AS (
    SELECT user_key, product_key, COUNT(*) AS up_times_bought, MAX(order_number) AS last_order_number,
           MAX(cum_days) AS last_cum_days, AVG(add_to_cart_order) AS up_avg_cart_pos
    FROM prior_lines GROUP BY user_key, product_key
),
train_labels AS (    -- the ONLY place the train order is used
    SELECT DISTINCT l.user_key, l.product_key
    FROM fact_order_line l
    JOIN order_eval e ON l.order_id = e.order_id
    WHERE e.eval_set = 'train' AND l.user_key IN (SELECT user_key FROM sample_users)
)
SELECT up.user_key, up.product_key,
       CASE WHEN tl.product_key IS NULL THEN 0 ELSE 1 END AS label,
       uo.u_orders, uo.u_avg_basket, ul.u_reorder_ratio,
       uo.total_days / NULLIF(uo.u_orders - 1, 0) AS u_avg_days_between,
       ul.u_distinct_products,
       ps.p_orders, ps.p_reorder_rate, ps.p_users,
       up.up_times_bought,
       up.up_times_bought * 1.0 / uo.u_orders AS up_share,
       uo.u_orders - up.last_order_number AS up_orders_since_last,
       uo.total_days - up.last_cum_days AS up_days_since_last,
       up.up_avg_cart_pos
FROM user_product up
JOIN user_orders uo ON up.user_key = uo.user_key
JOIN user_lines ul ON up.user_key = ul.user_key
JOIN product_stats ps ON up.product_key = ps.product_key
LEFT JOIN train_labels tl ON up.user_key = tl.user_key AND up.product_key = tl.product_key
ORDER BY up.user_key, up.product_key
"""


def build_pairs(con, user_keys) -> pd.DataFrame:
    """The finished feature table (one row per user x product pair) for these users, with the label."""
    con.register("sample_users", pd.DataFrame({"user_key": np.asarray(user_keys)}))
    try:
        df = con.execute(FEATURE_SQL).df()
    finally:
        con.unregister("sample_users")
    # u_avg_days_between is NULL for a user with a single prior order; 0 means "no gap seen"
    df["u_avg_days_between"] = df["u_avg_days_between"].fillna(0.0)
    return df


def split_users(user_keys, seed: int = SEED) -> dict[str, np.ndarray]:
    """Split the USERS (not the rows) into train / validation / test, so no user is in two sets."""
    users = np.random.default_rng(seed).permutation(np.unique(np.asarray(user_keys)))
    n_train = int(len(users) * SPLIT["train"])
    n_val = int(len(users) * SPLIT["validation"])
    return {
        "train": users[:n_train],
        "validation": users[n_train:n_train + n_val],
        "test": users[n_train + n_val:],
    }


# ---------------------------------------------------------------------------
# 2. Models
# ---------------------------------------------------------------------------
def make_models() -> dict:
    return {
        # standardised inputs; class_weight balances the 9.8% positive class
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=1000, random_state=SEED),
        ),
        # no class weights: the threshold is tuned on the validation users instead
        "lightgbm": LGBMClassifier(
            n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=100,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
            random_state=SEED, n_jobs=-1, verbose=-1,
        ),
    }


def best_threshold(y_true, proba) -> float:
    """The probability threshold with the highest F1 on these (validation) rows."""
    precision, recall, thresholds = precision_recall_curve(y_true, proba)
    f1 = 2 * precision[:-1] * recall[:-1] / np.clip(precision[:-1] + recall[:-1], 1e-12, None)
    return float(thresholds[int(np.argmax(f1))])


def evaluate(y_true, proba, threshold: float) -> dict:
    """Precision, recall and F1 at the threshold, and ROC-AUC (which needs no threshold)."""
    pred = (proba >= threshold).astype(int)
    return {
        "precision": precision_score(y_true, pred, zero_division=0),
        "recall": recall_score(y_true, pred, zero_division=0),
        "f1": f1_score(y_true, pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, proba),
        "threshold": threshold,
    }


def threshold_curve(name: str, y_true, proba, thresholds=None) -> pd.DataFrame:
    """Confusion-matrix counts at each threshold (0.01 to 0.99 by default), counted the same way as evaluate()."""
    y = np.asarray(y_true).astype(bool)
    proba = np.asarray(proba)
    if thresholds is None:
        thresholds = np.round(np.arange(1, 100) / 100, 2)
    rows = []
    for t in thresholds:
        pred = proba >= t
        rows.append({"model": name, "threshold": float(t),
                     "tp": int((pred & y).sum()), "fp": int((pred & ~y).sum()),
                     "fn": int((~pred & y).sum()), "tn": int((~pred & ~y).sum())})
    return pd.DataFrame(rows)


def importance(name: str, model) -> pd.DataFrame:
    """Feature importance as shares that add up to 1: LightGBM split gain, or |coefficient| for the logistic model."""
    if name == "lightgbm":
        raw = model.booster_.feature_importance(importance_type="gain").astype(float)
    else:
        raw = np.abs(model[-1].coef_[0])   # inputs are standardised, so coefficients are comparable
    share = raw / raw.sum() if raw.sum() > 0 else raw   # all zeros: a model that never split
    return pd.DataFrame({"model": name, "feature": FEATURES, "importance": share}).sort_values("importance", ascending=False)


def plot_roc(curves: dict, filename: str = "reorder_roc.png") -> None:
    fig, ax = plt.subplots(figsize=(5.5, 5))
    for name, (fpr, tpr, auc) in curves.items():
        ax.plot(fpr, tpr, label=f"{name} (AUC {auc:.3f})")
    ax.plot([0, 1], [0, 1], "k:", label="random guess (AUC 0.5)")
    ax.set_xlabel("false positive rate")
    ax.set_ylabel("true positive rate (recall)")
    ax.set_title("ROC curve on the test users")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / filename, dpi=150)
    plt.close(fig)


def plot_importance(imp: pd.DataFrame, model_name: str, filename: str = "reorder_feature_importance.png") -> None:
    imp = imp.sort_values("importance")
    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.barh(imp["feature"], imp["importance"])
    ax.set_xlabel("share of total importance")
    ax.set_title(f"Feature importance ({model_name})")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / filename, dpi=150)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    con = connect()
    try:
        users = sample_train_users(con)
        data = build_pairs(con, users)
    finally:
        con.close()
    print(f"{len(users):,} sampled users, {len(data):,} user x product pairs, {data['label'].mean():.1%} positive")

    sets = split_users(data["user_key"])
    part = {name: data[data["user_key"].isin(keys)] for name, keys in sets.items()}
    print({name: f"{len(d):,} rows / {len(sets[name]):,} users" for name, d in part.items()})

    metrics, importances, curves, val_auc, threshold_tables = [], {}, {}, {}, []
    for name, model in make_models().items():
        model.fit(part["train"][FEATURES], part["train"]["label"])
        p_val = model.predict_proba(part["validation"][FEATURES])[:, 1]
        threshold = best_threshold(part["validation"]["label"], p_val)
        p_test = model.predict_proba(part["test"][FEATURES])[:, 1]
        result = evaluate(part["test"]["label"], p_test, threshold)
        metrics.append({"model": name, **result,
                        "n_train_rows": len(part["train"]), "n_test_rows": len(part["test"])})
        val_auc[name] = roc_auc_score(part["validation"]["label"], p_val)
        fpr, tpr, _ = roc_curve(part["test"]["label"], p_test)
        curves[name] = (fpr, tpr, result["roc_auc"])
        threshold_tables.append(threshold_curve(name, part["test"]["label"], p_test))
        importances[name] = importance(name, model)
        print(f"{name}: " + ", ".join(f"{k} {v:.3f}" for k, v in result.items()))

    metrics = pd.DataFrame(metrics)
    best = max(val_auc, key=val_auc.get)   # the better model is chosen on the validation users, not the test users
    print(f"better model on the validation users: {best}")
    metrics.round({"precision": 4, "recall": 4, "f1": 4, "roc_auc": 4, "threshold": 4}).to_csv(
        RESULTS_DIR / "reorder_metrics.csv", index=False)
    importances[best].round({"importance": 5}).to_csv(RESULTS_DIR / "reorder_feature_importance.csv", index=False)
    pd.concat(threshold_tables).to_csv(RESULTS_DIR / "reorder_threshold_curve.csv", index=False)
    print(importances[best].round(3).to_string(index=False))
    plot_roc(curves)
    plot_importance(importances[best], best)


if __name__ == "__main__":
    main()
