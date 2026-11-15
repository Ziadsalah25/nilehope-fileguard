export type Row = Record<string, any>;
let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api(
  path: string,
  options: RequestInit = {},
): Promise<any> {
  let response: Response;
  try {
    response = await fetch(`/api/console${path}`, {
      credentials: "same-origin",
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
        ...options.headers,
      },
    });
  } catch (error) {
    window.dispatchEvent(new Event("backend-offline"));
    throw error;
  }
  window.dispatchEvent(
    new Event(response.status >= 500 ? "backend-offline" : "backend-online"),
  );
  const data = await response
    .json()
    .catch(() => ({ error: "The request could not be completed." }));
  if (!response.ok) {
    if (response.status === 401 && path !== "/login")
      window.dispatchEvent(new Event("session-expired"));
    throw new Error(data.error || "The request could not be completed.");
  }
  if (data.csrf) setCsrf(data.csrf);
  return data;
}
export function relative(value: string | null): string {
  if (!value) return "Not yet seen";
  const seconds = Math.max(0, (Date.now() - Date.parse(value)) / 1000);
  if (seconds < 60) return "Just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
export function clock(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
