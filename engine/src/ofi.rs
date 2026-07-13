use std::collections::BTreeMap;

use crate::tick::{Aggressor, Tick};

/// Aggressor volume totals for one fixed time window.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct OfiBucket {
    /// Window start, aligned to a multiple of the window length.
    pub bucket_start_ns: i64,
    pub buy_volume: u64,
    pub sell_volume: u64,
}

impl OfiBucket {
    /// Order-flow imbalance: `(buy − sell) / (buy + sell)`, in `[-1, 1]`.
    ///
    /// Buckets only exist when at least one tick landed in them, so the
    /// denominator is never zero.
    #[must_use]
    pub fn ofi(&self) -> f64 {
        let buy = self.buy_volume as f64;
        let sell = self.sell_volume as f64;
        (buy - sell) / (buy + sell)
    }
}

/// Aggregate a tape into fixed windows of `window_ns`, aligned to the epoch.
///
/// Input order does not matter; output is sorted by bucket start and skips
/// windows with no ticks.
///
/// # Panics
///
/// Panics if `window_ns` is not positive.
#[must_use]
pub fn compute(ticks: &[Tick], window_ns: i64) -> Vec<OfiBucket> {
    assert!(window_ns > 0, "window_ns must be positive");
    let mut volumes: BTreeMap<i64, (u64, u64)> = BTreeMap::new();
    for tick in ticks {
        let bucket_start_ns = tick.timestamp_ns - tick.timestamp_ns.rem_euclid(window_ns);
        let (buy, sell) = volumes.entry(bucket_start_ns).or_default();
        match tick.aggressor {
            Aggressor::Buy => *buy += u64::from(tick.size),
            Aggressor::Sell => *sell += u64::from(tick.size),
        }
    }
    volumes
        .into_iter()
        .map(|(bucket_start_ns, (buy_volume, sell_volume))| OfiBucket {
            bucket_start_ns,
            buy_volume,
            sell_volume,
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tick(timestamp_ns: i64, size: u32, aggressor: Aggressor) -> Tick {
        Tick {
            timestamp_ns,
            price: 21400.0,
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
        assert_eq!(
            buckets,
            vec![
                OfiBucket {
                    bucket_start_ns: 0,
                    buy_volume: 2,
                    sell_volume: 1
                },
                OfiBucket {
                    bucket_start_ns: 1000,
                    buy_volume: 3,
                    sell_volume: 0
                },
                OfiBucket {
                    bucket_start_ns: 3000,
                    buy_volume: 0,
                    sell_volume: 4
                },
            ]
        );
    }

    #[test]
    fn ofi_is_bounded_and_signed_correctly() {
        let balanced = OfiBucket {
            bucket_start_ns: 0,
            buy_volume: 5,
            sell_volume: 5,
        };
        let all_buy = OfiBucket {
            bucket_start_ns: 0,
            buy_volume: 7,
            sell_volume: 0,
        };
        let all_sell = OfiBucket {
            bucket_start_ns: 0,
            buy_volume: 0,
            sell_volume: 7,
        };
        let mixed = OfiBucket {
            bucket_start_ns: 0,
            buy_volume: 2,
            sell_volume: 1,
        };
        assert!((balanced.ofi() - 0.0).abs() < f64::EPSILON);
        assert!((all_buy.ofi() - 1.0).abs() < f64::EPSILON);
        assert!((all_sell.ofi() + 1.0).abs() < f64::EPSILON);
        assert!((mixed.ofi() - 1.0 / 3.0).abs() < 1e-12);
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
}
