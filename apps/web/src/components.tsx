import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function Shell({ children }: { children: ReactNode }) {
  return (
    <>
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>
      <header className="topbar">
        <Link to="/" className="brand">
          Motor de Evaluación Universitario
        </Link>
        <nav aria-label="Principal">
          <Link to="/ingresar">Alumno</Link>
          <Link to="/admin">Docentes</Link>
        </nav>
      </header>
      <main id="contenido" className="container">
        {children}
      </main>
      <footer className="footer">Plataforma académica · Respuestas y calificaciones se procesan en el servidor</footer>
    </>
  );
}
