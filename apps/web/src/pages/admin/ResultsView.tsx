import { useEffect, useState } from 'react';
import { adminApi, ApiError, type Exam, type Results } from '../../lib/admin';

const STATUS: Record<string, string> = {
  in_progress: 'En curso',
  finished: 'Terminado',
  expired: 'Tiempo agotado',
  voided: 'Anulado',
};
const REFRESH_MS = 10_000;

export function ResultsView({ exam, onBack }: { exam: Exam; onBack: () => void }) {
  const [data, setData] = useState<Results | null>(null);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState<Date | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      adminApi
        .results(exam.id)
        .then((d) => {
          if (!alive) return;
          setData(d);
          setUpdated(new Date());
          setError('');
        })
        .catch((e: unknown) => alive && setError(e instanceof ApiError ? e.message : 'Sin conexión; reintentando…'));
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [exam.id]);

  return (
    <section className="card stack" aria-labelledby="titulo-res">
      <div className="row-between">
        <h2 id="titulo-res">Calificaciones · {exam.name}</h2>
        <button className="linklike" onClick={onBack}>
          ← Volver a exámenes
        </button>
      </div>
      {data && (
        <div className="kpis">
          <div>
            <span className="kpi">{data.summary.attempts}</span> ingresaron
          </div>
          <div>
            <span className="kpi">{data.summary.in_progress}</span> en curso
          </div>
          <div>
            <span className="kpi">{data.summary.finished}</span> terminaron
          </div>
          <div>
            <span className="kpi">{data.summary.average ?? '—'}</span> promedio
          </div>
        </div>
      )}
      <div className="actions">
        <a className="button" href={adminApi.resultsCsvUrl(exam.id)}>
          Descargar CSV (Excel)
        </a>
        <span className="muted small" aria-live="polite">
          {updated ? `Actualizado ${updated.toLocaleTimeString('es-MX')} · se actualiza cada 10 s` : 'Cargando…'}
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      {data && (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Folio</th>
                <th>Nombre</th>
                <th>Matrícula</th>
                <th>Estado</th>
                <th>Avance</th>
                <th>Correctas</th>
                <th>Incorrectas</th>
                <th>Omitidas</th>
                <th>Calificación</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.length === 0 && (
                <tr>
                  <td colSpan={9} className="muted">
                    Aún nadie ha ingresado.
                  </td>
                </tr>
              )}
              {data.rows.map((r) => (
                <tr key={r.attempt_id}>
                  <td>{r.folio}</td>
                  <td>{r.full_name}</td>
                  <td>{r.matricula}</td>
                  <td>{STATUS[r.status] ?? r.status}</td>
                  <td>
                    {r.status === 'in_progress' ? `${r.answered}/${r.total}` : `${r.total - (r.expired ?? 0)}/${r.total}`}
                  </td>
                  <td>{r.correct ?? '—'}</td>
                  <td>{r.wrong ?? '—'}</td>
                  <td>{r.omitted !== null && r.expired !== null ? r.omitted + r.expired : '—'}</td>
                  <td>
                    <strong>{r.grade ?? '—'}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
