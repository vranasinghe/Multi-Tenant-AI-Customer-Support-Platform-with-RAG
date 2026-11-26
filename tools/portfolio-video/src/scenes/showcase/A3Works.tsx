import { Sequence } from "remotion";

import { DemoWarning } from "../../components/DemoWarning";
import { EvidenceLabel } from "../../components/EvidenceLabel";
import { LowerThird } from "../../components/LowerThird";
import { SceneShell } from "../../components/SceneShell";
import { FootageShot } from "./FootageShot";

export const A3Works = () => (
  <SceneShell
    evidence={<EvidenceLabel kind="footage" note="Fictional business and data" />}
    warning={<DemoWarning />}
  >
    <Sequence durationInFrames={218} name="Playground">
      {/* The crop ends above the token and cost line: those figures come from the offline fixture. */}
      <FootageShot
        caption="Playground: streamed demo reply with its source"
        clip="R07-playground"
        segments={[{ from: 11, frames: 210, rate: 1 }]}
        width={1600}
        height={522}
        crop={{ x: 330, y: 140, w: 1340 }}
        zoomTo={{ x: 436, y: 224, w: 1100 }}
        zoomAt={50}
        highlights={[{ x: 492, y: 529, w: 278, h: 33, at: 80 }]}
      />
    </Sequence>
    <Sequence from={210} durationInFrames={218} name="Widget">
      <FootageShot
        fadeIn
        caption="Embedded widget on a fictional store"
        clip="R09-customer-widget"
        segments={[{ from: 10.2, frames: 210, rate: 1 }]}
        width={1320}
        height={742}
        crop={{ x: 0, y: 0, w: 1920 }}
        zoomTo={{ x: 1095, y: 300, w: 825 }}
        zoomAt={42}
        zoomFrames={30}
        highlights={[{ x: 1420, y: 674, w: 258, h: 22, at: 96 }]}
      />
    </Sequence>
    <Sequence from={420} name="Inbox">
      <FootageShot
        fadeIn
        caption="Conversation inbox: stored transcript and source"
        clip="R12-inbox"
        segments={[
          { from: 12.3, frames: 51, rate: 1 },
          { from: 14.2, frames: 129, rate: 0 },
        ]}
        width={1320}
        height={742}
        crop={{ x: 320, y: 180, w: 1600 }}
        zoomTo={{ x: 410, y: 490, w: 853 }}
        zoomAt={72}
        highlights={[{ x: 456, y: 922, w: 266, h: 24, at: 104 }]}
      />
    </Sequence>
    <div style={{ position: "absolute", left: 48, top: 890 }}>
      <LowerThird text="Streaming · Sources · Inbox" at={20} />
    </div>
  </SceneShell>
);
