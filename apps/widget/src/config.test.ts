import { describe, expect, it } from "vitest";

import { readLoaderConfig } from "./config";

describe("readLoaderConfig", () => {
  it("accepts a well-formed public key", () => {
    expect(readLoaderConfig({ botKey: "pk_live_8fK2abcdEFGH" })).toEqual({
      ok: true,
      config: { botKey: "pk_live_8fK2abcdEFGH" },
    });
  });

  it("trims surrounding whitespace", () => {
    const result = readLoaderConfig({ botKey: "  pk_test_abcdefgh  " });
    expect(result).toEqual({ ok: true, config: { botKey: "pk_test_abcdefgh" } });
  });

  it("rejects a missing key", () => {
    expect(readLoaderConfig({})).toMatchObject({ ok: false });
  });

  it.each(["sk_live_abcdefgh", "pk_live_short", "pk_prod_abcdefghij", "pk_live_abc/../../x"])(
    "rejects malformed key %s",
    (botKey) => {
      expect(readLoaderConfig({ botKey })).toMatchObject({ ok: false });
    },
  );
});
