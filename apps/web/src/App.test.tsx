import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App } from './App';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ status: 'ok', database: 'ok', migration: '0001', build: 'dev', environment: 'local' }),
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it('muestra la portada en español y el estado del servicio', async () => {
    renderAt('/');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/calificación auditable/i);
    expect(await screen.findByText('Servicio disponible.')).toBeInTheDocument();
  });

  it('informa servicio no disponible si la API falla', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('red')));
    renderAt('/');
    expect(await screen.findByText(/no disponible/i)).toBeInTheDocument();
  });

  it('el ingreso del alumno pide código, nombre completo y matrícula', () => {
    renderAt('/ingresar');
    expect(screen.getByLabelText('Código de acceso')).toBeRequired();
    expect(screen.getByLabelText('Nombre completo')).toBeRequired();
    expect(screen.getByLabelText('Matrícula')).toBeRequired();
  });

  it('el alumno ve la pregunta, el tiempo y las opciones sin claves', async () => {
    const now = new Date();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: 'in_progress',
          ordinal: 3,
          total: 200,
          module: 2,
          stem: 'Una empresa de logística evalúa su ERP. ¿Qué conviene?',
          options: ['Uno', 'Dos', 'Tres', 'Cuatro'].map((t, i) => ({ index: i, label: 'ABCD'[i], text: t })),
          seconds_per_question: 30,
          deadline_at: new Date(now.getTime() + 30000).toISOString(),
          server_now: now.toISOString(),
          window_deadline_at: new Date(now.getTime() + 3600000).toISOString(),
          allow_skip: true,
        }),
      }),
    );
    renderAt('/examen');
    expect(await screen.findByText(/Una empresa de logística/)).toBeInTheDocument();
    expect(screen.getByText(/Pregunta/)).toHaveTextContent('Pregunta 3 de 200');
    expect(screen.getAllByRole('radio')).toHaveLength(4);
    expect(screen.getByRole('button', { name: /Omitir/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Responder' })).toBeDisabled();
  });

  it('el comprobante final no muestra calificación si el docente no lo permite', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: 'finished', folio: 'AB12CD34', exam: 'Parcial 1', full_name: 'Ana López', finished_at: null,
          total: 200, answered: 180, omitted: 15, expired: 5, reason: 'completed',
        }),
      }),
    );
    renderAt('/examen');
    expect(await screen.findByText('AB12CD34')).toBeInTheDocument();
    expect(screen.queryByText('Calificación')).not.toBeInTheDocument();
  });

  it('panel docente sin sesión muestra el formulario de acceso', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: 'Inicia sesión.' }) }));
    renderAt('/admin');
    expect(await screen.findByRole('heading', { name: 'Acceso docente' })).toBeInTheDocument();
    expect(screen.getByLabelText('Contraseña')).toHaveAttribute('type', 'password');
  });

  it('docente con contraseña temporal debe cambiarla', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ username: 'admin', display_name: 'Admin', role: 'platform_admin', must_change_password: true }),
      }),
    );
    renderAt('/admin');
    expect(await screen.findByRole('heading', { name: /contraseña temporal/i })).toBeInTheDocument();
  });

  it('ruta desconocida muestra 404', () => {
    renderAt('/no-existe');
    expect(screen.getByText('Página no encontrada')).toBeInTheDocument();
  });
});
