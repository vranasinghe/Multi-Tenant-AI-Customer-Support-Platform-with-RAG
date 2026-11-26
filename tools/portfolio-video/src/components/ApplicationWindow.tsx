import type { CSSProperties, ReactNode } from "react";

import { COLORS, SANS } from "../styles/theme";

export const TITLE_BAR = 36;

type Props = {
  width: number;
  height: number;
  /** A plain description of what is inside. Never a made-up address. */
  caption: string;
  children: ReactNode;
  style?: CSSProperties;
};

/** Rounded window around real application footage. The application keeps its own light theme. */
export const ApplicationWindow = ({ width, height, caption, children, style }: Props) => (
  <div
    style={{
      width,
      height: height + TITLE_BAR,
      borderRadius: 16,
      overflow: "hidden",
      background: COLORS.surface,
      border: `1px solid ${COLORS.line}`,
      boxShadow: "0 30px 80px rgba(0,0,0,0.55), 0 0 60px rgba(37,99,235,0.14)",
      ...style,
    }}
  >
    <div
      style={{
        height: TITLE_BAR,
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "0 14px",
      }}
    >
      {[0, 1, 2].map((i) => (
        <span key={i} style={{ width: 10, height: 10, borderRadius: 5, background: COLORS.line }} />
      ))}
      <span style={{ marginLeft: 10, color: COLORS.muted, fontFamily: SANS, fontSize: 15 }}>
        {caption}
      </span>
    </div>
    <div style={{ position: "relative", width, height, overflow: "hidden" }}>{children}</div>
  </div>
);
