import { headers } from "next/headers";

import { Badge } from "@acs/ui/components/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@acs/ui/components/card";

import { serverEnv } from "@/env";
import { checkApiReadiness } from "@/lib/api-health";
import { REQUEST_ID_HEADER, resolveRequestId } from "@/lib/request-id";

export const dynamic = "force-dynamic";

const STATUS_LABEL = { ok: "Ready", degraded: "Degraded", unreachable: "Unreachable" } as const;

/** Development status page: shows whether the web app can reach a ready API. */
export default async function Home() {
  const requestId = resolveRequestId((await headers()).get(REQUEST_ID_HEADER));
  const api = await checkApiReadiness({ baseUrl: serverEnv().API_INTERNAL_URL, requestId });
  const checks = Object.entries(api.checks ?? {});

  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-6 px-4 py-12">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Support Platform</h1>
        <p className="text-sm text-muted-foreground">Local development environment status</p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between gap-4">
            API
            <Badge variant={api.status === "ok" ? "default" : "destructive"}>
              {STATUS_LABEL[api.status]}
            </Badge>
          </CardTitle>
          <CardDescription>
            {api.http_status === null
              ? "No response from the API."
              : `HTTP ${api.http_status} in ${api.latency_ms} ms`}
          </CardDescription>
        </CardHeader>
        {checks.length > 0 && (
          <CardContent>
            <ul className="divide-y text-sm">
              {checks.map(([name, check]) => (
                <li key={name} className="flex items-center justify-between gap-4 py-2">
                  <span className="font-medium capitalize">{name}</span>
                  <span className="truncate text-muted-foreground">
                    {check.status === "ok" ? (check.detail ?? "ok") : `error: ${check.detail}`}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        )}
      </Card>

      <p className="text-xs text-muted-foreground">
        Request ID <code className="font-mono">{requestId}</code>
      </p>
    </main>
  );
}
