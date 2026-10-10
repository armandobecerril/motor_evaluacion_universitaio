export function AdminPage() {
  return (
    <section aria-labelledby="titulo-admin" className="card">
      <h1 id="titulo-admin">Panel docente</h1>
      <p>
        Acceso con cuenta institucional (Microsoft Entra ID). Aquí se importará y aprobará el banco, se configurarán
        convocatorias y se exportarán resultados a CSV para Excel.
      </p>
      <p className="muted">Disponible en el hito H3.</p>
    </section>
  );
}
