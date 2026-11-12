const DAILY_AI_KEY = "cs-daily-ai-search";

export function readDailyAI(): boolean {
  return localStorage.getItem(DAILY_AI_KEY) === "true";
}

export function saveDailyAI(enabled: boolean): void {
  localStorage.setItem(DAILY_AI_KEY, String(enabled));
}
