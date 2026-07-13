"""Generate a synthetic MNQ tick tape for development and demos.

All output is synthetic — no real trades, accounts or amounts are involved.
The simulation is intentionally simple but keeps the one property the engine
cares about: aggressor side is correlated with short-term price direction,
so order-flow imbalance computed over this tape is non-trivial.

Usage:
    python data/generate_ticks.py [--ticks N] [--seed S] [--out PATH]
"""

import argparse
import csv
import random

TICK_SIZE = 0.25  # MNQ minimum price increment
START_PRICE = 21_400.00
START_TIMESTAMP_NS = 1_760_000_000_000_000_000  # arbitrary fixed epoch, keeps output stable
MEAN_INTERARRIVAL_NS = 100_000_000  # ~10 trades/second on average


def generate(n_ticks: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    price = START_PRICE
    timestamp_ns = START_TIMESTAMP_NS
    # Slowly drifting buy-pressure regime in [0.35, 0.65]; this is what makes
    # imbalance windows show persistent (not purely noisy) signal.
    buy_pressure = 0.5
    rows = []
    for _ in range(n_ticks):
        timestamp_ns += int(rng.expovariate(1 / MEAN_INTERARRIVAL_NS)) + 1
        buy_pressure = min(0.65, max(0.35, buy_pressure + rng.gauss(0, 0.01)))
        is_buy = rng.random() < buy_pressure
        # Aggressive orders move price in their direction ~30% of the time.
        if rng.random() < 0.3:
            price += TICK_SIZE if is_buy else -TICK_SIZE
        size = min(rng.randint(1, 5) + rng.randint(0, 5), 10)
        rows.append(
            {
                "timestamp_ns": timestamp_ns,
                "price": f"{price:.2f}",
                "size": size,
                "aggressor": "B" if is_buy else "S",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/sample_mnq_ticks.csv")
    args = parser.parse_args()

    rows = generate(args.ticks, args.seed)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_ns", "price", "size", "aggressor"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} ticks to {args.out}")


if __name__ == "__main__":
    main()
