/** 统一 API 客户端：VITE_API_BASE_URL 或开发环境 Vite 代理（同源 /api）。 */

const BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const error = body?.error ?? {};
    throw new ApiError(
      response.status,
      error.code ?? 'UNKNOWN',
      error.message ?? `请求失败（${response.status}）`,
    );
  }
  return body as T;
}

/** SSE 走原生 EventSource，需绝对/同源 URL。 */
export function apiEventSourceUrl(path: string): string {
  return `${BASE}${path}`;
}
