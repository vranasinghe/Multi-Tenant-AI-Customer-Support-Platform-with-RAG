import type { CSSProperties } from "react";
import { useCurrentFrame } from "remotion";

import { progress, useRise } from "../animations";
import { COLORS, SANS } from "../styles/theme";

type Props = {
  text: string;
  subtitle?: string;
  at?: number;
  size?: number;
  style?: CSSProperties;
};

/** Large headline that wipes in from the left, with an optional line under it. */
export const CinematicTitle = ({ text, subtitle, at = 0, size = 64, style }: Props) => {
  const wipe = progress(useCurrentFrame(), at, 22);
  const sub = useRise(at + 14);
  return (
    <div style={{ textAlign: "center", fontFamily: SANS, ...style }}>
      <div
        style={{
          color: COLORS.white,
          fontSize: size,
          fontWeight: 700,
          lineHeight: 1.18,
          letterSpacing: -0.5,
          clipPath: `inset(-20% ${(1 - wipe) * 100}% -20% 0)`,
        }}
      >
        {text}
      </div>
      {subtitle ? (
        <div style={{ ...sub, color: COLORS.muted, fontSize: size * 0.46, marginTop: 14 }}>
          {subtitle}
        </div>
      ) : null}
    </div>
  );
};
