import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Plus } from "lucide-react";

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
import { ApiError, api, type Connection, type Instance } from "@/lib/api";
import { formatTime } from "@/lib/format";

export function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [adding, setAdding] = useState(false);
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    const [conn, inst] = await Promise.all([
      api.connections(),
      api.instances(),
    ]);
    setConnections(conn.connections);
    setInstances(inst.instances);
    setAdding(conn.connections.length === 0);
  }, []);

  useEffect(() => {
    void load().catch(() => setConnections([]));
  }, [load]);

  async function bind(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await api.bind({ identifier, password });
      setIdentifier("");
      setPassword("");
      setAdding(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "绑定失败，请稍后重试");
    } finally {
      setPending(false);
    }
  }

  async function unbind(id: string) {
    setBusyId(id);
    setError("");
    try {
      await api.unbind(id);
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "解除绑定失败，请稍后重试",
      );
    } finally {
      setBusyId("");
    }
  }

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader
        title="已连接账户"
        description="把平台账户与 TouchFish 服务器账号关联后，即可免密登录"
        actions={
          connections && connections.length > 0 && !adding ? (
            <Button variant="outline" onClick={() => setAdding(true)}>
              <Plus />
              新增连接
            </Button>
          ) : null
        }
      />

      {error ? <Alert variant="destructive">{error}</Alert> : null}

      {connections === null ? (
        <Skeleton className="h-32 w-full" />
      ) : (
        <motion.div
          variants={listContainerVariants}
          initial="initial"
          animate="animate"
          className="flex flex-col gap-4"
        >
          {connections.map((item) => (
            <motion.div key={item.id} variants={listItemVariants}>
              <Card>
                <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
                  <div className="min-w-0">
                    <CardTitle className="flex items-center gap-2">
                      {item.instance_name}
                      <StatusBadge
                        tone={
                          item.bind_channel === "platform"
                            ? "success"
                            : "warning"
                        }
                      >
                        {item.bind_channel === "platform"
                          ? "专用通道"
                          : "兼容通道"}
                      </StatusBadge>
                    </CardTitle>
                    <CardDescription className="mt-1.5">
                      {item.tfv5_username}
                      <span className="ml-2 font-mono text-xs">
                        uid {item.tfv5_uid}
                      </span>
                    </CardDescription>
                  </div>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={busyId === item.instance_id}
                    onClick={() => unbind(item.instance_id)}
                  >
                    {busyId === item.instance_id ? (
                      <Loader2 className="animate-spin" />
                    ) : null}
                    解除绑定
                  </Button>
                </CardHeader>
                <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
                  <Meta label="服务器地址" value={item.instance_url} mono />
                  <Meta label="绑定时间" value={formatTime(item.bound_at)} />
                </CardContent>
              </Card>
            </motion.div>
          ))}

          {connections.length === 0 && !adding ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
                <p className="text-sm text-muted-foreground">
                  还没有连接任何 TouchFish 服务器
                </p>
                <Button variant="outline" onClick={() => setAdding(true)}>
                  连接一个
                </Button>
              </CardContent>
            </Card>
          ) : null}

          {adding ? (
            <motion.div variants={listItemVariants}>
              <Card>
                <CardHeader>
                  <CardTitle>连接 TouchFish 账号</CardTitle>
                  <CardDescription>
                    凭据仅用于向服务器验证，不会保存在本平台
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <form className="space-y-4" onSubmit={bind}>
                    <Field>
                      <FieldLabel htmlFor="identifier">
                        用户名或数字 ID
                      </FieldLabel>
                      <Input
                        id="identifier"
                        value={identifier}
                        onChange={(event) => setIdentifier(event.target.value)}
                        aria-invalid={Boolean(error)}
                        required
                      />
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="password">密码</FieldLabel>
                      <Input
                        id="password"
                        type="password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        aria-invalid={Boolean(error)}
                        required
                      />
                      <FieldDescription>
                        服务器：{instances[0]?.base_url ?? "未配置"}
                      </FieldDescription>
                    </Field>
                    <div className="flex gap-2">
                      <Button
                        type="submit"
                        variant="primary"
                        disabled={pending}
                      >
                        {pending ? (
                          <>
                            <Loader2 className="animate-spin" />
                            正在连接…
                          </>
                        ) : (
                          "连接"
                        )}
                      </Button>
                      {connections.length > 0 ? (
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => setAdding(false)}
                        >
                          取消
                        </Button>
                      ) : null}
                    </div>
                  </form>
                </CardContent>
              </Card>
            </motion.div>
          ) : null}
        </motion.div>
      )}
    </PageWrapper>
  );
}

function Meta({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className={mono ? "mt-0.5 font-mono text-sm" : "mt-0.5 text-sm"}>
        {value}
      </div>
    </div>
  );
}
