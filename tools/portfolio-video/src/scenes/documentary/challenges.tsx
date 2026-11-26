import type { FC, ReactNode } from "react";
import { Sequence, useCurrentFrame } from "remotion";

import { progress, useRise } from "../../animations";
import { ApplicationWindow } from "../../components/ApplicationWindow";
import { ArtifactExcerpt, CodeExcerpt } from "../../components/Evidence";
import type { EvidenceKind } from "../../components/EvidenceLabel";
import { ScreenRecording } from "../../components/ScreenRecording";
import { TechnicalDiagram, type ViewBox } from "../../components/TechnicalDiagram";
import type { SceneProps } from "../../compositions/TimedVideo";
import { COLORS, SANS } from "../../styles/theme";
import { Labels, Note, Shell, steps } from "./shared";

// Every statement here comes from the AUD and stabilization reports in docs/mvp-improvement and
// the project fact check (§4). Change a statement only when its source changes.

const ROWS = [
  { name: "Problem", color: COLORS.red },
  { name: "Root cause", color: COLORS.amber },
  { name: "Implementation", color: COLORS.accent },
  { name: "Validation", color: COLORS.green },
  { name: "Remaining limitation", color: COLORS.amber },
] as const;

/** Where each row appears, as a share of the scene. */
const ROW_AT = [0.02, 0.17, 0.34, 0.55, 0.75];

const PANEL = { left: 696, top: 104, width: 1176, height: 800 };

type View = {
  /** Share of the scene at which this evidence takes over the right panel. */
  at: number;
  kind: EvidenceKind;
  node: (frames: number) => ReactNode;
};

type Challenge = {
  number: number;
  title: string;
  rows: [string, string, string, string, string];
  views: View[];
};

type Box = ViewBox;

/** A diagram region shown at its own aspect ratio, so nothing outside the region is visible. */
const Region = ({ file, box, reveal }: { file: string; box: Box; reveal: number[] }) => {
  const scale = Math.min(PANEL.width / box[2], PANEL.height / box[3]);
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: COLORS.background,
      }}
    >
      <TechnicalDiagram
        file={file}
        reveal={reveal}
        width={box[2] * scale}
        height={box[3] * scale}
        viewBox={box}
      />
    </div>
  );
};

/** One region, then optionally a second one: each holds whole elements, with a cut between. */
const diagram = (at: number, file: string, first: Box, second?: Box): View => ({
  at,
  kind: "diagram",
  node: (frames) => (
    <>
      <Region file={file} box={first} reveal={steps(14, 6, Math.max(8, Math.floor(frames / 14)))} />
      {second ? (
        <Sequence from={Math.floor(frames * 0.5)} layout="none">
          <Region file={file} box={second} reveal={steps(14, -40, 0)} />
        </Sequence>
      ) : null}
    </>
  ),
});

const code = (at: number, id: Parameters<typeof CodeExcerpt>[0]["id"]): View => ({
  at,
  kind: "stored",
  node: () => (
    <div style={{ display: "flex", alignItems: "center", height: PANEL.height }}>
      <CodeExcerpt id={id} width={PANEL.width} at={4} />
    </div>
  ),
});

type ArtifactId = Parameters<typeof ArtifactExcerpt>[0]["id"];

const artifacts = (at: number, ids: ArtifactId[], note?: string): View => ({
  at,
  kind: "stored",
  node: () => (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 22,
        height: PANEL.height,
      }}
    >
      {ids.map((id, i) => (
        <ArtifactExcerpt key={id} id={id} width={PANEL.width} at={4 + i * 24} />
      ))}
      {note ? <Note at={30}>{note}</Note> : null}
    </div>
  ),
});

