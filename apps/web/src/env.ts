import { z } from "zod";

/**
 * Environment validation for the web app.
 *
 * - Server variables are read at runtime and validated once at startup (instrumentation.ts).
 * - Public (NEXT_PUBLIC_*) variables are inlined at build time and validated in next.config.ts.
 *
 * Invalid configuration fails fast with a readable list of problems instead of surfacing
 * later as an obscure runtime error.
 */

const serverSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  /** Base URL the Next.js server uses to reach the API (container network or localhost). */
  API_INTERNAL_URL: z.url({ protocol: /^https?$/ }),
  /** Case-insensitive so the web app can share the API's LOG_LEVEL=INFO in the root .env. */
  LOG_LEVEL: z.preprocess(
    (value) => (typeof value === "string" ? value.toLowerCase() : value),
    z.enum(["debug", "info", "warn", "error"]).default("info"),
  ),
});

const publicSchema = z.object({
  /** Base URL browsers use to reach the API. */
  NEXT_PUBLIC_API_URL: z.url({ protocol: /^https?$/ }),
});

export type ServerEnv = z.infer<typeof serverSchema>;
export type PublicEnv = z.infer<typeof publicSchema>;

export class EnvValidationError extends Error {
  constructor(scope: string, details: string) {
    super(`Invalid ${scope} environment variables:\n${details}`);
    this.name = "EnvValidationError";
  }
}

type EnvSource = Record<string, string | undefined>;

function parse<T extends z.ZodType>(schema: T, source: EnvSource, scope: string): z.infer<T> {
  // Treat empty strings as unset so `FOO=` in a .env file triggers the "required" error.
  const cleaned = Object.fromEntries(
    Object.entries(source).filter(([, value]) => value !== undefined && value !== ""),
  );
  const result = schema.safeParse(cleaned);
  if (!result.success) {
    throw new EnvValidationError(scope, z.prettifyError(result.error));
  }
  return result.data;
}

export function parseServerEnv(source: EnvSource): ServerEnv {
  return parse(serverSchema, source, "server");
}

export function parsePublicEnv(source: EnvSource): PublicEnv {
  return parse(publicSchema, source, "public");
}

let cachedServerEnv: ServerEnv | undefined;

/** Validated server environment (cached after the first successful parse). */
export function serverEnv(): ServerEnv {
  cachedServerEnv ??= parseServerEnv(process.env);
  return cachedServerEnv;
}
