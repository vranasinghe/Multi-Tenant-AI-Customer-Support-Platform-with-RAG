import { useCurrentFrame } from "remotion";

import { progress, useRise } from "../animations";
import { COLORS, SANS } from "../styles/theme";

type Props = {
  /** The measured value. The counter ends exactly here and never passes it. */
  value: number;
  label: string;
  at?: number;
  frames?: number;
  suffix?: string;
  color?: string;
  size?: number;
};

export const MetricCounter = ({
  value,
  label,
  at = 0,
  frames = 36,
  suffix = "",
  color = COLORS.green,
  size = 150,
}: Props) => {
  const p = progress(useCurrentFrame(), at, frames);
  const style = useRise(at);
  return (
    <div style={{ ...style, textAlign: "center", fontFamily: SANS }}>
      <div style={{ color, fontSize: size, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
        {Math.round(value * p).toLocaleString("en-US")}
        {suffix}
      </div>
      <div style={{ color: COLORS.white, fontSize: size * 0.2, fontWeight: 500 }}>{label}</div>
    </div>
  );
};
