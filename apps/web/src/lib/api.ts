/**
 * Cliente HTTP mínimo. Regla: el cliente nunca recibe ni calcula claves, notas ni deadlines
 * autoritativos; solo muestra lo que el servidor devuelve.
 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api';

export interface HealthStatus {
  status: 'ok' | 'degraded';
  database: 'ok' | 'error' | 'unavailable';
  migration: string | null;
  build: string;
  environment: string;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/health`, { signal, credentials: 'same-origin' });
  if (!res.ok && res.status !== 503) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as HealthStatus;
}
