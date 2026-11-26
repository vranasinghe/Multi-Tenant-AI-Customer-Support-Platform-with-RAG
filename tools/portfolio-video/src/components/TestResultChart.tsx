import { useCurrentFrame } from "remotion";

import { progress } from "../animations";
import { COLORS, SANS } from "../styles/theme";

export type SuiteResult = { name: string; passed: number };

/** One row per suite, all on the same linear scale. */
export const TestResultChart = ({
  results,
  at = 0,
  width = 1000,
}: {
  results: SuiteResult[];
  at?: number;
  width?: number;
}) => {
  const frame = useCurrentFrame();
  const max = Math.max(...results.map((r) => r.passed));
  const barSpace = width - 330;
  return (
    <div style={{ width, fontFamily: SANS }}>
      {results.map((result, index) => {
        const p = progress(frame, at + index * 5, 22);
        return (
          <div
            key={result.name}
            style={{ display: "flex", alignItems: "center", height: 46, opacity: p }}
          >
            <div style={{ width: 220, color: COLORS.muted, fontSize: 22 }}>{result.name}</div>
            <div
              style={{
                width: Math.max(4, (result.passed / max) * barSpace) * p,
                height: 20,
                borderRadius: 6,
                background: COLORS.green,
              }}
            />
            <div style={{ marginLeft: 14, color: COLORS.white, fontSize: 22, fontWeight: 700 }}>
              {result.passed.toLocaleString("en-US")}
            </div>
          </div>
        );
      })}
    </div>
  );
};
