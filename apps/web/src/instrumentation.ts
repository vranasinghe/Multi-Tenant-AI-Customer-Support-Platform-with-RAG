/**
 * Runs once when the Next.js server starts. Validating here makes a misconfigured
 * deployment crash at boot rather than on the first request.
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  const { serverEnv } = await import("./env");
  const { logger } = await import("./lib/logger");
  const env = serverEnv();
  logger.info("web.startup", { node_env: env.NODE_ENV, api_internal_url: env.API_INTERNAL_URL });
}
