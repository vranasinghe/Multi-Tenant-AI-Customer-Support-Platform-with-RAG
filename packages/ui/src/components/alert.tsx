import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "../lib/utils";

const alertVariants = cva("w-full rounded-md border px-4 py-3 text-sm", {
  variants: {
    variant: {
      default: "bg-muted/50 text-foreground",
      destructive: "border-destructive/40 bg-destructive/5 text-destructive",
      success: "border-success/40 bg-success/5 text-foreground",
    },
  },
  defaultVariants: { variant: "default" },
});

/** Errors use role="alert" (announced immediately); everything else uses role="status". */
function Alert({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return (
    <div
      data-slot="alert"
      role={variant === "destructive" ? "alert" : "status"}
      className={cn(alertVariants({ variant }), className)}
      {...props}
    />
  );
}

export { Alert };
