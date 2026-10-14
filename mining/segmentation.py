"""
Customer segmentation (K-Means on RFM-style features).

Owner: Member 4 (Customer Segmentation)
Spec:  docs/PROJECT_BRIEF.md, section 6.4

Builds four features per user (recency, frequency, a monetary proxy and the
reorder ratio), standardises them, picks k with the elbow method plus the
silhouette score, clusters with K-Means, names each segment from its averages
and writes the name back to dim_user.segment.

Writes reports/results/segment_profiles.csv, segment_pca_sample.csv and three
charts in reports/figures/. This script is the only one that writes into the
warehouse: close the dashboard and any notebook before running it.

Run from the project root:
    python mining/segmentation.py
"""
import matplotlib

matplotlib.use("Agg")   # draw to files, no window
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from common.db import FIGURES_DIR, PROJECT_ROOT, get_connection

SEED = 42
RESULTS_DIR = PROJECT_ROOT / "reports" / "results"

# The four K-Means features, in the order of RFM + reorder ratio.
FEATURES = ["recency_days", "total_orders", "avg_basket_size", "reorder_ratio"]
# These two are right-skewed (a few users have 100 orders or 60-item baskets), so
# they are log-transformed before scaling; recency (capped at 30) and the ratio (0 to 1) are not.
LOG_FEATURES = ["total_orders", "avg_basket_size"]

K_RANGE = range(2, 11)          # k values tried for the elbow and silhouette curves
# k is chosen from these. k = 2 only splits "active" from "not active". k = 3 scores the same as
# 4 and 5 (the differences are inside the noise of the 20,000-user sample) but it merges the
# small-basket shoppers into other groups, so we ask for at least 4 segments.
K_CANDIDATES = range(4, 9)
SILHOUETTE_SAMPLE = 20_000      # silhouette compares every pair of points, so it uses a sample
PCA_SAMPLE = 10_000


# ---------------------------------------------------------------------------
# 1. Features
# ---------------------------------------------------------------------------
def build_features(con) -> pd.DataFrame:
    """
    One row per user: user_key, the four features, and avg_days_between_orders
    (kept for the profile table only, it is not a clustering feature).

    Recency is days_since_prior of the user's LAST order (highest order_number).
    The data has no calendar dates, so this is the gap before the last order, not
    the time since it. The last order can be a test order with no items: that is
    fine for recency (we never use its basket_size).
    """
    return con.execute("""
        WITH last_order AS (
            SELECT user_key, days_since_prior,
                   ROW_NUMBER() OVER (PARTITION BY user_key ORDER BY order_number DESC) AS rn
            FROM fact_order
        )
        SELECT u.user_key,
               l.days_since_prior AS recency_days,
               u.total_orders,
               u.avg_basket_size,
               u.reorder_ratio,
               u.avg_days_between_orders
        FROM dim_user u
        JOIN last_order l ON l.user_key = u.user_key AND l.rn = 1
        ORDER BY u.user_key
    """).df()


def scale_features(features: pd.DataFrame) -> np.ndarray:
    """Log-transform the skewed features, then standardise all four (mean 0, std 1)."""
    x = features[FEATURES].astype(float).copy()
    for col in LOG_FEATURES:
        x[col] = np.log1p(x[col])
    return StandardScaler().fit_transform(x)


# ---------------------------------------------------------------------------
# 2. Choosing k
# ---------------------------------------------------------------------------
def fit_kmeans(scaled: np.ndarray, k: int) -> KMeans:
    return KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(scaled)


def evaluate_k(scaled: np.ndarray, ks=K_RANGE) -> pd.DataFrame:
    """Inertia (for the elbow) and silhouette score (on a fixed random sample) for each k."""
    rows = []
    for k in ks:
        model = fit_kmeans(scaled, k)
        sample = min(SILHOUETTE_SAMPLE, len(scaled))
        sil = silhouette_score(scaled, model.labels_, sample_size=sample, random_state=SEED)
        rows.append({"k": k, "inertia": model.inertia_, "silhouette": sil})
    return pd.DataFrame(rows)