const footage = (
  at: number,
  clip: string,
  caption: string,
  from: number,
  rate: number,
  crop: { x: number; y: number; w: number },
): View => ({
  at,
  kind: "footage",
  node: (frames) => (
    <div style={{ paddingTop: 50 }}>
      <ApplicationWindow width={PANEL.width} height={662} caption={caption}>
        <ScreenRecording
          clip={clip}
          segments={[{ from, frames, rate }]}
          width={PANEL.width}
          height={662}
          crop={crop}
        />
      </ApplicationWindow>
    </div>
  ),
});

const CHALLENGES: Record<string, Challenge> = {
  "6.1": {
    number: 1,
    title: "Connection pool starvation",
    rows: [
      "10 concurrent chats → 10 × HTTP 500 after 30 s waits.",
      "Each request held its sign-in database session while opening a second. Pool: 5 + 5.",
      "Release early, short transactions, no connection held while streaming, bounded admission.",
      "100 concurrent: 67 served, 33 controlled rejections, 0 unexpected failures.",
      "Offline provider on one laptop. Not production capacity.",
    ],
    views: [
      diagram(0, "D05-pool-starvation.svg", [60, 180, 1300, 820], [690, 180, 1170, 720]),
      diagram(0.32, "D06-admission-control.svg", [80, 300, 1160, 420], [80, 290, 1760, 640]),
      code(0.55, "pool"),
      artifacts(0.76, ["capacity"], "Final local run · served P95 1,682 ms"),
    ],
  },
  "6.2": {
    number: 2,
    title: "Citation provenance",
    rows: [
      "A source cut from the prompt by the size budget could still be cited.",
      "Citations were checked against the selected passages, not the rendered ones.",
      "One renderer returns the sources actually shown; markers are checked across stream chunks.",
      "The original failing test passes, with 32 new tests.",
      "Provenance only: support for a sentence is not verified.",
    ],
    views: [
      diagram(0, "D07-citation-provenance.svg", [60, 180, 1300, 570], [860, 180, 1000, 760]),
      code(0.5, "citation"),
    ],
  },
  "6.3": {
    number: 3,
    title: "Provider transport security",
    rows: [
      "Production settings accepted a plain HTTP embedding endpoint.",
      "No transport rule was applied to provider addresses.",
      "HTTPS with certificate verification; redirects refused; environment proxies ignored.",
      "159 new transport tests; deliberate breaks were caught.",
      "No real provider endpoint has been exercised.",
    ],
    views: [
      code(0, "transport"),
      artifacts(0.55, ["mutantsTransport"], "Fix removed on purpose → tests fail"),
    ],
  },
  "6.4": {
    number: 4,
    title: "Trusted proxy policy",
    rows: [
      "A client could rewrite its address: 25 logins with forged headers drew no 429.",
      "The server trusted forwarding headers from every peer.",
      "No proxy is trusted unless listed; unsafe values stop startup.",
      "197 unit cases and 17 runtime checks pass.",
      "The real production ingress is unverified.",
    ],
    views: [code(0, "proxy"), artifacts(0.55, ["proxyTests", "mutantsProxy"])],
  },
  "6.5": {
    number: 5,
    title: "Parser resource containment",
    rows: [
      "A hostile document could tie up a worker.",
      "Parsing ran inside the long-lived worker with no time or memory limit.",
      "Fresh process per document: wall 60 s, CPU 30 s, 512 MiB, 32 MiB result.",
      "100 new tests; real workers killed and restarted.",
      "Not a sandbox: same user, files and network. A .docx over about 40 MiB of XML now fails.",
    ],
    views: [diagram(0, "D04-celery-workers.svg", [880, 200, 620, 400]), code(0.45, "parser")],
  },
  "6.6": {
    number: 6,
    title: "Worker recovery and attempt fencing",
    rows: [
      "A superseded job could resume and publish over newer work.",
      "A claim did not identify which attempt owned the job.",
      "Every claim carries an attempt number; stale attempts change nothing.",
      "Killed workers recovered: 30.7 s and 32.2 s, shortened test intervals, 40 s bound.",
      "With default settings recovery can take about 17 minutes.",
    ],
    views: [
      code(0, "fencing"),
      artifacts(0.55, ["hardLimit", "workerRestart"], "Shortened test intervals"),
    ],
  },
  "6.7": {
    number: 7,
    title: "Object storage consistency",
    rows: [
      "A stale crawl could overwrite newer stored pages. Found during the parser work.",
      "One fixed object key per page, written outside any transaction.",
      "New key per write, published only by the owning attempt; unused uploads reclaimed.",
      "13 of 20 new tests failed before; 20 of 20 pass after.",
      "Local object storage only; no AWS S3 or production host.",
    ],
    views: [
      diagram(0, "D08-immutable-storage.svg", [60, 200, 1356, 680], [520, 200, 1340, 680]),
      code(0.55, "storage"),
    ],
  },
  "6.8": {
    number: 8,
    title: "Pagination and stale state",
    rows: [
      "Only the newest 200 messages showed; a bad cursor returned page one; data could be stale.",
      "No transcript paging, unchecked cursors, screen state kept across organizations.",
      "Scoped, validated cursors; older messages on request; reset on organization change.",
      "26 new backend tests; removing the cursor scope is caught.",
      "Pages are not a snapshot: a conversation can be missed until refresh.",
    ],
    views: [
      footage(0, "R12-inbox", "Conversation inbox · fictional data", 10.9, 0.3, {
        x: 320,
        y: 0,
        w: 1600,
      }),
      code(0.34, "inbox"),
      artifacts(0.62, ["cursorMutant"], "Fix removed on purpose → test fails"),
    ],
  },
  "6.9": {
    number: 9,
    title: "Widget lifecycle and public privacy",
    rows: [
      "Installing twice broke it; nothing removed it; visitors received internal usage fields.",
      "No shared instance registry or destroy; the dashboard response shape was reused.",
      "Page-wide registry, destroy(), and a separate public view of messages.",
      "Loader 5,248 gzip bytes of a 10,240 budget; removing de-duplication is caught.",
      "Tested in Chrome with localhost origins only.",
    ],
    views: [
      diagram(0, "D09-widget-lifecycle.svg", [60, 170, 1364, 600], [940, 170, 920, 600]),
      // Ends before the test harness mounts an explicit second instance.
      footage(
        0.34,
        "R10-widget-lifecycle",
        "Test harness page, not part of the product",
        2.5,
        0.9,
        {
          x: 0,
          y: 0,
          w: 1280,
        },
      ),
      code(0.55, "widget"),
      artifacts(0.78, ["widgetDedup", "web"]),
    ],
  },
  "6.10": {
    number: 10,
    title: "Scheduler and maintenance reliability",
    rows: [
      "Recovery shared the busy ingestion workers; the health check did not check scheduling.",
      "One shared queue; health meant only that a process was running.",
      "Own queue and worker; healthy means tasks are being accepted.",
      "Recovery ran in 1.7 s with both ingestion slots busy (bound 15 s, test interval).",
      "One earlier scheduler crash is unexplained and not reproduced.",
    ],
    views: [code(0, "scheduler"), artifacts(0.55, ["busySlots"])],
  },
  "6.11": {
    number: 11,
    title: "Backup and restore",
    rows: [
      "A backup is unproven until it has been restored.",
      "The rehearsal found the restored database had regained DELETE permissions.",
      "Restore fixed; data fingerprints, counts, policies and permissions are compared.",
      "Local rehearsal passed: backup 3 s, restore and verify 25 s.",
      "Tiny synthetic data. No off-site copies, alerting or production-sized test.",
    ],
    views: [
      diagram(0, "D13-backup-restore.svg", [60, 220, 940, 500], [980, 220, 880, 500]),
      code(0.45, "backup"),
      artifacts(0.68, ["restore", "restoreApp"]),
    ],
  },
};

