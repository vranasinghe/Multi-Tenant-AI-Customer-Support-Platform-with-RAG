import type { FC } from "react";
import { Sequence } from "remotion";

import { useRise } from "../../animations";
import { BigScreen } from "../../components/BigScreen";
import { CodeExcerpt } from "../../components/Evidence";
import type { SceneProps } from "../../compositions/TimedVideo";
import { COLORS, SANS } from "../../styles/theme";
import { Card, Diagram, Labels, Panel, Shell } from "./shared";

const StatusCard = () => {
  const style = useRise(120);
  return (
    <div
      style={{
        ...style,
        position: "absolute",
        right: 280,
        top: 560,
        padding: "20px 30px",
        borderRadius: 14,
        background: COLORS.surface,
        border: `2px solid ${COLORS.green}`,
        fontFamily: SANS,
        fontSize: 30,
        fontWeight: 700,
        color: COLORS.white,
      }}
    >
      <div style={{ color: COLORS.muted, fontSize: 20, fontWeight: 400, marginBottom: 8 }}>
        Recorded status codes · second owner
      </div>
      <div>
        First business’s data: <span style={{ color: COLORS.amber }}>404</span>
      </div>
      <div>
        Own data: <span style={{ color: COLORS.green }}>200</span>
      </div>
    </div>
  );
};

export const TwoBusinesses: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={140}>
      <Diagram
        file="D02-tenant-isolation.svg"
        reveal={[6, 60, 70, 80, 90, 40, 100]}
        viewBox={[0, 170, 1920, 890]}
      />
      <Labels kind="diagram" />
    </Sequence>
    <Sequence from={130}>
      <BigScreen
        clip="R14-tenant-isolation"
        caption="Signed in as a second business"
        label="Another business is refused"
        segments={[
          { from: 1, frames: 90, rate: 1 },
          { from: 6, frames: 170, rate: 0.5 },
        ]}
        crop={{ x: 0, y: 0, w: 1920 }}
        to={{ x: 0, y: 0, w: 1400 }}
        moveAt={90}
        moveFrames={30}
      />
      <StatusCard />
      <Labels kind="footage" />
    </Sequence>
  </Shell>
);

export const Layers: FC<SceneProps> = () => (
  <Shell kind="diagram">
    <Diagram
      file="D02-tenant-isolation.svg"
      reveal={[0, 70, 180, 280, 390, 10, 450]}
      viewBox={[0, 170, 1920, 890]}
    />
  </Shell>
);

export const PublicBoundaries: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={340}>
      <div
        style={{
          position: "absolute",
          top: 200,
          left: 150,
          display: "grid",
          gridTemplateColumns: "790px 790px",
          gap: 40,
        }}
      >
        <Card
          at={20}
          width={790}
          title="Short-lived widget token"
          lines={["Limited to one conversation."]}
        />
        <Card
          at={80}
          width={790}
          title="Minimal public fields"
          lines={["No internal usage, token or cost data in visitor responses."]}
        />
        <Card
          at={160}
          width={790}
          title="Trusted proxies only"
          lines={["Forwarding headers are ignored unless the sender is listed."]}
        />
        <Card
          at={220}
          width={790}
          title="HTTPS AI providers"
          lines={["Redirects refused, environment proxies ignored."]}
        />
      </div>
      <Card
        at={290}
        color={COLORS.amber}
        width={1620}
        title="Tested design, not a security certification"
      />
    </Sequence>
    <Sequence from={330}>
      <Panel>
        <div style={{ position: "absolute", top: 120, left: 285 }}>
          <CodeExcerpt id="widget" width={1350} at={6} />
        </div>
      </Panel>
      <Labels kind="stored" />
    </Sequence>
  </Shell>
);
