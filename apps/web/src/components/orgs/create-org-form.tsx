"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";

import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import { useAuth } from "@/lib/auth/auth-context";
import { storeOrgId } from "@/lib/orgs";
import { fieldErrorsFromZod, orgNameSchema } from "@/lib/validation";
import type { FieldErrors } from "@/lib/validation";

import { TextField, useFocusFirstInvalid } from "../form/text-field";

export function CreateOrgForm() {
  const router = useRouter();
  const { refresh } = useAuth();
  const formRef = useRef<HTMLFormElement>(null);
  const [name, setName] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useFocusFirstInvalid(formRef, errors);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setFormError(null);
    const parsed = orgNameSchema.safeParse({ name });
    if (!parsed.success) {
      setErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setErrors({});
    setPending(true);
    try {
      const org = await api.createOrg(parsed.data.name);
      await refresh();
      storeOrgId(org.id);
      router.push(`/orgs/${encodeURIComponent(org.id)}`);
    } catch (error) {
      setFormError(describeApiError(error));
      setPending(false);
    }
  }

  return (
    <form ref={formRef} onSubmit={onSubmit} noValidate className="grid max-w-sm gap-4">
      {formError && <Alert variant="destructive">{formError}</Alert>}
      <TextField
        label="Organization name"
        name="organization"
        autoComplete="organization"
        value={name}
        onChange={(event) => setName(event.target.value)}
        error={errors.name}
      />
      <Button type="submit" disabled={pending} className="justify-self-start">
        {pending ? "Creating…" : "Create organization"}
      </Button>
    </form>
  );
}
