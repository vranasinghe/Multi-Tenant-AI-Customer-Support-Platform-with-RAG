import { useCurrentFrame } from "remotion";

import { progress } from "../animations";
import { COLORS } from "../styles/theme";

/** A line that draws in the direction data travels; dashed lines keep flowing. */
export const AnimatedConnection = ({
  length,
  at = 0,
  frames = 15,
  dashed = false,
  color = COLORS.blue,
}: {
  length: number;
  at?: number;
  frames?: number;
  dashed?: boolean;
  color?: string;
}) => {
  const frame = useCurrentFrame();
  const drawn = Math.max(0, (length - 14) * progress(frame, at, frames));
  return (
    <svg width={length} height={24} viewBox={`0 0 ${length} 24`}>
      <line
        x1={2}
        y1={12}
        x2={2 + drawn}
        y2={12}
        stroke={color}
        strokeWidth={4}
        strokeLinecap="round"
        strokeDasharray={dashed ? "12 10" : undefined}
        strokeDashoffset={dashed ? -frame * 1.2 : undefined}
      />
      <path
        d={`M ${drawn} 4 L ${drawn + 12} 12 L ${drawn} 20 z`}
        fill={color}
        opacity={drawn > 0 ? 1 : 0}
      />
    </svg>
  );
};
