import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getHealth, type HealthStatus } from '../lib/api';

type State = { kind: 'loading' } | { kind: 'ok'; data: HealthStatus } | { kind: 'error' };

export function HomePage() {
  const [state, setState] = useState<State>({ kind: 'loading' });

  useEffect(() => {
    const ctrl = new AbortController();
    getHealth(ctrl.signal)
      .then((data) => setState({ kind: 'ok', data }))
      .catch((err: unknown) => {
        if (!(err instanceof DOMException && err.name === 'AbortError')) setState({ kind: 'error' });
      });
    return () => ctrl.abort();
  }, []);

  return (
    <section aria-labelledby="titulo">
      <p className="eyebrow">Evaluación académica</p>
      <h1 id="titulo">Exámenes en línea con reglas claras y calificación auditable</h1>
      <p className="lead">
        Cada pregunta tiene un tiempo definido por la convocatoria. Puedes responder u omitir; al vencer el tiempo, la
        pregunta se omite y el examen avanza. No se muestran respuestas correctas durante la evaluación.
      </p>
      <div className="actions">
        <Link className="button primary" to="/ingresar">
          Ingresar como alumno
        </Link>
        <Link className="button" to="/admin">
          Acceso docente
        </Link>
      </div>
      <p className="status" role="status" aria-live="polite">
        {state.kind === 'loading' && 'Verificando servicio…'}
        {state.kind === 'error' && 'Servicio no disponible en este momento.'}
        {state.kind === 'ok' &&
          (state.data.status === 'ok' ? 'Servicio disponible.' : 'Servicio con incidencias; intenta más tarde.')}
      </p>
    </section>
  );
}
