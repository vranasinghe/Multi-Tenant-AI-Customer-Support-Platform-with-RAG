import { describe, expect, it } from "vitest";

import { EnvValidationError, parsePublicEnv, parseServerEnv } from "./env";

describe("parseServerEnv", () => {
  it("accepts a valid configuration and applies defaults", () => {
    const env = parseServerEnv({ API_INTERNAL_URL: "http://api:8000" });
    expect(env).toEqual({
      API_INTERNAL_URL: "http://api:8000",
      NODE_ENV: "development",
      LOG_LEVEL: "info",
    });
  });

  it("reports a missing required variable by name", () => {
    expect(() => parseServerEnv({})).toThrow(EnvValidationError);
    expect(() => parseServerEnv({})).toThrow(/API_INTERNAL_URL/);
  });

  it("treats an empty string as missing", () => {
    expect(() => parseServerEnv({ API_INTERNAL_URL: "" })).toThrow(/API_INTERNAL_URL/);
  });

  it("rejects non-http URLs", () => {
    expect(() => parseServerEnv({ API_INTERNAL_URL: "ftp://api:21" })).toThrow(EnvValidationError);
  });

  it("accepts log levels case-insensitively (shared root .env uses INFO)", () => {
    expect(
      parseServerEnv({ API_INTERNAL_URL: "http://api:8000", LOG_LEVEL: "INFO" }).LOG_LEVEL,
    ).toBe("info");
  });

  it("rejects unknown log levels", () => {
    expect(() =>
      parseServerEnv({ API_INTERNAL_URL: "http://api:8000", LOG_LEVEL: "verbose" }),
    ).toThrow(/LOG_LEVEL/);
  });
});

describe("parsePublicEnv", () => {
  it("requires NEXT_PUBLIC_API_URL to be a URL", () => {
    expect(parsePublicEnv({ NEXT_PUBLIC_API_URL: "http://localhost:8000" })).toEqual({
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
    });
    expect(() => parsePublicEnv({ NEXT_PUBLIC_API_URL: "not-a-url" })).toThrow(
      /NEXT_PUBLIC_API_URL/,
    );
  });
});
