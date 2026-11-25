import type { ReactNode } from "react";

/** Narrow single-column frame for the credential screens. */
export function AuthCard({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-6 px-4 py-12">
      <header className="grid gap-1">
        <p className="text-sm font-medium text-muted-foreground">Support Platform</p>
        <h1 className="text-2xl font-semibold tracking-tight text-balance">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </header>
      {children}
      {footer && <footer className="text-sm text-muted-foreground">{footer}</footer>}
    </main>
  );
}
