import { Github, KeyRound, Server, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AuthMethod } from "@/lib/api";

const ICONS: Record<string, LucideIcon> = {
  password: KeyRound,
  tfv5: Server,
  github: Github,
};

export function MethodButton({
  method,
  onClick,
  disabled,
}: {
  method: AuthMethod;
  onClick: () => void;
  disabled?: boolean;
}) {
  const Icon = ICONS[method.id] ?? ICONS[method.kind] ?? KeyRound;
  return (
    <Button
      type="button"
      variant="outline"
      className="w-full justify-start"
      onClick={onClick}
      disabled={disabled}
    >
      <Icon />
      <span className="flex-1 text-left">{method.display_name}</span>
    </Button>
  );
}

export function OrDivider() {
  return (
    <div className="flex items-center gap-4 py-1">
      <div className="h-px flex-1 bg-border" />
      <span className="text-xs text-muted-foreground">或</span>
      <div className="h-px flex-1 bg-border" />
    </div>
  );
}
