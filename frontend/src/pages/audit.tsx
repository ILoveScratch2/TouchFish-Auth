import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";

import { PageHeader } from "@/components/page-header";
import { Alert } from "@/components/ui/alert";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  PageWrapper,
  listContainerVariants,
  listItemVariants,
} from "@/components/ui/motion";
import { Skeleton } from "@/components/ui/primitives";
import { api, type AuditEntry } from "@/lib/api";
import { formatTime } from "@/lib/format";

const TONE: Record<
  string,
  "neutral" | "success" | "warning" | "info" | "danger"
> = {
  failed: "danger",
  blocked: "danger",
};

function toneFor(
  event: string,
): "neutral" | "success" | "warning" | "info" | "danger" {
  if (event.includes("failed") || event.includes("blocked")) return "danger";
  if (event.startsWith("admin.") || event.startsWith("cli.")) return "info";
  if (event.startsWith("mail.")) return "warning";
  if (
    event.includes("register") ||
    event.includes("login") ||
    event.includes("verified")
  ) {
    return "success";
  }
  return TONE.neutral;
}

export function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [applied, setApplied] = useState("");

  const load = useCallback(async (event: string) => {
    const result = await api.adminAudit(200, event);
    setEntries(result.entries);
  }, []);

  useEffect(() => {
    load(applied).catch(() =>
      setError("读取审计日志失败，请确认你有管理员权限"),
    );
  }, [load, applied]);

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader
        title="审计日志"
        description="最近 200 条"
        actions={
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setApplied(filter.trim());
            }}
          >
            <Input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="按事件前缀筛选，如 user."
              className="w-56"
            />
            <Button type="submit" variant="outline">
              筛选
            </Button>
            {applied ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setFilter("");
                  setApplied("");
                }}
              >
                清除
              </Button>
            ) : null}
          </form>
        }
      />

      {error ? <Alert variant="destructive">{error}</Alert> : null}

      {entries === null ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <motion.div
          variants={listContainerVariants}
          initial="initial"
          animate="animate"
        >
          <motion.div variants={listItemVariants}>
            <Card>
              <CardHeader>
                <CardTitle>
                  {applied ? `筛选：${applied}*` : "全部事件"}
                </CardTitle>
                <CardDescription>共 {entries.length} 条</CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <div className="divide-y divide-border">
                  {entries.map((entry) => (
                    <div key={entry.id} className="px-6 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge tone={toneFor(entry.event)}>
                          {entry.event}
                        </StatusBadge>
                        <span className="text-xs text-muted-foreground">
                          {formatTime(entry.at)}
                        </span>
                        {entry.ip ? (
                          <span className="font-mono text-xs text-muted-foreground">
                            {entry.ip}
                          </span>
                        ) : null}
                      </div>
                      {entry.detail ? (
                        <div className="mt-1 break-all font-mono text-xs text-muted-foreground">
                          {entry.detail}
                        </div>
                      ) : null}
                      {entry.user_id ? (
                        <div className="mt-0.5 font-mono text-[11px] text-muted-foreground/70">
                          uid {entry.user_id}
                        </div>
                      ) : null}
                    </div>
                  ))}
                  {entries.length === 0 ? (
                    <div className="px-6 py-8 text-center text-sm text-muted-foreground">
                      没有匹配的日志
                    </div>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>
      )}
    </PageWrapper>
  );
}
