export async function get<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const url = new URL(path, window.location.href);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value) url.searchParams.set(key, value);
    });
  }
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

export function websocketUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}${path}`;
}
