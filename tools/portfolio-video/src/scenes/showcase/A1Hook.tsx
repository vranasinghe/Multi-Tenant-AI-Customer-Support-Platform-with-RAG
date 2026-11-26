import { useCurrentFrame } from "remotion";

import { mix, progress } from "../../animations";
import { ApplicationWindow, TITLE_BAR } from "../../components/ApplicationWindow";
import { CinematicTitle } from "../../components/CinematicTitle";
import { DemoWarning } from "../../components/DemoWarning";
import { EvidenceLabel } from "../../components/EvidenceLabel";
import { SceneShell } from "../../components/SceneShell";
import { ScreenRecording, type Crop, type Segment } from "../../components/ScreenRecording";
import { COLORS } from "../../styles/theme";

const W = 520;
const H = 293;
const TOP = 96;

const TILES: {
  clip: string;
  caption: string;
  crop: Crop;
  segments: Segment[];
  from: [number, number];
}[] = [
  {
    clip: "R15-dashboard-populated",
    caption: "Dashboard",
    crop: { x: 0, y: 0, w: 1340 },
    segments: [{ from: 2, frames: 300, rate: 0.4 }],
    from: [-70, -40],
  },
  {
    clip: "R04-upload-and-process",
    caption: "Knowledge processing",
    crop: { x: 420, y: 600, w: 853 },
    // Ends before 10.8 s, where the passages dialog opens.
    segments: [{ from: 5.8, frames: 300, rate: 0.48 }],
    from: [70, -40],
  },
  {
    clip: "R09-customer-widget",
    caption: "Customer widget",
    crop: { x: 640, y: 360, w: 1280 },
    segments: [{ from: 11, frames: 300, rate: 0.55 }],
    from: [-70, 40],
  },
  {
    clip: "R12-inbox",
    caption: "Conversation inbox",
    crop: { x: 320, y: 180, w: 1600 },
    segments: [{ from: 14.2, frames: 300, rate: 0 }],
    from: [70, 40],
  },
];

export const A1Hook = () => {
  const frame = useCurrentFrame();
  // The windows part along a divider in the second half of the line.
  const part = progress(frame, 150, 36);
  const gap = mix(14, 48, part);
  const left = (1920 - (W * 2 + gap)) / 2;
  const tileHeight = H + TITLE_BAR;
  const gridTop = TOP + (48 - gap) / 2;

  return (
    <SceneShell
      fadeIn={false}
      evidence={<EvidenceLabel kind="footage" note="Fictional business and data" />}
      warning={<DemoWarning />}
    >
      {TILES.map((tile, index) => {
        // The first window is already arriving on frame 0, so the video never opens empty.
        const p = progress(frame, index * 15 - 8, 18);
        const column = index % 2;
        const row = Math.floor(index / 2);
        return (
          <div
            key={tile.clip}
            style={{
              position: "absolute",
              left: left + column * (W + gap) + (1 - p) * tile.from[0],
              top: gridTop + row * (tileHeight + gap) + (1 - p) * tile.from[1],
              opacity: p,
            }}
          >
            <ApplicationWindow width={W} height={H} caption={tile.caption}>
              <ScreenRecording
                clip={tile.clip}
                segments={tile.segments}
                width={W}
                height={H}
                crop={tile.crop}
              />
            </ApplicationWindow>
          </div>
        );
      })}
      <div
        style={{
          position: "absolute",
          left: 960 - 1.5,
          top: gridTop,
          width: 3,
          height: (tileHeight * 2 + gap) * progress(frame, 162, 30),
          background: COLORS.blue,
          boxShadow: `0 0 16px ${COLORS.blue}`,
        }}
      />
      <div style={{ position: "absolute", left: 0, right: 0, top: 838 }}>
        <CinematicTitle text="Many businesses. One platform. Kept apart." at={60} size={50} />
      </div>
    </SceneShell>
  );
};
