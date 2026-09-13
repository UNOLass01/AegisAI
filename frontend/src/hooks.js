import { useCallback, useEffect, useRef, useState } from "react";

/** Load async data with loading/error states; optional polling. */
export function useApi(loader, { deps = [], pollMs = 0 } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const cancelled = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await loader();
      if (!cancelled.current) {
        setData(result);
      }
    } catch (err) {
      if (!cancelled.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (!cancelled.current) {
        setLoading(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    cancelled.current = false;
    load();
    let timer = null;
    if (pollMs > 0) {
      timer = setInterval(load, pollMs);
    }
    return () => {
      cancelled.current = true;
      if (timer) {
        clearInterval(timer);
      }
    };
  }, [load, pollMs]);

  return { data, error, loading, reload: load };
}

export function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(digits);
}

export function formatTime(iso) {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return String(iso);
  }
  return date.toLocaleString();
}
