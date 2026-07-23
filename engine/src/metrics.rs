use std::collections::BTreeMap;

use crate::tick::{Aggressor, Tick};

/// Microstructure metrics for one fixed time window.
///
/// Volumes and trade count come from the ticks that land inside the window;
/// [`vwap`](Self::vwap) is the volume-weighted average price of those ticks;
/// `realized_volatility` is the square root of the summed squared log returns
/// *realizing* inside the window (see [`compute`]).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct MetricsBucket {
    /// Window start, aligned to a multiple of the window length.
    pub bucket_start_ns: i64,
    pub buy_volume: u64,
    pub sell_volume: u64,
    pub trade_count: u64,
    /// Volume-weighted average price over the window's ticks.
    pub vwap: f64,
    /// `sqrt(Σ rᵢ²)` of the log returns realizing in this window.
    pub realized_volatility: f64,
}

impl MetricsBucket {
    /// Order-flow imbalance: `(buy − sell) / (buy + sell)`, in `[-1, 1]`.
    ///
    /// Buckets only exist when at least one tick landed in them, and tick sizes
    /// are validated positive when the tape is parsed (`tick::read_csv`), so the
    /// total volume — and thus the denominator — is never zero.
    #[must_use]
    pub fn ofi(&self) -> f64 {
        let buy = self.buy_volume as f64;
        let sell = self.sell_volume as f64;
        (buy - sell) / (buy + sell)
    }

    /// Total traded volume in the window (`buy + sell`).
    #[must_use]
    pub fn total_volume(&self) -> u64 {
        self.buy_volume + self.sell_volume
    }
}

/// Per-window running totals collected in a single time-ordered pass.
#[derive(Default)]
struct Acc {
    buy_volume: u64,
    sell_volume: u64,
    trade_count: u64,
    price_size_sum: f64,
    sum_sq_returns: f64,
}

