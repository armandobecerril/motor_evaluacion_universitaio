-- Solo desarrollo local (docker-compose). Crea BD de pruebas y rol de aplicación.
CREATE DATABASE exam_test OWNER exam_owner;
CREATE ROLE exam_app LOGIN PASSWORD 'apppass' NOSUPERUSER NOBYPASSRLS;
