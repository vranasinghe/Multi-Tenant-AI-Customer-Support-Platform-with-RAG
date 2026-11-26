import type { ReactNode } from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";

import { progress } from "../animations";
import { COLORS, SANS } from "../styles/theme";

// The architecture as four conceptual layers of one modular monolith. Every connection drawn here
// exists in docker-compose.yml, app/workers/celery_app.py or the API code (fact check F-20–F-25).

const KINDS = {
  sync: { color: COLORS.blue, dash: undefined, label: "Synchronous request" },
  sse: { color: COLORS.accent, dash: "2 12", label: "SSE stream" },
  job: { color: COLORS.muted, dash: "16 12", label: "Background job" },
  db: { color: COLORS.white, dash: undefined, label: "Database transaction" },
  obj: { color: "#A78BFA", dash: undefined, label: "Object storage" },
  ai: { color: COLORS.accent, dash: "24 9 4 9", label: "AI provider request" },
} as const;
type Kind = keyof typeof KINDS;

export type LayerId = 0 | 1 | 2 | 3 | 4;

type BoxProps = {
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  lines?: string[];
  at?: number;
  color?: string;
  size?: number;
  dashed?: boolean;
};

const Box = ({
  x,
  y,
  w,
  h,
  title,
  lines = [],
  at = 0,
  color = COLORS.blue,
  size = 36,
  dashed,
}: BoxProps) => {
  const p = progress(useCurrentFrame(), at, 12);
  const detail = Math.round(size * 0.68);
  const block = size + lines.length * (detail + 12);
  const top = y + (h - block) / 2 + size - 5;
  return (
    <g style={{ opacity: p, transform: `translateY(${(1 - p) * 18}px)` }}>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={18}
        fill={COLORS.surface}
        stroke={color}
        strokeWidth={2.5}
        strokeDasharray={dashed ? "12 8" : undefined}
      />
      <text
        x={x + w / 2}
        y={top}
        textAnchor="middle"
        fill={COLORS.white}
        fontSize={size}
        fontWeight={700}
      >
        {title}
      </text>
      {lines.map((line, i) => (
        <text
          key={line}
          x={x + w / 2}
          y={top + (i + 1) * (detail + 12)}
          textAnchor="middle"
          fill={COLORS.muted}
          fontSize={detail}
        >
          {line}
        </text>
      ))}
    </g>
  );
};

const Arrow = ({
  points,
  kind,
  at = 0,
  label,
  labelAt,
}: {
  points: [number, number][];
  kind: Kind;
  at?: number;
  label?: string;
  labelAt?: [number, number];
}) => {
  const frame = useCurrentFrame();
  const p = progress(frame, at, 16);
  const { color, dash } = KINDS[kind];
  const d = `M ${points.map(([x, y]) => `${x} ${y}`).join(" L ")}`;
  const [lx, ly] = labelAt ?? [
    (points[0]![0] + points[points.length - 1]![0]) / 2,
    (points[0]![1] + points[points.length - 1]![1]) / 2,
  ];
  return (
    <g style={{ opacity: p }}>
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={4}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={dash}
        strokeDashoffset={dash ? -frame * 1.3 : undefined}
        markerEnd={`url(#arch-${kind})`}
      />
      {label ? (
        <text
          x={lx}
          y={ly}
          textAnchor="middle"
          fill={color}
          fontSize={24}
          fontWeight={600}
          stroke={COLORS.background}
          strokeWidth={8}
          paintOrder="stroke"
        >
          {label}
        </text>
      ) : null}
    </g>
  );
};

const Text = ({
  x,
  y,
  children,
  size = 24,
  color = COLORS.muted,
  weight = 500,
  anchor = "start",
}: {
  x: number;
  y: number;
  children: ReactNode;
  size?: number;
  color?: string;
  weight?: number;
  anchor?: "start" | "middle" | "end";
}) => (
  <text x={x} y={y} fontSize={size} fill={color} fontWeight={weight} textAnchor={anchor}>
    {children}
  </text>
);

const Legend = ({ kinds, y = 918 }: { kinds: Kind[]; y?: number }) => {
  let x = 96;
  return (
    <g>
      {kinds.map((kind) => {
        const { color, dash, label } = KINDS[kind];
        const start = x;
        x += 100 + label.length * 11;
        return (
          <g key={kind}>
            <line
              x1={start}
              y1={y}
              x2={start + 56}
              y2={y}
              stroke={color}
              strokeWidth={4}
              strokeDasharray={dash}
              strokeLinecap="round"
            />
            <Text x={start + 70} y={y + 7} size={20}>
              {label}
            </Text>
          </g>
        );
      })}
    </g>
  );
};

