-- Pedidos e livro de movimentos do estoque.

CREATE TABLE doce.pedido (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  numero bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
  canal text NOT NULL CHECK (canal IN ('app', 'balcao')),
  cliente jsonb,
  endereco jsonb,
  distancia_m integer CHECK (distancia_m >= 0),
  subtotal_centavos integer NOT NULL CHECK (subtotal_centavos >= 0),
  desconto_centavos integer NOT NULL DEFAULT 0 CHECK (desconto_centavos >= 0),
  taxa_entrega_centavos integer NOT NULL DEFAULT 0 CHECK (taxa_entrega_centavos >= 0),
  total_centavos integer NOT NULL CHECK (total_centavos >= 0),
  tipo_entrega text CHECK (tipo_entrega IN ('pronta_entrega', 'encomenda')),
  recebimento text NOT NULL DEFAULT 'entrega' CHECK (recebimento IN ('entrega', 'retirada')),
  entrega_a_partir_de timestamptz,
  forma_pagamento text NOT NULL CHECK (forma_pagamento IN ('pix_manual', 'externo')),
  estado text NOT NULL CHECK (estado IN (
    'aguardando_pagamento', 'pago', 'em_preparo', 'saiu', 'entregue', 'cancelado')),
  expira_em timestamptz,
  criado_em timestamptz NOT NULL DEFAULT now(),
  pago_em timestamptz,
  cancelado_em timestamptz,
  confirmado_por uuid REFERENCES doce.operador(id),
  -- Pix pago com valor diferente do cobrado, aceito pelo operador.
  diferenca_pagamento_centavos integer NOT NULL DEFAULT 0,
  devolvido_centavos integer NOT NULL DEFAULT 0 CHECK (devolvido_centavos >= 0),
  entregador jsonb,
  saiu_em timestamptz,
  entregue_em timestamptz,
  observacao text CHECK (observacao IS NULL OR char_length(observacao) <= 300),
  CHECK (total_centavos = subtotal_centavos - desconto_centavos + taxa_entrega_centavos),
  CONSTRAINT pedido_retirada_sem_taxa
    CHECK (recebimento = 'entrega' OR (taxa_entrega_centavos = 0 AND endereco IS NULL))
);
CREATE INDEX pedido_criado_em ON doce.pedido (criado_em);
CREATE INDEX pedido_saiu ON doce.pedido (saiu_em) WHERE estado = 'saiu';
CREATE INDEX pedido_aguardando ON doce.pedido (expira_em) WHERE estado = 'aguardando_pagamento';
-- Reconhecimento do cliente que volta: telefone + primeiro nome.
CREATE INDEX pedido_cliente_reconhecimento ON doce.pedido
  ((cliente->>'telefone'), (cliente->>'primeiro_nome'), criado_em DESC)
  WHERE canal = 'app';

CREATE TABLE doce.item_pedido (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pedido_id uuid NOT NULL REFERENCES doce.pedido(id) ON DELETE CASCADE,
  variante_id uuid NOT NULL REFERENCES doce.variante(id),
  quantidade integer NOT NULL CHECK (quantidade > 0),
  preco_unitario_centavos integer NOT NULL CHECK (preco_unitario_centavos >= 0),
  total_centavos integer NOT NULL CHECK (total_centavos = quantidade * preco_unitario_centavos)
);

-- Livro imutável (ADR 0003): o papel da API só insere e lê.
CREATE TABLE doce.movimento (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variante_id uuid NOT NULL REFERENCES doce.variante(id),
  tipo text NOT NULL CHECK (tipo IN ('producao', 'entrada', 'congelamento',
    'inicio_descongelamento', 'fim_descongelamento', 'transferencia', 'separacao',
    'liberacao_separacao', 'venda', 'perda', 'ajuste')),
  quantidade integer NOT NULL CHECK (quantidade > 0),
  de_estado text,
  para_estado text,
  pedido_id uuid REFERENCES doce.pedido(id),
  autor text NOT NULL,
  motivo text NOT NULL DEFAULT '',
  criado_em timestamptz NOT NULL DEFAULT now(),
  CHECK (tipo NOT IN ('separacao', 'liberacao_separacao', 'venda') OR pedido_id IS NOT NULL),
  CHECK (tipo NOT IN ('perda', 'ajuste') OR motivo <> '')
);
CREATE INDEX movimento_variante ON doce.movimento (variante_id, criado_em);
CREATE INDEX movimento_descongelando ON doce.movimento (variante_id, criado_em)
  WHERE de_estado = 'descongelando' OR para_estado = 'descongelando';
