import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { studentApi, StudentApiError } from '../lib/student';

export function StudentLoginPage() {
  const nav = useNavigate();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<'form' | 'rules'>('form');

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError('');
    try {
      const r = await studentApi.start(String(f.get('code')), String(f.get('name')), String(f.get('matricula')));
      if (r.resumed) nav('/examen');
      else setStep('rules');
    } catch (err) {
      setError(err instanceof StudentApiError ? err.message : 'No fue posible conectar. Revisa tu internet.');
    } finally {
      setBusy(false);
    }
  }

  if (step === 'rules')
    return (
      <section className="card narrow" aria-labelledby="titulo-reglas">
        <h1 id="titulo-reglas">Antes de comenzar</h1>
        <ul className="rules">
          <li>Cada pregunta tiene un tiempo límite que verás en pantalla. Al terminar el tiempo, la pregunta se omite y pasa a la siguiente.</li>
          <li>
            Respuesta correcta <strong>+1</strong>, incorrecta <strong>resta</strong>, omitida <strong>0</strong>. Si no
            estás seguro, conviene <strong>omitir</strong>.
          </li>
          <li>No puedes regresar a preguntas anteriores. Cada respuesta se guarda al momento.</li>
          <li>Si se corta tu conexión o recargas la página, vuelve a entrar con los mismos datos: continuarás donde ibas, sin tiempo extra.</li>
          <li>Solo tienes un intento. No se muestran respuestas correctas durante el examen.</li>
        </ul>
        <button className="button primary" onClick={() => nav('/examen')}>
          Comenzar examen
        </button>
      </section>
    );

  return (
    <section aria-labelledby="titulo-ingreso" className="card narrow">
      <h1 id="titulo-ingreso">Ingreso al examen</h1>
      <p>Escribe el código de acceso que te dio tu docente, tu nombre completo y tu matrícula.</p>
      <form onSubmit={submit}>
        <label>
          Código de acceso
          <input name="code" autoComplete="off" autoCapitalize="characters" spellCheck={false} required
                 placeholder="ABCD-EFGH" maxLength={32} />
        </label>
        <label>
          Nombre completo
          <input name="name" autoComplete="name" required minLength={5} maxLength={200} placeholder="Nombre y apellidos" />
        </label>
        <label>
          Matrícula
          <input name="matricula" autoComplete="off" required maxLength={64} />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="button primary" disabled={busy}>
          {busy ? 'Verificando…' : 'Continuar'}
        </button>
      </form>
    </section>
  );
}
