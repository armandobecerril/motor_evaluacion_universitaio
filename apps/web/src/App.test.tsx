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

  it('el formulario de alumno pide matrícula y código, deshabilitado hasta H2', () => {
    renderAt('/ingresar');
    expect(screen.getByLabelText('Matrícula')).toBeDisabled();
    expect(screen.getByLabelText('Código de convocatoria')).toBeDisabled();
  });

  it('ruta desconocida muestra 404', () => {
    renderAt('/no-existe');
    expect(screen.getByText('Página no encontrada')).toBeInTheDocument();
  });
});
