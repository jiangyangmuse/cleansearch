import { useEffect, useState } from "react";
import { applyServiceWorkerUpdate, UPDATE_EVENT, waitingServiceWorker } from "../swRegister";

/** 新版本就绪提示：确认后才让等待中的 SW 接管并刷新。 */
export default function UpdateToast() {
  const [worker, setWorker] = useState(waitingServiceWorker);
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState<ServiceWorker | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const sync = () => setWorker(waitingServiceWorker());
    window.addEventListener(UPDATE_EVENT, sync);
    sync();
    return () => window.removeEventListener(UPDATE_EVENT, sync);
  }, []);

  if (!worker || worker === dismissed) return null;

  return (
    <div className="update-toast">
      <span role="status">{error || "有新版本可用"}</span>
      <button type="button" className="update-toast__action" disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          if (await applyServiceWorkerUpdate(worker)) window.location.reload();
          else {
            setError("更新尚未接管，请重试");
            setBusy(false);
          }
        }}>
        {busy ? "更新中…" : "立即更新"}
      </button>
      <button type="button" className="update-toast__dismiss" aria-label="稍后再说" disabled={busy}
        onClick={() => { setDismissed(worker); setError(""); }}>稍后</button>
    </div>
  );
}
