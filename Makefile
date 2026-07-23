# Root shortcuts for the per-component commands documented in the README.
# Recipes mirror CI (.github/workflows/ci.yml) — no logic of their own.

.PHONY: help setup demo verify build test lint clean

help: ## list the available targets
	@grep -E '^[a-z]+:.*## ' Makefile | awk -F':.*## ' '{printf "  make %-7s %s\n", $$1, $$2}'

setup: .venv ## install the Python venv (.venv) and dashboard node_modules
	npm ci --prefix dashboard

.venv:
	python3 -m venv .venv
	.venv/bin/pip install -e "backtest[dev]"

demo: ## full-stack demo on the synthetic sample data (Ctrl-C stops it)
	bash scripts/demo.sh

verify: ## end-to-end pipeline smoke test (tape -> engine -> journal -> regime join)
	bash scripts/verify_pipeline.sh

build: ## release build of the engine + production build of the dashboard
	cargo build --release --manifest-path engine/Cargo.toml
	npm run build --prefix dashboard

test: | .venv ## all three test suites, same as CI
	cargo test --manifest-path engine/Cargo.toml
	cd backtest && ../.venv/bin/pytest
	npm test --prefix dashboard

lint: | .venv ## all linters and format checks, same as CI
	cargo fmt --check --manifest-path engine/Cargo.toml
	cargo clippy --all-targets --manifest-path engine/Cargo.toml -- -D warnings
	cd backtest && ../.venv/bin/ruff check . && ../.venv/bin/ruff format --check .
	npm run lint --prefix dashboard
	npm run typecheck --prefix dashboard

clean: ## remove the generated DB, engine target/ and dashboard .next/
	rm -f metrics.db
	cargo clean --manifest-path engine/Cargo.toml
	rm -rf dashboard/.next
