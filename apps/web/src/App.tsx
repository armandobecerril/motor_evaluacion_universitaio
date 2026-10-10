import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { Shell } from './components';
import { HomePage } from './pages/HomePage';
import { StudentLoginPage } from './pages/StudentLoginPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ExamPage } from './pages/ExamPage';

// El panel docente se carga aparte: el código del alumno nunca incluye vistas con claves de respuesta.
const AdminPage = lazy(() => import('./pages/AdminPage').then((m) => ({ default: m.AdminPage })));

export function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/ingresar" element={<StudentLoginPage />} />
        <Route path="/examen" element={<ExamPage />} />
        <Route
          path="/admin/*"
          element={
            <Suspense fallback={<p role="status">Cargando panel…</p>}>
              <AdminPage />
            </Suspense>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Shell>
  );
}
