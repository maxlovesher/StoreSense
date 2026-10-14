"""
Association rule mining (Apriori and FP-Growth).

Owner: Member 3 (Association Rules)
Spec:  docs/PROJECT_BRIEF.md, section 6.3

Mines rules at aisle level and product level (top products, sampled orders),
keeps rules with lift > 1, and offers a 'frequently bought together' lookup.
An order is a basket and each aisle or product is an item.

Run from the project root (writes reports/results/rules_aisle.csv and
rules_product.csv):
    python mining/association_rules.py
"""
import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules, fpgrowth
from scipy import sparse

from common.db import PROJECT_ROOT, get_connection

SEED = 42
RESULTS_DIR = PROJECT_ROOT / "reports" / "results"
RULES_PRODUCT_PATH = RESULTS_DIR / "rules_product.csv"

RULE_COLUMNS = [
    "antecedents", "consequents", "antecedent_support", "consequent_support",
    "support", "confidence", "lift", "algorithm", "interpretation",
]
MAX_RULES = 5000   # keep each result file small (shared contract: under about 5 MB)

# Settings for the two levels. min_support is chosen per level: aisles are
# common items (a few percent of baskets), single products are rare (a fraction
# of a percent). max_len caps the itemset size (3 items = rules like A + B -> C).
LEVELS = {
    "aisle": {"n_orders": 500_000, "top_products": None, "min_support": 0.01, "max_len": 3},
    "product": {"n_orders": 500_000, "top_products": 1000, "min_support": 0.0015, "max_len": 3},
}


# ---------------------------------------------------------------------------
# 1. Baskets: warehouse -> one-hot table
# ---------------------------------------------------------------------------
def load_pairs(level: str, n_orders: int | None, top_products: int | None, con=None) -> pd.DataFrame:
    """
    Return one row per (order_id, item): the items in each basket.

    Only orders with 2 or more items are baskets (a single item cannot make a
    rule). A random sample of n_orders of them is drawn with a fixed seed.
    At product level only the top_products most popular products are kept, and
    orders left with fewer than 2 of them are dropped. At aisle level the
    'missing' and 'other' aisles are dropped (they are not real shelves).
    """
    own_con = con is None
    con = con or get_connection(read_only=True)
    try:
        order_ids = con.execute(
            "SELECT order_id FROM fact_order WHERE basket_size >= 2 ORDER BY order_id"
        ).df()["order_id"].to_numpy()
        if n_orders is not None and n_orders < len(order_ids):
            order_ids = np.sort(np.random.default_rng(SEED).choice(order_ids, n_orders, replace=False))
        con.register("sampled_orders", pd.DataFrame({"order_id": order_ids}))

        if level == "aisle":
            sql = """
                SELECT DISTINCT l.order_id, p.aisle AS item
                FROM fact_order_line l
                JOIN sampled_orders s ON l.order_id = s.order_id
                JOIN dim_product p ON l.product_key = p.product_key
                WHERE p.aisle NOT IN ('missing', 'other')
            """
        elif level == "product":
            sql = f"""
                WITH top AS (
                    SELECT product_key FROM fact_order_line
                    GROUP BY product_key ORDER BY COUNT(*) DESC, product_key LIMIT {int(top_products)}
                )
                SELECT l.order_id, p.product_name AS item
                FROM fact_order_line l
                JOIN sampled_orders s ON l.order_id = s.order_id
                JOIN top t ON l.product_key = t.product_key
                JOIN dim_product p ON l.product_key = p.product_key
            """
        else:
            raise ValueError(f"level must be 'aisle' or 'product', not {level!r}")
        pairs = con.execute(sql).df()
    finally:
        if own_con:
            con.close()
    # keep only orders that still have 2 or more distinct items at this level
    sizes = pairs.groupby("order_id")["item"].transform("size")
    # sorted, because the database returns rows in no fixed order
    return pairs[sizes >= 2].sort_values(["order_id", "item"]).reset_index(drop=True)


def to_onehot(pairs: pd.DataFrame) -> pd.DataFrame:
    """
    Turn (order_id, item) pairs into a sparse True/False table: one row per
    order, one column per item. Sparse storage keeps 500,000 x 1,000 small
    (a basket holds about 10 items out of 1,000 columns).
    """
    order_codes, orders = pd.factorize(pairs["order_id"])
    item_codes, items = pd.factorize(pairs["item"], sort=True)   # sort=True: columns in alphabetical order
    matrix = sparse.csr_matrix(
        (np.ones(len(pairs), dtype=bool), (order_codes, item_codes)),
        shape=(len(orders), len(items)),
    )
    return pd.DataFrame.sparse.from_spmatrix(matrix, columns=items)


# ---------------------------------------------------------------------------
# 2. Mining
# ---------------------------------------------------------------------------
ALGORITHMS = {"apriori": apriori, "fpgrowth": fpgrowth}


