import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, KeyRound, ShieldCheck, Users } from "lucide-react";

import { IdentifierBlock } from "@/components/identifier-block";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageWrapper } from "@/components/ui/motion";
import { useSiteName } from "@/lib/site";

type Discovery = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  userinfo_endpoint: string;
  jwks_uri: string;
  scopes_supported: string[];
};

const SCOPES: { id: string; title: string; detail: string }[] = [
  {
    id: "openid",
    title: "确认身份",
    detail: "返回一个稳定不变的账号标识（sub）",
  },
  { id: "profile", title: "基本资料", detail: "用户名与昵称" },
  { id: "email", title: "邮箱地址", detail: "邮箱与是否已验证" },
];

const FLOW = [
  "应用重定向到本站授权",
  "登录并确认要授予的权限范围",
  "本站把授权码回传到回调地址",
  "应用用它换取信息",
];


export function AboutPage() {
  const siteName = useSiteName();
  const [discovery, setDiscovery] = useState<Discovery | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/.well-known/openid-configuration")
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!cancelled) setDiscovery(data);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="h-dvh overflow-y-auto overscroll-contain bg-background p-4 sm:p-8">
      <PageWrapper className="mx-auto flex w-full max-w-3xl flex-col gap-6 pb-8">
        <header className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <img
              src="/logo.png"
              alt={siteName}
              className="size-10 rounded-xl border bg-background object-contain p-1"
            />
            <div>
              <h1 className="font-display text-2xl font-semibold">
                {siteName}
              </h1>
              <p className="mt-0.5 text-sm text-muted-foreground">
                The Ultimate Authorize Platform for TouchFish
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" asChild>
              <Link to="/login">
                回到登录
                <ArrowRight className="size-3.5" />
              </Link>
            </Button>
          </div>
        </header>

        <Card>
          <CardHeader>
            <CardTitle>介绍</CardTitle>
            <CardDescription>
              TouchFish 的认证与授权平台
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="flex gap-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <p>
                <span className="font-medium">对外签发令牌</span>
                ：第三方应用按标准 OIDC 授权接入，获得
                <code className="mx-1 font-mono text-xs">openid</code>
                <code className="mx-1 font-mono text-xs">profile</code>
                <code className="mx-1 font-mono text-xs">email</code>
                范围内的信息。
              </p>
            </div>
            <div className="flex gap-3">
              <Users className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <p>
                <span className="font-medium">对内统一账号</span>
                ：可以把本站账号与 TouchFish 服务器账号关联。
              </p>
            </div>
            <div className="flex gap-3">
              <KeyRound className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <p>
                <span className="font-medium">凭据安全存储</span>
                ：使用安全哈希算法存储凭据，不保存 TouchFish 服务器内账户密码。
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>端点</CardTitle>
            <CardDescription>
              标准 OIDC 配置
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {discovery ? (
              <>
                <IdentifierBlock label="Issuer" value={discovery.issuer} />
                <IdentifierBlock
                  label="授权端点"
                  value={discovery.authorization_endpoint}
                />
                <IdentifierBlock
                  label="令牌端点"
                  value={discovery.token_endpoint}
                />
                <IdentifierBlock
                  label="用户信息"
                  value={discovery.userinfo_endpoint}
                />
                <IdentifierBlock label="公钥" value={discovery.jwks_uri} />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">正在读取文档…</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>权限范围</CardTitle>
            <CardDescription>
              授权时可申请
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {SCOPES.map((scope) => (
              <div
                key={scope.id}
                className="flex flex-wrap items-baseline gap-2"
              >
                <StatusBadge tone="neutral" className="font-mono">
                  {scope.id}
                </StatusBadge>
                <span className="font-medium">{scope.title}</span>
                <span className="text-muted-foreground">{scope.detail}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>登录流程</CardTitle>
            <CardDescription>标准认证</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="space-y-3 text-sm">
              {FLOW.map((step, index) => (
                <li key={step} className="flex gap-3">
                  <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border text-xs text-muted-foreground">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>

        <footer className="pt-2 text-center text-xs text-muted-foreground">
          {siteName} Developed by ILoveScratch2(YWD2023)
        </footer>
      </PageWrapper>
    </div>
  );
}
