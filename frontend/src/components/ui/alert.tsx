import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// soft 底 + border 描边 + foreground 文字
const alertVariants = cva("rounded-lg border p-4 text-sm", {
  variants: {
    variant: {
      default: "bg-card text-card-foreground",
      info: "border-info-border bg-info-soft text-info-foreground",
      success: "border-success-border bg-success-soft text-success-foreground",
      warning: "border-warning-border bg-warning-soft text-warning-foreground",
      destructive: "border-error-border bg-error-soft text-error-foreground",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface AlertProps
  extends
    React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {}

const Alert = React.forwardRef<HTMLDivElement, AlertProps>(
  ({ className, variant, ...props }, ref) => (
    <div
      ref={ref}
      role="alert"
      className={cn(alertVariants({ variant }), className)}
      {...props}
    />
  ),
);
Alert.displayName = "Alert";

export { Alert, alertVariants };