const Row = ({ index, text, at }: { index: number; text: string; at: number }) => {
  const style = useRise(at);
  const { name, color } = ROWS[index]!;
  return (
    <div style={style}>
      <div style={{ color, fontSize: 18, fontWeight: 700, letterSpacing: 1 }}>
        {name.toUpperCase()}
      </div>
      <div style={{ color: COLORS.white, fontSize: 23, lineHeight: 1.35, marginTop: 5 }}>
        {text}
      </div>
    </div>
  );
};

const Fade = ({ children }: { children: ReactNode }) => (
  <div
    style={{
      position: "absolute",
      ...PANEL,
      opacity: progress(useCurrentFrame(), 0, 9),
      background: COLORS.background,
    }}
  >
    {children}
  </div>
);

const ChallengeScene = ({ challenge, frames }: { challenge: Challenge; frames: number }) => {
  const title = useRise(2);
  const { views, rows, number } = challenge;
  return (
    <Shell>
      <div
        style={{
          position: "absolute",
          left: 48,
          top: 104,
          width: 612,
          display: "flex",
          flexDirection: "column",
          gap: 20,
          fontFamily: SANS,
        }}
      >
        <div style={title}>
          <div style={{ color: COLORS.muted, fontSize: 20 }}>
            Engineering problem {number} of 11
          </div>
          <div style={{ color: COLORS.white, fontSize: 36, fontWeight: 700, lineHeight: 1.2 }}>
            {challenge.title}
          </div>
        </div>
        {rows.map((text, i) => (
          <Row key={text} index={i} text={text} at={Math.round(frames * ROW_AT[i]!)} />
        ))}
      </div>
      {views.map((view, i) => {
        const from = Math.round(frames * view.at);
        const length = Math.round(frames * (views[i + 1]?.at ?? 1)) - from;
        const last = i === views.length - 1;
        return (
          <Sequence key={view.at} from={from} durationInFrames={last ? length + 8 : length + 9}>
            <Fade>{view.node(length)}</Fade>
            <Labels kind={view.kind} />
          </Sequence>
        );
      })}
      <Sequence from={Math.round(frames * ROW_AT[3]!)}>
        <Labels local />
      </Sequence>
      {number === 8 ? (
        <Sequence durationInFrames={Math.round(frames * views[1]!.at)}>
          <Labels demo />
        </Sequence>
      ) : null}
    </Shell>
  );
};

