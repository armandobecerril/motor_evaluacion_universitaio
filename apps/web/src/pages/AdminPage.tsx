import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { adminApi, ApiError, type Me } from '../lib/admin';
import { BankPanel } from './admin/BankPanel';
import { ExamsPanel } from './admin/ExamsPanel';
import { ReviewPanel } from './admin/ReviewPanel';
import type { CatalogEntry } from '../lib/admin';

export function AdminPage() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);

  const refresh = useCallback(() => {
    adminApi
      .me()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);
  useEffect(refresh, [refresh]);

  if (me === undefined) return <p role="status">Cargando…</p>;
  if (me === null) return <LoginForm onDone={setMe} />;
  if (me.must_change_password) return <ChangePasswordForm onDone={() => setMe(null)} />;
  return (
    <section aria-labelledby="titulo-admin">
      <div className="row-between">
        <h1 id="titulo-admin">Panel docente</h1>
        <div className="muted">
          {me.display_name} ·{' '}
          <button className="linklike" onClick={() => adminApi.logout().finally(() => setMe(null))}>
            Cerrar sesión
          </button>
        </div>
      </div>
      <AdminHome />
    </section>
  );
}

function LoginForm({ onDone }: { onDone: (me: Me) => void }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError('');
    try {
      onDone(await adminApi.login(String(f.get('username')), String(f.get('password'))));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No fue posible conectar con el servidor.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card narrow" aria-labelledby="titulo-login">
      <h1 id="titulo-login">Acceso docente</h1>
      <form onSubmit={submit}>
        <label>
          Usuario
          <input name="username" autoComplete="username" required />
        </label>
        <label>
          Contraseña
          <input name="password" type="password" autoComplete="current-password" required />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="button primary" disabled={busy}>
          {busy ? 'Verificando…' : 'Entrar'}
        </button>
      </form>
    </section>
  );
}

function ChangePasswordForm({ onDone }: { onDone: () => void }) {
  const [error, setError] = useState('');
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (f.get('new') !== f.get('confirm')) {
      setError('Las contraseñas nuevas no coinciden.');
      return;
    }
    try {
      await adminApi.changePassword(String(f.get('current')), String(f.get('new')));
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No fue posible cambiar la contraseña.');
    }
  }
  return (
    <section className="card narrow" aria-labelledby="titulo-cambio">
      <h1 id="titulo-cambio">Cambia tu contraseña temporal</h1>
      <p className="muted">Mínimo 12 caracteres, combinando mayúsculas, minúsculas, dígitos o símbolos.</p>
      <form onSubmit={submit}>
        <label>
          Contraseña actual
          <input name="current" type="password" autoComplete="current-password" required />
        </label>
        <label>
          Nueva contraseña
          <input name="new" type="password" autoComplete="new-password" minLength={12} required />
        </label>
        <label>
          Confirmar nueva contraseña
          <input name="confirm" type="password" autoComplete="new-password" minLength={12} required />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="button primary">Guardar</button>
      </form>
    </section>
  );
}

type Tab = 'banco' | 'revision' | 'examenes';
const TABS: { id: Tab; label: string }[] = [
  { id: 'banco', label: '1. Banco de preguntas' },
  { id: 'revision', label: '2. Revisión y aprobación' },
  { id: 'examenes', label: '3. Exámenes y calificaciones' },
];

function AdminHome() {
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [courseId, setCourseId] = useState('');
  const [tab, setTab] = useState<Tab>('banco');
  const [version, setVersion] = useState(0);

  useEffect(() => {
    adminApi
      .catalog()
      .then((c) => {
        setCatalog(c);
        if (c[0]) setCourseId(c[0].course.id);
      })
      .catch(() => setCatalog([]));
  }, []);

  return (
    <div className="stack">
      <section className="card">
        <label>
          Universidad y materia
          <select value={courseId} onChange={(e) => setCourseId(e.target.value)}>
            {catalog.map((c) => (
              <option key={c.course.id} value={c.course.id}>
                {c.university.code} · {c.course.name}
              </option>
            ))}
          </select>
        </label>
      </section>
      <div role="tablist" aria-label="Secciones del panel" className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? 'tab active' : 'tab'}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {courseId && tab === 'banco' && <BankPanel key={`b${courseId}${version}`} courseId={courseId} />}
      {courseId && tab === 'revision' && (
        <ReviewPanel key={`r${courseId}`} courseId={courseId} onChanged={() => setVersion((v) => v + 1)} />
      )}
      {courseId && tab === 'examenes' && <ExamsPanel key={`e${courseId}${version}`} courseId={courseId} />}
    </div>
  );
}
