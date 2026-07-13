mod tick;

use std::path::PathBuf;
use std::process::ExitCode;

// Bare-bones entry point for the vertical slice; a real CLI (window size,
// output database) arrives together with the OFI computation.
fn main() -> ExitCode {
    let Some(path) = std::env::args().nth(1).map(PathBuf::from) else {
        eprintln!("usage: microstructure-engine <ticks.csv>");
        return ExitCode::FAILURE;
    };
    match tick::read_csv(&path) {
        Ok(ticks) => {
            println!("parsed {} ticks from {}", ticks.len(), path.display());
            ExitCode::SUCCESS
        }
        Err(err) => {
            eprintln!("error: {err}");
            ExitCode::FAILURE
        }
    }
}
