import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  newKey,
  studentApi,
  StudentApiError,
  type AttemptState,
  type FinishedState,
  type QuestionState,
} from '../lib/student';

/** Pantalla del examen. El tiempo lo decide el servidor; aquí solo se muestra una cuenta regresiva
 *  calculada con el desfase entre el reloj del servidor y el del navegador. */
export function ExamPage() {
  const [state, setState] = useState<AttemptState | null>(null);
  const [error, setError] = useState('');
  const [fatal, setFatal] = useState('');

  const apply = useCallback((s: AttemptState) => {
    setState(s);
    setError('');
  }, []);

  useEffect(() => {
    studentApi
      .current()
      .then(apply)
      .catch((e: unknown) =>
        setFatal(e instanceof StudentApiError ? e.message : 'No fue posible cargar el examen. Revisa tu conexión.'),
      );
  }, [apply]);

  if (fatal)
    return (
      <section className="card narrow">
        <h1>No hay examen en curso</h1>
        <p className="error">{fatal}</p>
        <Link className="button primary" to="/ingresar">
          Ir al ingreso
        </Link>
      </section>
    );
  if (!state) return <p role="status">Cargando examen…</p>;
  if (state.status === 'finished') return <Receipt r={state} />;
  return <QuestionView key={state.ordinal} q={state} onNext={apply} error={error} setError={setError} />;
}

function QuestionView({
  q,
  onNext,
  error,
  setError,
}: {
  q: QuestionState;
  onNext: (s: AttemptState) => void;
  error: string;
  setError: (s: string) => void;
}) {
  const [choice, setChoice] = useState<number | null>(null);
  const [sending, setSending] = useState(false);
  const keyRef = useRef(newKey()); // misma clave en reintentos → el servidor no duplica
  const sentRef = useRef(false);
  // desfase servidor-navegador medido al recibir la pregunta
  const offset = useRef(new Date(q.server_now).getTime() - Date.now());
  const deadline = new Date(q.deadline_at).getTime();
  const [left, setLeft] = useState(() => Math.max(0, deadline - (Date.now() + offset.current)));

  const send = useCallback(
    async (c: number | null) => {
      if (sentRef.current) return;
      sentRef.current = true;
      setSending(true);
      for (let attempt = 0; attempt < 8; attempt++) {
        try {
          const next = await studentApi.answer(q.ordinal, c, keyRef.current);
          onNext(next);
          return;
        } catch (e) {
          if (e instanceof StudentApiError && e.status < 500 && e.status !== 429) {
            setError(e.message);
            break;
          }
          setError('Conexión inestable: reintentando guardar tu respuesta…');
          await new Promise((r) => setTimeout(r, Math.min(4000, 500 * 2 ** attempt)));
        }
      }
      // Sin éxito: recuperar el estado real desde el servidor.
      try {
        onNext(await studentApi.current());
      } catch {
        setError('Sin conexión. Recarga la página cuando vuelva tu internet; tu avance está guardado.');
        sentRef.current = false;
        setSending(false);
      }
    },
    [q.ordinal, onNext, setError],
  );

  useEffect(() => {
    const t = setInterval(() => {
      const ms = Math.max(0, deadline - (Date.now() + offset.current));
      setLeft(ms);
      if (ms <= 0) {
        clearInterval(t);
        void send(null); // al expirar: se omite y avanza (el servidor lo registra como expirada)
      }
    }, 200);
    return () => clearInterval(t);
  }, [deadline, send]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (sending) return;
      const k = e.key.toUpperCase();
      const idx = ['A', 'B', 'C', 'D'].indexOf(k);
      const num = ['1', '2', '3', '4'].indexOf(k);
      if (idx >= 0 || num >= 0) setChoice(idx >= 0 ? idx : num);
      else if (e.key === 'Enter' && choice !== null) void send(choice);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [choice, send, sending]);

  const secs = Math.ceil(left / 1000);
  const pct = Math.max(0, Math.min(100, (left / (q.seconds_per_question * 1000)) * 100));
  const warn = secs <= 5;
  return (
    <section className="exam" aria-labelledby="enunciado">
      <div className="exam-top">
        <span>
          Pregunta <strong>{q.ordinal}</strong> de {q.total} · Módulo {q.module}
        </span>
        <span className={warn ? 'timer warn' : 'timer'} aria-live={warn ? 'assertive' : 'off'}>
          {secs} s
        </span>
      </div>
      <div className="bar" aria-hidden="true">
        <div className={warn ? 'fill warn' : 'fill'} style={{ width: `${pct}%` }} />
      </div>
      <div className="card">
        <p id="enunciado" className="stem">
          {q.stem}
        </p>
        <div role="radiogroup" aria-labelledby="enunciado" className="choices">
          {q.options.map((o) => (
            <button
              key={o.index}
              role="radio"
              aria-checked={choice === o.index}
              className={choice === o.index ? 'choice selected' : 'choice'}
              disabled={sending}
              onClick={() => setChoice(o.index)}
            >
              <span className="letter">{o.label}</span>
              <span>{o.text}</span>
            </button>
          ))}
        </div>
        <div className="actions">
          <button className="button primary" disabled={choice === null || sending} onClick={() => send(choice)}>
            Responder
          </button>
          {q.allow_skip && (
            <button className="button" disabled={sending} onClick={() => send(null)}>
              Omitir (0 puntos)
            </button>
          )}
          <span className="muted small">Teclas: A–D para elegir, Enter para responder.</span>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
    </section>
  );
}

function Receipt({ r }: { r: FinishedState }) {
  return (
    <section className="card narrow" aria-labelledby="titulo-fin">
      <h1 id="titulo-fin">Examen enviado</h1>
      <p>
        {r.full_name}, tu examen <strong>{r.exam}</strong> quedó registrado
        {r.reason === 'window_expired' ? ' al agotarse el tiempo máximo.' : '.'}
      </p>
      <dl className="receipt">
        <dt>Folio</dt>
        <dd>{r.folio}</dd>
        <dt>Preguntas</dt>
        <dd>{r.total}</dd>
        <dt>Respondidas</dt>
        <dd>{r.answered}</dd>
        <dt>Omitidas o sin tiempo</dt>
        <dd>{r.omitted + r.expired}</dd>
        {r.grade && (
          <>
            <dt>Calificación</dt>
            <dd>
              <strong>{r.grade}</strong>
            </dd>
          </>
        )}
      </dl>
      <p className="muted">Guarda tu folio. Tu docente publicará los resultados.</p>
    </section>
  );
}
