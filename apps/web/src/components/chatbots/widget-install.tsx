"use client";
import { useEffect, useState } from "react";
import { createApiClient, publicApiBaseUrl } from "@/lib/api/client";
import type { Chatbot, Org } from "@/lib/api/types";
import { can } from "@/lib/orgs";
import { Button } from "@acs/ui/components/button";
import { Input } from "@acs/ui/components/input";
import { Label } from "@acs/ui/components/label";
import { Alert } from "@acs/ui/components/alert";

interface Config {
  domains: { id: string; origin: string; token: string; verified_until: string | null }[];
  retention_days: number;
}
export function WidgetInstall({
  org,
  bot,
  onRotate,
}: {
  org: Org;
  bot: Chatbot;
  onRotate: () => void;
}) {
  const [checkedAt] = useState(() => Date.now());
  const [config, setConfig] = useState<Config | null>(null);
  const [origin, setOrigin] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("about:blank");
  const base = `/orgs/${encodeURIComponent(org.id)}/chatbots/${encodeURIComponent(bot.id)}`;
  const apiBase = publicApiBaseUrl();
  const client = createApiClient({ baseUrl: apiBase });
  const allowed = can(org, "domain:manage") && org.status === "active";
  const snippet = `<script async src="${apiBase}/widget/v1/loader.js" data-bot-key="${bot.public_key}"></script>`;
  async function reload() {
    setConfig(await client.get<Config>(`${base}/widget-config`));
  }
  useEffect(() => {
    let active = true;
    void createApiClient({ baseUrl: apiBase })
      .get<Config>(`${base}/widget-config`)
      .then((c) => {
        if (active) {
          setConfig(c);
          setPreviewUrl(
            `${apiBase}/widget/frame/${encodeURIComponent(bot.public_key)}?parent_origin=${encodeURIComponent(window.location.origin)}&instance=${crypto.randomUUID()}`,
          );
        }
      })
      .catch((e) => {
        if (active)
          setError(e instanceof Error ? e.message : "Could not load installation settings");
      });
    return () => {
      active = false;
    };
  }, [base, apiBase, bot.public_key]);
  async function action(task: () => Promise<unknown>) {
    setPending(true);
    setError("");
    try {
      await task();
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Please try again");
    } finally {
      setPending(false);
    }
  }
  function mountPreview() {
    setPreviewUrl(
      `${apiBase}/widget/frame/${encodeURIComponent(bot.public_key)}?parent_origin=${encodeURIComponent(window.location.origin)}&instance=${crypto.randomUUID()}`,
    );
  }
  return (
    <section className="grid max-w-3xl min-w-0 gap-6" aria-label="Widget installation">
      <h2 className="font-semibold">Install your website chatbot</h2>
      {error && <Alert variant="destructive">{error}</Alert>}
      <p className="text-sm text-muted-foreground">
        Activate this chatbot, verify your website origin, then paste the script before the closing
        body tag. The public key identifies your chatbot and grants no admin access.
      </p>
      <Label htmlFor="public-widget-key">Public key</Label>
      <Input id="public-widget-key" readOnly value={bot.public_key} />
      <Label htmlFor="widget-snippet">Installation script</Label>
      <textarea
        id="widget-snippet"
        readOnly
        value={snippet}
        rows={4}
        className="w-full rounded-md border p-3 font-mono text-sm"
      />
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={() => {
            void navigator.clipboard
              .writeText(snippet)
              .then(() => setCopied(true))
              .catch(() => setError("Select the installation script and copy it manually."));
          }}
        >
          {copied ? "Copied" : "Copy installation script"}
        </Button>
        {allowed && (
          <Button type="button" variant="outline" onClick={onRotate}>
            Rotate
          </Button>
        )}
      </div>
      <section className="grid gap-3" aria-labelledby="allowed-origins">
        <h3 id="allowed-origins" className="font-medium">
          Allowed website origins
        </h3>
        <p className="text-sm text-muted-foreground">
          Use an exact origin such as https://www.example.com. Add its DNS TXT record at
          _acs-widget.www.example.com with the proof shown below. Verification lasts seven days.
          Localhost verification is available only in local development.
        </p>
        {allowed && (
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid flex-1 gap-2">
              <Label htmlFor="widget-origin">Website origin</Label>
              <Input
                id="widget-origin"
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
                placeholder="https://www.example.com"
              />
            </div>
            <Button
              type="button"
              disabled={pending || !origin.trim()}
              onClick={() =>
                void action(() => client.post(`${base}/domains`, { origin })).then(() =>
                  setOrigin(""),
                )
              }
            >
              Add origin
            </Button>
          </div>
        )}
        {!config ? (
          <p role="status">Loading allowed origins…</p>
        ) : config.domains.length === 0 ? (
          <p className="text-sm">
            No origins configured. The public widget is blocked until an origin is verified.
          </p>
        ) : (
          <ul className="grid gap-4">
            {config.domains.map((d) => (
              <li key={d.id} className="grid gap-2 border-b pb-4">
                <strong className="text-sm break-all">{d.origin}</strong>
                <code className="text-xs break-all">{d.token}</code>
                <p className="text-xs text-muted-foreground">
                  {d.verified_until && Date.parse(d.verified_until) > checkedAt
                    ? `Verified until ${new Date(d.verified_until).toLocaleString()}`
                    : "Not verified"}
                </p>
                {allowed && (
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      disabled={pending}
                      onClick={() =>
                        void action(() => client.post(`${base}/domains/${d.id}/verify`))
                      }
                    >
                      Verify origin
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={pending}
                      onClick={() => void action(() => client.delete(`${base}/domains/${d.id}`))}
                    >
                      Remove origin
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      {config && (
        <div className="grid max-w-xs gap-2">
          <Label htmlFor="widget-retention">Anonymous session retention (days)</Label>
          <Input
            id="widget-retention"
            type="number"
            min={0}
            max={30}
            disabled={!allowed || pending}
            value={config.retention_days}
            onChange={(e) => setConfig({ ...config, retention_days: Number(e.target.value) })}
          />
          <p className="text-xs text-muted-foreground">
            0 keeps resumption in memory only. This controls visitor access, not database deletion.
          </p>
          {allowed && (
            <Button
              type="button"
              disabled={pending}
              onClick={() =>
                void action(() =>
                  client.patch(`${base}/widget-retention`, { days: config.retention_days }),
                )
              }
            >
              Save retention
            </Button>
          )}
        </div>
      )}
      <section className="grid gap-3" aria-labelledby="live-widget">
        <h3 id="live-widget" className="font-medium">
          Live widget preview
        </h3>
        <p className="text-sm text-muted-foreground">
          Verify this dashboard origin to test the real widget here. Public chat uses saved branding
          and an active chatbot.
        </p>
        <iframe
          title="Live widget preview"
          src={previewUrl}
          sandbox="allow-scripts allow-same-origin"
          className="h-[660px] w-full rounded-xl border bg-card"
        />
        <Button type="button" variant="outline" onClick={mountPreview}>
          Reload live preview
        </Button>
      </section>
    </section>
  );
}
