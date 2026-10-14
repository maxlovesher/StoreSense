"""
Apriori vs FP-Growth benchmark.

Owner: Member 3 (Association Rules)
Spec:  docs/PROJECT_BRIEF.md, section 6.3

Compares runtime and memory of both algorithms across several min_support
values, at both levels, and saves reports/results/benchmark.csv plus two
charts in reports/figures/.

Only the mining step is measured, not loading the data. Runtime and memory are
measured in separate runs, because tracemalloc slows Python down and would
distort the timings. Memory is the peak extra memory used while mining
(tracemalloc sees numpy and pandas arrays too).

Run from the project root:
    python mining/benchmark.py
"""
import time
import tracemalloc

import matplotlib

matplotlib.use("Agg")   # draw to files, no window
import matplotlib.pyplot as plt
import pandas as pd

from common.db import FIGURES_DIR, get_connection
from mining.association_rules import ALGORITHMS, RESULTS_DIR, load_pairs, mine_itemsets, to_onehot

BENCH_ORDERS = 100_000   # a smaller sample than the real run, so that low min_support still finishes
MAX_LEN = 3              # same cap as the real run
PRODUCT_TOP = 1000

# From a high min_support (few itemsets) down to a low one (many itemsets).
# Aisles are common items, products are rare, so the two levels use different ranges.
SUPPORTS = {
    "aisle": [0.05, 0.03, 0.02, 0.01, 0.005],
    "product": [0.01, 0.005, 0.003, 0.002, 0.0015],
}
COLUMNS = ["level", "algorithm", "min_support", "n_transactions", "n_itemsets", "runtime_seconds", "peak_memory_mb"]


def measure(onehot: pd.DataFrame, algorithm: str, min_support: float) -> dict:
    """Run one algorithm twice: once for the runtime, once for the peak memory."""
    start = time.perf_counter()
    itemsets = mine_itemsets(onehot, min_support, algorithm, MAX_LEN)
    runtime = time.perf_counter() - start

    tracemalloc.start()
    mine_itemsets(onehot, min_support, algorithm, MAX_LEN)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    return {"itemsets": itemsets, "runtime_seconds": runtime, "peak_memory_mb": peak / 1024 / 1024}


def run_benchmark() -> pd.DataFrame:
    rows = []
    con = get_connection(read_only=True)
    try:
        for level, supports in SUPPORTS.items():
            top = PRODUCT_TOP if level == "product" else None
            onehot = to_onehot(load_pairs(level, BENCH_ORDERS, top, con=con))
            print(f"[{level}] {len(onehot):,} baskets x {onehot.shape[1]:,} items")
            for min_support in supports:
                found = {}
                for algo in ALGORITHMS:
                    result = measure(onehot, algo, min_support)
                    found[algo] = {frozenset(s) for s in result["itemsets"]["itemsets"]}
                    rows.append({
                        "level": level, "algorithm": algo, "min_support": min_support,
                        "n_transactions": len(onehot), "n_itemsets": len(result["itemsets"]),
                        "runtime_seconds": round(result["runtime_seconds"], 3),
                        "peak_memory_mb": round(result["peak_memory_mb"], 1),
                    })
                    print(f"[{level}] min_support={min_support:<7} {algo:<9} {len(found[algo]):>6,} itemsets "
                          f"{result['runtime_seconds']:>7.2f} s {result['peak_memory_mb']:>8.1f} MB")
                if found["apriori"] != found["fpgrowth"]:
                    raise RuntimeError(f"Apriori and FP-Growth disagree at {level}, min_support={min_support}")
    finally:
        con.close()
    return pd.DataFrame(rows, columns=COLUMNS)


def plot(bench: pd.DataFrame, column: str, ylabel: str, filename: str) -> None:
    """One chart, two panels (aisle and product): metric against min_support, one line per algorithm."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, level in zip(axes, SUPPORTS):
        supports = SUPPORTS[level]   # high to low: reading left to right, the work grows
        for algo, style in (("apriori", "o-"), ("fpgrowth", "s--")):
            d = bench[(bench["level"] == level) & (bench["algorithm"] == algo)].set_index("min_support").loc[supports]
            ax.plot(range(len(supports)), d[column], style, label=algo)
        ax.set_xticks(range(len(supports)), [str(s) for s in supports])
        ax.set_yscale("log")
        ax.set_xlabel("min_support (lower = more itemsets)")
        ax.set_ylabel(ylabel)
        ax.set_title(f"{level} level")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / filename, dpi=150)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    bench = run_benchmark()
    bench.to_csv(RESULTS_DIR / "benchmark.csv", index=False)
    plot(bench, "runtime_seconds", "runtime of the mining step (seconds)", "benchmark_runtime.png")
    plot(bench, "peak_memory_mb", "peak extra memory (MB)", "benchmark_memory.png")
    print(f"written to {RESULTS_DIR / 'benchmark.csv'} and {FIGURES_DIR}")


if __name__ == "__main__":
    main()
