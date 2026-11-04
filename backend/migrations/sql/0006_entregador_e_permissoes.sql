-- Entregadores já usados (para escolher na saída do pedido) e permissões finas da API.

CREATE TABLE doce.entregador (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nome text NOT NULL CHECK (length(nome) BETWEEN 1 AND 80),
  telefone text NOT NULL DEFAULT '' CHECK (telefone ~ '^[0-9]{0,13}$'),
  criado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (nome, telefone)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA doce TO doce_api;
-- O livro de movimentos só cresce; a configuração tem uma linha que nasce na migration.
REVOKE UPDATE, DELETE ON doce.movimento FROM doce_api;
REVOKE INSERT, DELETE ON doce.configuracao_loja FROM doce_api;
REVOKE UPDATE, DELETE ON doce.entregador FROM doce_api;

GRANT SELECT ON ALL TABLES IN SCHEMA doce TO doce_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA doce TO doce_backup;
