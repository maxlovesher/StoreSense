"""
Tests for the association rules (mining/association_rules.py).

A tiny set of 5 baskets, small enough to work out by hand:

    basket 1: milk, bread
    basket 2: milk, bread, eggs
    basket 3: milk, eggs
    basket 4: bread, butter
    basket 5: milk, bread, butter

Support = share of the 5 baskets that contain the items:
    milk 4/5 = 0.8     bread 4/5 = 0.8     eggs 2/5 = 0.4     butter 2/5 = 0.4
    milk+bread 3/5 = 0.6    milk+eggs 2/5 = 0.4    bread+butter 2/5 = 0.4
    bread+eggs 1/5 = 0.2    milk+butter 1/5 = 0.2   (below min_support 0.4)

Confidence(A -> B) = support(A and B) / support(A); lift = confidence / support(B):
    eggs -> milk:    0.4 / 0.4 = 1.0,   lift 1.0 / 0.8 = 1.25
    milk -> eggs:    0.4 / 0.8 = 0.5,   lift 0.5 / 0.4 = 1.25
    butter -> bread: 0.4 / 0.4 = 1.0,   lift 1.0 / 0.8 = 1.25
    bread -> butter: 0.4 / 0.8 = 0.5,   lift 0.5 / 0.4 = 1.25
    milk -> bread:   0.6 / 0.8 = 0.75,  lift 0.75 / 0.8 = 0.9375   (below 1: dropped)

The last test runs on the real warehouse; it is skipped until
`python etl/load.py` has been run.
"""
import pandas as pd
import pytest

from mining.association_rules import (
    frequently_bought_together,
    load_pairs,
    make_rules,
    mine_itemsets,
    to_onehot,
)

BASKETS = [
    ["milk", "bread"],
    ["milk", "bread", "eggs"],
    ["milk", "eggs"],
    ["bread", "butter"],
    ["milk", "bread", "butter"],
]
MIN_SUPPORT = 0.4


@pytest.fixture
def onehot():
    pairs = pd.DataFrame(
        [(order, item) for order, basket in enumerate(BASKETS, start=1) for item in basket],
        columns=["order_id", "item"],
    )
    return to_onehot(pairs)


def _as_dict(itemsets):
    return {frozenset(s): round(sup, 6) for s, sup in zip(itemsets["itemsets"], itemsets["support"])}


def test_onehot_shape(onehot):
    assert onehot.shape == (5, 4)
    assert list(onehot.columns) == ["bread", "butter", "eggs", "milk"]   # alphabetical
    assert int(onehot["milk"].sum()) == 4


@pytest.mark.parametrize("algorithm", ["apriori", "fpgrowth"])
def test_frequent_itemsets_match_hand_count(onehot, algorithm):
    found = _as_dict(mine_itemsets(onehot, MIN_SUPPORT, algorithm))
    assert found == {
        frozenset({"milk"}): 0.8, frozenset({"bread"}): 0.8,
        frozenset({"eggs"}): 0.4, frozenset({"butter"}): 0.4,
        frozenset({"milk", "bread"}): 0.6,
        frozenset({"milk", "eggs"}): 0.4,
        frozenset({"bread", "butter"}): 0.4,
    }


def test_apriori_and_fpgrowth_agree(onehot):
    for min_support in (0.2, 0.4, 0.6):
        a = _as_dict(mine_itemsets(onehot, min_support, "apriori"))
        f = _as_dict(mine_itemsets(onehot, min_support, "fpgrowth"))
        assert a == f


def test_max_len_caps_itemset_size(onehot):
    itemsets = mine_itemsets(onehot, 0.2, "fpgrowth", max_len=2)
    assert itemsets["itemsets"].map(len).max() == 2


def test_rules_support_confidence_lift(onehot):
    itemsets = mine_itemsets(onehot, MIN_SUPPORT, "fpgrowth")
    rules = make_rules(itemsets, n_transactions=len(BASKETS), algorithm="fpgrowth")

    # only the four rules with lift 1.25 survive; milk <-> bread has lift 0.9375 and is dropped
    assert set(zip(rules["antecedents"], rules["consequents"])) == {
        ("eggs", "milk"), ("milk", "eggs"), ("butter", "bread"), ("bread", "butter"),
    }
    assert (rules["lift"] > 1).all()
    assert list(rules.columns) == [
        "antecedents", "consequents", "antecedent_support", "consequent_support",
        "support", "confidence", "lift", "algorithm", "interpretation",
    ]

    by_pair = rules.set_index(["antecedents", "consequents"])
    eggs_milk = by_pair.loc[("eggs", "milk")]
    assert eggs_milk["antecedent_support"] == pytest.approx(0.4)
    assert eggs_milk["consequent_support"] == pytest.approx(0.8)
    assert eggs_milk["support"] == pytest.approx(0.4)
    assert eggs_milk["confidence"] == pytest.approx(1.0)
    assert eggs_milk["lift"] == pytest.approx(1.25)

    milk_eggs = by_pair.loc[("milk", "eggs")]
    assert milk_eggs["confidence"] == pytest.approx(0.5)
    assert milk_eggs["lift"] == pytest.approx(1.25)
    assert "milk" in milk_eggs["interpretation"] and "eggs" in milk_eggs["interpretation"]


def test_rules_join_several_items_with_plus(onehot):
    # at min_support 0.2 the itemset {milk, bread, eggs} (1/5) is frequent, and the rule
    # bread + eggs -> milk has confidence 0.2 / 0.2 = 1.0 and lift 1.0 / 0.8 = 1.25
    # (the rule milk + bread -> eggs has lift 0.2/0.6 / 0.4 = 0.83, so it is dropped)
    itemsets = mine_itemsets(onehot, 0.2, "fpgrowth")
    rules = make_rules(itemsets, n_transactions=len(BASKETS), algorithm="fpgrowth")
    row = rules.set_index(["antecedents", "consequents"]).loc[("bread + eggs", "milk")]
    assert row["confidence"] == pytest.approx(1.0)
    assert row["lift"] == pytest.approx(1.25)
    assert ("bread + milk", "eggs") not in set(zip(rules["antecedents"], rules["consequents"]))


def test_make_rules_with_no_itemsets_returns_empty_table(onehot):
    empty = mine_itemsets(onehot, 0.99, "fpgrowth")
    rules = make_rules(empty, n_transactions=len(BASKETS), algorithm="fpgrowth")
    assert rules.empty and "interpretation" in rules.columns


def test_frequently_bought_together(onehot, tmp_path):
    itemsets = mine_itemsets(onehot, MIN_SUPPORT, "fpgrowth")
    path = tmp_path / "rules_product.csv"
    make_rules(itemsets, len(BASKETS), "fpgrowth").to_csv(path, index=False)

    out = frequently_bought_together("Eggs", rules_path=path)   # name matching ignores case
    assert list(out.columns) == ["product", "confidence", "lift", "support"]
    assert list(out["product"]) == ["milk"]
    assert out.loc[0, "confidence"] == pytest.approx(1.0)

    assert frequently_bought_together("not a product", rules_path=path).empty
    assert len(frequently_bought_together("bread", top_n=1, rules_path=path)) == 1


def test_real_warehouse_baskets(warehouse):
    """On the real warehouse every basket has 2+ items and the product filter is respected."""
    pairs = load_pairs("product", n_orders=2000, top_products=50, con=warehouse)
    assert pairs.groupby("order_id")["item"].nunique().min() >= 2
    assert pairs["item"].nunique() <= 50
    again = load_pairs("product", n_orders=2000, top_products=50, con=warehouse)
    assert pairs.equals(again)   # fixed seed: the same sample every time
