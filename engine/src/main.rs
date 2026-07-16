mod metrics;
mod storage;
mod tick;

use std::path::PathBuf;

use anyhow::Context;
use clap::Parser;

/// Compute microstructure metrics from a tick CSV and persist them to `SQLite`.
#[derive(Parser)]
#[command(version)]
struct Args {
    /// Input tick tape (CSV: `timestamp_ns,price,size,aggressor`)
    #[arg(long)]
    input: PathBuf,
    /// `SQLite` database the metrics are written to
    #[arg(long, default_value = "metrics.db")]
    db: PathBuf,
    /// Aggregation window, e.g. 250ms, 1s, 5m
    #[arg(long, default_value = "1s")]
    window: String,
}

fn main() -> anyhow::Result<()> {
    let args = Args::parse();
    let window_ns = parse_window(&args.window)?;

    let ticks = tick::read_csv(&args.input)
        .with_context(|| format!("reading ticks from {}", args.input.display()))?;
    let buckets = metrics::compute(&ticks, window_ns);

    let mut conn = rusqlite::Connection::open(&args.db)
        .with_context(|| format!("opening database {}", args.db.display()))?;
    storage::write_metrics(&mut conn, window_ns, &buckets)?;

    println!(
        "{} ticks -> {} metric buckets (window {}) -> {}",
        ticks.len(),
        buckets.len(),
        args.window,
        args.db.display()
    );
    Ok(())
}

/// Parse a human-friendly window like `250ms`, `1s` or `5m` into nanoseconds.
fn parse_window(input: &str) -> anyhow::Result<i64> {
    let (value, unit_ns) = if let Some(v) = input.strip_suffix("ms") {
        (v, 1_000_000)
    } else if let Some(v) = input.strip_suffix('s') {
        (v, 1_000_000_000)
    } else if let Some(v) = input.strip_suffix('m') {
        (v, 60_000_000_000)
    } else {
        anyhow::bail!("window '{input}' must end in ms, s or m");
    };
    let value: i64 = value
        .parse()
        .with_context(|| format!("invalid window '{input}'"))?;
    anyhow::ensure!(value > 0, "window must be positive, got '{input}'");
    Ok(value * unit_ns)
}

#[cfg(test)]
mod tests {
    use super::parse_window;

    #[test]
    fn parses_supported_units() {
        assert_eq!(parse_window("250ms").unwrap(), 250_000_000);
        assert_eq!(parse_window("1s").unwrap(), 1_000_000_000);
        assert_eq!(parse_window("5m").unwrap(), 300_000_000_000);
    }

    #[test]
    fn rejects_bad_windows() {
        for bad in ["1h", "0s", "-1s", "s", "abc"] {
            assert!(parse_window(bad).is_err(), "expected error for {bad}");
        }
    }
}