def mine_itemsets(onehot: pd.DataFrame, min_support: float, algorithm: str, max_len: int | None = None) -> pd.DataFrame:
    """
    Frequent itemsets (columns: support, itemsets) with Apriori or FP-Growth.

    Apriori runs with low_memory=True: the default builds one (baskets x candidates)
    table for each itemset size, which asked for 81.6 GiB on the product baskets.
    """
    if algorithm == "apriori":
        return apriori(onehot, min_support=min_support, use_colnames=True, max_len=max_len, low_memory=True)
    return fpgrowth(onehot, min_support=min_support, use_colnames=True, max_len=max_len)


def interpret(antecedents: str, consequents: str, lift: float, confidence: float) -> str:
    """One plain-English sentence for a rule."""
    return (
        f"Customers who buy {antecedents} are {lift:.1f} times more likely than average "
        f"to also buy {consequents} ({confidence:.0%} of baskets with {antecedents} also contain it)."
    )


def make_rules(itemsets: pd.DataFrame, n_transactions: int, algorithm: str, max_rules: int | None = MAX_RULES) -> pd.DataFrame:
    """
    Turn frequent itemsets into rules, keep lift > 1 and return the shared-contract
    columns, strongest first (highest lift, then highest support).
    """
    if len(itemsets) == 0:
        return pd.DataFrame(columns=RULE_COLUMNS)
    rules = association_rules(
        itemsets, num_itemsets=n_transactions, metric="lift", min_threshold=1.0,
        return_metrics=["antecedent support", "consequent support", "support", "confidence", "lift"],
    )
    # metric='lift' with min_threshold=1.0 keeps lift >= 1; the brief asks for lift > 1
    rules = rules[rules["lift"] > 1].copy()
    rules["antecedents"] = rules["antecedents"].map(lambda s: " + ".join(sorted(s)))
    rules["consequents"] = rules["consequents"].map(lambda s: " + ".join(sorted(s)))
    rules = rules.rename(columns={"antecedent support": "antecedent_support", "consequent support": "consequent_support"})
    rules["algorithm"] = algorithm
    rules["interpretation"] = [
        interpret(a, c, lift, conf)
        for a, c, lift, conf in zip(rules["antecedents"], rules["consequents"], rules["lift"], rules["confidence"])
    ]
    rules = rules.sort_values(["lift", "support", "antecedents", "consequents"], ascending=[False, False, True, True])
    if max_rules is not None:
        rules = rules.head(max_rules)
    return rules[RULE_COLUMNS].reset_index(drop=True)


def mine_level(level: str, con=None) -> pd.DataFrame:
    """Mine one level with both algorithms, check they agree, return the rules."""
    cfg = LEVELS[level]
    pairs = load_pairs(level, cfg["n_orders"], cfg["top_products"], con=con)
    onehot = to_onehot(pairs)
    n = len(onehot)
    print(f"[{level}] {n:,} baskets x {onehot.shape[1]:,} items, min_support={cfg['min_support']}, max_len={cfg['max_len']}")

    found = {}
    for algo in ALGORITHMS:
        found[algo] = mine_itemsets(onehot, cfg["min_support"], algo, cfg["max_len"])
        print(f"[{level}] {algo}: {len(found[algo]):,} frequent itemsets")
    same = {frozenset(s) for s in found["apriori"]["itemsets"]} == {frozenset(s) for s in found["fpgrowth"]["itemsets"]}
    if not same:
        raise RuntimeError(f"Apriori and FP-Growth found different itemsets at {level} level")

    # both algorithms give the same itemsets, so the rules are the same: write them once
    return make_rules(found["fpgrowth"], n, "fpgrowth")


# ---------------------------------------------------------------------------
# 3. Lookup used by the dashboard
# ---------------------------------------------------------------------------
def frequently_bought_together(product_name: str, top_n: int = 10, rules_path=RULES_PRODUCT_PATH) -> pd.DataFrame:
    """
    Products most often bought together with product_name.

    Reads the saved product rules (no database needed). Returns columns
    product, confidence, lift, support, best matches first (highest confidence,
    then lift). The name is matched ignoring upper/lower case; an unknown name
    gives an empty table.
    """
    rules = pd.read_csv(rules_path)
    wanted = product_name.strip().lower()
    # single product on both sides: "bought X, also buys Y"
    hit = rules[
        (rules["antecedents"].str.lower() == wanted) & ~rules["consequents"].str.contains(" + ", regex=False)
    ]
    hit = hit.rename(columns={"consequents": "product"})
    hit = hit.sort_values(["confidence", "lift"], ascending=False)
    return hit[["product", "confidence", "lift", "support"]].head(top_n).reset_index(drop=True)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    con = get_connection(read_only=True)
    try:
        for level in LEVELS:
            rules = mine_level(level, con=con)
            path = RESULTS_DIR / f"rules_{level}.csv"
            rules.to_csv(path, index=False)
            print(f"[{level}] {len(rules):,} rules with lift > 1 written to {path}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
