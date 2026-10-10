-- Ejecutar UNA vez por servidor con un usuario administrador, ANTES de las migraciones.
-- Sustituye :'app_password' por una contraseña generada (no la guardes en el repo).
--   psql "host=... dbname=exam user=<admin> sslmode=require" -v app_password='***' -f bootstrap_roles.sql
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'exam_app') THEN
    CREATE ROLE exam_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;
ALTER ROLE exam_app WITH PASSWORD :'app_password';
SELECT format('GRANT CONNECT ON DATABASE %I TO exam_app', current_database()) \gexec
GRANT USAGE ON SCHEMA public TO exam_app;
