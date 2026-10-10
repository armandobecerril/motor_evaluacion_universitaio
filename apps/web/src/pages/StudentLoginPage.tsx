export function StudentLoginPage() {
  return (
    <section aria-labelledby="titulo-ingreso" className="card narrow">
      <h1 id="titulo-ingreso">Ingreso de alumno</h1>
      <p>
        Necesitarás tu <strong>matrícula</strong> y el <strong>código de convocatoria</strong> que te entregue tu
        docente. Solo pueden ingresar matrículas registradas en la convocatoria.
      </p>
      <form aria-describedby="aviso-ingreso" onSubmit={(e) => e.preventDefault()}>
        <label>
          Universidad (código)
          <input name="institution" autoComplete="organization" required disabled />
        </label>
        <label>
          Matrícula
          <input name="matricula" autoComplete="username" required disabled />
        </label>
        <label>
          Código de convocatoria
          <input name="code" autoComplete="one-time-code" required disabled />
        </label>
        <button type="submit" className="button primary" disabled>
          Iniciar
        </button>
      </form>
      <p id="aviso-ingreso" className="muted">
        El ingreso se habilitará cuando el motor de examen esté activo (hito H2).
      </p>
    </section>
  );
}
