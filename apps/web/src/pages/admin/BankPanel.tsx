import { useEffect, useState } from 'react';
import { adminApi, ApiError, type BankSummary, type ImportResult, type ValidateResult } from '../../lib/admin';

export const STATUS_ES: Record<string, string> = {
  draft: 'borrador',
  reviewed: 'revisada',
  approved: 'aprobada',
  retired: 'retirada',
};

const LEVEL_LABEL: Record<string, string> = { BLOQUEANTE: 'Bloqueante', ALTO: 'Alto', MEDIO: 'Medio', INFO: 'Info' };

export function BankPanel({ courseId }: { courseId: string }) {
  const [summary, setSummary] = useState<BankSummary | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [quota, setQuota] = useState(50);
  const [maxVariants, setMaxVariants] = useState(2);
  const [seconds, setSeconds] = useState(20);
  const [validation, setValidation] = useState<ValidateResult | null>(null);
  const [imported, setImported] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!courseId) return;
    adminApi.summary(courseId).then(setSummary).catch(() => setSummary(null));
  }, [courseId, imported]);

  async function run<T>(fn: () => Promise<T>, onOk: (v: T) => void) {
    setBusy(true);
    setError('');
    try {
      onOk(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Error de conexión.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      {summary && (
        <p className="muted">
          Banco actual: {summary.total} reactivos vigentes
          {Object.entries(summary.modules).map(([m, st]) => (
            <span key={m}>
              {' '}
              · M{m}: {Object.entries(st).map(([k, n]) => `${n} ${STATUS_ES[k] ?? k}`).join(', ')}
            </span>
          ))}
        </p>
      )}
      {courseId && (
        <section className="card" aria-labelledby="paso-banco">
          <h2 id="paso-banco">Banco maestro de preguntas</h2>
          <p className="muted">
            Sube el JSON o CSV. Primero se valida sin guardar nada; si no hay errores podrás importarlo. Reimportar el
            mismo archivo no duplica preguntas; los cambios crean una nueva versión.
          </p>
          <div className="grid3">
            <label>
              Preguntas por módulo
              <input type="number" min={1} value={quota} onChange={(e) => setQuota(Number(e.target.value))} />
            </label>
            <label>
              Máx. variantes por concepto
              <input
                type="number"
                min={1}
                max={4}
                value={maxVariants}
                onChange={(e) => setMaxVariants(Number(e.target.value))}
              />
            </label>
            <label>
              Segundos por pregunta
              <input type="number" min={5} value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} />
            </label>
          </div>
          <label>
            Archivo
            <input
              type="file"
              accept=".json,.csv"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setValidation(null);
                setImported(null);
              }}
            />
          </label>
          <div className="actions">
            <button
              className="button"
              disabled={!file || busy}
              onClick={() => file && run(() => adminApi.validate(courseId, file, quota, maxVariants, seconds), setValidation)}
            >
              Validar
            </button>
            <button
              className="button primary"
              disabled={!file || busy || !validation?.valid}
              onClick={() => file && run(() => adminApi.importBank(courseId, file), setImported)}
            >
              Importar como borrador
            </button>
          </div>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {validation && <ValidationView v={validation} />}
          {imported && (
            <p className="ok" role="status">
              Importado {imported.bank_code}: {imported.created} nuevos, {imported.new_versions} nuevas versiones,{' '}
              {imported.unchanged} sin cambios. Todos quedan en <strong>borrador</strong> hasta tu aprobación.
            </p>
          )}
        </section>
      )}
    </div>
  );
}

function ValidationView({ v }: { v: ValidateResult }) {
  return (
    <div className="stack" aria-live="polite">
      <p className={v.valid ? 'ok' : 'error'}>
        {v.valid
          ? `Formato válido: ${v.items} reactivos (${v.bank_code}).`
          : `${v.error_count} errores: corrige el archivo antes de importar.`}
        {v.blocking && ' La configuración elegida NO alcanza para armar el examen.'}
      </p>
      {v.errors.length > 0 && (
        <ul className="findings">
          {v.errors.slice(0, 30).map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      {v.warnings.length > 0 && (
        <ul className="findings">
          {v.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <h3>Reporte de calidad</h3>
      <ul className="findings">
        {v.findings.map((f) => (
          <li key={f.text} className={`lvl-${f.level}`}>
            <strong>{LEVEL_LABEL[f.level]}</strong> — {f.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
