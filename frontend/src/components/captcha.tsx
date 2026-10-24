import { useEffect, useRef, useState } from "react";

type Provider = "turnstile" | "hcaptcha";

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, options: Record<string, unknown>) => string;
      remove: (id: string) => void;
      reset: (id?: string) => void;
    };
    hcaptcha?: {
      render: (el: HTMLElement, options: Record<string, unknown>) => string;
      remove: (id: string) => void;
      reset: (id?: string) => void;
    };
  }
}

const SCRIPTS: Record<Provider, string> = {
  turnstile:
    "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit",
  hcaptcha: "https://js.hcaptcha.com/1/api.js?render=explicit",
};

const loaded = new Set<string>();

function loadScript(src: string): Promise<void> {
  if (loaded.has(src)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${src}"]`,
    );
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () =>
        reject(new Error("script error")),
      );
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.defer = true;
    script.onload = () => {
      loaded.add(src);
      resolve();
    };
    script.onerror = () => reject(new Error("script error"));
    document.head.appendChild(script);
  });
}

interface CaptchaWidgetProps {
  provider: Provider;
  siteKey: string;
  onToken: (token: string | null) => void;
  /** 递增这个值可强制重置组件 */
  resetSignal?: number;
}

/**
 * Turnstile / hCaptcha 的显式渲染封装
 */
export function CaptchaWidget({
  provider,
  siteKey,
  onToken,
  resetSignal = 0,
}: CaptchaWidgetProps) {
  const container = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const [error, setError] = useState("");
  const firstRun = useRef(true);

  useEffect(() => {
    // 首次渲染由下面的 effect 负责
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    const api = provider === "turnstile" ? window.turnstile : window.hcaptcha;
    if (widgetId.current && api?.reset) {
      try {
        api.reset(widgetId.current);
      } catch {
        /* 组件已卸载，忽略 */
      }
    }
    onToken(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetSignal]);

  useEffect(() => {
    let cancelled = false;
    if (!siteKey) return;

    loadScript(SCRIPTS[provider])
      .then(() => {
        if (cancelled || !container.current) return;
        const api =
          provider === "turnstile" ? window.turnstile : window.hcaptcha;
        if (!api) {
          setError("验证组件未能加载");
          return;
        }
        const id = api.render(container.current, {
          sitekey: siteKey,
          callback: (token: string) => onToken(token),
          "expired-callback": () => onToken(null),
          "error-callback": () => {
            onToken(null);
            setError("验证组件报错，请刷新重试");
          },
        });
        widgetId.current = id;
      })
      .catch(() => {
        if (!cancelled) setError("验证组件未能加载，请检查网络");
      });

    return () => {
      cancelled = true;
      const api = provider === "turnstile" ? window.turnstile : window.hcaptcha;
      if (widgetId.current && api) {
        try {
          api.remove(widgetId.current);
        } catch {
          /* 组件已卸载，忽略 */
        }
        widgetId.current = null;
      }
      onToken(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider, siteKey]);

  return (
    <div className="space-y-1">
      <div ref={container} />
      {error ? <p className="text-xs text-error-foreground">{error}</p> : null}
    </div>
  );
}
