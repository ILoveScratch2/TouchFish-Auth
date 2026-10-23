import { useCallback, useEffect, useState } from "react";

import { api, type SiteConfig } from "@/lib/api";

let cache: SiteConfig | null = null;

/** 站点公开配置。未登录页面也要用 */
export function useSiteConfig() {
  const [config, setConfig] = useState<SiteConfig | null>(cache);
  const [loading, setLoading] = useState(cache === null);

  const reload = useCallback(async () => {
    try {
      const result = await api.site();
      cache = result;
      setConfig(result);
      return result;
    } catch {
      return cache;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (cache === null) void reload();
  }, [reload]);

  return { config, loading, reload };
}

export function invalidateSiteConfig() {
  cache = null;
}
