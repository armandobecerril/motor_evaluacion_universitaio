/** Cliente del panel docente. La sesión viaja en cookie HttpOnly; nunca se guarda en el navegador. */
import { API_BASE } from './api';

const HEADERS = { 'X-Requested-With': 'mev' };

export interface Me {
  username: string;
  display_name: string;
  role: string;
  must_change_password: boolean;
}
export interface CatalogEntry {
  university: { id: string; code: string; name: string };
  course: { id: string; code: string; name: string };
}
export interface Finding {
  level: 'BLOQUEANTE' | 'ALTO' | 'MEDIO' | 'INFO';
  text: string;
}
export interface ValidateResult {
  valid: boolean;
  bank_code: string;
  items: number;
  errors: string[];
  error_count: number;
  warnings: string[];
  blocking: boolean;
  findings: Finding[];
  totals: Record<string, unknown>;
}
export interface ImportResult {
  bank_code: string;
  total: number;
  created: number;
  new_versions: number;
  unchanged: number;
  warnings: string[];
}
export interface BankSummary {
  course: string;
  total: number;
  modules: Record<string, Record<string, number>>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function detailText(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => (typeof d === 'string' ? d : (d?.msg ?? ''))).join(' ');
  if (detail && typeof detail === 'object' && 'errors' in detail) return (detail as { errors: string[] }).errors.join(' ');
  return 'Error inesperado.';
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}/admin${path}`, {
    credentials: 'same-origin',
    ...init,
    headers: { ...HEADERS, ...(init.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, detailText((body as { detail?: unknown }).detail));
  return body as T;
}

const json = (data: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
});

export const adminApi = {
  me: () => call<Me>('/me'),
  login: (username: string, password: string) => call<Me>('/login', json({ username, password })),
  logout: () => call<{ status: string }>('/logout', { method: 'POST' }),
  changePassword: (current_password: string, new_password: string) =>
    call<{ message: string }>('/password', json({ current_password, new_password })),
  catalog: () => call<CatalogEntry[]>('/catalog'),
  summary: (courseId: string) => call<BankSummary>(`/courses/${courseId}/bank/summary`),
  validate: (courseId: string, file: File, quota: number, maxVariants: number, seconds: number) => {
    const fd = new FormData();
    fd.append('file', file);
    const q = `per_module_quota=${quota}&max_variants_per_group=${maxVariants}&seconds_per_question=${seconds}`;
    return call<ValidateResult>(`/courses/${courseId}/bank/validate?${q}`, { method: 'POST', body: fd });
  },
  importBank: (courseId: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return call<ImportResult>(`/courses/${courseId}/bank/import`, { method: 'POST', body: fd });
  },
};
