import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { IdentifierBlock } from "@/components/identifier-block";
import { PageHeader } from "@/components/page-header";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageWrapper, listContainerVariants, listItemVariants } from "@/components/ui/motion";
import { Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";

type Summary = Awaited<ReturnType<typeof api.developer>>;

export function IntegrationPage() {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .developer()
      .then(setData)
      .catch(() => setError("读取对接信息失败，请确认你有管理员权限"));
  }, []);

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader
        title="对接"
        description="把这些值填进 TouchFish 服务器的 config.json 即可完成对接"
      />

      {error ? <Alert variant="destructive">{error}</Alert> : null}

      {!data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <motion.div
          variants={listContainerVariants}
          initial="initial"
          animate="animate"
          className="flex flex-col gap-6"
        >
          <motion.div variants={listItemVariants}>
            <Card>
              <CardHeader>
                <CardTitle>服务器侧配置</CardTitle>
                <CardDescription>
                  写入 <code className="font-mono text-xs">res/&lt;port&gt;/config.json</code>
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <IdentifierBlock label="issuer（jwt_external_issuers[].iss）" value={data.issuer} />
                <IdentifierBlock label="jwks_uri" value={data.jwks_uri} />
                <IdentifierBlock label="external_auth_url" value={data.issuer} />
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={listItemVariants}>
            <Card>
              <CardHeader>
                <CardTitle>签名密钥</CardTitle>
                <CardDescription>
                  算法 RS256，kid 为 RFC 7638 指纹；轮换后旧公钥保留 7 天
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <IdentifierBlock label="当前 kid" value={data.active_kid} />
                <IdentifierBlock label="指纹" value={data.active_fingerprint} />
                {data.all_kids.length > 1 ? (
                  <IdentifierBlock label="全部 kid" value={data.all_kids.join("\n")} />
                ) : null}
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={listItemVariants}>
            <Card>
              <CardHeader>
                <CardTitle>令牌</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
                <Meta label="external_token 有效期" value={`${data.token_ttl} 秒`} />
                <Meta label="ticket 有效期" value={`${data.ticket_ttl} 秒`} />
                <Meta label="注册策略" value={data.registration_mode} />
                <Meta label="发现文档" value={data.discovery_uri} mono />
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={listItemVariants}>
            <Card>
              <CardHeader>
                <CardTitle>已配置实例</CardTitle>
                <CardDescription>实例的增删改在「管理」页</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {data.instances.map((item) => (
                  <div key={item.id} className="rounded-lg border bg-muted px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium">{item.display_name}</span>
                      <span className="font-mono text-xs text-muted-foreground">{item.id}</span>
                    </div>
                    <div className="mt-1 break-all font-mono text-xs text-muted-foreground">
                      {item.base_url}
                    </div>
                  </div>
                ))}
                {data.instances.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    尚未配置实例，请在「管理」页添加
                  </p>
                ) : null}
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>
      )}
    </PageWrapper>
  );
}

function Meta({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className={mono ? "mt-0.5 break-all font-mono text-sm" : "mt-0.5 text-sm"}>{value}</div>
    </div>
  );
}
