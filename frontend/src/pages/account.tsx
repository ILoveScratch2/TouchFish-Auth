import { useState } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PageWrapper, listContainerVariants, listItemVariants } from "@/components/ui/motion";
import { ApiError, api } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { useSession } from "@/lib/session";

export function AccountPage() {
  const { user, refresh } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  if (!user) return null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    setMessage("");
    try {
      await api.changePassword({
        current_password: user!.has_password ? current : undefined,
        new_password: next,
      });
      setCurrent("");
      setNext("");
      setMessage("密码已更新，其他设备已退出登录");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新失败，请稍后重试");
    } finally {
      setPending(false);
    }
  }

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader title="账户" description="管理你的 TouchFish Auth 身份" />

      <motion.div
        variants={listContainerVariants}
        initial="initial"
        animate="animate"
        className="grid gap-6 lg:grid-cols-2"
      >
        <motion.div variants={listItemVariants}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>基本信息</CardTitle>
              <CardDescription>这些信息用于向 TouchFish 标识你</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Row label="用户名" value={user.username} mono />
              <Row label="显示名" value={user.display_name ?? user.username} />
              <Row label="邮箱" value={user.email ?? "未设置"} />
              <Row label="创建时间" value={formatTime(user.created_at)} />
              <Row label="平台密码" value={user.has_password ? "已设置" : "未设置"} />
              <Row label="权限" value={user.role === "admin" ? "管理员" : "普通用户"} />
            </CardContent>
          </Card>
        </motion.div>

        <motion.div variants={listItemVariants}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>{user.has_password ? "修改密码" : "设置密码"}</CardTitle>
              <CardDescription>
                {user.has_password
                  ? "修改后其他设备会被退出登录"
                  : "当前账号只能通过 TouchFish 登录，设置密码后可直接登录"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={submit}>
                {error ? <Alert variant="destructive">{error}</Alert> : null}
                {message ? <Alert variant="success">{message}</Alert> : null}

                {user.has_password ? (
                  <Field>
                    <FieldLabel htmlFor="current">当前密码</FieldLabel>
                    <Input
                      id="current"
                      type="password"
                      autoComplete="current-password"
                      value={current}
                      onChange={(event) => setCurrent(event.target.value)}
                      required
                    />
                  </Field>
                ) : null}

                <Field>
                  <FieldLabel htmlFor="next">新密码</FieldLabel>
                  <Input
                    id="next"
                    type="password"
                    autoComplete="new-password"
                    value={next}
                    onChange={(event) => setNext(event.target.value)}
                    required
                  />
                  <FieldDescription>至少 8 位</FieldDescription>
                </Field>

                <Button type="submit" variant="primary" disabled={pending}>
                  {pending ? (
                    <>
                      <Loader2 className="animate-spin" />
                      正在保存…
                    </>
                  ) : (
                    "保存"
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </motion.div>
      </motion.div>
    </PageWrapper>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border pb-2 last:border-0 last:pb-0">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono text-sm" : "text-sm"}>{value}</span>
    </div>
  );
}
