"""
Tests for the customer segmentation (mining/segmentation.py).

Everything runs on small made-up data, so no warehouse is needed (the warehouse
is never written to). The made-up users form three obvious groups:

    group A  frequent, big baskets, high reorder ratio, short gap before the last order
    group B  rare, small baskets, low reorder ratio, long gap
    group C  medium on everything

The feature test uses a tiny in-memory DuckDB with the same two tables the real
code reads (fact_order and dim_user), with answers worked out by hand.
"""
import duckdb
import numpy as np
import pandas as pd
import pytest

from mining.segmentation import (
    FEATURES,
    build_features,
    choose_k,
    evaluate_k,
    fit_kmeans,
    name_segments,
    pca_sample,
    profile_segments,
    scale_features,
    write_segments,
)

GROUPS = {
    # recency_days, total_orders, avg_basket_size, reorder_ratio
    "A": (5, 60, 15.0, 0.80),
    "B": (28, 5, 3.0, 0.10),
    "C": (14, 20, 8.0, 0.45),
}


def make_users(per_group: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for g, (rec, orders, basket, ratio) in GROUPS.items():
        for _ in range(per_group):
            rows.append({
                "group": g,
                "recency_days": float(np.clip(rec + rng.normal(0, 1), 0, 30)),
                "total_orders": float(max(4, orders + rng.normal(0, orders * 0.05))),
                "avg_basket_size": float(max(1, basket + rng.normal(0, basket * 0.05))),
                "reorder_ratio": float(np.clip(ratio + rng.normal(0, 0.02), 0, 1)),
                "avg_days_between_orders": float(30 / (orders / 4)),
            })
    df = pd.DataFrame(rows)
    df.insert(0, "user_key", np.arange(1, len(df) + 1))
    return df


# ---------------------------------------------------------------------------
# Features, from a tiny database
#
#   user 1: orders 1,2,3 with days_since_prior NULL, 7, 12  -> recency 12 (order 3)
#   user 2: orders 1,2 with NULL and 30; order 2 is a test order (basket_size 0)
#           -> recency 30: a test order still gives a valid recency
# ---------------------------------------------------------------------------
@pytest.fixture
def tiny_db():
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE fact_order (order_id INTEGER, user_key INTEGER, order_number INTEGER,
                                 days_since_prior DOUBLE, basket_size INTEGER);
        INSERT INTO fact_order VALUES
            (11, 1, 1, NULL, 4), (13, 1, 3, 12, 6), (12, 1, 2, 7, 5),
            (21, 2, 1, NULL, 3), (22, 2, 2, 30, 0);
        CREATE TABLE dim_user (user_key INTEGER PRIMARY KEY, total_orders INTEGER, avg_basket_size DOUBLE,
                               avg_days_between_orders DOUBLE, reorder_ratio DOUBLE, segment VARCHAR);
        INSERT INTO dim_user VALUES (1, 3, 5.0, 9.5, 0.4, NULL), (2, 2, 3.0, 30.0, 0.0, NULL);
    """)
    yield con
    con.close()


def test_recency_is_the_gap_before_the_last_order(tiny_db):
    f = build_features(tiny_db).set_index("user_key")
    assert f.loc[1, "recency_days"] == 12     # order_number 3 is the last, whatever the row order
    assert f.loc[2, "recency_days"] == 30     # the last order is a test order: recency still works
    assert f.loc[1, "total_orders"] == 3
    assert f.loc[1, "avg_basket_size"] == pytest.approx(5.0)   # taken from dim_user, not from the test order
    assert len(f) == 2


def test_write_segments_updates_every_user_in_one_statement(tiny_db):
    write_segments(tiny_db, [2, 1], ["Small", "Big"])
    rows = dict(tiny_db.execute("SELECT user_key, segment FROM dim_user").fetchall())
    assert rows == {1: "Big", 2: "Small"}


# ---------------------------------------------------------------------------
# Scaling, choosing k and clustering
# ---------------------------------------------------------------------------
def test_scaling_gives_mean_zero_and_std_one():
    z = scale_features(make_users())
    assert z.shape == (180, 4)
    assert np.allclose(z.mean(axis=0), 0, atol=1e-9)
    assert np.allclose(z.std(axis=0), 1, atol=1e-9)


def test_log_transform_reduces_skew():
    df = make_users()
    df.loc[0, "total_orders"] = 100_000.0   # one extreme user
    z_log = scale_features(df)[:, FEATURES.index("total_orders")]
    raw = (df["total_orders"] - df["total_orders"].mean()) / df["total_orders"].std(ddof=0)
    assert abs(z_log[0]) < abs(raw.iloc[0])   # the outlier is pulled in


def test_kmeans_recovers_the_three_groups():
    df = make_users()
    labels = fit_kmeans(scale_features(df), 3).labels_
    # each true group must sit entirely in one cluster, and the three clusters must differ
    table = pd.crosstab(df["group"], labels)
    assert (table.gt(0).sum(axis=1) == 1).all()
    assert table.gt(0).sum(axis=0).eq(1).all()
    assert len(set(labels)) == 3


def test_choose_k_finds_three_clusters():
    scores = evaluate_k(scale_features(make_users()), ks=range(2, 7))
    assert choose_k(scores, candidates=range(3, 7)) == 3
    assert scores.loc[scores["k"] == 3, "silhouette"].iloc[0] > 0.5   # well separated groups


def test_choose_k_takes_the_smallest_k_among_ties():
    scores = pd.DataFrame({"k": [4, 5, 6], "inertia": [3.0, 2.0, 1.0], "silhouette": [0.2741, 0.2744, 0.2]})
    assert choose_k(scores, candidates=range(4, 7)) == 4   # 0.274 and 0.274 tie at 3 decimals


def test_clustering_is_repeatable():
    z = scale_features(make_users())
    assert (fit_kmeans(z, 3).labels_ == fit_kmeans(z, 3).labels_).all()


# ---------------------------------------------------------------------------
# Profiles and names
# ---------------------------------------------------------------------------
def test_profiles_sizes_and_names_match_the_numbers():
    df = make_users()
    labels = fit_kmeans(scale_features(df), 3).labels_
    prof = name_segments(profile_segments(df, labels), df)

    assert prof["users"].sum() == 180
    assert prof["share_of_users"].sum() == pytest.approx(1.0)
    assert prof["segment"].is_unique

    # group A (60 orders, 5-day gap) must be the loyal segment, group B (3 items) the small basket
    a_cluster = pd.Series(labels)[df["group"] == "A"].iloc[0]
    b_cluster = pd.Series(labels)[df["group"] == "B"].iloc[0]
    assert prof.loc[a_cluster, "segment"] == "Loyal frequent shopper"
    assert prof.loc[b_cluster, "segment"] == "Occasional small basket"
    assert prof.loc[a_cluster, "avg_total_orders"] == pytest.approx(60, abs=3)
    assert "orders" in prof.loc[a_cluster, "description"]


def test_pca_sample_columns_and_size():
    df = make_users()
    z = scale_features(df)
    names = np.array(["x"] * len(df))
    sample, explained = pca_sample(z, df, names, n=50)
    assert list(sample.columns) == ["user_key", "pc1", "pc2", "segment"]
    assert len(sample) == 50 and sample["user_key"].is_unique
    assert 0 < explained.sum() <= 1


def test_real_warehouse_features(warehouse):
    """On the real warehouse: one row per user, no missing values, recency within 0 to 30."""
    f = build_features(warehouse)
    assert len(f) == 206_209
    assert not f[FEATURES].isna().any().any()
    assert f["recency_days"].between(0, 30).all()
