import { describe, expect, it } from "vitest";

import {
  fieldErrorsFromZod,
  forgotPasswordSchema,
  inviteSchema,
  loginSchema,
  resetPasswordSchema,
  signupSchema,
} from "./validation";

describe("signupSchema", () => {
  const valid = {
    name: "Dana Lee",
    orgName: "Acme",
    email: "dana@acme.com",
    password: "correct horse battery staple",
  };

  it("accepts a long passphrase without composition rules", () => {
    expect(signupSchema.safeParse(valid).success).toBe(true);
  });

  it("requires at least 10 characters", () => {
    const result = signupSchema.safeParse({ ...valid, password: "short" });
    expect(fieldErrorsFromZod(result.error!).password).toMatch(/at least 10/i);
  });

  it("rejects passwords over 128 characters", () => {
    const result = signupSchema.safeParse({ ...valid, password: "x".repeat(129) });
    expect(fieldErrorsFromZod(result.error!).password).toMatch(/at most 128/i);
  });

  it("rejects passwords containing the email's local part", () => {
    const result = signupSchema.safeParse({
      ...valid,
      email: "dana@acme.com",
      password: "dana-is-the-best",
    });
    expect(fieldErrorsFromZod(result.error!).password).toMatch(/email/i);
  });

  it("trims names and rejects blanks", () => {
    const result = signupSchema.safeParse({ ...valid, name: "   ", orgName: "" });
    const errors = fieldErrorsFromZod(result.error!);
    expect(errors.name).toBeDefined();
    expect(errors.orgName).toBeDefined();
  });

  it("rejects malformed emails", () => {
    const result = signupSchema.safeParse({ ...valid, email: "not-an-email" });
    expect(fieldErrorsFromZod(result.error!).email).toMatch(/valid email/i);
  });
});

describe("loginSchema", () => {
  it("only requires an email and some password (never reveals policy at login)", () => {
    expect(loginSchema.safeParse({ email: "a@b.co", password: "x" }).success).toBe(true);
    const bad = loginSchema.safeParse({ email: "", password: "" });
    expect(Object.keys(fieldErrorsFromZod(bad.error!))).toEqual(["email", "password"]);
  });
});

describe("forgotPasswordSchema", () => {
  it("requires a valid email", () => {
    expect(forgotPasswordSchema.safeParse({ email: "a@b.co" }).success).toBe(true);
    expect(forgotPasswordSchema.safeParse({ email: "nope" }).success).toBe(false);
  });
});

describe("resetPasswordSchema", () => {
  it("requires matching confirmation and minimum length", () => {
    const mismatch = resetPasswordSchema.safeParse({
      password: "a long enough one",
      confirm: "different one!!",
    });
    expect(fieldErrorsFromZod(mismatch.error!).confirm).toMatch(/match/i);
    expect(
      resetPasswordSchema.safeParse({ password: "a long enough one", confirm: "a long enough one" })
        .success,
    ).toBe(true);
  });
});

describe("inviteSchema", () => {
  it("never allows inviting an owner", () => {
    expect(inviteSchema.safeParse({ email: "a@b.co", role: "owner" }).success).toBe(false);
    for (const role of ["admin", "agent", "viewer"]) {
      expect(inviteSchema.safeParse({ email: "a@b.co", role }).success).toBe(true);
    }
  });
});
