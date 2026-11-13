/** 安装入口：捕获 beforeinstallprompt，供设置页显示「安装到桌面」。 */
interface InstallPrompt extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: InstallPrompt | null = null;
let prompting = false;
const INSTALLABLE = "cs:installable";

export function initInstallPrompt(): void {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferred = event as InstallPrompt;
    window.dispatchEvent(new Event(INSTALLABLE));
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    window.dispatchEvent(new Event(INSTALLABLE));
  });
}

export function canInstall(): boolean {
  return deferred !== null && !prompting;
}

export function isStandalone(): boolean {
  return window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as unknown as { standalone?: boolean }).standalone === true;
}

export async function promptInstall(): Promise<"accepted" | "dismissed" | "unavailable" | "failed"> {
  if (!deferred || prompting) return "unavailable";
  const prompt = deferred;
  deferred = null;
  prompting = true;
  try {
    await prompt.prompt();
    return (await prompt.userChoice).outcome;
  } catch {
    return "failed";
  } finally {
    prompting = false;
    window.dispatchEvent(new Event(INSTALLABLE));
  }
}

export { INSTALLABLE };
