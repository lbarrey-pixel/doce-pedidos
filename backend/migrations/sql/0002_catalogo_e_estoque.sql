-- Catálogo (categoria > produto > variante) e estoque (saldo materializado + livro).

CREATE TABLE doce.categoria (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nome text NOT NULL UNIQUE,
  ordem integer NOT NULL
);

CREATE TABLE doce.produto (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nome text NOT NULL UNIQUE
);

CREATE TABLE doce.variante (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  produto_id uuid NOT NULL REFERENCES doce.produto(id),
  categoria_id uuid NOT NULL REFERENCES doce.categoria(id),
  tamanho text NOT NULL,
  peso_g integer CHECK (peso_g > 0),
  porcoes text NOT NULL DEFAULT '',
  descricao text NOT NULL DEFAULT '',
  ingredientes text NOT NULL DEFAULT '',
  observacao text NOT NULL DEFAULT '',
  foto text NOT NULL DEFAULT '',
  preco_centavos integer NOT NULL CHECK (preco_centavos > 0),
  ativa boolean NOT NULL DEFAULT true,
  edicao_limitada boolean NOT NULL DEFAULT false,
  ordem integer NOT NULL DEFAULT 0,
  -- congelavel: pronta, congelada e descongelando; reserva: bebidas; simples: embalagens
  controle_estoque text NOT NULL DEFAULT 'congelavel'
    CHECK (controle_estoque IN ('congelavel', 'reserva', 'simples')),
  excluida_em timestamptz,
  UNIQUE (produto_id, tamanho)
);

-- Saldo materializado; a linha é travada (FOR UPDATE) em todo movimento.
CREATE TABLE doce.saldo (
  variante_id uuid PRIMARY KEY REFERENCES doce.variante(id),
  pronta integer NOT NULL DEFAULT 0 CHECK (pronta >= 0),
  congelada integer NOT NULL DEFAULT 0 CHECK (congelada >= 0),
  descongelando integer NOT NULL DEFAULT 0 CHECK (descongelando >= 0),
  separada integer NOT NULL DEFAULT 0 CHECK (separada >= 0),
  reserva integer NOT NULL DEFAULT 0 CHECK (reserva >= 0)
);
