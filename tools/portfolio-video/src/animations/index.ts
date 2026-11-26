import type { CSSProperties } from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";

export const EASE = Easing.bezier(0.4, 0, 0.2, 1);

/** 0 → 1 between two frames, eased and clamped. */
export function progress(frame: number, from: number, duration: number): number {
  return interpolate(frame, [from, from + Math.max(duration, 1)], [0, 1], {
    easing: EASE,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

export const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/** The standard reveal: fade in while moving up. */
export function useRise(from: number, duration = 12, distance = 16): CSSProperties {
  const p = progress(useCurrentFrame(), from, duration);
  return { opacity: p, transform: `translateY(${(1 - p) * distance}px)` };
}

export function useFade(from: number, duration = 12): number {
  return progress(useCurrentFrame(), from, duration);
}
