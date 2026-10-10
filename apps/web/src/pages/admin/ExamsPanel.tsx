import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { adminApi, ApiError, type Exam } from '../../lib/admin';
import { ResultsView } from './ResultsView';

const fmt = (iso: string) =>
  new Date(iso).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' });

function localInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

const STATUS: Record<string, string> = {
  draft: 'Borrador',
  published: 'Publicado',
  closed: 'Cerrado',
  cancelled: 'Cancelado',
};

export function ExamsPanel({ courseId }: { courseId: string }) {
  const [exams, setExams] = useState<Exam[]>([]);
  const [error, setError] = useState('');
  const [code, setCode] = useState<{ examId: string; value: string } | null>(null);
  const [resultsFor, setResultsFor] = useState<Exam | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    adminApi.exams(courseId).then(setExams).catch(() => setExams([]));
  }, [courseId]);
  useEffect(load, [load]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await fn();
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Error de conexión.');
    } finally {
      setBusy(false);
    }
  }

  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const num = (k: string) => Number(f.get(k));
    await run(async () => {
      await adminApi.createExam(courseId, {
        name: String(f.get('name')),
        code: String(f.get('code')),
        starts_at: new Date(String(f.get('starts_at'))).toISOString(),
        ends_at: new Date(String(f.get('ends_at'))).toISOString(),
        seconds_per_question: num('seconds'),
        per_module_quota: num('quota'),
        max_variants_per_group: num('variants'),
        window_minutes: num('window'),
        wrong_penalty: num('penalty'),
        show_grade_to_student: f.get('show_grade') === 'on',
      });
    });
  }

  if (resultsFor) return <ResultsView exam={resultsFor} onBack={() => setResultsFor(null)} />;

  const now = new Date();
  const later = new Date(now.getTime() + 2 * 3600 * 1000);
  return (
    <div className="stack">
      {code && (
        <section className="card codebox" aria-live="polite">
          <h2>Código de acceso del examen</h2>
          <p className="code">{code.value}</p>
          <p>
            Compártelo con tus alumnos. Entran con este código, su <strong>nombre completo</strong> y su{' '}
            <strong>matrícula</strong>. Por seguridad no se vuelve a mostrar: anótalo ahora (si lo pierdes, genera uno
            nuevo; el anterior deja de funcionar).
          </p>
          <div className="actions">
            <button className="button" onClick={() => navigator.clipboard?.writeText(code.value)}>
              Copiar código
            </button>
            <button className="button" onClick={() => setCode(null)}>
              Ya lo guardé
            </button>
          </div>
        </section>
      )}

      <section className="card" aria-labelledby="titulo-nuevo">
        <h2 id="titulo-nuevo">Nuevo examen</h2>
        <form onSubmit={create}>
          <div className="grid3">
            <label>
              Nombre
              <input name="name" defaultValue="Parcial 1" required minLength={3} />
            </label>
            <label>
              Identificador
              <input name="code" defaultValue="PARCIAL-1" required pattern="[A-Za-z0-9_\-]+" />
            </label>
            <label>
              Apertura
              <input name="starts_at" type="datetime-local" defaultValue={localInput(now)} required />
            </label>
            <label>
              Cierre
              <input name="ends_at" type="datetime-local" defaultValue={localInput(later)} required />
            </label>
            <label>
              Segundos por pregunta
              <input name="seconds" type="number" min={5} max={600} defaultValue={30} required />
            </label>
            <label>
              Preguntas por módulo
              <input name="quota" type="number" min={1} defaultValue={50} required />
            </label>
            <label>
              Máx. variantes por concepto
              <input name="variants" type="number" min={1} max={4} defaultValue={2} required />
            </label>
            <label>
              Minutos máximos por alumno
              <input name="window" type="number" min={5} max={600} defaultValue={120} required />
            </label>
            <label>
              Puntos que resta un error
              <input name="penalty" type="number" min={0} max={5} defaultValue={1} required />
            </label>
          </div>
          <label className="check">
            <input name="show_grade" type="checkbox" /> Mostrar la calificación al alumno al terminar
          </label>
          <button className="button primary" disabled={busy}>
            Crear examen (borrador)
          </button>
        </form>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </section>

      <section className="card" aria-labelledby="titulo-lista">
        <h2 id="titulo-lista">Exámenes</h2>
        {exams.length === 0 && <p className="muted">Aún no hay exámenes en esta materia.</p>}
        <ul className="exams">
          {exams.map((ex) => (
            <li key={ex.id} className="qcard">
              <div className="row-between">
                <strong>
                  {ex.name} <span className="muted">({ex.code})</span>
                </strong>
                <span className={`badge ex-${ex.status}`}>{STATUS[ex.status]}</span>
              </div>
              <p className="muted">
                {fmt(ex.starts_at)} → {fmt(ex.ends_at)} · {ex.config.questions_per_attempt} preguntas (
                {ex.config.per_module_quota} por módulo) · {ex.config.seconds_per_question} s c/u · error resta{' '}
                {Math.abs(ex.config.scoring.wrong)}
              </p>
              {ex.status === 'draft' && ex.readiness && (
                <div>
                  <p className={ex.readiness.ready ? 'ok' : 'error'}>
                    {ex.readiness.ready
                      ? 'Listo para publicar.'
                      : 'Faltan preguntas aprobadas para esta configuración:'}
                  </p>
                  <ul className="findings">
                    {ex.readiness.modules.map((m) => (
                      <li key={m.module}>
                        Módulo {m.module}: {m.approved} aprobadas · {m.selectable} seleccionables / {m.required}{' '}
                        requeridas
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="actions">
                {ex.status === 'draft' && (
                  <button
                    className="button primary"
                    disabled={busy || !ex.readiness?.ready}
                    onClick={() =>
                      run(async () => {
                        const r = await adminApi.publish(ex.id);
                        if (r.access_code) setCode({ examId: ex.id, value: r.access_code });
                      })
                    }
                  >
                    Publicar y generar código
                  </button>
                )}
                {ex.status === 'published' && (
                  <>
                    <button
                      className="button"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          const r = await adminApi.regenerateCode(ex.id);
                          setCode({ examId: ex.id, value: r.access_code });
                        })
                      }
                    >
                      Generar nuevo código
                    </button>
                    <button className="button" disabled={busy} onClick={() => run(async () => void (await adminApi.closeExam(ex.id)))}>
                      Cerrar examen
                    </button>
                  </>
                )}
                {ex.status !== 'draft' && (
                  <button className="button primary" onClick={() => setResultsFor(ex)}>
                    Ver calificaciones
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
