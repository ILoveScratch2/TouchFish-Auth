import { StatusBadge } from "@/components/ui/badge";
import { PageHeader } from "@/components/page-header";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageWrapper } from "@/components/ui/motion";
import { IdentifierBlock } from "@/components/identifier-block";
import { useSiteConfig } from "@/lib/site";

/**
 * 开发者页：集成分类下的第三方 OAuth 应用入口
 */
export function DeveloperPage() {
  const { config } = useSiteConfig();
  const policy = config?.oauth_apps;
  const selfService = policy?.self_service ?? false;
  const limit = policy?.max_per_user ?? 0;

  return (
    <PageWrapper className="flex flex-col gap-6">
      <PageHeader
        title="开发者"
        description="第三方 OAuth 应用（集成分类）"
        actions={<StatusBadge tone="warning">未开放</StatusBadge>}
      />

      <Alert variant="info">
        这一页用于让其他应用通过 TouchFish Auth 完成登录（我们也要有 OAuth）。尚未实现！
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>当前策略</CardTitle>
          <CardDescription>由管理员设置</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">自助创建</span>
            <span>{selfService ? "允许，你可自行创建应用" : "仅管理员可创建"}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">每人上限</span>
            <span>{selfService ? `${limit} 个` : "—"}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">功能状态</span>
            <StatusBadge tone="warning">尚未实现</StatusBadge>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>协议（Plan）</CardTitle>
          <CardDescription>
            沿用现有 ticket external_token 的两段式，不给第三方直接发长期凭据
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <IdentifierBlock
            label="授权端点"
            value="/authorize?client_id=&state=&response_mode=bridge"
          />
          <IdentifierBlock label="换 ticket 端点" value="/api/auth/ticket" />
          <IdentifierBlock label="发现文档" value="/.well-known/openid-configuration" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>接入后</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li>创建 / 停用 OAuth 应用，签发 client_id 与 client_secret</li>
            <li>为每个应用配置回调地址白名单与允许的 scope</li>
            <li>按应用统计授权次数与失败原因</li>
            <li>应用级限流与审计</li>
          </ul>
        </CardContent>
      </Card>
    </PageWrapper>
  );
}
