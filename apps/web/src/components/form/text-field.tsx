"use client";

import { useEffect, useId } from "react";
import type { ComponentProps, ReactNode, RefObject } from "react";

import { Input } from "@acs/ui/components/input";
import { Label } from "@acs/ui/components/label";

interface TextFieldProps extends Omit<ComponentProps<"input">, "id"> {
  label: string;
  error?: string;
  hint?: ReactNode;
}

/** Label + input + hint + error, wired together for assistive tech (aria-invalid/-describedby). */
export function TextField({ label, error, hint, className, ...input }: TextFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");

  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        className={className}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        {...input}
      />
      {hint && (
        <p id={hintId} className="text-sm text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

/** After a failed validation, move focus to the first invalid control. */
export function useFocusFirstInvalid(
  formRef: RefObject<HTMLFormElement | null>,
  errors: Record<string, string>,
) {
  useEffect(() => {
    if (Object.keys(errors).length === 0) return;
    formRef.current?.querySelector<HTMLElement>("[aria-invalid='true']")?.focus();
  }, [errors, formRef]);
}
