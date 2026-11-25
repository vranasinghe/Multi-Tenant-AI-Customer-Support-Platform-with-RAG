import { z } from "zod";

/**
 * Client-side form validation. This is UX only: the API enforces the same rules (and more,
 * e.g. a common-password list) and is the authority.
 */

export const PASSWORD_MIN = 10;
export const PASSWORD_MAX = 128;

const email = z
  .string()
  .trim()
  .min(1, "Enter your email address.")
  .pipe(z.email("Enter a valid email address."));

const name = (label: string) =>
  z.string().trim().min(1, `Enter ${label}.`).max(120, "Keep it under 120 characters.");

const newPassword = z
  .string()
  .min(PASSWORD_MIN, `Use at least ${PASSWORD_MIN} characters.`)
  .max(PASSWORD_MAX, `Use at most ${PASSWORD_MAX} characters.`);

export const loginSchema = z.object({
  email,
  password: z.string().min(1, "Enter your password."),
});

export const signupSchema = z
  .object({
    name: name("your name"),
    orgName: name("an organization name"),
    email,
    password: newPassword,
  })
  .superRefine((value, ctx) => {
    const localPart = value.email.split("@")[0]?.toLowerCase() ?? "";
    if (localPart.length >= 3 && value.password.toLowerCase().includes(localPart)) {
      ctx.addIssue({
        code: "custom",
        path: ["password"],
        message: "Password must not contain your email address.",
      });
    }
  });

export const forgotPasswordSchema = z.object({ email });

export const resetPasswordSchema = z
  .object({ password: newPassword, confirm: z.string() })
  .refine((value) => value.password === value.confirm, {
    path: ["confirm"],
    message: "Passwords don't match.",
  });

export const changePasswordSchema = z
  .object({
    currentPassword: z.string().min(1, "Enter your current password."),
    newPassword,
    confirm: z.string(),
  })
  .refine((value) => value.newPassword === value.confirm, {
    path: ["confirm"],
    message: "Passwords don't match.",
  });

export const inviteSchema = z.object({
  email,
  role: z.enum(["admin", "agent", "viewer"], { error: "Choose a role." }),
});

export const orgNameSchema = z.object({ name: name("an organization name") });
export const profileSchema = z.object({ name: name("your name") });

export type FieldErrors = Record<string, string>;

/** First message per top-level field, keyed by field name. */
export function fieldErrorsFromZod(error: z.ZodError): FieldErrors {
  const result: FieldErrors = {};
  for (const issue of error.issues) {
    const key = String(issue.path[0] ?? "form");
    if (!(key in result)) result[key] = issue.message;
  }
  return result;
}
