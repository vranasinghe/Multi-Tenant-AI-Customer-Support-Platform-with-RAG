/** Public widget keys look like `pk_live_…` / `pk_test_…` (ADR-006). They are not secrets. */
export const PUBLIC_KEY_PATTERN = /^pk_(live|test)_[A-Za-z0-9]{8,64}$/;

export interface LoaderConfig {
  botKey: string;
}

export type LoaderConfigResult = { ok: true; config: LoaderConfig } | { ok: false; error: string };

/** Read and validate the loader's `data-*` attributes (passed as a DOMStringMap-like object). */
export function readLoaderConfig(dataset: Record<string, string | undefined>): LoaderConfigResult {
  const botKey = dataset.botKey?.trim();
  if (!botKey) {
    return { ok: false, error: "Missing data-bot-key attribute on the widget <script> tag." };
  }
  if (!PUBLIC_KEY_PATTERN.test(botKey)) {
    return { ok: false, error: "data-bot-key is not a valid public widget key." };
  }
  return { ok: true, config: { botKey } };
}
