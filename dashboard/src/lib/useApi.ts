"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  /** True while a fetch is in flight (first load and refetches alike). */
  loading: boolean;
  refetch: () => void;
}

interface Settled<T> {
  data: T | null;
  error: ApiError | null;
  /** Which (fetcher, generation) produced this result. */
  fetcher: () => Promise<T>;
  generation: number;
}

/**
 * Minimal fetch-on-mount hook with manual refetch. `loading` is derived — the
 * currently wanted (fetcher, generation) hasn't settled yet — so the effect
 * never sets state synchronously. On refetch or error the previous data is
 * kept, letting charts hold their frame at reduced opacity instead of
 * flashing empty. `fetcher` must be memoized: every identity change is a new
 * request.
 */
export function useApi<T>(fetcher: () => Promise<T>): ApiState<T> {
  const [generation, setGeneration] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  useEffect(() => {
    let live = true;
    fetcher().then(
      (data) => {
        if (live) setSettled({ data, error: null, fetcher, generation });
      },
      (err: unknown) => {
        if (!live) return;
        const error = err instanceof ApiError ? err : new ApiError(0, String(err));
        setSettled((prev) => ({ data: prev?.data ?? null, error, fetcher, generation }));
      },
    );
    return () => {
      live = false;
    };
  }, [fetcher, generation]);

  const refetch = useCallback(() => setGeneration((g) => g + 1), []);

  return {
    data: settled?.data ?? null,
    error: settled?.error ?? null,
    loading: settled?.fetcher !== fetcher || settled.generation !== generation,
    refetch,
  };
}
