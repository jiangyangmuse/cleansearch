/** Service Worker 注册与更新提示；只在生产构建里启用，避免开发热更新被缓存干扰。 */
const UPDATE_EVENT = "cs:sw-update";
let registration: ServiceWorkerRegistration | undefined;

export function waitingServiceWorker() {
  return registration?.waiting ?? null;
}

export function registerServiceWorker(): void {
  if (!import.meta.env.PROD) return;
  if (!("serviceWorker" in navigator)) return;

  const register = async () => {
    try {
      const workerRegistration = await navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" });
      registration = workerRegistration;

      // 首次安装直接接管；后续更新等用户在提示里确认
      const notify = () => window.dispatchEvent(new Event(UPDATE_EVENT));
      const watchInstall = () => {
        const installing = workerRegistration.installing;
        if (installing) installing.addEventListener("statechange", notify);
      };
      watchInstall();
      notify();
      workerRegistration.addEventListener("updatefound", watchInstall);
      navigator.serviceWorker.addEventListener("controllerchange", notify);
      // 每小时检查一次更新；页面重新可见时也查一次
      window.setInterval(() => void workerRegistration.update().catch(() => {}), 60 * 60 * 1000);
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") void workerRegistration.update().catch(() => {});
      });
    } catch {
      // 注册失败（非安全上下文、隐私模式）不影响主应用
    }
  };

  if (document.readyState === "complete") void register();
  else window.addEventListener("load", () => void register(), { once: true });
}

/** 让等待中的新版本立即接管，然后由调用方刷新页面。 */
export function applyServiceWorkerUpdate(worker: ServiceWorker): Promise<boolean> {
  const serviceWorker = navigator.serviceWorker;
  return new Promise(resolve => {
    const finish = (activated: boolean) => {
      window.clearTimeout(timer);
      serviceWorker.removeEventListener("controllerchange", check);
      resolve(activated);
    };
    const check = () => {
      if (serviceWorker.controller === worker) finish(true);
    };
    const timer = window.setTimeout(() => finish(false), 8000);
    serviceWorker.addEventListener("controllerchange", check);
    if (serviceWorker.controller === worker) check();
    else if (waitingServiceWorker() === worker) {
      try { worker.postMessage("SKIP_WAITING"); } catch { finish(false); }
    } else finish(false);
  });
}

export { UPDATE_EVENT };
