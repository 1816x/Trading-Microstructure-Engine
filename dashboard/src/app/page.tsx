"use client";

import { useCallback, useState } from "react";

import { getOfi, getVolatility, getVolume } from "@/lib/api";
import { fmtInt, fmtPrice, fmtSig, fmtSigned } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { OfiChart } from "@/components/charts/OfiChart";
import { VolatilityChart } from "@/components/charts/VolatilityChart";
import { VolumeChart } from "@/components/charts/VolumeChart";
import { VwapChart } from "@/components/charts/VwapChart";
import { StatTile } from "@/components/StatTile";
import { EmptyState, ErrorState } from "@/components/states";

const LIMITS = [100, 500, 1000, 5000] as const;

const ENGINE_HINT = (
  <>
    Produce metrics first:{" "}
    <code className="font-mono">
      cargo run --manifest-path engine/Cargo.toml --release -- --input
      data/sample_mnq_ticks.csv --db metrics.db --window 1s
    </code>{" "}
    then serve them with <code className="font-mono">uvicorn backtest.api:app</code>.
  </>
);

export default function MetricsPage() {
  const [limit, setLimit] = useState<number>(100);

  const ofi = useApi(useCallback(() => getOfi(limit), [limit]));
  const volatility = useApi(useCallback(() => getVolatility(limit), [limit]));
  const volume = useApi(useCallback(() => getVolume(limit), [limit]));

  const refetchAll = () => {
    ofi.refetch();
    volatility.refetch();
    volume.refetch();
  };

  const loading = ofi.loading || volatility.loading || volume.loading;
  const firstError = [ofi, volatility, volume].map((s) => s.error).find(Boolean) ?? null;
  const noData = !ofi.data && !volatility.data && !volume.data;

  // Newest bucket first, straight from the API ordering.
  const latestOfi = ofi.data?.[0];
  const latestVol = volatility.data?.[0];
  const latestVolume = volume.data?.[0];
  const totalVolume = volume.data?.reduce((sum, row) => sum + row.total_volume, 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div
          className="inline-flex overflow-hidden rounded-md border border-hairline"
          role="group"
          aria-label="Windows to fetch"
        >
          {LIMITS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setLimit(option)}
              aria-pressed={limit === option}
              className={`px-3 py-1.5 text-xs ${
                limit === option
                  ? "bg-surface font-medium text-ink"
                  : "text-ink-2 hover:text-ink"
              }`}
            >
              {fmtInt(option)}
            </button>
          ))}
        </div>
        <span className="text-xs text-muted">most recent windows</span>
        <button
          type="button"
          onClick={refetchAll}
          disabled={loading}
          className="rounded-md border border-hairline px-3 py-1.5 text-xs text-ink-2 hover:text-ink disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {firstError && noData ? (
        <ErrorState
          error={firstError}
          hint={firstError.status === 503 ? ENGINE_HINT : undefined}
        />
      ) : ofi.data?.length === 0 && volume.data?.length === 0 ? (
        <EmptyState title="No metric buckets yet" body={ENGINE_HINT} />
      ) : (
        <>
          {firstError ? (
            <p className="text-xs text-sell">
              Refresh failed ({firstError.detail}) — showing the last good data.
            </p>
          ) : null}
          <div
            className={`flex flex-col gap-4 transition-opacity ${loading ? "opacity-60" : ""}`}
          >
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatTile
                label="Order-flow imbalance"
                value={latestOfi ? fmtSigned(latestOfi.ofi, 3) : "—"}
                sub="latest window"
              />
              <StatTile
                label="Realized volatility"
                value={latestVol ? fmtSig(latestVol.realized_volatility) : "—"}
                sub="latest window"
              />
              <StatTile
                label="VWAP"
                value={latestVolume ? fmtPrice(latestVolume.vwap) : "—"}
                sub="latest window"
              />
              <StatTile
                label="Volume"
                value={totalVolume !== undefined ? fmtInt(totalVolume) : "—"}
                sub={`across ${volume.data?.length ?? 0} fetched windows`}
              />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              {ofi.data ? <OfiChart rows={ofi.data} /> : null}
              {volatility.data ? <VolatilityChart rows={volatility.data} /> : null}
              {volume.data ? <VolumeChart rows={volume.data} /> : null}
              {volume.data ? <VwapChart rows={volume.data} /> : null}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
