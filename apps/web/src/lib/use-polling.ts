"use client";

import { useEffect, useRef } from "react";

/**
 * Calls `tick` every `intervalMs` while `active`, skipping ticks while the tab is hidden. Stops
 * when the condition clears or the component unmounts. Stale responses are the caller's concern
 * (`useAsyncData` already ignores out-of-date ones).
 */
export function usePolling(active: boolean, tick: () => void, intervalMs = 2000): void {
  const latest = useRef(tick);
  useEffect(() => {
    latest.current = tick;
  }, [tick]);

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") latest.current();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [active, intervalMs]);
}
