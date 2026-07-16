use rusqlite::Connection;

use crate::metrics::MetricsBucket;

/// Persist metric buckets, replacing any previous run for the same window size.
///
/// The `(bucket_start_ns, window_ns)` primary key makes reruns idempotent and
/// lets different window sizes coexist in the same database.
pub fn write_metrics(
    conn: &mut Connection,
    window_ns: i64,
    buckets: &[MetricsBucket],
) -> rusqlite::Result<()> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS metrics (
            bucket_start_ns     INTEGER NOT NULL,
            window_ns           INTEGER NOT NULL,
            buy_volume          INTEGER NOT NULL,
            sell_volume         INTEGER NOT NULL,
            total_volume        INTEGER NOT NULL,
            trade_count         INTEGER NOT NULL,
            ofi                 REAL    NOT NULL,
            vwap                REAL    NOT NULL,
            realized_volatility REAL    NOT NULL,
            PRIMARY KEY (bucket_start_ns, window_ns)
        )",
    )?;
    let tx = conn.transaction()?;
    {
        let mut stmt = tx.prepare(
            "INSERT OR REPLACE INTO metrics
             (bucket_start_ns, window_ns, buy_volume, sell_volume, total_volume,
              trade_count, ofi, vwap, realized_volatility)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
        )?;
        for bucket in buckets {
            stmt.execute((
                bucket.bucket_start_ns,
                window_ns,
                bucket.buy_volume,
                bucket.sell_volume,
                bucket.total_volume(),
                bucket.trade_count,
                bucket.ofi(),
                bucket.vwap,
                bucket.realized_volatility,
            ))?;
        }
    }
    tx.commit()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bucket(bucket_start_ns: i64, buy_volume: u64, sell_volume: u64) -> MetricsBucket {
        MetricsBucket {
            bucket_start_ns,
            buy_volume,
            sell_volume,
            trade_count: buy_volume + sell_volume,
            vwap: 21_400.0,
            realized_volatility: 0.01,
        }
    }

    #[test]
    fn writes_buckets_and_is_idempotent() {
        let mut conn = Connection::open_in_memory().unwrap();
        let buckets = [bucket(0, 3, 1), bucket(1000, 0, 2)];
        write_metrics(&mut conn, 1000, &buckets).unwrap();
        write_metrics(&mut conn, 1000, &buckets).unwrap();

        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM metrics", [], |row| row.get(0))
            .unwrap();
        assert_eq!(count, 2);

        let (ofi, total_volume, vwap, trade_count): (f64, i64, f64, i64) = conn
            .query_row(
                "SELECT ofi, total_volume, vwap, trade_count
                 FROM metrics WHERE bucket_start_ns = 0",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .unwrap();
        assert!((ofi - 0.5).abs() < f64::EPSILON);
        assert_eq!(total_volume, 4);
        assert!((vwap - 21_400.0).abs() < f64::EPSILON);
        assert_eq!(trade_count, 4);
    }
}
