"use client";

import { useEffect, useState } from "react";
import { ApiError } from "./api";

/** Load data once on mount (or when ``deps`` change). */
export function useApi<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    load()
      .then((value) => !cancelled && setData(value))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : "Couldn't load this."));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, setData };
}