export const challengeScenes: Record<string, FC<SceneProps>> = Object.fromEntries(
  Object.entries(CHALLENGES).map(([id, challenge]) => {
    const Scene: FC<SceneProps> = ({ segment }) => (
      <ChallengeScene challenge={challenge} frames={segment.frames} />
    );
    return [id, Scene];
  }),
);

export const ProblemList: FC<SceneProps> = () => (
  <Shell>
    <div style={{ position: "absolute", top: 130, left: 240, width: 1440, fontFamily: SANS }}>
      <Note at={40} color={COLORS.white} size={44}>
        Problems the passing tests had missed, and what fixing them uncovered
      </Note>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gridTemplateRows: "repeat(6, 88px)",
          gridAutoFlow: "column",
          columnGap: 48,
          rowGap: 20,
          marginTop: 56,
        }}
      >
        {Object.values(CHALLENGES).map((challenge, i) => (
          <ListItem
            key={challenge.title}
            number={challenge.number}
            title={challenge.title}
            at={60 + i * 18}
          />
        ))}
      </div>
    </div>
  </Shell>
);

const ListItem = ({ number, title, at }: { number: number; title: string; at: number }) => {
  const style = useRise(at);
  return (
    <div
      style={{
        ...style,
        display: "flex",
        alignItems: "center",
        gap: 22,
        padding: "0 28px",
        borderRadius: 14,
        background: COLORS.surface,
        border: `2px solid ${COLORS.line}`,
        color: COLORS.white,
        fontSize: 30,
      }}
    >
      <span style={{ color: COLORS.accent, fontWeight: 700, width: 40 }}>{number}</span>
      {title}
    </div>
  );
};
