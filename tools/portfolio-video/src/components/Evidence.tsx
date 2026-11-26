import { AbsoluteFill, useCurrentFrame } from "remotion";

import { progress, useRise } from "../animations";
import { SUITES, TOTAL_PASSED, ORIGINAL_BACKEND, SCORE } from "../data/metrics";
import excerpts from "../data/generated/excerpts.json";
import { COLORS, MONO, SANS } from "../styles/theme";

export type CodeKey = keyof typeof excerpts.code;
export type ArtifactKey = keyof typeof excerpts.artifacts;

const Frame = ({
  heading,
  detail,
  color,
  children,
  width,
}: {
  heading: string;
  detail: string;
  color: string;
  children: React.ReactNode;
  width: number;
}) => (
  <div
    style={{
      width,
      borderRadius: 16,
      border: `2px solid ${color}`,
      background: COLORS.surface,
      overflow: "hidden",
      fontFamily: SANS,
    }}
  >
    <div style={{ padding: "14px 22px", borderBottom: `1px solid ${COLORS.line}` }}>
      <span style={{ color, fontSize: 19, fontWeight: 700, letterSpacing: 1 }}>{heading}</span>
      <div style={{ color: COLORS.muted, fontSize: 18, fontFamily: MONO, marginTop: 4 }}>
        {detail}
      </div>
    </div>
    <div style={{ padding: "18px 22px" }}>{children}</div>
  </div>
);

/** Exact lines from a repository file, with their real line numbers. Not a live editor. */
export const CodeExcerpt = ({
  id,
  width = 1150,
  at = 0,
}: {
  id: CodeKey;
  width?: number;
  at?: number;
}) => {
  const style = useRise(at);
  const { file, first, last, lines } = excerpts.code[id];
  const indent = Math.min(
    ...lines.filter((l) => l.trim()).map((l) => l.length - l.trimStart().length),
  );
  const shown = lines.map((l) => l.slice(indent));
  const longest = Math.min(Math.max(...shown.map((l) => l.length), 40), 100);
  const size = Math.min(
    24,
    Math.floor((width - 120) / (longest * 0.6)),
    Math.floor(640 / (shown.length * 1.5)),
  );
  return (
    <div style={style}>
      <Frame
        heading="SOURCE CODE EXCERPT"
        detail={`${file} · lines ${first}–${last}`}
        color={COLORS.accent}
        width={width}
      >
        {shown.map((line, i) => (
          <div
            key={first + i}
            style={{ display: "flex", fontFamily: MONO, fontSize: size, lineHeight: 1.5 }}
          >
            <span style={{ width: 62, color: COLORS.muted, opacity: 0.6, flexShrink: 0 }}>
              {first + i}
            </span>
            <span style={{ color: COLORS.white, whiteSpace: "pre-wrap", minWidth: 0 }}>
              {line || " "}
            </span>
          </div>
        ))}
      </Frame>
    </div>
  );
};

/** Lines selected from a stored test artifact. Deliberately not styled as a running terminal. */
export const ArtifactExcerpt = ({
  id,
  width = 1150,
  at = 0,
}: {
  id: ArtifactKey;
  width?: number;
  at?: number;
}) => {
  const style = useRise(at);
  const { file, lines } = excerpts.artifacts[id];
  const shown = lines.map((l) => l.replace(/^ {1,6}/, (m) => (m.length > 2 ? "  " : m)));
  const longest = Math.max(...shown.map((l) => l.length), 40);
  const size = Math.min(26, Math.floor((width - 60) / (longest * 0.6)));
  const parts = file.split("/");
  return (
    <div style={style}>
      <Frame
        heading="STORED TEST ARTIFACT · selected lines"
        detail={`…/${parts.slice(-3).join("/")}`}
        color={COLORS.green}
        width={width}
      >
        {shown.map((line, i) => (
          <div
            key={i}
            style={{
              fontFamily: MONO,
              fontSize: size,
              lineHeight: 1.55,
              color: COLORS.white,
              whiteSpace: "pre",
            }}
          >
            {line}
          </div>
        ))}
      </Frame>
    </div>
  );
};

