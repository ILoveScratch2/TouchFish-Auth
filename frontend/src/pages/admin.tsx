import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, RotateCw, ShieldCheck } from "lucide-react";

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
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  PageWrapper,
  listContainerVariants,
  listItemVariants,
} from "@/components/ui/motion";
import { Skeleton } from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { formatTime } from "@/lib/format";

type Overview = Awaited<ReturnType<typeof api.adminOverview>>;

export function AdminPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const result = await api.adminOverview();
    setData(result);
  }, []);

  useEffect(() => {
    load().catch(() => setData(null));
  }, [load]);

  async function act(key: string, fn: () => Promise<unknown>, message: string) {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await fn();
      await load();
      setNotice(message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "操作失败，请稍后重试");
    } finally {
      setBusy("");
    }
  }

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader
        title="管理"
        description="用户权限、实例与签名密钥。管理员由运维命令行授予。"
        actions={
          <Button
            variant="outline"
            disabled={busy === "rotate"}
            onClick={() =>
              act(
                "rotate",
                api.adminRotateKeys,
                "已轮换签名密钥，旧公钥保留 7 天",
              )
            }
          >
            {busy === "rotate" ? (
              <Loader2 className="animate-spin" />
            ) : (
              <RotateCw />
            )}
            轮换密钥
          </Button>
        }
      />

      {error ? <Alert variant="destructive">{error}</Alert> : null}
      {notice ? <Alert variant="success">{notice}</Alert> : null}

      {!data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <motion.div
          variants={listContainerVariants}
          initial="initial"
          animate="animate"
          className="flex flex-col gap-6"
        >
          <motion.div
            variants={listItemVariants}
            className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5"
          >
            <Stat label="用户" value={data.stats.users} />
            <Stat label="管理员" value={data.stats.admins} />
            <Stat label="活跃会话" value={data.stats.active_sessions} />
            <Stat label="已绑定连接" value={data.stats.connections} />
            <Stat label="已绑定用户" value={data.stats.bound_users} />
          </motion.div>

          <motion.div variants={listItemVariants}>
            <Card>
              <CardHeader>
                <CardTitle>用户</CardTitle>
                <CardDescription>
                  停用会立刻吊销该用户的全部会话；管理员可在此授予或收回权限
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <div className="divide-y divide-border">
                  {data.users.map((user) => {
                    const isSelf = user.id === data.me.id;
                    return (
                      <div
                        key={user.id}
                        className="flex flex-wrap items-center justify-between gap-3 px-6 py-3"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 text-sm font-medium">
                            {user.username}
                            {user.role === "admin" ? (
                              <StatusBadge tone="info">
                                <ShieldCheck className="size-3" />
                                管理员
                              </StatusBadge>
                            ) : null}
                            {user.status === "suspended" ? (
                              <StatusBadge tone="danger">已停用</StatusBadge>
                            ) : null}
                            {isSelf ? (
                              <StatusBadge tone="neutral">我</StatusBadge>
                            ) : null}
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            创建于 {formatTime(user.created_at)}
                            {user.email ? ` · ${user.email}` : ""}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={isSelf || busy === `role-${user.id}`}
                            onClick={() =>
                              act(
                                `role-${user.id}`,
                                () =>
                                  api.adminSetRole(
                                    user.id,
                                    user.role === "admin" ? "user" : "admin",
                                  ),
                                user.role === "admin"
                                  ? "已收回管理员权限"
                                  : "已授予管理员权限",
                              )
                            }
                          >
                            {user.role === "admin" ? "收回权限" : "设为管理员"}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={isSelf || busy === `status-${user.id}`}
                            onClick={() =>
                              act(
                                `status-${user.id}`,
                                () =>
                                  api.adminSetStatus(
                                    user.id,
                                    user.status === "active"
                                      ? "suspended"
                                      : "active",
                                  ),
                                user.status === "active"
                                  ? "已停用该用户"
                                  : "已恢复该用户",
                              )
                            }
                          >
                            {user.status === "active" ? "停用" : "恢复"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy === `logout-${user.id}`}
                            onClick={() =>
                              act(
                                `logout-${user.id}`,
                                () => api.adminLogoutAll(user.id),
                                "已使该用户全部会话失效",
                              )
                            }
                          >
                            强制下线
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={listItemVariants}>
            <InstanceEditor
              existing={data.instances}
              busy={busy}
              onSave={(body) =>
                act(
                  `inst-${body.id}`,
                  () => api.adminUpsertInstance(body),
                  "实例已保存",
                )
              }
              onDelete={(id) =>
                act(
                  `del-${id}`,
                  () => api.adminDeleteInstance(id),
                  `已删除实例 ${id}`,
                )
              }
            />
          </motion.div>

          <motion.div variants={listItemVariants}>
            <Card>
              <CardHeader>
                <CardTitle>签名密钥</CardTitle>
                <CardDescription>
                  轮换后新 token 用新钥签发，旧公钥保留 7 天供对端缓存过期
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between gap-4">
                  <span className="text-xs font-medium text-muted-foreground">
                    当前 kid
                  </span>
                  <span className="font-mono">{data.keys.active_kid}</span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-xs font-medium text-muted-foreground">
                    公钥数量
                  </span>
                  <span>{data.keys.all_kids.length}</span>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>
      )}
    </PageWrapper>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function InstanceEditor({
  existing,
  busy,
  onSave,
  onDelete,
}: {
  existing: Overview["instances"];
  busy: string;
  onSave: (body: {
    id: string;
    base_url: string;
    display_name: string;
    audience?: string;
  }) => void;
  onDelete: (instanceId: string) => void;
}) {
  const first = existing[0];
  const [id, setId] = useState("main");
  const [baseUrl, setBaseUrl] = useState(
    first?.base_url ?? "http://127.0.0.1:7001",
  );
  const [name, setName] = useState(first?.display_name ?? "TouchFish");
  const [audience, setAudience] = useState(first?.audience ?? "");

  return (
    <Card>
      <CardHeader>
        <CardTitle>TouchFish 实例</CardTitle>
        <CardDescription>
          issuer 始终等于本平台地址；改动后需要同步更新服务器侧的
          jwt_external_issuers
        </CardDescription>
      </CardHeader>
      <CardContent>
        {existing.length > 0 ? (
          <div className="mb-4 space-y-2">
            {existing.map((item) => (
              <div
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-muted px-4 py-2.5"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium">
                    {item.display_name}
                    <span className="ml-2 font-mono text-xs text-muted-foreground">
                      {item.id}
                    </span>
                  </div>
                  <div className="truncate font-mono text-xs text-muted-foreground">
                    {item.base_url}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy === `del-${item.id}`}
                  onClick={() => onDelete(item.id)}
                >
                  {busy === `del-${item.id}` ? (
                    <Loader2 className="animate-spin" />
                  ) : null}
                  删除
                </Button>
              </div>
            ))}
          </div>
        ) : null}

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            onSave({
              id,
              base_url: baseUrl,
              display_name: name,
              audience: audience || undefined,
            });
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="inst-id">实例 ID</FieldLabel>
              <Input
                id="inst-id"
                value={id}
                onChange={(event) => setId(event.target.value)}
                pattern="[a-z0-9_-]+"
                required
              />
              <FieldDescription>
                小写字母、数字、下划线或连字符
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="inst-name">显示名</FieldLabel>
              <Input
                id="inst-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </Field>
          </div>
          <Field>
            <FieldLabel htmlFor="inst-url">服务器地址</FieldLabel>
            <Input
              id="inst-url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              required
            />
            <FieldDescription>
              例如 https://touchfish.xin，不带结尾斜杠
            </FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="inst-aud">audience（可选）</FieldLabel>
            <Input
              id="inst-aud"
              value={audience}
              onChange={(event) => setAudience(event.target.value)}
            />
            <FieldDescription>
              须与服务器 jwt_external_issuers[].audience 一致
            </FieldDescription>
          </Field>
          <Button type="submit" disabled={busy === `inst-${id}`}>
            {busy === `inst-${id}` ? (
              <Loader2 className="animate-spin" />
            ) : null}
            保存实例
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
