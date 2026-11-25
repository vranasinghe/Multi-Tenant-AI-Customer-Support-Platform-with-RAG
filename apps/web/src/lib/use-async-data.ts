"use client";

import { useCallback, useEffect, useState } from "react";

import { describeApiError } from "@/lib/api/messages";

/**
 * Loads data when `deps` change (and again on `reload()`), ignoring responses that arrive after
 * the inputs changed or the component unmounted, so a slow response for one org can never be
 * painted over another org's screen. State is only set from promise callbacks, never
 * synchronously in the effect body.
 */
export function useAsyncData<T>(fetcher: () => Promise<T>, deps: readonly unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    fetcher()
      .then((value) => {
        if (!current) return;
        setData(value);
        setError(null);
      })
      .catch((failure: unknown) => {
        if (current) setError(describeApiError(failure));
      });
    return () => {
      current = false;
    };
    // `fetcher` is intentionally excluded: callers key reloads on `deps` and `reload()`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  const reload = useCallback(() => {
    setError(null);
    setAttempt((value) => value + 1);
  }, []);

  return { data, error, reload, update: setData };
}
