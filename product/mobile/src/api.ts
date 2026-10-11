import Constants from 'expo-constants';

export const API_BASE_URL = String(Constants.expoConfig?.extra?.apiBaseUrl ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

export type TokenResponse = { access_token: string; token_type: string; expires_in: number };
export type Conversation = { id: string; title: string; created_at: string; updated_at: string };
export type Message = { id: string; role: 'user' | 'assistant'; content: string; created_at: string };
export type ConversationDetail = Conversation & { messages: Message[] };
export type ChatResponse = {
  conversation_id: string;
  user_message: Message;
  assistant_message: Message;
  model: string;
  prompt_tokens: number | null;
  completion_tokens: number | null;
};
export type Usage = {
  requests: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: number | null;
  note: string;
};

export async function api<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError('API base URL is not configured.', 0);
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError('The API could not be reached. Check the API URL and network.', 0);
  }
  const raw = await response.text();
  let data: unknown = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    data = null;
  }
  if (!response.ok) {
    const detail = typeof data === 'object' && data !== null && 'detail' in data
      ? String((data as { detail: unknown }).detail)
      : `Request failed (${response.status}).`;
    throw new ApiError(detail, response.status);
  }
  return data as T;
}

export function jsonBody(value: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(value) };
}