const Big = ({
  value,
  label,
  note,
  color,
  at,
}: {
  value: string;
  label: string;
  note?: string;
  color: string;
  at: number;
}) => {
  const style = useRise(at, 16, 24);
  return (
    <div style={{ ...style, textAlign: "center", width: 640, fontFamily: SANS }}>
      <div
        style={{
          color,
          fontSize: 170,
          fontWeight: 700,
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1.1,
        }}
      >
        {value}
      </div>
      <div style={{ color: COLORS.white, fontSize: 34, fontWeight: 600 }}>{label}</div>
      {note ? <div style={{ color: COLORS.muted, fontSize: 26, marginTop: 10 }}>{note}</div> : null}
    </div>
  );
};

/** First audit versus final local run, backend only. */
export const BackendGrowth = ({ second = 60 }: { second?: number }) => {
  const arrow = progress(useCurrentFrame(), second - 18, 14);
  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "center",
        paddingBottom: 90,
        fontFamily: SANS,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 40 }}>
        <Big
          value={ORIGINAL_BACKEND.toLocaleString("en-US")}
          label="backend tests · first audit"
          note="all passed; added audit checks still failed"
          color={COLORS.white}
          at={4}
        />
        <div style={{ color: COLORS.blue, fontSize: 100, opacity: arrow }}>→</div>
        <Big
          value="1,209"
          label="backend tests · final local run"
          note="17 skipped here, run separately"
          color={COLORS.green}
          at={second}
        />
      </div>
      <div style={{ color: COLORS.muted, fontSize: 24, marginTop: 70, opacity: arrow }}>
        Growth includes tests added with the inbox and analytics phase. A test count is not a
        coverage figure.
      </div>
    </AbsoluteFill>
  );
};

/** Each suite arrives in turn and the running total follows. */
export const SuiteTally = ({ interval = 30 }: { interval?: number }) => {
  const frame = useCurrentFrame();
  const names = [
    "Backend",
    "Runtime proxy (run separately)",
    "Web unit",
    "Widget unit",
    "Browser journeys",
  ];
  const total = SUITES.reduce(
    (sum, suite, i) => sum + suite.passed * progress(frame, 8 + i * interval, 18),
    0,
  );
  return (
    <AbsoluteFill style={{ fontFamily: SANS }}>
      <div style={{ position: "absolute", left: 200, top: 190, width: 860 }}>
        {SUITES.map((suite, i) => {
          const p = progress(frame, 8 + i * interval, 12);
          return (
            <div
              key={suite.name}
              style={{
                display: "flex",
                justifyContent: "space-between",
                padding: "22px 0",
                borderBottom: `2px solid ${COLORS.line}`,
                opacity: p,
                transform: `translateY(${(1 - p) * 14}px)`,
              }}
            >
              <span style={{ color: COLORS.muted, fontSize: 36 }}>{names[i]}</span>
              <span
                style={{
                  color: COLORS.white,
                  fontSize: 40,
                  fontWeight: 700,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {suite.passed.toLocaleString("en-US")}
              </span>
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 1140, top: 300, width: 660, textAlign: "center" }}>
        <div
          style={{
            color: COLORS.green,
            fontSize: 200,
            fontWeight: 700,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {Math.round(Math.min(total, TOTAL_PASSED)).toLocaleString("en-US")}
        </div>
        <div style={{ color: COLORS.white, fontSize: 36, fontWeight: 600 }}>
          listed tests passing locally
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const FindingsAndScore = ({ second = 36 }: { second?: number }) => (
  <AbsoluteFill
    style={{ alignItems: "center", justifyContent: "center", paddingBottom: 80, fontFamily: SANS }}
  >
    <div style={{ display: "flex", alignItems: "flex-start", gap: 140 }}>
      <Big
        value="7 / 7"
        label="original audit findings"
        note="validated locally"
        color={COLORS.green}
        at={4}
      />
      <div>
        <Big
          value={`${SCORE.original} → ${SCORE.current}`}
          label="self-audit score, out of 100"
          color={COLORS.white}
          at={second}
        />
        <div
          style={{
            color: COLORS.amber,
            fontSize: 28,
            fontWeight: 600,
            textAlign: "center",
            marginTop: 18,
            opacity: progress(useCurrentFrame(), second + 14, 12),
          }}
        >
          Scored by the engineer who did the work.
          <br />
          Not independent certification.
        </div>
      </div>
    </div>
  </AbsoluteFill>
);
