"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";

import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import { useAuth } from "@/lib/auth/auth-context";
import { safeRedirectPath } from "@/lib/safe-redirect";
import { fieldErrorsFromZod, loginSchema } from "@/lib/validation";
import type { FieldErrors } from "@/lib/validation";

import { TextField, useFocusFirstInvalid } from "../form/text-field";

export function LoginForm({ next }: { next?: string | null }) {
  const router = useRouter();
  const { setSession } = useAuth();
  const formRef = useRef<HTMLFormElement>(null);
  const submitting = useRef(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useFocusFirstInvalid(formRef, errors);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current) return;
    setFormError(null);

    const parsed = loginSchema.safeParse({ email, password });
    if (!parsed.success) {
      setErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setErrors({});

    submitting.current = true;
    setPending(true);
    try {
      const me = await api.login(parsed.data);
      setSession(me);
      router.replace(safeRedirectPath(next));
    } catch (error) {
      setFormError(describeApiError(error));
      setPassword("");
      submitting.current = false;
      setPending(false);
    }
  }

  return (
    <form ref={formRef} onSubmit={onSubmit} noValidate className="grid gap-4">
      {formError && <Alert variant="destructive">{formError}</Alert>}
      <TextField
        label="Email"
        type="email"
        name="email"
        autoComplete="username"
        inputMode="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        error={errors.email}
      />
      <div className="grid gap-1.5">
        <TextField
          label="Password"
          type="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={errors.password}
        />
        <Link
          href="/forgot-password"
          className="justify-self-end text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Forgot password?
        </Link>
      </div>
      <Button type="submit" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
