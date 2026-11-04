import { useCallback, useEffect, useState } from "react";

import { api, type SiteConfig } from "@/lib/api";

/** 站点尚未加载完成 */
export const DEFAULT_SITE_NAME = "TouchFish Auth";

let cache: SiteConfig | null = null;
// 只发一次请求
let inflight: Promise<SiteConfig | null> | null = null;
const listeners = new Set<() => void>();

/** 站点公开配置。未登录页面也要用 */
export function useSiteConfig() {
  const [config, setConfig] = useState<SiteConfig | null>(cache);
  const [loading, setLoading] = useState(cache === null);

  const reload = useCallback(async () => {
    const request = (inflight ??= (async () => {
      try {
        const result = await api.site();
        cache = result;
        return result;
      } catch {
        return cache;
      } finally {
        inflight = null;
      }
    })());
    const result = await request;
    if (result) setConfig(result);
    setLoading(false);
    return result;
  }, []);

  useEffect(() => {
    if (cache === null) void reload();
  }, [reload]);
  useEffect(() => {
    const onInvalidate = () => {
      void reload();
    };
    listeners.add(onInvalidate);
    return () => {
      listeners.delete(onInvalidate);
    };
  }, [reload]);

  return { config, loading, reload };
}

export function useSiteName(): string {
  const { config } = useSiteConfig();
  return config?.site_name?.trim() || DEFAULT_SITE_NAME;
}

export function splitSiteName(name: string): [string, string] {
  const trimmed = name.trim();
  const cut = trimmed.indexOf(" ");
  if (cut <= 0) return [trimmed, ""];
  return [trimmed.slice(0, cut), trimmed.slice(cut + 1).trim()];
}

export function invalidateSiteConfig() {
  cache = null;
  inflight = null;
  for (const notify of listeners) notify();
}
