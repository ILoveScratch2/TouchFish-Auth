import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Alert } from "@/components/ui/alert";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageWrapper, listContainerVariants, listItemVariants } from "@/components/ui/motion";
import { Skeleton } from "@/components/ui/primitives";
import { ApiError, api, type SessionRow } from "@/lib/api";
import { describeAgent, formatTime } from "@/lib/format";

export function SessionsPage() {
  const [rows, setRows] = useState<SessionRow[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    const result = await api.sessions();
    setRows(result.sessions);
  }, []);

  useEffect(() => {
    void load().catch(() => setRows([]));
  }, [load]);

  async function revoke(id: string) {
    setBusy(id);
    setError("");
    try {
      await api.revokeSession(id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "退出失败，请稍后重试");
    } finally {
      setBusy("");
    }
  }

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader title="登录设备" description="这些浏览器会话可以访问你的账户" />

      {error ? <Alert variant="destructive">{error}</Alert> : null}

      {rows === null ? (
        <Skeleton className="h-28 w-full" />
      ) : (
        <motion.div
          variants={listContainerVariants}
          initial="initial"
          animate="animate"
          className="flex flex-col gap-3"
        >
          {rows.map((row) => (
            <motion.div key={row.id} variants={listItemVariants}>
              <Card>
                <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      {describeAgent(row.user_agent)}
                      {row.current ? <StatusBadge tone="info">当前设备</StatusBadge> : null}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      最近活动 {formatTime(row.last_seen_at)} · IP {row.ip || "未知"}
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={row.current || busy === row.id}
                    onClick={() => revoke(row.id)}
                  >
                    {busy === row.id ? <Loader2 className="animate-spin" /> : null}
                    {row.current ? "当前会话" : "退出"}
                  </Button>
                </CardContent>
              </Card>
            </motion.div>
          ))}

          {rows.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                没有其他活动会话
              </CardContent>
            </Card>
          ) : null}
        </motion.div>
      )}
    </PageWrapper>
  );
}