const Experience = () => (
  <>
    <Box
      x={220}
      y={220}
      w={660}
      h={220}
      title="Business dashboard"
      lines={["Next.js · React · TypeScript", "signed-in organization members"]}
      at={6}
    />
    <Box
      x={1040}
      y={220}
      w={660}
      h={220}
      title="Embeddable widget"
      lines={["small loader + isolated iframe", "on the customer's website"]}
      at={16}
    />
    <Box
      x={460}
      y={700}
      w={1000}
      h={130}
      title="Application layer · FastAPI"
      at={28}
      color={COLORS.line}
      size={32}
    />
    <Arrow
      kind="sync"
      points={[
        [430, 440],
        [430, 570],
        [620, 570],
        [620, 700],
      ]}
      at={34}
      label="REST + session cookie"
      labelAt={[430, 530]}
    />
    <Arrow
      kind="sync"
      points={[
        [1490, 440],
        [1490, 570],
        [1300, 570],
        [1300, 700],
      ]}
      at={40}
      label="short-lived scoped token"
      labelAt={[1490, 530]}
    />
    <Arrow
      kind="sse"
      points={[
        [780, 700],
        [780, 440],
      ]}
      at={48}
      label="answer stream"
      labelAt={[780, 640]}
    />
    <Arrow
      kind="sse"
      points={[
        [1140, 700],
        [1140, 440],
      ]}
      at={48}
      label="answer stream"
      labelAt={[1140, 640]}
    />
    <Legend kinds={["sync", "sse"]} />
  </>
);

const Application = () => (
  <>
    <rect
      x={140}
      y={250}
      width={1640}
      height={520}
      rx={26}
      fill="none"
      stroke={COLORS.blue}
      strokeWidth={2.5}
      strokeDasharray="14 10"
    />
    <Text x={180} y={300} size={30} color={COLORS.accent} weight={700}>
      api · FastAPI — one codebase, a modular monolith
    </Text>
    <Box
      x={190}
      y={340}
      w={750}
      h={180}
      title="Authentication & authorization"
      lines={["server-side sessions · role checks"]}
      at={8}
      size={34}
    />
    <Box
      x={980}
      y={340}
      w={750}
      h={180}
      title="Conversation services"
      lines={["chat · streaming · inbox · analytics"]}
      at={16}
      size={34}
    />
    <Box
      x={190}
      y={560}
      w={750}
      h={180}
      title="Knowledge services"
      lines={["uploads · websites · retrieval tester"]}
      at={24}
      size={34}
    />
    <Box
      x={980}
      y={560}
      w={750}
      h={180}
      title="Public widget routes"
      lines={["verified origins · minimal responses"]}
      at={32}
      size={34}
    />
    <Arrow
      kind="sync"
      points={[
        [760, 150],
        [760, 248],
      ]}
      at={28}
      label="requests"
      labelAt={[660, 210]}
    />
    <Arrow
      kind="sse"
      points={[
        [1160, 248],
        [1160, 150],
      ]}
      at={32}
      label="streamed answers"
      labelAt={[1300, 210]}
    />
    <Arrow
      kind="db"
      points={[
        [960, 772],
        [960, 860],
      ]}
      at={36}
      label="to data and processing"
      labelAt={[1140, 828]}
    />
    <Legend kinds={["sync", "sse", "db"]} />
  </>
);

