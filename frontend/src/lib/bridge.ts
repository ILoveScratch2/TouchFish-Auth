// hosted 授权页与应用之间的回传
// 原生（Flutter InAppWebView）：window.flutter_inappwebview.callHandler
// Web（iframe）：window.parent.postMessage
// 都不在：返回 false，页面降级为"显示票据文本"

declare global {
  interface Window {
    flutter_inappwebview?: {
      callHandler: (name: string, ...args: unknown[]) => Promise<unknown>;
    };
  }
}

export const BRIDGE_HANDLER = "touchfishAuthDone";

export type BridgePayload = {
  type: "touchfish-auth:done";
  state: string | null;
  ticket: string;
  expires_in: number;
};

export function deliverTicket(payload: BridgePayload): boolean {
  if (typeof window === "undefined") return false;

  if (window.flutter_inappwebview?.callHandler) {
    void window.flutter_inappwebview.callHandler(BRIDGE_HANDLER, payload);
    return true;
  }

  if (window.parent && window.parent !== window) {
    window.parent.postMessage(payload, "*");
    return true;
  }

  return false;
}

export function readQuery(name: string): string | null {
  const params = new URLSearchParams(window.location.search);
  const value = params.get(name);
  return value && value.length > 0 ? value : null;
}
