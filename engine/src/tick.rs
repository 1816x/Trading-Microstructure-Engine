use std::io::Read;
use std::path::Path;

use serde::Deserialize;

/// One trade print from the tape.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Tick {
    pub timestamp_ns: i64,
    pub price: f64,
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
}
