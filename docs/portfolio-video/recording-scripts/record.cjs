// Records the portfolio demo clips against a DISPOSABLE local QA stack.
// Usage and safety rules: README.md in this folder.
//
// It refuses to run unless the target containers use the demo LLM and hash embeddings with no
// provider key, so a recording can never make a paid model call.
"use strict";

const { createRequire } = require("module");
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");
const crypto = require("crypto");

const HERE = __dirname;
const ROOT = path.resolve(HERE, "../../..");
const { chromium } = createRequire(path.join(ROOT, "apps/web/package.json"))("@playwright/test");

const env = (name, fallback) => {
  const value = process.env[name] ?? fallback;
  if (value === undefined) {
    console.error(`Set ${name}. See README.md.`);
    process.exit(2);
  }
  return value;
};

const PROJECT = env("COMPOSE_PROJECT_NAME");
const WEB = env("WEB_URL");
const API = env("API_URL");
const MAIL = env("MAILPIT_URL");
const OUT = path.resolve(env("OUT_DIR", path.join(ROOT, "output/video/portfolio")));
const SHOP_PORT = Number(env("SHOP_PORT", "3511"));
const SHOP = `http://localhost:${SHOP_PORT}`;
// 1.25 gives 1920x1080 frames; 2.5 asks for 3840x2160 (check text sharpness and frame rate).
const SCALE = Number(env("SCALE", "1.25"));
const VIEW = { width: 1536, height: 864 };
// Optional: a public website you own. Left unset, only the refusal of a private address is shown.
const PUBLIC_SITE = process.env.PUBLIC_SITE_URL ?? "";
const DATA = path.join(ROOT, "docs/portfolio-video/assets/demo-data");

// ------------------------------------------------------------------ safety preflight
function docker(...args) {
  return execFileSync("docker", args, { encoding: "utf8" }).trim();
}

function preflight() {
  if (["ai-chatbot-saas", "acs-prod"].includes(PROJECT)) {
    throw new Error(`refusing to record against the ${PROJECT} stack`);
  }
  for (const service of ["api", "worker"]) {
    const list = JSON.parse(
      docker("inspect", `${PROJECT}-${service}-1`, "--format", "{{json .Config.Env}}"),
    );
    const get = (key) =>
      (list.find((v) => v.startsWith(`${key}=`)) ?? `${key}=`).slice(key.length + 1);
    // Report the variable name only; never its value.
    if (get("LLM_PROVIDER") !== "demo") throw new Error(`${service}: LLM_PROVIDER is not demo`);
    if (get("EMBEDDING_PROVIDER") !== "hash")
      throw new Error(`${service}: EMBEDDING_PROVIDER is not hash`);
    for (const key of ["LLM_API_KEY", "EMBEDDING_API_KEY"]) {
      if (get(key)) throw new Error(`${service}: ${key} is set`);
    }
  }
  for (const [service, url, inner] of [
    ["api", API, "8000"],
    ["web", WEB, "3000"],
  ]) {
    const published = docker("port", `${PROJECT}-${service}-1`, inner).split(":").pop();
    if (published !== new URL(url).port) {
      throw new Error(`${url} is not the ${service} of project ${PROJECT} (port ${published})`);
    }
  }
}

// ------------------------------------------------------------------ capture
const manifest = { generated_at: null, scale: SCALE, clips: [] };
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

class Studio {
  constructor(page) {
    this.page = page;
    this.cur = { x: 760, y: 430 };
    this.scene = null;
  }

  static async open(context) {
    const page = await context.newPage();
    page.setDefaultTimeout(30_000);
    const studio = new Studio(page);
    studio.cdp = await context.newCDPSession(page);
    studio.cdp.on("Page.screencastFrame", (frame) => {
      studio.cdp.send("Page.screencastFrameAck", { sessionId: frame.sessionId }).catch(() => {});
      const scene = studio.scene;
      if (!scene) return;
      const file = `${String(scene.frames.length).padStart(6, "0")}.jpg`;
      fs.writeFileSync(path.join(scene.dir, file), Buffer.from(frame.data, "base64"));
      scene.frames.push([file, Date.now() / 1000]);
    });
    return studio;
  }

