"""
Tests for the reorder model (mining/reorder_model.py).

A tiny made-up database (two users) with answers worked out by hand. Products
are A=10, B=11, C=12, D=13, E=14.

  user 1: prior order 1 (day gap NULL): A, B        order 2 (gap 7): A, C
          prior order 3 (gap 5): A                  TRAIN order 4: A, D
  user 2: prior order 5 (gap NULL): A, E            order 6 (gap 10): A
          TRAIN order 7: E

Candidate pairs are products seen in PRIOR orders only, so D (bought only in
the train order) is not a candidate. Labels (is it in the train order?):
user 1: A=1, B=0, C=0     user 2: A=0, E=1

Hand-worked features for user 1 (cumulative days: order 1 = 0, 2 = 7, 3 = 12):
  u_orders = 3, u_avg_basket = (2+2+1)/3, u_reorder_ratio = 2/5 (A,B,A,C,A: two reorders),
  u_avg_days_between = 12/(3-1) = 6, u_distinct_products = 3
  A: times bought 3, share 3/3, orders since last 3-3 = 0, days since last 12-12 = 0, avg cart position (1+2+1)/3
  B: times 1, share 1/3, orders since last 3-1 = 2, days since last 12-0 = 12, cart position 2
  C: times 1, share 1/3, orders since last 3-2 = 1, days since last 12-7 = 5,  cart position 1
Product features (all prior lines): A has 5 lines, 3 of them reorders -> rate 0.6, bought by 2 users.
"""
import duckdb
import numpy as np
import pandas as pd
import pytest

from etl.extract import missing_raw_files
from mining.reorder_model import (
    FEATURES,
    best_threshold,
    build_pairs,
    connect,
    evaluate,
    importance,
    make_models,
    sample_train_users,
    split_users,
)

A, B, C, D, E = 10, 11, 12, 13, 14


