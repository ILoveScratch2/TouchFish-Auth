import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";

interface IdentifierBlockProps {
  label?: string;
  value: string;
}

export function IdentifierBlock({ label, value }: IdentifierBlockProps) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="rounded-lg border bg-muted px-4 py-3">
      {label ? (
        <div className="mb-1.5 text-xs font-medium text-muted-foreground">{label}</div>
      ) : null}
      <div className="flex items-start gap-3">
        <code className="min-w-0 flex-1 font-mono text-sm [overflow-wrap:anywhere]">{value}</code>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={copy}
          aria-label={copied ? "已复制" : "复制"}
          className="shrink-0"
        >
          {copied ? <Check className="text-success" /> : <Copy />}
        </Button>
      </div>
    </div>
  );
}
