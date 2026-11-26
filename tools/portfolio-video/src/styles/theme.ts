export const COLORS = {
  background: "#080C14",
  surface: "#111827",
  line: "#1F2A3D",
  blue: "#2563EB",
  accent: "#38BDF8",
  white: "#FFFFFF",
  muted: "#94A3B8",
  green: "#22C55E",
  amber: "#F59E0B",
  red: "#EF4444",
} as const;

export const SANS = "Inter, 'Segoe UI', sans-serif";
export const MONO = "'JetBrains Mono', Consolas, monospace";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

/** Vertical bands, so labels, footage, captions and the watermark never collide. */
export const LAYOUT = {
  labelTop: 28,
  contentTop: 100,
  contentBottom: 912,
  captionBottom: 34,
  side: 48,
} as const;
