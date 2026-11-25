"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";

import { api, ApiError } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import { useAuth } from "@/lib/auth/auth-context";
import { safeRedirectPath } from "@/lib/safe-redirect";
import { fieldErrorsFromZod, PASSWORD_MIN, signupSchema } from "@/lib/validation";
import type { FieldErrors } from "@/lib/validation";

import { TextField, useFocusFirstInvalid } from "../form/text-field";

/** Server field names (snake_case) → this form's field names. */
const SERVER_FIELDS: Record<string, string> = { org_name: "orgName" };

export function SignupForm({ next }: { next?: string | null }) {
  const router = useRouter();
  const { refresh } = useAuth();
  const formRef = useRef<HTMLFormElement>(null);
  const submitting = useRef(false);
  const [values, setValues] = useState({ name: "", orgName: "", email: "", password: "" });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [checkEmail, setCheckEmail] = useState<string | null>(null);

  useFocusFirstInvalid(formRef, errors);

  const set = (key: keyof typeof values) => (event: { target: { value: string } }) =>
    setValues((current) => ({ ...current, [key]: event.target.value }));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current) return;
    setFormError(null);

    const parsed = signupSchema.safeParse(values);
    if (!parsed.success) {
      setErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setErrors({});

    submitting.current = true;
    setPending(true);
    try {
      await api.signup({
        email: parsed.data.email,
        password: parsed.data.password,
        name: parsed.data.name,
        org_name: parsed.data.orgName,
      });
      const state = await refresh();
      if (state.status === "authenticated") {
        router.replace(safeRedirectPath(next));
        return;
      }
      // The API deliberately answers the same way for an already-registered email and issues no
      // session. Say nothing that distinguishes the two cases.
      setCheckEmail(parsed.data.email);
    } catch (error) {
      if (error instanceof ApiError && Object.keys(error.fieldErrors).length > 0) {
        setErrors(
          Object.fromEntries(
            Object.entries(error.fieldErrors).map(([key, message]) => [
              SERVER_FIELDS[key] ?? key,
              message,
            ]),
          ),
        );
      } else {
        setFormError(describeApiError(error));
      }
    } finally {
      submitting.current = false;
      setPending(false);
    }
  }

  if (checkEmail) {
    return (
      <div className="grid gap-4">
        <Alert variant="success">
          <p className="font-medium">Check your email</p>
          <p className="mt-1 text-muted-foreground">
            We sent instructions to {checkEmail}. If you already have an account, you can sign in.
          </p>
        </Alert>
        <Button asChild variant="outline">
          <Link href="/login">Go to sign in</Link>
        </Button>
      </div>
    );
  }

  return (
    <form ref={formRef} onSubmit={onSubmit} noValidate className="grid gap-4">
      {formError && <Alert variant="destructive">{formError}</Alert>}
      <TextField
        label="Your name"
        name="name"
        autoComplete="name"
        value={values.name}
        onChange={set("name")}
        error={errors.name}
      />
      <TextField
        label="Organization name"
        name="organization"
        autoComplete="organization"
        value={values.orgName}
        onChange={set("orgName")}
        error={errors.orgName}
      />
      <TextField
        label="Email"
        type="email"
        name="email"
        autoComplete="username"
        inputMode="email"
        value={values.email}
        onChange={set("email")}
        error={errors.email}
      />
      <TextField
        label="Password"
        type="password"
        name="password"
        autoComplete="new-password"
        value={values.password}
        onChange={set("password")}
        error={errors.password}
        hint={`At least ${PASSWORD_MIN} characters. A passphrase works well.`}
      />
      <Button type="submit" disabled={pending}>
        {pending ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
