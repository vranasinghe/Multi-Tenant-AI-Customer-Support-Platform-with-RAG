interface Saved {
  resume: string;
  until: number;
}
interface Brand {
  primary_color?: string;
  accent_color?: string;
  position?: string;
  launcher_label?: string;
  avatar_url?: string;
  show_branding?: boolean;
}
interface Session {
  token: string;
  resume_token: string;
  retain_until: string;
  expires_at: string;
  retention_days: number;
  name: string;
  welcome: string;
  branding: Brand;
}
interface Message {
  content: string;
  role: string;
  citations?: { title: string; uri: string; id: number }[];
}
function el<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  return node;
}
function contrast(hex: string) {
  const n = hex
    .slice(1)
    .match(/../g)!
    .map((v) => parseInt(v, 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return n[0]! * 0.2126 + n[1]! * 0.7152 + n[2]! * 0.0722 > 0.179 ? "#111111" : "#ffffff";
}
export function mountFrame(script: HTMLScriptElement) {
  const key = script.dataset.frameKey!;
  const parent = script.dataset.parentOrigin!;
  const instance = script.dataset.instance!;
  // An explicit second instance of one chatbot keeps its own conversation.
  const instanceKey = script.dataset.instanceKey;
  const storageKey = `acs:v1:${parent}:${key}` + (instanceKey ? `:${instanceKey}` : "");
  const style = el("style");
  style.textContent = `*{box-sizing:border-box}body{margin:0;font:14px system-ui,sans-serif;color:#171717;background:transparent}button,textarea{font:inherit}button{cursor:pointer;border:1px solid #d4d4d4;border-radius:8px;padding:10px;background:#fff;color:#171717}button:focus-visible,textarea:focus-visible,a:focus-visible{outline:3px solid #2563eb;outline-offset:2px}button:disabled{opacity:.6;cursor:wait}#launcher{position:fixed;bottom:8px;right:8px;width:60px;height:60px;border-radius:30px;padding:5px;overflow:hidden;font-size:12px;overflow-wrap:anywhere}#panel{height:100dvh;display:flex;flex-direction:column;border:1px solid #d4d4d4;border-radius:14px;background:#fff;overflow:hidden}header{display:flex;align-items:center;gap:8px;padding:12px}header strong{flex:1;overflow-wrap:anywhere}header img{width:30px;height:30px;border-radius:50%}#log{flex:1;overflow:auto;padding:16px;min-height:0}article{white-space:pre-wrap;overflow-wrap:anywhere;margin-bottom:18px;line-height:1.5}article[data-role=user]{color:#171717;background:#f3f4f6;border-radius:8px;padding:10px}article small{display:block;font-weight:600;margin-bottom:4px}article>span+span{display:block;font-size:12px;margin-top:6px}article a{display:block;font-size:12px;color:inherit;text-underline-offset:3px}footer{padding:12px;border-top:1px solid #ddd;display:grid;gap:8px}textarea{width:100%;resize:none;border:1px solid #aaa;border-radius:8px;padding:10px;color:#171717;background:#fff}#status{padding:0 12px;font-size:12px;line-height:1.5;overflow-wrap:anywhere}#controls{display:flex;justify-content:space-between;gap:8px}label{font-weight:600;font-size:12px}.branding{font-size:11px;text-align:center;color:inherit;opacity:.75}[hidden]{display:none!important}`;
  document.head.append(style);
  const launcher = el("button", "Chat");
  launcher.id = "launcher";
  launcher.setAttribute("aria-label", "Open support chat");
  launcher.setAttribute("aria-expanded", "false");
  const panel = el("section");
  panel.id = "panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", "Support chat");
  const header = el("header");
  const title = el("strong", "Support");
  const close = el("button", "Close");
  close.setAttribute("aria-label", "Close support chat");
  header.append(title, close);
  const log = el("div");
  log.id = "log";
  log.setAttribute("role", "log");
  log.setAttribute("aria-live", "polite");
  log.setAttribute("aria-label", "Conversation");
  const status = el("p");
  status.id = "status";
  status.setAttribute("role", "status");
  const footer = el("footer");
  const label = el("label", "Your question");
  label.htmlFor = "question";
  const input = el("textarea");
  input.id = "question";
  input.rows = 2;
  input.maxLength = 4000;
  const controls = el("div");
  controls.id = "controls";
  const reset = el("button", "New chat");
  const send = el("button", "Send");
  const stop = el("button", "Stop");
  stop.hidden = true;
  controls.append(reset, stop, send);
  const branding = el("span", "Support Platform");
  branding.className = "branding";
  footer.append(label, input, controls, branding);
  panel.append(header, log, status, footer);
  document.body.append(launcher, panel);
  let session: Session | null = null;
  let opening: Promise<void> | null = null;
  let abort: AbortController | null = null;
  let resume: string | undefined;
  let left = false;
  // Raised by "New chat" and "forget": work started before it must not touch what comes after.
  let generation = 0;
  let loading: AbortController | null = null;
  function size(open: boolean) {
    window.parent.postMessage({ type: "acs-size", instance, open, left }, parent);
    panel.hidden = !open;
    launcher.hidden = open;
    launcher.setAttribute("aria-expanded", String(open));
  }
  function save(s: Session) {
    resume = s.resume_token;
    try {
      if (s.retention_days)
        localStorage.setItem(
          storageKey,
          JSON.stringify({ resume, until: Date.parse(s.retain_until) }),
        );
      else localStorage.removeItem(storageKey);
    } catch {
      /* Storage may be blocked; in-memory sessions still work. */
    }
  }
  function append(m: Message) {
    const article = el("article");
    article.dataset.role = m.role;
    const name = el("small", m.role === "user" ? "You" : (session?.name ?? "Support"));
    const body = el("span", m.content);
    article.append(name, body);
    log.append(article);
    for (const c of m.citations ?? []) {
      const source = el("span", `[${c.id}] ${c.title}`);
      try {
        const u = new URL(c.uri);
        if (u.protocol === "https:" && !u.username && !u.password) {
          const a = el("a", source.textContent!);
          a.href = u.href;
          a.target = "_blank";
          a.rel = "noopener noreferrer nofollow";
          article.append(a);
          continue;
        }
      } catch {
        /* Private file IDs stay plain text. */
      }
      article.append(source);
    }
    log.scrollTop = log.scrollHeight;
    return { article, body };
  }
  async function request(path: string, init: RequestInit = {}) {
    const asked = generation;
    const r = await fetch(path, {
      ...init,
      credentials: "omit",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
      },
    });
    if (asked !== generation) throw Error("Superseded");
    if (!r.ok) {
      if (r.status === 401) session = null;
      throw Error(
        r.status === 429
          ? "Chat limit reached. Please try again later."
          : r.status === 403
            ? "Chat is not available on this website."
            : "Chat is unavailable. Please reopen it to try again.",
      );
    }
    return r;
  }
  async function load() {
    loading?.abort();
    const { signal } = (loading = new AbortController());
    const mine = generation;
    status.textContent = "Connecting…";
    try {
      if (!resume)
        try {
          const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null") as Saved | null;
          if (saved && saved.until > Date.now()) resume = saved.resume;
          else localStorage.removeItem(storageKey);
        } catch {
          /* Storage is optional. */
        }
      const r = await request("/public/v1/widget/sessions", {
        method: "POST",
        signal,
        body: JSON.stringify({ key, parent_origin: parent, resume_token: resume }),
      });
      const opened = (await r.json()) as Session;
      if (mine !== generation) return;
      session = opened;
      save(session);
      title.textContent = session.name;
      launcher.textContent = session.branding.launcher_label ?? "Chat";
      left = session.branding.position === "bottom-left";
      for (const n of [header, launcher]) {
        const color = session.branding.primary_color;
        if (color && /^#[0-9a-f]{6}$/i.test(color)) {
          n.style.background = color;
          n.style.color = contrast(color);
        }
      }
      const surface = session.branding.accent_color;
      if (surface && /^#[0-9a-f]{6}$/i.test(surface)) {
        panel.style.background = surface;
        panel.style.color = contrast(surface);
      }
      if (session.branding.avatar_url?.startsWith("https://")) {
        const img = el("img");
        img.src = session.branding.avatar_url;
        img.alt = "";
        img.referrerPolicy = "no-referrer";
        img.onerror = () => img.remove();
        header.querySelector("img")?.remove();
        header.prepend(img);
      }
      branding.hidden = session.branding.show_branding === false;
      const history = (await (await request("/public/v1/chat", { signal })).json()) as {
        messages: Message[];
      };
      if (mine !== generation) return;
      log.replaceChildren();
      if (!history.messages.length) append({ role: "assistant", content: session.welcome });
      for (const m of history.messages) append(m);
      status.textContent = "";
      size(!panel.hidden);
    } catch (e) {
      if (mine !== generation) return;
      status.textContent = e instanceof Error ? e.message : "Could not connect";
      session = null;
    }
  }
  function start() {
    const run = load().finally(() => {
      if (opening === run) opening = null;
    });
    opening = run;
  }
  function discard() {
    generation++;
    abort?.abort();
    loading?.abort();
    resume = undefined;
    session = null;
    try {
      localStorage.removeItem(storageKey);
    } catch {
      /* Optional storage. */
    }
  }
  launcher.onclick = () => {
    size(true);
    input.focus();
    if (!session && !opening) start();
  };
  close.onclick = () => {
    size(false);
    launcher.focus();
  };
  reset.onclick = () => {
    discard();
    log.replaceChildren();
    start();
  };
  window.addEventListener("message", (event) => {
    // Only the page that embedded this frame, naming this very instance.
    if (event.source !== window.parent || event.origin !== parent) return;
    if (event.data?.instance !== instance || event.data.type !== "acs-forget") return;
    discard();
    window.parent.postMessage({ type: "acs-forgotten", instance }, parent);
  });
  stop.onclick = () => abort?.abort();
  async function submit() {
    if (abort || !input.value.trim()) return;
    if (opening) await opening;
    if (!session) {
      await load();
      if (!session) return;
    }
    if (Date.parse(session.expires_at) < Date.now() + 5000) {
      await load();
      if (!session) return;
    }
    const question = input.value.trim();
    input.value = "";
    append({ role: "user", content: question });
    const answer = append({ role: "assistant", content: "" });
    abort = new AbortController();
    send.disabled = true;
    reset.disabled = true;
    stop.hidden = false;
    status.textContent = "Finding an answer…";
    try {
      const r = await request("/public/v1/chat/messages", {
        method: "POST",
        signal: abort.signal,
        body: JSON.stringify({ content: question }),
      });
      const reader = r.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "",
        finished = false;
      try {
        while (true) {
          const part = await reader.read();
          buffer += decoder.decode(part.value, { stream: !part.done });
          buffer = buffer.replace(/\r\n/g, "\n");
          if (buffer.length > 256000) throw Error("Response too large");
          let end;
          while ((end = buffer.indexOf("\n\n")) >= 0) {
            const frame = buffer.slice(0, end);
            buffer = buffer.slice(end + 2);
            const lines = frame.split("\n");
            const kind = lines
              .find((l) => l.startsWith("event:"))
              ?.slice(6)
              .trim();
            const raw = lines
              .filter((l) => l.startsWith("data:"))
              .map((l) => l.slice(5).trim())
              .join("\n");
            if (!raw) continue;
            const data = JSON.parse(raw);
            if (kind === "delta") {
              answer.body.textContent += data.text;
              status.textContent = "Answering…";
              log.scrollTop = log.scrollHeight;
            }
            if (kind === "error") throw Error(data.message);
            if (kind === "done") {
              finished = true;
              answer.article.remove();
              append(data as Message);
            }
          }
          if (part.done) break;
        }
        if (!finished) throw Error("Connection interrupted. Please try again.");
        status.textContent = "";
        const actions = el("div");
        actions.setAttribute("role", "group");
        actions.setAttribute("aria-label", "Conversation follow-up");
        const yes = el("button", "Helpful");
        const no = el("button", "Not helpful");
        const human = el("button", "Talk to a person");
        async function scored(score: number, button: HTMLButtonElement) {
          try {
            await request("/public/v1/chat/satisfaction", {
              method: "PUT",
              body: JSON.stringify({ score }),
            });
            yes.disabled = true;
            no.disabled = true;
            button.setAttribute("aria-pressed", "true");
            status.textContent = "Thanks for the feedback.";
          } catch (err) {
            status.textContent = err instanceof Error ? err.message : "Could not save rating";
          }
        }
        yes.onclick = () => void scored(5, yes);
        no.onclick = () => void scored(1, no);
        human.onclick = async () => {
          const reason = window.prompt("Tell us why a person should follow up.");
          if (!reason?.trim()) return;
          try {
            await request("/public/v1/chat/handoff", {
              method: "POST",
              body: JSON.stringify({ reason: reason.trim() }),
            });
            human.disabled = true;
            status.textContent = "A teammate will follow up.";
          } catch (err) {
            status.textContent = err instanceof Error ? err.message : "Could not request a person";
          }
        };
        actions.append(yes, no, human);
        log.append(actions);
      } finally {
        await reader.cancel().catch(() => undefined);
        reader.releaseLock();
      }
    } catch (e) {
      status.textContent = abort?.signal.aborted
        ? "Answer stopped."
        : e instanceof Error
          ? e.message
          : "Could not send";
    } finally {
      abort = null;
      send.disabled = false;
      reset.disabled = false;
      stop.hidden = true;
      input.focus();
    }
  }
  send.onclick = () => void submit();
  input.onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      void submit();
    }
  };
  document.onkeydown = (e) => {
    if (panel.hidden) return;
    if (e.key === "Escape") {
      e.preventDefault();
      close.click();
    }
    if (e.key === "Tab") {
      const nodes = Array.from(
        panel.querySelectorAll<HTMLElement>("button:not([hidden]):not(:disabled),textarea,a[href]"),
      );
      const first = nodes[0]!,
        last = nodes[nodes.length - 1]!;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };
  window.addEventListener("pagehide", () => {
    abort?.abort();
    loading?.abort();
  });
  size(false);
  start();
}
