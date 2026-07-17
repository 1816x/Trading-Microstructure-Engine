"""Generate a synthetic trade journal for development and demos.

All output is synthetic — no real trades, accounts or amounts are involved. Entry
times fall inside the range of the bundled sample tick tape, so each journal
entry joins to a real microstructure bucket. The trades deliberately encode a few
behavioral narratives — revenge trading after losses, FOMO chasing, oversizing
after a big win, hesitation in choppy tape — so the behavioral agent has
something concrete to find.

Usage:
    python data/generate_journal.py [--seed S] [--out PATH]
"""

import argparse
import csv
import random

SYMBOL = "MNQ"
POINT_VALUE = 2.0  # MNQ: $2 per index point (synthetic)
START_TIMESTAMP_NS = 1_760_000_000_000_000_000  # matches generate_ticks.py
SPACING_NS = 30_000_000_000  # ~30s between entries, well inside the tape span

FIELDNAMES = [
    "symbol",
    "side",
    "entered_at_ns",
    "exited_at_ns",
    "entry_price",
    "exit_price",
    "size",
    "pnl",
    "notes",
    "emotion",
]

# (side, entry_price, exit_price, size, notes, emotion). pnl is derived from the
# prices, size, side and point value so the numbers are internally consistent.
_TRADES = [
    ("long", 21_400.00, 21_405.00, 1, "Waited for the pullback and followed my plan.", "calm"),
    ("long", 21_402.50, 21_407.50, 1, "Clean continuation setup, sized normally.", "calm"),
    ("long", 21_406.00, 21_402.00, 1, "Stopped out at my level. Part of the game.", "disciplined"),
    ("long", 21_403.00, 21_399.50, 3, "Jumped right back in bigger to win it back.", "frustrated"),
    ("long", 21_400.50, 21_396.00, 5, "Doubled down again, angry about the last two.", "angry"),
    ("short", 21_398.00, 21_401.00, 3, "Chased the breakdown well after it started.", "fomo"),
    ("long", 21_401.00, 21_402.00, 1, "Hesitated, finally entered late in choppy tape.", "anxious"),
    ("long", 21_404.00, 21_410.00, 2, "Reset, waited, took the A+ setup.", "calm"),
    ("short", 21_409.00, 21_402.00, 6, "Felt unstoppable after that win, went big.", "euphoric"),
    ("short", 21_403.50, 21_407.50, 6, "Kept the size huge and gave most of it back.", "careless"),
    ("long", 21_408.00, 21_405.50, 3, "Everyone was talking about it so I jumped in.", "fomo"),
    ("long", 21_405.00, 21_409.50, 1, "Back to my process, small and patient.", "calm"),
]


def generate(seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    slot_start = START_TIMESTAMP_NS + SPACING_NS
    for side, entry_price, exit_price, size, notes, emotion in _TRADES:
        entered_at_ns = slot_start + rng.randint(0, 5_000_000_000)  # jitter up to ~5s
        exited_at_ns = entered_at_ns + rng.randint(2_000_000_000, 20_000_000_000)
        direction = 1 if side == "long" else -1
        pnl = (exit_price - entry_price) * direction * size * POINT_VALUE
        rows.append(
            {
                "symbol": SYMBOL,
                "side": side,
                "entered_at_ns": entered_at_ns,
                "exited_at_ns": exited_at_ns,
                "entry_price": f"{entry_price:.2f}",
                "exit_price": f"{exit_price:.2f}",
                "size": size,
                "pnl": f"{pnl:.2f}",
                "notes": notes,
                "emotion": emotion,
            }
        )
        slot_start += SPACING_NS
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="data/sample_journal.csv")
    args = parser.parse_args()

    rows = generate(args.seed)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} journal entries to {args.out}")


if __name__ == "__main__":
    main()
