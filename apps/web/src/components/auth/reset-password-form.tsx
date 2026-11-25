"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";

import { api, ApiError } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import { fieldErrorsFromZod, PASSWORD_MIN, resetPasswordSchema } from "@/lib/validation";
import type { FieldErrors } from "@/lib/validation";

import { TextField, useFocusFirstInvalid } from "../form/text-field";

export function ResetPasswordForm({ token }: { token: string | null }) {
  const formRef = useRef<HTMLFormElement>(null);
  const [values, setValues] = useState({ password: "", confirm: "" });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [tokenDead, setTokenDead] = useState(false);
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);

  useFocusFirstInvalid(formRef, errors);

  if (!token) {
    return (
      <div className="grid gap-4">
        <Alert variant="destructive">This reset link is missing or incomplete.</Alert>
        <Link href="/forgot-password" className="text-sm underline underline-offset-4">
          Request a new link
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="grid gap-4">
        <Alert variant="success">Password updated. You were signed out everywhere else.</Alert>
        <Button asChild>
          <Link href="/login">Sign in</Link>
        </Button>
      </div>
    );
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending || !token) return;
    setFormError(null);

    const parsed = resetPasswordSchema.safeParse(values);
    if (!parsed.success) {
      setErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setErrors({});

    setPending(true);
    try {
      await api.resetPassword(token, parsed.data.password);
      setDone(true);
    } catch (error) {
      if (error instanceof ApiError && error.code === "invalid_token") {
        setTokenDead(true);
      }
      if (error instanceof ApiError && error.fieldErrors.password) {
        setErrors({ password: error.fieldErrors.password });
      } else {
        setFormError(describeApiError(error));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form ref={formRef} onSubmit={onSubmit} noValidate className="grid gap-4">
      {formError && <Alert variant="destructive">{formError}</Alert>}
      {tokenDead && (
        <Link href="/forgot-password" className="text-sm underline underline-offset-4">
          Request a new link
        </Link>
      )}
      <TextField
        label="New password"
        type="password"
        name="password"
        autoComplete="new-password"
        value={values.password}
        onChange={(event) => setValues((v) => ({ ...v, password: event.target.value }))}
        error={errors.password}
        hint={`At least ${PASSWORD_MIN} characters.`}
      />
      <TextField
        label="Confirm new password"
        type="password"
        name="confirm"
        autoComplete="new-password"
        value={values.confirm}
        onChange={(event) => setValues((v) => ({ ...v, confirm: event.target.value }))}
        error={errors.confirm}
      />
      <Button type="submit" disabled={pending}>
        {pending ? "Saving…" : "Set new password"}
      </Button>
    </form>
  );
}
