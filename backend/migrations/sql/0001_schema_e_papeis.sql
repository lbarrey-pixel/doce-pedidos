-- Schema doce e papéis de banco.
-- Mesmo SQL para o Postgres local (docker compose, testes) e para o Supabase.
-- As senhas dos papéis são definidas fora do repositório.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'doce_api') THEN
    CREATE ROLE doce_api LOGIN NOINHERIT;
  END IF;
  -- Papel só de leitura para o backup: o segredo do agendador não precisa poder escrever.
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'doce_backup') THEN
    CREATE ROLE doce_backup LOGIN NOINHERIT;
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS doce;
REVOKE ALL ON SCHEMA doce FROM PUBLIC;
GRANT USAGE ON SCHEMA doce TO doce_api, doce_backup;
REVOKE ALL ON SCHEMA public FROM doce_api;

DO $$
DECLARE r text;
BEGIN
  -- No Supabase, anon e authenticated nunca enxergam o schema doce.
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON SCHEMA doce FROM %I', r);
    END IF;
  END LOOP;
END $$;

ALTER ROLE doce_api SET search_path = doce;

ALTER DEFAULT PRIVILEGES IN SCHEMA doce GRANT SELECT ON TABLES TO doce_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA doce GRANT SELECT ON SEQUENCES TO doce_backup;