  async cast() {
    await this.cdp.send("Page.stopScreencast").catch(() => {});
    await this.cdp.send("Page.startScreencast", {
      format: "jpeg",
      quality: 95,
      maxWidth: 3840,
      maxHeight: 2160,
    });
  }

  async clip(id, title, body) {
    const dir = path.join(OUT, "frames", id);
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
    this.scene = { dir, frames: [] };
    await this.cast();
    try {
      await body();
      await sleep(1500);
      await this.page.screenshot({ path: path.join(OUT, "stills", `${id}.png`) });
    } catch (error) {
      await this.page
        .screenshot({ path: path.join(OUT, "stills", `${id}-FAILED.png`) })
        .catch(() => {});
      manifest.clips.push({ id, title, result: "FAILED", error: String(error).split("\n")[0] });
      throw error;
    } finally {
      const { frames } = this.scene;
      fs.writeFileSync(
        path.join(dir, "index.json"),
        JSON.stringify({ frames, end: Date.now() / 1000 }),
      );
      this.scene = null;
    }
    manifest.clips.push({ id, title, result: "recorded" });
    console.log(`${id} recorded`);
  }

  async cursor(x, y, down = false) {
    await this.page
      .evaluate(
        ([x, y, down]) => {
          let c = document.getElementById("__cur");
          if (!c) {
            c = document.createElement("div");
            c.id = "__cur";
            Object.assign(c.style, {
              position: "fixed",
              width: "22px",
              height: "22px",
              marginLeft: "-11px",
              marginTop: "-11px",
              borderRadius: "50%",
              background: "rgba(56,189,248,.35)",
              border: "2px solid #2563EB",
              zIndex: "2147483647",
              pointerEvents: "none",
              transition: "transform .12s",
            });
          }
          const host = document.querySelector("dialog[open]") || document.body;
          if (c.parentElement !== host) host.appendChild(c);
          c.style.left = `${x}px`;
          c.style.top = `${y}px`;
          c.style.transform = down ? "scale(.65)" : "scale(1)";
        },
        [x, y, down],
      )
      .catch(() => {});
  }

