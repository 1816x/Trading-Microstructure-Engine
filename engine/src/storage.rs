use rusqlite::Connection;

use crate::ofi::OfiBucket;

/// Persist OFI buckets, replacing any previous run for the same window size.
///
/// The `(bucket_start_ns, window_ns)` primary key makes reruns idempotent and
/// lets different window sizes coexist in the same database.
pub fn write_ofi(
    conn: &mut Connection,
    window_ns: i64,
    buckets: &[OfiBucket],
) -> rusqlite::Result<()> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS ofi (
            bucket_start_ns INTEGER NOT NULL,
            window_ns       INTEGER NOT NULL,
            buy_volume      INTEGER NOT NULL,
            sell_volume     INTEGER NOT NULL,
            ofi             REAL    NOT NULL,
            PRIMARY KEY (bucket_start_ns, window_ns)
        )",
    )?;
    let tx = conn.transaction()?;
    {
        let mut stmt = tx.prepare(
            "INSERT OR REPLACE INTO ofi
             (bucket_start_ns, window_ns, buy_volume, sell_volume, ofi)
             VALUES (?1, ?2, ?3, ?4, ?5)",
        )?;
        for bucket in buckets {
            stmt.execute((
                bucket.bucket_start_ns,
                window_ns,
                bucket.buy_volume,
                bucket.sell_volume,
                bucket.ofi(),
            ))?;
        }
    }
    tx.commit()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn writes_buckets_and_is_idempotent() {
        let mut conn = Connection::open_in_memory().unwrap();
        let buckets = [
            OfiBucket {
                bucket_start_ns: 0,
                buy_volume: 3,
                sell_volume: 1,
            },
            OfiBucket {
                bucket_start_ns: 1000,
                buy_volume: 0,
                sell_volume: 2,
            },
        ];
        write_ofi(&mut conn, 1000, &buckets).unwrap();
        write_ofi(&mut conn, 1000, &buckets).unwrap();

        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM ofi", [], |row| row.get(0))
            .unwrap();
        assert_eq!(count, 2);

        let ofi: f64 = conn
            .query_row("SELECT ofi FROM ofi WHERE bucket_start_ns = 0", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert!((ofi - 0.5).abs() < f64::EPSILON);
    }
}