const DataLayer = () => (
  <>
    <Box
      x={160}
      y={220}
      w={500}
      h={190}
      title="PostgreSQL"
      lines={["relational data + pgvector", "forced row-level security"]}
      at={6}
      size={34}
    />
    <Box
      x={710}
      y={220}
      w={500}
      h={190}
      title="Redis"
      lines={["queues · rate limits · leases"]}
      at={12}
      size={34}
    />
    <Box
      x={1260}
      y={220}
      w={500}
      h={190}
      title="Object storage"
      lines={["private original files"]}
      at={18}
      size={34}
    />
    <Box
      x={160}
      y={640}
      w={500}
      h={180}
      title="Maintenance worker"
      lines={["recovery sweep, own queue"]}
      at={36}
      size={34}
    />
    <Box
      x={710}
      y={640}
      w={500}
      h={180}
      title="Celery worker"
      lines={["parse · crawl · embed"]}
      at={30}
      size={34}
    />
    <Box
      x={1260}
      y={640}
      w={500}
      h={180}
      title="Beat scheduler"
      lines={["exactly one instance"]}
      at={42}
      size={34}
    />
    <Arrow
      kind="job"
      points={[
        [960, 410],
        [960, 640],
      ]}
      at={24}
      label="jobs"
      labelAt={[1000, 530]}
    />
    <Arrow
      kind="job"
      points={[
        [780, 410],
        [780, 480],
        [330, 480],
        [330, 640],
      ]}
      at={28}
      label="sweep"
      labelAt={[330, 575]}
    />
    <Arrow
      kind="job"
      points={[
        [1590, 640],
        [1590, 470],
        [1140, 470],
        [1140, 410],
      ]}
      at={32}
      label="schedule"
      labelAt={[1590, 575]}
    />
    <Arrow
      kind="db"
      points={[
        [800, 640],
        [800, 555],
        [520, 555],
        [520, 410],
      ]}
      at={36}
    />
    <Arrow
      kind="obj"
      points={[
        [1120, 640],
        [1120, 555],
        [1400, 555],
        [1400, 410],
      ]}
      at={40}
    />
    <Legend kinds={["job", "db", "obj"]} />
  </>
);

const Intelligence = () => {
  const steps: [string, string[], string, Kind | null][] = [
    ["Document processing", ["extract · clean", "chunk · embed"], "runs in the worker", null],
    ["Retrieval", ["vector + keyword", "rank fusion"], "runs in the api", "db"],
    ["Prompt construction", ["only what fits;", "sources tracked"], "runs in the api", "sync"],
    [
      "Provider adapters",
      ["language + embedding", "models · HTTPS"],
      "never run on a real one",
      "ai",
    ],
  ];
  return (
    <>
      {steps.map(([title, lines, where, kind], i) => {
        const x = 90 + i * 455;
        return (
          <g key={title}>
            <Box
              x={x}
              y={300}
              w={375}
              h={260}
              title={title}
              lines={lines}
              at={4 + i * 8}
              size={30}
              color={kind === "ai" ? COLORS.accent : COLORS.blue}
            />
            <Text
              x={x + 187}
              y={606}
              anchor="middle"
              size={23}
              color={i === 3 ? COLORS.amber : COLORS.accent}
            >
              {where}
            </Text>
            {kind ? (
              <Arrow
                kind={kind}
                points={[
                  [x - 76, 430],
                  [x - 8, 430],
                ]}
                at={10 + i * 8}
              />
            ) : null}
          </g>
        );
      })}
      <Text x={960} y={720} anchor="middle" size={32} color={COLORS.white} weight={700}>
        Code inside the api and worker processes — not separate services
      </Text>
      <Text x={960} y={766} anchor="middle" size={24}>
        Document processing stores vectors that retrieval later reads
      </Text>
      <Legend kinds={["db", "sync", "ai"]} />
    </>
  );
};

const Band = ({ y, h, label, at }: { y: number; h: number; label: string; at: number }) => {
  const p = progress(useCurrentFrame(), at, 12);
  return (
    <g style={{ opacity: p }}>
      <rect
        x={60}
        y={y}
        width={1800}
        height={h}
        rx={18}
        fill="rgba(17,24,39,0.45)"
        stroke={COLORS.line}
        strokeWidth={2}
      />
      <Text x={90} y={y + 38} size={24} color={COLORS.accent} weight={700}>
        {label}
      </Text>
    </g>
  );
};

