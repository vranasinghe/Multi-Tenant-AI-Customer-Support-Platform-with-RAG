import { Img, staticFile } from "remotion";

/** The package's demo label, required on every chat, retrieval and analytics shot. */
export const DemoWarning = () => (
  <Img src={staticFile("graphics/label-demo.svg")} style={{ height: 44 }} />
);
