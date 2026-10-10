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

export interface ReviewOption {
  code: string;
  text: string;
  correct: boolean;
}
export interface ReviewQuestion {
  id: string;
  external_id: string;
  version: number;
  module: number;
  topic: string;
  conceptual_group: string;
  case_type: string | null;
  bloom: string;
  difficulty: string;
  stem: string;
  options: ReviewOption[];
  rationale: string;
  status: string;
  reviewer: string | null;
}
export interface ReviewPage {
  total: number;
  page: number;
  items: ReviewQuestion[];
}
export interface ModuleReadiness {
  module: number;
  approved: number;
  selectable: number;
  required: number;
}
export interface Exam {
  id: string;
  code: string;
  name: string;
  status: 'draft' | 'published' | 'closed' | 'cancelled';
  starts_at: string;
  ends_at: string;
  config: Record<string, unknown> & {
    seconds_per_question: number;
    per_module_quota: number;
    max_variants_per_group: number;
    questions_per_attempt: number;
    window_minutes: number;
    scoring: { correct: number; wrong: number };
    show_grade_to_student: boolean;
  };
  published_at: string | null;
  readiness?: { ready: boolean; modules: ModuleReadiness[] };
  access_code?: string;
}
export interface ExamInput {
  name: string;
  code: string;
  starts_at: string;
  ends_at: string;
  seconds_per_question: number;
  per_module_quota: number;
  max_variants_per_group: number;
  window_minutes: number;
  wrong_penalty: number;
  show_grade_to_student: boolean;
}
export interface ResultRow {
  attempt_id: string;
  folio: string;
  full_name: string;
  matricula: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  answered: number;
  total: number;
  correct: number | null;
  wrong: number | null;
  omitted: number | null;
  expired: number | null;
  grade: string | null;
}
export interface Results {
  exam: Exam;
  summary: { attempts: number; in_progress: number; finished: number; average: string | null };
  rows: ResultRow[];
}

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
  questions: (courseId: string, params: { module?: number; status?: string; q?: string; page: number; size: number }) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)));
    return call<ReviewPage>(`/courses/${courseId}/questions?${qs.toString()}`);
  },
  setStatus: (courseId: string, body: { action: 'approve' | 'retire'; ids?: string[]; module?: number; all?: boolean }) =>
    call<{ updated: number }>(`/courses/${courseId}/questions/status`, json(body)),
  exams: (courseId: string) => call<Exam[]>(`/courses/${courseId}/exams`),
  createExam: (courseId: string, body: ExamInput) => call<Exam>(`/courses/${courseId}/exams`, json(body)),
  publish: (examId: string) => call<Exam>(`/exams/${examId}/publish`, { method: 'POST' }),
  regenerateCode: (examId: string) => call<{ access_code: string }>(`/exams/${examId}/access-code`, { method: 'POST' }),
  closeExam: (examId: string) => call<Exam>(`/exams/${examId}/close`, { method: 'POST' }),
  results: (examId: string) => call<Results>(`/exams/${examId}/results`),
  resultsCsvUrl: (examId: string) => `${API_BASE}/admin/exams/${examId}/results.csv`,
  importBank: (courseId: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return call<ImportResult>(`/courses/${courseId}/bank/import`, { method: 'POST', body: fd });
  },
};
