const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function parseError(response: Response): Promise<Error> {
  const text = await response.text();
  if (!text) return new Error(`${response.status} ${response.statusText}`);
  try {
    const data = JSON.parse(text);
    if (typeof data.detail === 'string') return new Error(data.detail);
    return new Error(JSON.stringify(data.detail || data));
  } catch {
    return new Error(text);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(apiUrl(path), init);
    if (!response.ok) throw await parseError(response);
    if (response.status === 204) return undefined as T;
    return response.json();
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(`无法连接后端 API（${API_BASE_URL}），请检查 API 服务和 Tailscale 访问地址。`);
    }
    throw error;
  }
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function apiDelete(path: string): Promise<void> {
  return request<void>(path, { method: 'DELETE' });
}
