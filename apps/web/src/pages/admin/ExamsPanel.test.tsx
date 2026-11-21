import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ExamsPanel } from './ExamsPanel';

const MODULES = [
  { number: 1, name: 'Sistemas de Información' },
  { number: 5, name: 'Automatización Financiera' },
  { number: 6, name: 'BI a Business Analytics' },
];

describe('ExamsPanel', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('permite elegir los módulos del examen y los envía al crearlo', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    vi.stubGlobal('fetch', fetchMock);
    render(<ExamsPanel courseId="c1" modules={MODULES} />);

    const boxes = screen.getAllByRole('checkbox', { name: /Módulo \d/ });
    expect(boxes).toHaveLength(3);
    boxes.forEach((b) => expect(b).toBeChecked());

    fireEvent.click(screen.getByRole('checkbox', { name: /Módulo 1 ·/ }));
    fireEvent.click(screen.getByRole('button', { name: /Crear examen/ }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
      expect(post).toBeTruthy();
      expect(JSON.parse(post![1].body as string).modules).toEqual([5, 6]);
    });
  });

  it('no deja crear un examen sin módulos', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    vi.stubGlobal('fetch', fetchMock);
    render(<ExamsPanel courseId="c1" modules={MODULES} />);
    screen.getAllByRole('checkbox', { name: /Módulo \d/ }).forEach((b) => fireEvent.click(b));
    fireEvent.click(screen.getByRole('button', { name: /Crear examen/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('al menos un módulo');
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
  });
});
