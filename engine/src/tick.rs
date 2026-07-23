use std::io::Read;
use std::path::Path;

use serde::Deserialize;

/// One trade print from the tape.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Tick {
    pub timestamp_ns: i64,
    /// Trade print price. Validated positive and finite when the tape is parsed:
    /// it feeds VWAP and the log-return realized volatility, so a zero, negative
    /// or non-finite price would make those metrics `inf`/`NaN` and poison the
    /// `SQLite` write — the same failure mode a zero `size` causes for OFI/VWAP.
    #[serde(deserialize_with = "finite_positive_price")]
    pub price: f64,
    /// Contracts traded. Validated positive when the tape is parsed so a
    /// window's total volume is never zero (which would make OFI and VWAP
    /// divide by zero).
    #[serde(deserialize_with = "positive_size")]
    pub size: u32,
    pub aggressor: Aggressor,
}

/// Side of the aggressive (liquidity-taking) order.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum Aggressor {
    #[serde(rename = "B")]
    Buy,
    #[serde(rename = "S")]
    Sell,
}

/// Deserialize a tick `size`, rejecting zero.
///
/// A window whose ticks all have zero size would have zero total volume, so
/// order-flow imbalance and VWAP would divide by zero. Rejecting it at parse
/// time keeps those metrics well-defined. Negative inputs are already rejected
/// by `u32` parsing, before this runs.
fn positive_size<'de, D>(deserializer: D) -> Result<u32, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let size = u32::deserialize(deserializer)?;
    if size == 0 {
        return Err(serde::de::Error::custom("size must be positive, got 0"));
    }
    Ok(size)
}

/// Deserialize a tick `price`, rejecting non-positive and non-finite values.
///
/// The price feeds VWAP's numerator and the log return `ln(price / prev)` in
/// [`crate::metrics::compute`]. A zero, negative or non-finite (`NaN`/`inf`)
/// price would make realized volatility `inf`/`NaN`, which then poisons the
/// `SQLite` write. Rejecting it at parse time — with row context from the CSV
/// reader — keeps those metrics well-defined, mirroring [`positive_size`].
fn finite_positive_price<'de, D>(deserializer: D) -> Result<f64, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let price = f64::deserialize(deserializer)?;
    if !(price.is_finite() && price > 0.0) {
        return Err(serde::de::Error::custom(format!(
            "price must be a positive, finite number, got {price}"
        )));
    }
    Ok(price)
}

/// Read a tick tape from a CSV file with the header
/// `timestamp_ns,price,size,aggressor`.
pub fn read_csv(path: &Path) -> Result<Vec<Tick>, csv::Error> {
    read_from(std::fs::File::open(path).map_err(csv::Error::from)?)
}

fn read_from<R: Read>(reader: R) -> Result<Vec<Tick>, csv::Error> {
    csv::Reader::from_reader(reader)
        .into_deserialize()
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_well_formed_rows() {
        let csv = "timestamp_ns,price,size,aggressor\n\
                   1000,21400.00,3,B\n\
                   2000,21400.25,1,S\n";
        let ticks = read_from(csv.as_bytes()).unwrap();
        assert_eq!(
            ticks,
            vec![
                Tick {
                    timestamp_ns: 1000,
                    price: 21400.0,
                    size: 3,
                    aggressor: Aggressor::Buy
                },
                Tick {
                    timestamp_ns: 2000,
                    price: 21400.25,
                    size: 1,
                    aggressor: Aggressor::Sell
                },
            ]
        );
    }

    #[test]
    fn rejects_unknown_aggressor() {
        let csv = "timestamp_ns,price,size,aggressor\n1000,21400.00,3,X\n";
        assert!(read_from(csv.as_bytes()).is_err());
    }

    #[test]
    fn rejects_zero_size() {
        let csv = "timestamp_ns,price,size,aggressor\n\
                   1000,21400.00,3,B\n\
                   2000,21400.25,0,S\n";
        let err = read_from(csv.as_bytes()).unwrap_err();
        assert!(
            err.to_string().contains("size must be positive"),
            "unexpected error: {err}"
        );
    }

    #[test]
    fn rejects_negative_size() {
        let csv = "timestamp_ns,price,size,aggressor\n1000,21400.00,-1,B\n";
        assert!(read_from(csv.as_bytes()).is_err());
    }

    #[test]
    fn rejects_zero_price() {
        let csv = "timestamp_ns,price,size,aggressor\n\
                   1000,0,3,B\n";
        let err = read_from(csv.as_bytes()).unwrap_err();
        assert!(
            err.to_string()
                .contains("price must be a positive, finite number"),
            "unexpected error: {err}"
        );
    }

    #[test]
    fn rejects_negative_price() {
        let csv = "timestamp_ns,price,size,aggressor\n1000,-21400.00,3,B\n";
        let err = read_from(csv.as_bytes()).unwrap_err();
        assert!(
            err.to_string()
                .contains("price must be a positive, finite number"),
            "unexpected error: {err}"
        );
    }
}
