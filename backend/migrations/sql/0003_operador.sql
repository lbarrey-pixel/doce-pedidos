-- Operadores do painel. O id é o do Supabase Auth (ou o `sub` do JWT local).

CREATE TABLE doce.operador (
  id uuid PRIMARY KEY,
  nome text NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  -- Com senha provisória, o painel só abre a tela de troca de senha.
  trocar_senha boolean NOT NULL DEFAULT false,
  papel text NOT NULL DEFAULT 'operador' CHECK (papel IN ('dono', 'operador'))
);
