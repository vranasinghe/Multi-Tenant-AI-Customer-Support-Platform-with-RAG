import type { FC } from "react";
import { Sequence } from "remotion";

import { BigScreen } from "../../components/BigScreen";
import { SceneShell } from "../../components/SceneShell";
import type { SceneProps } from "../../compositions/TimedVideo";
import { Labels } from "./shared";

const MAIN = { x: 320, y: 0, w: 1600 };

export const SetUp: FC<SceneProps> = () => (
  <SceneShell>
    <Sequence durationInFrames={130}>
      <BigScreen
        clip="R01-sign-in"
        caption="Owner signs in (fictional account)"
        label="Sign in"
        segments={[{ from: 5, frames: 120, rate: 1.6 }]}
        crop={{ x: 0, y: 0, w: 1920 }}
      />
    </Sequence>
    <Sequence from={120} durationInFrames={100}>
      <BigScreen
        clip="R02-dashboard"
        caption="A new organization"
        label="Organization dashboard"
        segments={[{ from: 1, frames: 90, rate: 1 }]}
        crop={{ x: 0, y: 0, w: 1920 }}
        to={{ x: 320, y: 0, w: 1600 }}
      />
    </Sequence>
    <Sequence from={210} durationInFrames={280}>
      {/* The recording's model step is cut out. */}
      <BigScreen
        clip="R03-create-chatbot"
        caption="Create-chatbot wizard · sped up, some steps cut"
        label="Create a chatbot"
        segments={[
          { from: 4, frames: 90, rate: 2.5 },
          { from: 12, frames: 57, rate: 1 },
          { from: 14, frames: 63, rate: 2 },
          { from: 26.4, frames: 60, rate: 1 },
        ]}
        crop={{ x: 0, y: 0, w: 1920 }}
      />
    </Sequence>
    <Sequence from={480} durationInFrames={160}>
      <BigScreen
        clip="R04-upload-and-process"
        caption="Queued → Processing → Ready"
        label="Background document processing"
        segments={[{ from: 3.3, frames: 150, rate: 1 }]}
        crop={{ x: 320, y: 220, w: 1480 }}
        to={{ x: 420, y: 440, w: 1100 }}
        moveFrames={50}
      />
    </Sequence>
    <Sequence from={630} durationInFrames={100}>
      <BigScreen
        clip="R04-upload-and-process"
        caption="The passages produced from the file"
        label="Inspect passages"
        segments={[{ from: 11, frames: 90, rate: 1 }]}
        crop={MAIN}
      />
    </Sequence>
    <Sequence from={720} durationInFrames={130}>
      <BigScreen
        clip="R05-retrieval-test"
        caption="Which passages a question retrieves"
        label="Retrieval test"
        segments={[{ from: 12, frames: 120, rate: 0.9 }]}
        crop={MAIN}
        to={{ x: 420, y: 230, w: 1300 }}
      />
    </Sequence>
    <Sequence from={840}>
      <BigScreen
        clip="R06-website-source-guard"
        caption="A private network address is submitted"
        label="The crawler refuses it"
        labelAt="top"
        segments={[{ from: 13, frames: 90, rate: 1 }]}
        crop={{ x: 340, y: 130, w: 1280 }}
        to={{ x: 380, y: 210, w: 1150 }}
      />
    </Sequence>
    <Labels kind="footage" demo />
  </SceneShell>
);

/** Both crops stay above the token and cost line of the playground. */
export const Ask: FC<SceneProps> = () => (
  <SceneShell>
    <Sequence durationInFrames={430}>
      <BigScreen
        clip="R07-playground"
        caption="Playground: the fixed demo reply and its source"
        label="Numbered citation · reply is a fixed sentence"
        labelAt="top"
        width={1600}
        height={522}
        segments={[{ from: 12, frames: 420, rate: 0.5 }]}
        crop={{ x: 330, y: 140, w: 1340 }}
        to={{ x: 436, y: 224, w: 1100 }}
        moveAt={40}
        moveFrames={50}
        highlights={[{ x: 492, y: 529, w: 278, h: 33, at: 150 }]}
      />
    </Sequence>
    <Sequence from={420}>
      <BigScreen
        clip="R07-playground"
        caption="An unrelated question"
        label="Fallback: insufficient evidence"
        labelAt="top"
        width={1600}
        height={522}
        segments={[{ from: 26.5, frames: 210, rate: 0.55 }]}
        crop={{ x: 420, y: 280, w: 1100 }}
      />
    </Sequence>
    <Labels kind="footage" demo />
  </SceneShell>
);

export const Customers: FC<SceneProps> = () => (
  <SceneShell>
    <Sequence durationInFrames={130}>
      <BigScreen
        clip="R08-activate-and-install"
        caption="Allowed website origins (keys and proofs blurred)"
        label="Verify the website’s origin"
        segments={[{ from: 18.5, frames: 120, rate: 0.8 }]}
        crop={{ x: 420, y: 370, w: 1060 }}
      />
    </Sequence>
    <Sequence from={120} durationInFrames={220}>
      <BigScreen
        clip="R09-customer-widget"
        caption="A visitor on a fictional store"
        label="Customer widget · demo reply"
        segments={[{ from: 10, frames: 210, rate: 1 }]}
        crop={{ x: 0, y: 0, w: 1920 }}
        to={{ x: 840, y: 310, w: 1060 }}
        moveFrames={60}
        highlights={[{ x: 1420, y: 674, w: 258, h: 22, at: 100 }]}
      />
    </Sequence>
    <Sequence from={330} durationInFrames={160}>
      <BigScreen
        clip="R12-inbox"
        caption="The team marks it resolved"
        label="Conversation inbox"
        segments={[{ from: 6, frames: 150, rate: 1 }]}
        crop={{ x: 380, y: 0, w: 1360 }}
      />
    </Sequence>
    <Sequence from={480}>
      {/* Only the first metric row: the rows below hold fixture cost and token figures. */}
      <BigScreen
        clip="R13-analytics"
        caption="Analytics from stored events"
        label="Synthetic demo data · “grounded” means a citation was stored"
        labelAt="top"
        width={1600}
        height={400}
        segments={[{ from: 6, frames: 90, rate: 0 }]}
        crop={{ x: 420, y: 90, w: 1420 }}
      />
    </Sequence>
    <Labels kind="footage" demo />
  </SceneShell>
);