def choose_k(scores: pd.DataFrame, candidates=K_CANDIDATES) -> int:
    """
    The k with the best silhouette score among the candidates, rounded to 3 decimals.
    If several k tie, take the smallest: the same quality with fewer segments, and each
    segment is easier to describe in one sentence.
    """
    pool = scores[scores["k"].isin(list(candidates))].copy()
    pool["sil_rounded"] = pool["silhouette"].round(3)
    best = pool["sil_rounded"].max()
    return int(pool.loc[pool["sil_rounded"] == best, "k"].min())


# ---------------------------------------------------------------------------
# 3. Profiling and naming
# ---------------------------------------------------------------------------
def profile_segments(features: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    """Average of every feature per cluster, with its size. Clusters are numbered by the cluster id."""
    df = features.assign(cluster=labels)
    prof = df.groupby("cluster").agg(
        users=("user_key", "size"),
        avg_total_orders=("total_orders", "mean"),
        avg_basket_size=("avg_basket_size", "mean"),
        avg_days_between_orders=("avg_days_between_orders", "mean"),
        avg_reorder_ratio=("reorder_ratio", "mean"),
        avg_recency_days=("recency_days", "mean"),
    )
    prof["share_of_users"] = prof["users"] / prof["users"].sum()
    return prof


# What each name means for the store. The names come from the rules in name_segment(),
# which compare each cluster's averages with the average of all users.
MEANINGS = {
    "Loyal frequent shopper": "orders very often and reorders most of the basket",
    "Occasional small basket": "orders rarely and buys only a few items each time",
    "Infrequent big-basket shopper": "orders rarely, with a long gap before the last order, but buys a lot each time",
    "Regular mid-frequency shopper": "orders every couple of weeks, with a typical basket and few repeat items",
}


def name_segment(row: pd.Series, overall: pd.Series) -> str:
    """
    A name from the cluster's averages compared with all users (checked in order).
    Written after looking at the profile table, so each name matches its numbers.
    """
    if row["avg_total_orders"] > 1.5 * overall["avg_total_orders"]:
        return "Loyal frequent shopper"
    if row["avg_basket_size"] < 0.6 * overall["avg_basket_size"]:
        return "Occasional small basket"
    if row["avg_basket_size"] > 1.1 * overall["avg_basket_size"] and row["avg_recency_days"] > overall["avg_recency_days"]:
        return "Infrequent big-basket shopper"
    if row["avg_recency_days"] <= overall["avg_recency_days"]:
        return "Regular mid-frequency shopper"
    return f"Segment {int(row.name)}"   # no rule fits: keep a neutral name, never a wrong one


def name_segments(prof: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Add segment (name) and description columns to the profile table."""
    overall = pd.Series({
        "avg_total_orders": features["total_orders"].mean(),
        "avg_basket_size": features["avg_basket_size"].mean(),
        "avg_recency_days": features["recency_days"].mean(),
    })
    prof = prof.copy()
    prof["segment"] = prof.apply(name_segment, axis=1, overall=overall)
    # two clusters must never share a name: add the cluster id to them
    dup = prof["segment"].duplicated(keep=False)
    prof.loc[dup, "segment"] = prof.loc[dup, "segment"] + " (" + prof.loc[dup].index.astype(str) + ")"
    prof["description"] = [
        f"{MEANINGS.get(r.segment, 'a group of similar shoppers')}: about {r.avg_total_orders:.0f} orders, "
        f"a new order every {r.avg_days_between_orders:.0f} days, {r.avg_basket_size:.1f} items per basket, "
        f"{r.avg_reorder_ratio:.0%} of items reordered."
        for r in prof.itertuples()
    ]
    return prof


PROFILE_COLUMNS = [
    "segment", "users", "share_of_users", "avg_total_orders", "avg_basket_size",
    "avg_days_between_orders", "avg_reorder_ratio", "avg_recency_days", "description",
]


# ---------------------------------------------------------------------------
# 4. Write-back and outputs
# ---------------------------------------------------------------------------
def write_segments(con, user_keys, segments) -> None:
    """Set dim_user.segment for every user with one set-based UPDATE (needs a writable connection)."""
    seg = pd.DataFrame({"user_key": np.asarray(user_keys), "segment": np.asarray(segments)})
    con.register("new_segments", seg)
    con.execute("""
        UPDATE dim_user SET segment = s.segment
        FROM new_segments s
        WHERE dim_user.user_key = s.user_key
    """)
    con.unregister("new_segments")


def pca_sample(scaled: np.ndarray, features: pd.DataFrame, segments: np.ndarray, n: int = PCA_SAMPLE) -> tuple[pd.DataFrame, np.ndarray]:
    """Project all users to 2 components, return a random sample (for the dashboard scatter plot)."""
    pca = PCA(n_components=2, random_state=SEED)
    coords = pca.fit_transform(scaled)
    idx = np.sort(np.random.default_rng(SEED).choice(len(coords), min(n, len(coords)), replace=False))
    out = pd.DataFrame({
        "user_key": features["user_key"].to_numpy()[idx],
        "pc1": coords[idx, 0].round(4),
        "pc2": coords[idx, 1].round(4),
        "segment": np.asarray(segments)[idx],
    })
    return out, pca.explained_variance_ratio_


def plot_k_selection(scores: pd.DataFrame, k: int) -> None:
    for column, ylabel, filename, title in (
        ("inertia", "inertia (within-cluster sum of squares)", "segmentation_elbow.png", "Elbow method"),
        ("silhouette", "silhouette score (20,000-user sample)", "segmentation_silhouette.png", "Silhouette score"),
    ):
        fig, ax = plt.subplots(figsize=(5.5, 4))
        ax.plot(scores["k"], scores[column], "o-")
        ax.axvline(k, color="tab:red", linestyle="--", label=f"chosen k = {k}")
        ax.set_xlabel("number of clusters k")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / filename, dpi=150)
        plt.close(fig)


def plot_clusters(sample: pd.DataFrame, explained: np.ndarray) -> None:
    fig, ax = plt.subplots(figsize=(7, 5.5))
    for name, d in sample.groupby("segment"):
        ax.scatter(d["pc1"], d["pc2"], s=5, alpha=0.5, label=name)
    ax.set_xlabel(f"PC1 ({explained[0]:.0%} of variance)")
    ax.set_ylabel(f"PC2 ({explained[1]:.0%} of variance)")
    ax.set_title("Segments, 10,000 random users projected to 2 components")
    ax.legend(markerscale=4, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "segmentation_clusters.png", dpi=150)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    con = get_connection(read_only=False)
    try:
        features = build_features(con)
        scaled = scale_features(features)
        print(f"{len(features):,} users, features: {', '.join(FEATURES)}")

        scores = evaluate_k(scaled)
        print(scores.round(3).to_string(index=False))
        k = choose_k(scores)
        model = fit_kmeans(scaled, k)
        sil = scores.loc[scores["k"] == k, "silhouette"].iloc[0]
        print(f"chosen k = {k} (silhouette {sil:.3f})")

        prof = name_segments(profile_segments(features, model.labels_), features)
        names = prof["segment"].reindex(model.labels_).to_numpy()
        out = prof[PROFILE_COLUMNS].sort_values("users", ascending=False)
        out.round({"share_of_users": 4, "avg_total_orders": 2, "avg_basket_size": 2,
                   "avg_days_between_orders": 2, "avg_reorder_ratio": 3, "avg_recency_days": 2}
                  ).to_csv(RESULTS_DIR / "segment_profiles.csv", index=False)
        print(out.drop(columns="description").round(3).to_string(index=False))

        sample, explained = pca_sample(scaled, features, names)
        sample.to_csv(RESULTS_DIR / "segment_pca_sample.csv", index=False)
        plot_k_selection(scores, k)
        plot_clusters(sample, explained)

        write_segments(con, features["user_key"], names)
        check = con.execute("SELECT COUNT(*), COUNT(segment) FROM dim_user").fetchone()
        print(f"dim_user: {check[0]:,} users, {check[1]:,} with a segment, {check[0] - check[1]:,} NULL")
    finally:
        con.close()


if __name__ == "__main__":
    main()
