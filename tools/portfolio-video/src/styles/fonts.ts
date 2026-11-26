// Fonts are bundled (SIL OFL), so a render never depends on the network.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import { cancelRender, continueRender, delayRender } from "remotion";

const handle = delayRender("fonts");

Promise.all(
  [
    "400 20px Inter",
    "500 20px Inter",
    "600 20px Inter",
    "700 20px Inter",
    "400 20px 'JetBrains Mono'",
    "600 20px 'JetBrains Mono'",
  ].map((font) => document.fonts.load(font)),
)
  .then(() => continueRender(handle))
  .catch((error: unknown) => cancelRender(error));