  async moveTo(locator) {
    await locator.waitFor({ state: "visible" });
    await locator.evaluate((el) => {
      const r = el.getBoundingClientRect();
      if (r.top < 90 || r.bottom > innerHeight - 110) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
    await sleep(450);
    const box = await locator.boundingBox();
    const tx = box.x + Math.min(box.width / 2, 160);
    const ty = box.y + box.height / 2;
    const { x, y } = this.cur;
    for (let i = 1; i <= 18; i++) {
      const t = i / 18;
      const e = t * t * (3 - 2 * t);
      await this.cursor(x + (tx - x) * e, y + (ty - y) * e);
      await sleep(20);
    }
    this.cur = { x: tx, y: ty };
    await sleep(150);
  }

  async click(locator) {
    await this.moveTo(locator);
    await this.cursor(this.cur.x, this.cur.y, true);
    await sleep(110);
    await locator.click();
    await this.cursor(this.cur.x, this.cur.y, false);
    await sleep(600);
  }

  async type(locator, text, delay = 32) {
    await this.click(locator);
    await locator.fill("");
    await locator.pressSequentially(text, { delay });
    await sleep(450);
  }

  async go(url, hold = 1600) {
    await this.page.goto(url, { waitUntil: "networkidle" });
    await this.cast();
    await this.cursor(this.cur.x, this.cur.y);
    await sleep(hold);
  }

  async scrollThrough(hold = 1100) {
    const max = await this.page.evaluate(() => document.documentElement.scrollHeight - innerHeight);
    if (max <= 40) return;
    for (let y = 0; y < max;) {
      y = Math.min(max, y + 420);
      await this.page.evaluate((top) => scrollTo({ top, behavior: "smooth" }), y);
      await sleep(hold);
    }
    await this.page.evaluate(() => scrollTo({ top: 0, behavior: "smooth" }));
    await sleep(800);
  }
}

// ------------------------------------------------------------------ accounts and fixtures
const HEADERS = { "X-Requested-With": "platform", Origin: WEB };
const run = crypto.randomBytes(2).toString("hex");
const person = (name, orgName, local) => ({
  name,
  orgName,
  email: `${local}.${run}@example.com`,
  password: `demo-${crypto.randomBytes(12).toString("base64url")}`,
});

async function register(browser, who) {
  // Off camera: sign up through the UI, then verify with the link from the local test mailbox.
  const context = await browser.newContext({ viewport: VIEW });
  const page = await context.newPage();
  await page.goto(`${WEB}/signup`, { waitUntil: "networkidle" });
  await page.getByLabel("Your name").fill(who.name);
  await page.getByLabel("Organization name").fill(who.orgName);
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL(/\/orgs\/[0-9a-f-]{36}$/);
  who.orgPath = new URL(page.url()).pathname;

  let token = "";
  for (let i = 0; i < 40 && !token; i++) {
    const found = await (
      await fetch(`${MAIL}/api/v1/search?query=${encodeURIComponent(`to:${who.email}`)}`)
    ).json();
    if (found.messages?.length) {
      const message = await (await fetch(`${MAIL}/api/v1/message/${found.messages[0].ID}`)).json();
      token = /verify-email\?token=([A-Za-z0-9_-]+)/.exec(message.Text)?.[1] ?? "";
    }
    if (!token) await sleep(500);
  }
  if (!token) throw new Error("no verification email in the local mailbox");
  const verified = await page.request.post(`${API}/api/v1/auth/verify-email`, {
    data: { token },
    headers: HEADERS,
  });
  if (verified.status() !== 200) throw new Error(`verification failed: ${verified.status()}`);
  await context.close();
}

function shopPage(botKey) {
  const key = JSON.stringify(botKey);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Northwind Outdoor (fictional)</title><style>
body{margin:0;font-family:Segoe UI,system-ui,sans-serif;background:#f6f5f0;color:#1d2b25}
header{display:flex;justify-content:space-between;gap:12px;padding:20px 40px;background:#fff;border-bottom:1px solid #e3e1d8}
header b{font-size:21px;color:#0f766e}.hero{margin:32px 40px;padding:52px 40px;border-radius:18px;background:linear-gradient(135deg,#0f766e,#14423b);color:#fff}
.hero h1{font-size:38px;margin:0 0 10px}.note{margin:0 40px;color:#5b6b64;font-size:14px}
</style></head><body><header><b>Northwind Outdoor</b><span>Fictional demonstration store</span></header>
<section class="hero"><h1>Gear for the long way round</h1><p>Questions about returns or warranty? Ask our assistant.</p></section>
<p class="note">Synthetic website used to record the widget. No real business, products or customers.</p>
<script async src="${API}/widget/v1/loader.js" data-bot-key=${key}></script></body></html>`;
}

function harnessPage(botKey) {
  const key = JSON.stringify(botKey);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Widget lifecycle test harness</title><style>
body{margin:0;padding:48px;font-family:Segoe UI,system-ui,sans-serif;background:#080C14;color:#fff}
h1{margin:0 0 8px;font-size:30px}p{color:#94A3B8;max-width:640px}
button{font:inherit;margin:0 10px 10px 0;padding:12px 18px;border-radius:10px;border:1px solid #2563EB;background:#111827;color:#fff;cursor:pointer}
output{display:block;margin-top:22px;font-size:22px}output b{color:#38BDF8}
</style></head><body><h1>Widget lifecycle test harness</h1>
<p>A test page, not part of the product. The counter reads the number of widget frames in this page.</p>
<button id="again">Add the same script tag again</button>
<button id="second">Mount a second instance</button>
<button id="destroy">Destroy default instance</button>
<button id="mount">Mount default again</button>
<output>Widget frames on this page: <b id="count">0</b></output>
<script>
const KEY=${key}, SRC="${API}/widget/v1/loader.js";
function tag(instance){const s=document.createElement("script");s.src=SRC;s.dataset.botKey=KEY;
if(instance)s.dataset.instanceKey=instance;document.body.append(s);}
again.onclick=()=>tag();second.onclick=()=>tag("footer");
destroy.onclick=()=>window.AcsChat.destroy({botKey:KEY});
mount.onclick=()=>window.AcsChat.mount({botKey:KEY});
setInterval(()=>{count.textContent=document.querySelectorAll('iframe[title="Customer support chat"]').length},100);
tag();
</script></body></html>`;
}

const widgetFrame = (page, key, nth = 0) =>
  page.frameLocator(`iframe[src*="/widget/frame/${key}"]`).nth(nth);

async function ready(page, base, filename) {
  for (let i = 0; i < 120; i++) {
    const list = await (await page.request.get(`${base}/documents`)).json();
    const doc = (list.data ?? []).find((d) => d.title === filename || d.filename === filename);
    if (doc?.status === "ready") return;
    if (doc?.status === "failed") throw new Error(`${filename} failed to index`);
    await sleep(500);
  }
  throw new Error(`${filename} did not become ready`);
}

// ------------------------------------------------------------------ the recording
(async () => {
  preflight();
  console.log("preflight ok: demo LLM, hash embeddings, no provider key");
  fs.mkdirSync(path.join(OUT, "stills"), { recursive: true });

  const northwind = person("Maya Perera", "Northwind Outdoor", "maya");
  const bluepeak = person("Ravi Silva", "Bluepeak Fitness", "ravi");
  let botKey = "";
  const server = http.createServer((request, response) => {
    response.setHeader("Content-Type", "text/html; charset=utf-8");
    response.end(request.url.startsWith("/harness") ? harnessPage(botKey) : shopPage(botKey));
  });
  await new Promise((ok, bad) => {
    server.once("error", bad);
    server.listen(SHOP_PORT, "127.0.0.1", ok);
  });

  const browser = await chromium.launch({
    channel: process.env.E2E_BROWSER_CHANNEL ?? "chrome",
    args: [`--force-device-scale-factor=${SCALE}`],
  });
  const newContext = (viewport = VIEW) =>
    browser.newContext({
      viewport,
      deviceScaleFactor: SCALE,
      permissions: ["clipboard-read", "clipboard-write"],
    });

  try {
    await register(browser, northwind);
    await register(browser, bluepeak);

    const context = await newContext();
    const studio = await Studio.open(context);
    const { page } = studio;
    const org = () => `${WEB}${northwind.orgPath}`;

    await studio.clip("R01-sign-in", "Sign in", async () => {
      await studio.go(`${WEB}/login`);
      await studio.type(page.getByLabel("Email"), northwind.email, 24);
      await studio.type(page.getByLabel("Password"), northwind.password, 14);
      await studio.click(page.getByRole("button", { name: "Sign in" }));
      await page.waitForURL(/\/(orgs|dashboard)/);
    });

    await studio.clip("R02-dashboard", "Business dashboard", async () => {
      await studio.go(org(), 3200);
      await studio.scrollThrough();
    });

    let chatbotPath = "";
    await studio.clip("R03-create-chatbot", "Create and configure a chatbot", async () => {
      await studio.go(`${org()}/chatbots/new`);
      await studio.type(page.getByLabel("Name"), "Northwind Assistant");
      await studio.type(
        page.getByLabel("Description"),
        "Answers questions about returns and warranty.",
        18,
      );
      await studio.click(page.getByRole("button", { name: "Continue" }));
      await studio.click(page.getByRole("button", { name: "Continue" }));
      await studio.type(page.getByLabel("Brand color", { exact: true }), "#0F766E", 60);
      await studio.click(page.getByRole("button", { name: "Continue" }));
      await studio.click(page.getByRole("button", { name: "Continue" }));
      await studio.scrollThrough(800);
      await studio.click(page.getByRole("button", { name: "Create chatbot" }));
      await page.waitForURL(/\/chatbots\/[0-9a-f-]{36}$/);
      chatbotPath = new URL(page.url()).pathname;
      await sleep(1500);
    });
    const chatbotId = chatbotPath.split("/").pop();
    const base = `${API}/api/v1${northwind.orgPath}/chatbots/${chatbotId}`;

    await studio.clip(
      "R04-upload-and-process",
      "Upload documents and processing lifecycle",
      async () => {
        await studio.go(`${org()}/knowledge`);
        const chooser = page.getByLabel("Choose files to upload");
        await chooser.setInputFiles([
          path.join(DATA, "northwind-returns-and-shipping.txt"),
          path.join(DATA, "northwind-warranty-and-care.txt"),
        ]);
        for (const name of [
          "northwind-returns-and-shipping.txt",
          "northwind-warranty-and-care.txt",
        ]) {
          await page
            .getByRole("row", { name: new RegExp(name) })
            .getByText("Ready")
            .waitFor({ timeout: 60_000 });
        }
        await sleep(2000);
        await studio.click(
          page
            .getByRole("row", { name: /returns-and-shipping/ })
            .getByRole("button", { name: /Passages/ }),
        );
        await page.getByRole("dialog").waitFor();
        await sleep(2500);
        await page.keyboard.press("Escape");
      },
    );

    await studio.clip("R05-retrieval-test", "Retrieval tester", async () => {
      await studio.go(`${org()}/knowledge`);
      await studio.click(page.getByRole("tab", { name: "Test retrieval" }));
      await studio.type(
        page.getByLabel("Question"),
        "How many days are returns allowed after delivery?",
      );
      await studio.click(page.getByRole("button", { name: "Search" }));
      await page
        .getByRole("region", { name: "Search results" })
        .getByText(/within thirty days/)
        .waitFor();
      await sleep(3500);
    });

    await studio.clip(
      "R06-website-source-guard",
      "Website source and private-address refusal",
      async () => {
        await studio.go(`${org()}/knowledge`);
        await studio.click(page.getByRole("tab", { name: "Websites" }));
        await studio.type(
          page.getByLabel("Starting address"),
          "http://169.254.169.254/latest/meta-data/",
          22,
        );
        await studio.click(page.getByLabel(/I own this website/));
        await studio.click(page.getByRole("button", { name: "Add website" }));
        await page
          .getByRole("alert")
          .filter({ hasText: /Only public websites/ })
          .first()
          .waitFor();
        await sleep(3000);
        if (PUBLIC_SITE) {
          await studio.type(page.getByLabel("Starting address"), PUBLIC_SITE, 30);
          await studio.click(page.getByRole("button", { name: "Add website" }));
          await sleep(12_000);
        }
      },
    );

    await studio.clip("R07-playground", "Playground answer, citation and fallback", async () => {
      await studio.go(`${org()}/chatbots/${chatbotId}`);
      await studio.click(page.getByRole("tab", { name: "Test chat" }));
      await studio.type(
        page.getByLabel("Customer question"),
        "Are returns allowed within thirty days of delivery?",
      );
      await studio.click(page.getByRole("button", { name: "Send question" }));
      // The canned text proves the offline fixture answered; anything else stops the recording.
      await page.getByText(/Demo response: this confirms/).waitFor();
      await page
        .getByRole("log")
        .getByText(/northwind-returns/)
        .first()
        .waitFor();
      await sleep(4000);
      await studio.click(page.getByRole("button", { name: "Mark answer helpful" }));
      await studio.click(page.getByRole("button", { name: "New conversation" }));
      await studio.type(
        page.getByLabel("Customer question"),
        "Explain astrophysics quasars galaxies?",
      );
      await studio.click(page.getByRole("button", { name: "Send question" }));
      await page.getByText("Insufficient evidence").waitFor();
      await sleep(3000);
    });

    const bot = await (await page.request.get(base)).json();
    botKey = bot.public_key;

    await studio.clip(
      "R08-activate-and-install",
      "Activate, verify origin, installation script",
      async () => {
        await studio.go(`${org()}/chatbots/${chatbotId}`);
        await studio.moveTo(page.getByLabel("Status"));
        await page.getByLabel("Status").selectOption("active");
        await sleep(1800);
        // Mask identifiers (public key, the snippet that holds it, DNS proofs) BEFORE the tab opens:
        // adding the style afterwards leaves them readable for the first frames.
        await page.addStyleTag({
          content:
            "#public-widget-key,#widget-snippet,section[aria-labelledby='allowed-origins'] code{filter:blur(5px)}",
        });
        await studio.click(page.getByRole("tab", { name: "Install", exact: true }));
        for (const origin of [SHOP, WEB]) {
          await studio.type(page.getByRole("textbox", { name: "Website origin" }), origin, 26);
          await studio.click(page.getByRole("button", { name: "Add origin" }));
          const item = page.getByRole("listitem").filter({ hasText: origin });
          await studio.click(item.getByRole("button", { name: "Verify origin" }));
          await item.getByText(/Verified until/).waitFor();
        }
        await studio.click(page.getByRole("button", { name: "Copy installation script" }));
        // The preview first loaded before this origin was verified: reload it, then open it.
        await studio.click(page.getByRole("button", { name: "Reload live preview" }));
        const preview = page.frameLocator('iframe[title="Live widget preview"]');
        await studio.click(preview.getByRole("button", { name: "Open support chat" }));
        await preview.getByLabel("Your question").waitFor();
        await sleep(2500);
      },
    );

    await studio.clip(
      "R09-customer-widget",
      "Customer asks through the embedded widget",
      async () => {
        await studio.go(SHOP, 2200);
        const widget = widgetFrame(page, botKey);
        await studio.click(widget.getByRole("button", { name: "Open support chat" }));
        await studio.type(
          widget.getByLabel("Your question"),
          "Are returns allowed within thirty days of delivery?",
        );
        await studio.click(widget.getByRole("button", { name: "Send", exact: true }));
        await widget
          .getByRole("log")
          .getByText(/Demo response/)
          .waitFor();
        await widget.getByRole("button", { name: "Helpful", exact: true }).waitFor();
        await sleep(3500);
        await studio.click(widget.getByRole("button", { name: "Helpful", exact: true }));
        await studio.go(SHOP, 1500); // reload: the anonymous conversation resumes
        await studio.click(widget.getByRole("button", { name: "Open support chat" }));
        await widget
          .getByRole("log")
          .getByText(/thirty days of delivery\?/)
          .waitFor();
        await sleep(3000);
      },
    );

    await studio.clip(
      "R10-widget-lifecycle",
      "Duplicate install, instances, teardown",
      async () => {
        await studio.go(`${SHOP}/harness`, 2200);
        const count = page.locator("#count");
        const expectCount = async (n) => {
          await page.waitForFunction(
            (v) => document.getElementById("count").textContent === v,
            String(n),
          );
          await sleep(1400);
        };
        await expectCount(1);
        await studio.moveTo(count);
        await studio.click(page.getByRole("button", { name: "Add the same script tag again" }));
        await expectCount(1);
        await studio.click(page.getByRole("button", { name: "Mount a second instance" }));
        await expectCount(2);
        await studio.click(page.getByRole("button", { name: "Destroy default instance" }));
        await expectCount(1);
        await studio.click(page.getByRole("button", { name: "Mount default again" }));
        await expectCount(2);
      },
    );

    const phone = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: SCALE,
    });
    const mobile = await Studio.open(phone);
    await mobile.clip("R11-widget-mobile", "Widget at 390 px", async () => {
      await mobile.go(SHOP, 1800);
      const widget = widgetFrame(mobile.page, botKey);
      await mobile.click(widget.getByRole("button", { name: "Open support chat" }));
      await mobile.type(widget.getByLabel("Your question"), "Do tents carry a warranty?");
      await mobile.click(widget.getByRole("button", { name: "Send", exact: true }));
      await widget.getByRole("button", { name: "Helpful", exact: true }).first().waitFor();
      await sleep(3000);
    });
    await phone.close();

    await studio.clip("R12-inbox", "Conversation inbox and transcript", async () => {
      await studio.go(`${org()}/conversations`, 2800);
      const list = page.getByRole("list", { name: "Conversations" });
      await studio.click(
        list
          .getByRole("link", { name: /returns allowed/ })
          .filter({ hasText: "widget" })
          .first(),
      );
      const history = page.getByRole("list", { name: "Message history" });
      await history.getByRole("list", { name: "Sources" }).first().waitFor();
      await sleep(3500);
      await studio.click(page.getByRole("button", { name: "Mark resolved" }));
      await sleep(2000);
      await studio.scrollThrough();
    });

    await studio.clip("R13-analytics", "Analytics from stored events", async () => {
      await studio.go(`${org()}/analytics`, 3500);
      await page.getByRole("heading", { name: "Analytics" }).waitFor();
      // Stay on the metric cards. The bar charts below currently render without visible bars,
      // and cost and token figures come from the offline fixture: crop both in the edit.
      await sleep(5000);
    });

    // The same overview as R02, now with data: the better shot for montages.
    await studio.clip("R15-dashboard-populated", "Dashboard with demonstration data", async () => {
      await studio.go(org(), 4000);
      await studio.scrollThrough(1200);
    });

    // A second, unrelated owner. Each business sees only its own workspace.
    const otherContext = await newContext();
    const other = await Studio.open(otherContext);
    await other.page.goto(`${WEB}/login`, { waitUntil: "networkidle" });
    await other.page.getByLabel("Email").fill(bluepeak.email);
    await other.page.getByLabel("Password").fill(bluepeak.password);
    await other.page.getByRole("button", { name: "Sign in" }).click();
    await other.page.waitForURL(/\/(orgs|dashboard)/);
    const created = await other.page.request.post(`${API}/api/v1${bluepeak.orgPath}/chatbots`, {
      headers: HEADERS,
      data: { name: "Bluepeak Assistant" },
    });
    if (created.status() !== 201) throw new Error(`second chatbot: ${created.status()}`);
    const otherBot = (await created.json()).id;
    const otherBase = `${API}/api/v1${bluepeak.orgPath}/chatbots/${otherBot}`;
    const filename = "bluepeak-membership-policy.txt";
    const uploaded = await other.page.request.post(`${otherBase}/documents?filename=${filename}`, {
      headers: { ...HEADERS, "Content-Type": "text/plain" },
      data: fs.readFileSync(path.join(DATA, filename)),
    });
    if (uploaded.status() !== 201) throw new Error(`second upload: ${uploaded.status()}`);
    await ready(other.page, otherBase, filename);

    await other.clip(
      "R14-tenant-isolation",
      "Second organization cannot open the first",
      async () => {
        await other.go(`${WEB}${bluepeak.orgPath}/knowledge`, 3200);
        await other.page.getByRole("row", { name: /bluepeak/ }).waitFor();
        await other.go(`${WEB}${northwind.orgPath}/conversations`, 1200);
        await other.page.getByRole("heading", { name: "Organization not found" }).waitFor();
        await sleep(3000);
      },
    );
    // Evidence for the overlay card: the same request, as HTTP status codes only.
    const crossed = await other.page.request.get(`${API}/api/v1${northwind.orgPath}/conversations`);
    const own = await other.page.request.get(`${API}/api/v1${bluepeak.orgPath}/conversations`);
    fs.writeFileSync(
      path.join(OUT, "tenant-isolation-statuses.txt"),
      `Signed in as the Bluepeak Fitness owner (synthetic account)\n` +
        `GET /api/v1/orgs/{northwind}/conversations -> ${crossed.status()}\n` +
        `GET /api/v1/orgs/{bluepeak}/conversations  -> ${own.status()}\n`,
    );
    if (crossed.status() !== 404 || own.status() !== 200) {
      throw new Error(`isolation check: ${crossed.status()} / ${own.status()}`);
    }
    await otherContext.close();
    await context.close();
  } finally {
    manifest.generated_at = new Date().toISOString();
    fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 2));
    await browser.close();
    server.close();
  }
  console.log(
    `done: ${OUT}\nnext: python docs/portfolio-video/recording-scripts/encode.py "${OUT}"`,
  );
})().catch((error) => {
  console.error(String(error).split("\n").slice(0, 12).join("\n"));
  process.exit(1);
});
