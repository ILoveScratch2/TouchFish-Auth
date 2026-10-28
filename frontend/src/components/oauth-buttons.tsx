import { Github, KeyRound, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useSiteConfig } from "@/lib/site";

const ICONS: Record<string, LucideIcon> = {
  github: Github,
};

function startUrl(providerId: string, next: string): string {
  return `/api/auth/oauth/${encodeURIComponent(providerId)}/start?redirect=${encodeURIComponent(next)}`;
}

export function OAuthButtons({
  next,
  disabled,
}: {
  next: string;
  disabled?: boolean;
}) {
  const { config } = useSiteConfig();
  const providers = config?.oauth_providers ?? [];
  if (providers.length === 0) return null;

  return (
    <div className="space-y-2">
      {providers.map((provider) => {
        const Icon = ICONS[provider.id] ?? KeyRound;
        return (
          <Button
            key={provider.id}
            type="button"
            variant="outline"
            className="w-full justify-start"
            disabled={disabled}
            onClick={() => {
              window.location.href = startUrl(provider.id, next);
            }}
          >
            <Icon />
            <span className="flex-1 text-left">使用 {provider.name} 继续</span>
          </Button>
        );
      })}
    </div>
  );
}

const ERROR_TEXT: Record<string, string> = {
  access_denied: "已取消第三方授权",
  state_invalid: "授权会话已失效，请重新发起登录",
  provider_unavailable: "该登录方式当前不可用",
  provider_unreachable: "无法连接第三方平台，请稍后重试",
  token_failed: "第三方平台未返回访问令牌，请重试",
  profile_failed: "无法读取第三方账号信息",
  register_disabled: "本站未开放注册，无法自动开通账号",
  create_failed: "自动开通账号失败，请联系管理员",
  already_linked: "该第三方账号已绑定到其他平台账户",
};

export function oauthErrorText(code: string): string {
  return ERROR_TEXT[code] ?? "第三方登录失败，请稍后重试";
}