/// Aggregate a tape into fixed windows of `window_ns`, aligned to the epoch.
///
/// Input order does not matter — the tape is sorted by timestamp first — and
/// output is sorted by bucket start, skipping windows with no ticks.
///
/// Realized volatility is **continuous across window boundaries**: the log
/// return between two consecutive ticks is attributed to the window of the
/// *later* tick. Summing each window's realized *variance*
/// (`realized_volatility²`) therefore recovers the whole tape's realized
/// variance, and a window holding a single tick still carries the volatility
/// of its move away from the previous trade.
///
/// # Panics
///
/// Panics if `window_ns` is not positive.
#[must_use]
pub fn compute(ticks: &[Tick], window_ns: i64) -> Vec<MetricsBucket> {
    assert!(window_ns > 0, "window_ns must be positive");

    // Log returns need time order; sort a view so the caller's slice is left
    // untouched and an out-of-order tape still yields sorted buckets.
    let mut ordered: Vec<&Tick> = ticks.iter().collect();
    ordered.sort_by_key(|tick| tick.timestamp_ns);

    let mut buckets: BTreeMap<i64, Acc> = BTreeMap::new();
    let mut prev_price: Option<f64> = None;
    for tick in ordered {
        let bucket_start_ns = tick.timestamp_ns - tick.timestamp_ns.rem_euclid(window_ns);
        let acc = buckets.entry(bucket_start_ns).or_default();
        match tick.aggressor {
            Aggressor::Buy => acc.buy_volume += u64::from(tick.size),
            Aggressor::Sell => acc.sell_volume += u64::from(tick.size),
        }
        acc.trade_count += 1;
        acc.price_size_sum += tick.price * f64::from(tick.size);
        if let Some(prev) = prev_price {
            // Both prices are parse-validated positive and finite (see
            // `tick::finite_positive_price`), so the ratio is positive and its
            // log is a real, finite number — never `NaN`/`inf`.
            let log_return = (tick.price / prev).ln();
            acc.sum_sq_returns += log_return * log_return;
        }
        prev_price = Some(tick.price);
    }

    buckets
        .into_iter()
        .map(|(bucket_start_ns, acc)| {
            let total_volume = acc.buy_volume + acc.sell_volume;
            MetricsBucket {
                bucket_start_ns,
                buy_volume: acc.buy_volume,
                sell_volume: acc.sell_volume,
                trade_count: acc.trade_count,
                vwap: acc.price_size_sum / total_volume as f64,
                realized_volatility: acc.sum_sq_returns.sqrt(),
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tick(timestamp_ns: i64, size: u32, aggressor: Aggressor) -> Tick {
        priced_tick(timestamp_ns, 21_400.0, size, aggressor)
    }

    fn priced_tick(timestamp_ns: i64, price: f64, size: u32, aggressor: Aggressor) -> Tick {
        Tick {
            timestamp_ns,
            price,
            size,
            aggressor,
        }
    }

    #[test]
    fn buckets_align_to_window_and_skip_empty_ones() {
        let ticks = [
            tick(0, 2, Aggressor::Buy),
            tick(500, 1, Aggressor::Sell),
            tick(1000, 3, Aggressor::Buy),
            // nothing in [2000, 3000)
            tick(3999, 4, Aggressor::Sell),
        ];
        let buckets = compute(&ticks, 1000);
        let shape: Vec<(i64, u64, u64, u64)> = buckets
            .iter()
            .map(|b| {
                (
                    b.bucket_start_ns,
                    b.buy_volume,
                    b.sell_volume,
                    b.trade_count,
                )
            })
            .collect();
        assert_eq!(shape, vec![(0, 2, 1, 2), (1000, 3, 0, 1), (3000, 0, 4, 1)]);
        // A flat-price tape has zero log returns and a vwap equal to that price.
        for bucket in &buckets {
            assert!(bucket.realized_volatility.abs() < f64::EPSILON);
            assert!((bucket.vwap - 21_400.0).abs() < f64::EPSILON);
        }
    }

    #[test]
    fn ofi_is_bounded_and_signed_correctly() {
        let bucket = |buy_volume, sell_volume| MetricsBucket {
            bucket_start_ns: 0,
            buy_volume,
            sell_volume,
            trade_count: 1,
            vwap: 0.0,
            realized_volatility: 0.0,
        };
        assert!((bucket(5, 5).ofi() - 0.0).abs() < f64::EPSILON);
        assert!((bucket(7, 0).ofi() - 1.0).abs() < f64::EPSILON);
        assert!((bucket(0, 7).ofi() + 1.0).abs() < f64::EPSILON);
        assert!((bucket(2, 1).ofi() - 1.0 / 3.0).abs() < 1e-12);
    }

    #[test]
    fn unsorted_input_yields_sorted_buckets() {
        let ticks = [
            tick(2500, 1, Aggressor::Buy),
            tick(100, 1, Aggressor::Sell),
            tick(1100, 1, Aggressor::Buy),
        ];
        let starts: Vec<i64> = compute(&ticks, 1000)
            .iter()
            .map(|b| b.bucket_start_ns)
            .collect();
        assert_eq!(starts, vec![0, 1000, 2000]);
    }

    #[test]
    fn realized_volatility_is_continuous_and_additive() {
        // Two windows of two ticks each. Prices: 100 → 101 (in w0), then
        // 100 → 100 (in w1). The 101 → 100 return crosses the boundary and is
        // attributed to w1, the window of the later tick.
        let ticks = [
            priced_tick(0, 100.0, 1, Aggressor::Buy),
            priced_tick(400, 101.0, 1, Aggressor::Buy),
            priced_tick(1000, 100.0, 2, Aggressor::Sell),
            priced_tick(1500, 100.0, 1, Aggressor::Buy),
        ];
        let buckets = compute(&ticks, 1000);
        assert_eq!(buckets.len(), 2);

        let step = (101.0_f64 / 100.0).ln(); // magnitude of both non-zero returns

        let w0 = &buckets[0];
        assert_eq!(
            (w0.bucket_start_ns, w0.buy_volume, w0.sell_volume),
            (0, 2, 0)
        );
        assert_eq!(w0.trade_count, 2);
        assert!((w0.vwap - 100.5).abs() < 1e-12); // (100·1 + 101·1) / 2
        assert!((w0.realized_volatility - step.abs()).abs() < 1e-12);

        let w1 = &buckets[1];
        assert_eq!(
            (w1.bucket_start_ns, w1.buy_volume, w1.sell_volume),
            (1000, 1, 2)
        );
        assert_eq!(w1.trade_count, 2);
        assert!((w1.vwap - 100.0).abs() < 1e-12); // (100·2 + 100·1) / 3
        assert!((w1.realized_volatility - step.abs()).abs() < 1e-12);

        // Additivity: Σ per-window variance == variance of the whole tape.
        let per_window_var: f64 = buckets.iter().map(|b| b.realized_volatility.powi(2)).sum();
        let whole_tape_var = step.powi(2) + (-step).powi(2) + 0.0;
        assert!((per_window_var - whole_tape_var).abs() < 1e-12);
    }

    #[test]
    fn single_tick_window_carries_cross_boundary_volatility() {
        let ticks = [
            priced_tick(0, 100.0, 1, Aggressor::Buy),
            priced_tick(1000, 110.0, 1, Aggressor::Buy),
        ];
        let buckets = compute(&ticks, 1000);
        // First tick has no predecessor, so its window is flat...
        assert!(buckets[0].realized_volatility.abs() < f64::EPSILON);
        // ...while the lone tick in the next window still records its 100 → 110 move.
        assert_eq!(buckets[1].trade_count, 1);
        assert!((buckets[1].realized_volatility - (110.0_f64 / 100.0).ln()).abs() < 1e-12);
    }
}
