import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  authContainerVariants,
  authItemVariants,
  easings,
} from "@/components/ui/motion";
import { ShellThemeToggle } from "@/components/app-shell";
import { cn } from "@/lib/utils";

interface AuthLayoutProps {
  title: string;
  description?: ReactNode;
  eyebrow?: string;
  footer?: ReactNode;
  children: ReactNode;
}


export function AuthLayout({ title, description, eyebrow, footer, children }: AuthLayoutProps) {
  const reduced = useReducedMotion();
  return (
    <div className="h-dvh overflow-y-auto overscroll-contain p-4">
      <div className="flex min-h-full flex-col gap-4">
        <motion.div
          className="flex shrink-0 justify-end gap-2"
          initial={reduced ? { opacity: 0 } : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={reduced ? { duration: 0 } : { duration: 0.15 }}
        >
          <ShellThemeToggle />
        </motion.div>

        <motion.div
          initial="hidden"
          animate="visible"
          variants={reduced ? undefined : authContainerVariants}
          className="my-auto w-full max-w-md shrink-0 self-center"
        >
          <Card className="overflow-hidden">
            <CardHeader className="text-center">
              <motion.div
                variants={reduced ? undefined : authItemVariants}
                className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border bg-background p-2 text-foreground"
              >
                <img src="/logo.png" alt="TouchFish" className="h-full w-full object-contain" />
              </motion.div>
              {eyebrow ? (
                <motion.div variants={reduced ? undefined : authItemVariants}>
                  <p className="text-xs text-muted-foreground">{eyebrow}</p>
                </motion.div>
              ) : null}
              <motion.div variants={reduced ? undefined : authItemVariants}>
                <CardTitle className="font-display text-2xl">{title}</CardTitle>
              </motion.div>
              {description ? (
                <motion.div variants={reduced ? undefined : authItemVariants}>
                  <CardDescription>{description}</CardDescription>
                </motion.div>
              ) : null}
            </CardHeader>
            <CardContent>{children}</CardContent>
          </Card>
          {footer ? (
            <motion.div
              initial={reduced ? { opacity: 0 } : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={
                reduced ? { duration: 0 } : { duration: 0.3, ease: easings.easeOutExpo, delay: 0.25 }
              }
              className="mt-4 text-center text-sm text-muted-foreground"
            >
              {footer}
            </motion.div>
          ) : null}
        </motion.div>
      </div>
    </div>
  );
}

/** 单个入场元素。放在 AuthLayout 内会自动继承错开 */
export function AuthItem({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div variants={reduced ? undefined : authItemVariants} className={className}>
      {children}
    </motion.div>
  );
}

/** 表单内部字段再错开一次 */
export function AuthForm({
  children,
  onSubmit,
  className,
}: {
  children: ReactNode;
  onSubmit: (event: React.FormEvent) => void;
  className?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.form
      variants={reduced ? undefined : authContainerVariants}
      onSubmit={onSubmit}
      className={cn("space-y-4", className)}
    >
      {children}
    </motion.form>
  );
}
