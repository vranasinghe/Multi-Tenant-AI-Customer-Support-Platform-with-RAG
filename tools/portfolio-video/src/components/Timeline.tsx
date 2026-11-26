import { useCurrentFrame } from "remotion";

import { progress } from "../animations";
import { COLORS, SANS } from "../styles/theme";

/** Ordered steps on a line that fills as the story advances. Spacing is order, not time. */
export const Timeline = ({
  steps,
  at = 0,
  interval = 10,
  width = 1600,
}: {
  steps: string[];
  at?: number;
  interval?: number;
  width?: number;
}) => {
  const frame = useCurrentFrame();
  const filled = progress(frame, at, interval * steps.length);
  return (
    <div style={{ width, position: "relative", height: 110, fontFamily: SANS }}>
      <div
        style={{
          position: "absolute",
          top: 17,
          left: 0,
          right: 0,
          height: 4,
          background: COLORS.line,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 17,
          left: 0,
          width: width * filled,
          height: 4,
          background: COLORS.blue,
        }}
      />
      {steps.map((step, index) => {
        const p = progress(frame, at + index * interval, 10);
        const x = (width / steps.length) * (index + 0.5);
        return (
          <div
            key={step}
            style={{ position: "absolute", left: x - 90, width: 180, textAlign: "center" }}
          >
            <div
              style={{
                width: 38,
                height: 38,
                margin: "0 auto",
                borderRadius: 19,
                background: p > 0.5 ? COLORS.blue : COLORS.surface,
                border: `3px solid ${COLORS.blue}`,
                boxSizing: "border-box",
              }}
            />
            <div style={{ marginTop: 14, color: COLORS.white, fontSize: 20, opacity: p }}>
              {step}
            </div>
          </div>
        );
      })}
    </div>
  );
};