def make_db(train_lines_user1=((A, 1, 1), (D, 2, 0)), train_lines_user2=((E, 1, 1),)) -> duckdb.DuckDBPyConnection:
    """The tiny database. The train orders' contents can be changed to test for leakage."""
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE fact_order (order_id INTEGER, user_key INTEGER, order_number INTEGER,
                                 days_since_prior DOUBLE, basket_size INTEGER);
        INSERT INTO fact_order VALUES
            (1, 1, 1, NULL, 2), (2, 1, 2, 7, 2), (3, 1, 3, 5, 1), (4, 1, 4, 3, 2),
            (5, 2, 1, NULL, 2), (6, 2, 2, 10, 1), (7, 2, 3, 4, 1);
        CREATE TABLE order_eval (order_id INTEGER, eval_set VARCHAR);
        INSERT INTO order_eval VALUES
            (1, 'prior'), (2, 'prior'), (3, 'prior'), (4, 'train'),
            (5, 'prior'), (6, 'prior'), (7, 'train');
        CREATE TABLE fact_order_line (order_id INTEGER, product_key INTEGER, user_key INTEGER,
                                      add_to_cart_order INTEGER, reordered INTEGER);
    """)
    lines = [
        (1, A, 1, 1, 0), (1, B, 1, 2, 0),
        (2, C, 1, 1, 0), (2, A, 1, 2, 1),
        (3, A, 1, 1, 1),
        (5, A, 2, 1, 0), (5, E, 2, 2, 0),
        (6, A, 2, 1, 1),
    ]
    lines += [(4, p, 1, pos, r) for p, pos, r in train_lines_user1]
    lines += [(7, p, 2, pos, r) for p, pos, r in train_lines_user2]
    con.executemany("INSERT INTO fact_order_line VALUES (?, ?, ?, ?, ?)", lines)
    return con


@pytest.fixture
def pairs():
    con = make_db()
    try:
        return build_pairs(con, [1, 2]).set_index(["user_key", "product_key"])
    finally:
        con.close()


def test_candidates_are_the_prior_pairs_only(pairs):
    assert set(pairs.index) == {(1, A), (1, B), (1, C), (2, A), (2, E)}   # D (train only) is not a candidate


def test_labels_come_from_the_train_order(pairs):
    assert pairs["label"].to_dict() == {(1, A): 1, (1, B): 0, (1, C): 0, (2, A): 0, (2, E): 1}


def test_times_bought_and_user_features(pairs):
    assert pairs.loc[(1, A), "up_times_bought"] == 3
    assert pairs.loc[(1, B), "up_times_bought"] == 1
    assert pairs.loc[(2, A), "up_times_bought"] == 2
    row = pairs.loc[(1, B)]
    assert row["u_orders"] == 3
    assert row["u_avg_basket"] == pytest.approx(5 / 3)
    assert row["u_reorder_ratio"] == pytest.approx(0.4)
    assert row["u_avg_days_between"] == pytest.approx(6.0)
    assert row["u_distinct_products"] == 3


def test_recency_features(pairs):
    assert pairs.loc[(1, A), ["up_orders_since_last", "up_days_since_last"]].tolist() == [0, 0]
    assert pairs.loc[(1, B), ["up_orders_since_last", "up_days_since_last"]].tolist() == [2, 12]
    assert pairs.loc[(1, C), ["up_orders_since_last", "up_days_since_last"]].tolist() == [1, 5]
    assert pairs.loc[(2, E), ["up_orders_since_last", "up_days_since_last"]].tolist() == [1, 10]
    assert pairs.loc[(1, A), "up_share"] == pytest.approx(1.0)
    assert pairs.loc[(1, B), "up_share"] == pytest.approx(1 / 3)
    assert pairs.loc[(1, A), "up_avg_cart_pos"] == pytest.approx(4 / 3)


def test_product_features_use_prior_lines_of_all_users(pairs):
    a = pairs.loc[(1, A)]
    assert a["p_orders"] == 5
    assert a["p_reorder_rate"] == pytest.approx(0.6)   # the train order's reordered flag is NOT counted
    assert a["p_users"] == 2
    assert pairs.loc[(1, B), "p_orders"] == 1


def test_no_train_order_data_leaks_into_the_features(pairs):
    """Change everything about the train orders: the features must not move at all."""
    con = make_db(train_lines_user1=((B, 1, 1), (C, 2, 1), (D, 3, 1)),   # a completely different train basket
                  train_lines_user2=((A, 1, 1), (E, 2, 1)))
    try:
        other = build_pairs(con, [1, 2]).set_index(["user_key", "product_key"])
    finally:
        con.close()
    assert set(other.index) == set(pairs.index)                  # same candidates
    pd.testing.assert_frame_equal(other[FEATURES], pairs[FEATURES])   # same features
    assert other["label"].to_dict() != pairs["label"].to_dict()  # only the labels change
    assert other.loc[(1, B), "label"] == 1 and other.loc[(1, A), "label"] == 0


def test_a_user_with_one_prior_order_gets_zero_average_gap():
    con = make_db()
    con.execute("DELETE FROM order_eval WHERE order_id IN (2, 3)")   # user 1 now has one prior order
    try:
        df = build_pairs(con, [1]).set_index("product_key")
    finally:
        con.close()
    assert (df["u_avg_days_between"] == 0).all()


def test_split_is_by_user_with_no_overlap():
    users = np.arange(1, 1001)
    sets = split_users(np.repeat(users, 3))   # several rows per user
    assert len(sets["train"]) == 600 and len(sets["validation"]) == 200 and len(sets["test"]) == 200
    assert not set(sets["train"]) & set(sets["test"])
    assert not set(sets["train"]) & set(sets["validation"])
    assert not set(sets["validation"]) & set(sets["test"])
    assert set(sets["train"]) | set(sets["validation"]) | set(sets["test"]) == set(users)
    again = split_users(np.repeat(users, 3))
    assert all((sets[k] == again[k]).all() for k in sets)   # fixed seed


def test_evaluate_matches_hand_count():
    # predictions at 0.5: [1,0,1,0,1] against [1,1,0,0,1] -> TP 2, FP 1, FN 1
    y = np.array([1, 1, 0, 0, 1])
    p = np.array([0.9, 0.4, 0.6, 0.1, 0.8])
    r = evaluate(y, p, 0.5)
    assert r["precision"] == pytest.approx(2 / 3)
    assert r["recall"] == pytest.approx(2 / 3)
    assert r["f1"] == pytest.approx(2 / 3)
    assert r["roc_auc"] == pytest.approx(5 / 6)   # 5 of the 6 positive-negative pairs are ranked correctly
    assert r["threshold"] == 0.5


def test_best_threshold_maximises_f1():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.4, 0.35, 0.8])
    assert best_threshold(y, p) == pytest.approx(0.35)   # F1 0.80 there; 0.67 at 0.8 or 0.1; 0.5 at 0.4


def test_models_fit_and_importances_add_up_to_one():
    rng = np.random.default_rng(0)
    x = pd.DataFrame(rng.normal(size=(3000, len(FEATURES))), columns=FEATURES)
    y = (x["up_share"] + 0.3 * rng.normal(size=3000) > 0).astype(int)
    for name, model in make_models().items():
        model.fit(x, y)
        proba = model.predict_proba(x)[:, 1]
        assert proba.shape == (3000,) and ((proba >= 0) & (proba <= 1)).all()
        imp = importance(name, model)
        assert imp["importance"].sum() == pytest.approx(1.0)
        assert imp.iloc[0]["feature"] == "up_share"   # the feature that makes the label is ranked first


def test_real_data_features(warehouse):
    """On the real data: about 10% positives, no missing values, and every pair was bought before."""
    if missing_raw_files():
        pytest.skip("raw CSVs not in data/raw/")
    con = connect()
    try:
        users = sample_train_users(con, 300)
        df = build_pairs(con, users)
    finally:
        con.close()
    assert len(users) == 300
    assert 0.05 < df["label"].mean() < 0.15
    assert not df[FEATURES].isna().any().any()
    assert (df["up_times_bought"] >= 1).all()
    assert (df["up_orders_since_last"] >= 0).all()
    assert df["u_orders"].min() >= 3   # every user has at least 3 prior orders (4 orders in total)