const Overview = () => (
  <>
    <Band y={100} h={145} label="EXPERIENCE" at={0} />
    <Band y={297} h={150} label="APPLICATION · api (FastAPI)" at={6} />
    <Band y={500} h={250} label="DATA AND PROCESSING" at={12} />
    <Band y={782} h={112} label="INTELLIGENCE" at={18} />
    <Box x={470} y={125} w={420} h={96} title="Business dashboard" at={4} size={28} />
    <Box x={1180} y={125} w={420} h={96} title="Embeddable widget" at={4} size={28} />
    <Box x={470} y={330} w={360} h={96} title="Auth and roles" at={10} size={28} />
    <Box x={900} y={330} w={400} h={96} title="Conversations" at={10} size={28} />
    <Box x={1370} y={330} w={400} h={96} title="Knowledge" at={10} size={28} />
    <Box x={470} y={530} w={360} h={88} title="PostgreSQL + pgvector" at={16} size={26} />
    <Box x={900} y={530} w={400} h={88} title="Redis" at={16} size={28} />
    <Box x={1370} y={530} w={400} h={88} title="Object storage" at={16} size={28} />
    <Box x={470} y={652} w={360} h={80} title="Maintenance worker" at={20} size={26} />
    <Box x={900} y={652} w={400} h={80} title="Celery worker" at={20} size={26} />
    <Box x={1370} y={652} w={400} h={80} title="Beat scheduler" at={20} size={26} />
    <Arrow
      kind="sync"
      points={[
        [620, 221],
        [620, 328],
      ]}
      at={26}
    />
    <Arrow
      kind="sse"
      points={[
        [950, 328],
        [950, 285],
        [720, 285],
        [720, 223],
      ]}
      at={30}
    />
    <Arrow
      kind="sync"
      points={[
        [1330, 221],
        [1330, 262],
        [1100, 262],
        [1100, 328],
      ]}
      at={26}
    />
    <Arrow
      kind="sse"
      points={[
        [1160, 328],
        [1160, 282],
        [1420, 282],
        [1420, 223],
      ]}
      at={30}
    />
    <Arrow
      kind="db"
      points={[
        [650, 447],
        [650, 528],
      ]}
      at={34}
    />
    <Arrow
      kind="sync"
      points={[
        [1100, 447],
        [1100, 528],
      ]}
      at={36}
    />
    <Arrow
      kind="obj"
      points={[
        [1570, 447],
        [1570, 528],
      ]}
      at={38}
    />
    <Arrow
      kind="job"
      points={[
        [1100, 620],
        [1100, 650],
      ]}
      at={42}
    />
    <Arrow
      kind="job"
      points={[
        [900, 590],
        [865, 590],
        [865, 692],
        [832, 692],
      ]}
      at={42}
    />
    <Arrow
      kind="job"
      points={[
        [1370, 692],
        [1335, 692],
        [1335, 590],
        [1302, 590],
      ]}
      at={42}
    />
    {["Processing", "Retrieval", "Prompt", "Providers"].map((title, i) => (
      <g key={title}>
        <Box
          x={470 + i * 335}
          y={800}
          w={280}
          h={76}
          title={title}
          at={24}
          size={26}
          color={i === 3 ? COLORS.accent : COLORS.blue}
        />
        {i ? (
          <Arrow
            kind={i === 3 ? "ai" : "sync"}
            points={[
              [470 + i * 335 - 52, 838],
              [470 + i * 335 - 6, 838],
            ]}
            at={46}
          />
        ) : null}
      </g>
    ))}
    <Text x={90} y={856} size={19}>
      inside api + worker
    </Text>
    <Legend kinds={["sync", "sse", "job", "db", "obj", "ai"]} y={922} />
  </>
);

const VIEWS: { title: string; body: () => ReactNode }[] = [
  { title: "1 · Experience layer", body: Experience },
  { title: "2 · Application layer", body: Application },
  { title: "3 · Data and processing layer", body: DataLayer },
  { title: "4 · Intelligence layer", body: Intelligence },
  { title: "", body: Overview },
];

/** One view: a focused layer (0–3) or the complete system (4). */
export const ArchitectureView = ({ layer }: { layer: LayerId }) => {
  const frame = useCurrentFrame();
  const { title, body: Body } = VIEWS[layer]!;
  return (
    <AbsoluteFill style={{ opacity: progress(frame, 0, 10), backgroundColor: COLORS.background }}>
      <svg width={1920} height={1080} viewBox="0 0 1920 1080" fontFamily={SANS}>
        <defs>
          {Object.entries(KINDS).map(([kind, { color }]) => (
            <marker
              key={kind}
              id={`arch-${kind}`}
              viewBox="0 0 10 10"
              refX={8}
              refY={5}
              markerWidth={5}
              markerHeight={5}
              orient="auto-start-reverse"
            >
              <path d="M0 0L10 5L0 10z" fill={color} />
            </marker>
          ))}
        </defs>
        {title ? (
          <Text x={96} y={140} size={46} color={COLORS.white} weight={700}>
            {title}
          </Text>
        ) : null}
        <Body />
      </svg>
    </AbsoluteFill>
  );
};

/** All four layers in turn, then the whole. `starts` holds the five phase start frames. */
export const LayeredArchitecture = ({ starts, total }: { starts: number[]; total: number }) => (
  <>
    {starts.map((from, index) => (
      <Sequence key={from} from={from} durationInFrames={(starts[index + 1] ?? total) - from + 10}>
        <ArchitectureView layer={index as LayerId} />
      </Sequence>
    ))}
  </>
);
