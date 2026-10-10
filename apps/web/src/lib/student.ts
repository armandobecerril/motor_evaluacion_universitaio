/** Cliente del alumno. El intento se identifica con una cookie HttpOnly emitida por el servidor. */
import { API_BASE } from './api';

export interface QuestionState {
  status: 'in_progress';
  ordinal: number;
  total: number;
  module: number;
  stem: string;
  options: { index: number; label: string; text: string }[];
  seconds_per_question: number;
  deadline_at: string;
  server_now: string;
  window_deadline_at: string;
  allow_skip: boolean;
}
export interface FinishedState {
  status: 'finished';
  folio: string;
  exam: string;
  full_name: string;
  finished_at: string | null;
  total: number;
  answered: number;
  omitted: number;
  expired: number;
  reason: 'completed' | 'window_expired';
  grade?: string;
}
export type AttemptState = QuestionState | FinishedState;

export class StudentApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}/student${path}`, {
    credentials: 'same-origin',
    ...init,
    headers: { 'X-Requested-With': 'mev', 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: unknown }).detail;
    throw new StudentApiError(res.status, typeof detail === 'string' ? detail : 'No fue posible completar la solicitud.');
  }
  return body as T;
}

export const studentApi = {
  start: (access_code: string, full_name: string, matricula: string) =>
    call<{ resumed: boolean }>('/start', { method: 'POST', body: JSON.stringify({ access_code, full_name, matricula }) }),
  current: () => call<AttemptState>('/current'),
  answer: (ordinal: number, choice: number | null, idempotency_key: string) =>
    call<AttemptState>('/answer', { method: 'POST', body: JSON.stringify({ ordinal, choice, idempotency_key }) }),
};

export function newKey(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replace(/-/g, '')
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
}
