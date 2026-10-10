import { useCallback, useEffect, useState } from 'react';
import { adminApi, ApiError, type ReviewPage } from '../../lib/admin';
import { STATUS_ES } from './BankPanel';

const SIZE = 10;

export function ReviewPanel({ courseId, onChanged }: { courseId: string; onChanged: () => void }) {
  const [module, setModule] = useState<number | ''>('');
  const [status, setStatus] = useState('draft');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ReviewPage | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmAll, setConfirmAll] = useState(false);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    adminApi
      .questions(courseId, { module: module || undefined, status, q, page, size: SIZE })
      .then((d) => {
        setData(d);
        setSelected(new Set());
      })
      .catch((e: unknown) => setMsg(e instanceof ApiError ? e.message : 'Error al cargar.'));
  }, [courseId, module, status, q, page]);
  useEffect(load, [load]);

  async function act(body: Parameters<typeof adminApi.setStatus>[1], verb: string) {
    setBusy(true);
    setMsg('');
    try {
      const r = await adminApi.setStatus(courseId, body);
      setMsg(`${r.updated} preguntas ${verb}.`);
      setConfirmAll(false);
      onChanged();
      load();
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : 'Error.');
    } finally {
      setBusy(false);
    }
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / SIZE)) : 1;
  const toggle = (id: string) =>
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <section className="card stack" aria-labelledby="titulo-revision">
      <h2 id="titulo-revision">Revisión y aprobación</h2>
      <p className="muted">
        Solo las preguntas <strong>aprobadas</strong> entran a un examen. Aquí ves la respuesta correcta y la
        justificación (el alumno nunca las ve). Una pregunta aprobada ya no se edita: las correcciones se suben como
        nueva versión en el banco.
      </p>
      <div className="grid3">
        <label>
          Módulo
          <select
            value={module}
            onChange={(e) => {
              setModule(e.target.value ? Number(e.target.value) : '');
              setPage(1);
            }}
          >
            <option value="">Todos</option>
            {[1, 2, 3, 4].map((m) => (
              <option key={m} value={m}>
                Módulo {m}
              </option>
            ))}
          </select>
        </label>
        <label>
          Estado
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="draft">Borrador</option>
            <option value="approved">Aprobadas</option>
            <option value="retired">Retiradas</option>
            <option value="">Todas</option>
          </select>
        </label>
        <label>
          Buscar
          <input
            value={q}
            placeholder="texto, tema o id"
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
        </label>
      </div>

      <div className="actions">
        <button
          className="button primary"
          disabled={busy || selected.size === 0}
          onClick={() => act({ action: 'approve', ids: [...selected] }, 'aprobadas')}
        >
          Aprobar seleccionadas ({selected.size})
        </button>
        {module !== '' && (
          <button className="button" disabled={busy} onClick={() => act({ action: 'approve', module }, 'aprobadas')}>
            Aprobar todo el módulo {module}
          </button>
        )}
        {!confirmAll ? (
          <button className="button" disabled={busy} onClick={() => setConfirmAll(true)}>
            Aprobar todas las pendientes
          </button>
        ) : (
          <span className="confirm">
            ¿Confirmas que revisaste el banco completo?{' '}
            <button className="button primary" disabled={busy} onClick={() => act({ action: 'approve', all: true }, 'aprobadas')}>
              Sí, aprobar todas
            </button>{' '}
            <button className="button" onClick={() => setConfirmAll(false)}>
              Cancelar
            </button>
          </span>
        )}
        <button
          className="button"
          disabled={busy || selected.size === 0}
          onClick={() => act({ action: 'retire', ids: [...selected] }, 'retiradas')}
        >
          Retirar seleccionadas
        </button>
      </div>
      {msg && (
        <p role="status" className="ok">
          {msg}
        </p>
      )}

      {data && (
        <>
          <p className="muted">
            {data.total} preguntas · página {data.page} de {pages}
          </p>
          <ol className="qlist">
            {data.items.map((it) => (
              <li key={it.id} className="qcard">
                <label className="qhead">
                  <input type="checkbox" checked={selected.has(it.id)} onChange={() => toggle(it.id)} />
                  <span>
                    <strong>{it.external_id}</strong> · M{it.module} · {it.topic} · {it.conceptual_group}
                    {it.case_type ? ` · ${it.case_type}` : ''} · {it.bloom} · {it.difficulty}
                  </span>
                  <span className={`badge st-${it.status}`}>{STATUS_ES[it.status] ?? it.status}</span>
                </label>
                <p>{it.stem}</p>
                <ul className="opts">
                  {it.options.map((o) => (
                    <li key={o.code} className={o.correct ? 'correct' : ''}>
                      <strong>{o.code}.</strong> {o.text} {o.correct && <span aria-label="respuesta correcta">✓</span>}
                    </li>
                  ))}
                </ul>
                <p className="muted small">Justificación: {it.rationale}</p>
                {it.reviewer && <p className="muted small">Aprobó: {it.reviewer}</p>}
              </li>
            ))}
          </ol>
          <div className="actions">
            <button className="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              ← Anterior
            </button>
            <button className="button" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Siguiente →
            </button>
          </div>
        </>
      )}
    </section>
  );
}
