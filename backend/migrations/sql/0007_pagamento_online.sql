-- Pagamento online por gateway de checkout (ADR 0006). Só acrescenta; a única coisa que muda de
-- forma é o CHECK de forma_pagamento, que passa a aceitar também 'pix' e 'cartao'.
ALTER TABLE doce.pedido DROP CONSTRAINT pedido_forma_pagamento_check;
ALTER TABLE doce.pedido ADD CONSTRAINT pedido_forma_pagamento_check
  CHECK (forma_pagamento IN ('pix_manual', 'externo', 'pix', 'cartao'));

ALTER TABLE doce.pedido
  ADD COLUMN parcelas integer CHECK (parcelas IS NULL OR parcelas >= 1),
  ADD COLUMN valor_pago_centavos integer
    CHECK (valor_pago_centavos IS NULL OR valor_pago_centavos >= 0),
  ADD COLUMN pago_apos_expirar boolean NOT NULL DEFAULT false,
  -- Só vendas lançadas no painel: estado do link de pagamento gerado pelo operador.
  ADD COLUMN pagamento_link text CHECK (pagamento_link IS NULL
    OR pagamento_link IN ('aguardando', 'pago', 'expirado')),
  -- Quem cancelou: cancelar pedido pago pelo gateway pede estorno à mão.
  ADD COLUMN cancelado_por uuid REFERENCES doce.operador(id);

CREATE TABLE doce.link_pagamento (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pedido_id uuid NOT NULL REFERENCES doce.pedido(id),
  url text NOT NULL,
  valor_centavos integer NOT NULL CHECK (valor_centavos > 0),
  valido_ate timestamptz NOT NULL,
  criado_em timestamptz NOT NULL DEFAULT now(),
  resposta jsonb NOT NULL DEFAULT '{}'  -- resposta da criação do link, sem dado pessoal
);
CREATE INDEX link_pagamento_pedido ON doce.link_pagamento (pedido_id, criado_em DESC);

CREATE TABLE doce.confirmacao_pagamento (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  pedido_id uuid REFERENCES doce.pedido(id),  -- vazio: order_nsu de pedido desconhecido
  origem text NOT NULL CHECK (origem IN ('aviso', 'volta', 'painel')),
  resultado text NOT NULL CHECK (resultado IN ('confirmado', 'pago_depois_de_expirar',
    'repetido', 'nao_confirmado', 'valor_recusado', 'a_estornar', 'a_decidir')),
  transaction_nsu text,
  slug text,
  metodo text CHECK (metodo IS NULL OR metodo IN ('pix', 'credit_card')),
  parcelas integer,
  valor_cobrado_centavos integer,
  valor_pago_centavos integer,
  criado_em timestamptz NOT NULL DEFAULT now(),
  resolvido_em timestamptz,
  resolvido_por uuid REFERENCES doce.operador(id)
);
CREATE INDEX confirmacao_pagamento_pedido ON doce.confirmacao_pagamento (pedido_id, id DESC);
-- Idempotência: cada pagamento do gateway mexe em um pedido uma vez só. Além de confirmado e
-- pago_depois_de_expirar, a_estornar e a_decidir também ficam únicos por transaction_nsu: o aviso
-- repetido não duplica a pendência do operador.
CREATE UNIQUE INDEX confirmacao_pagamento_nsu ON doce.confirmacao_pagamento (transaction_nsu)
  WHERE resultado IN ('confirmado', 'pago_depois_de_expirar', 'a_estornar', 'a_decidir');
CREATE INDEX confirmacao_pagamento_pendente ON doce.confirmacao_pagamento (id)
  WHERE resolvido_em IS NULL
    AND resultado IN ('a_estornar', 'a_decidir', 'valor_recusado');

-- Tarifas para a taxa estimada dos resumos, em pontos-base: 420 = 4,20%. Valores de exemplo.
ALTER TABLE doce.configuracao_loja
  ADD COLUMN tarifa_cartao_bps integer NOT NULL DEFAULT 420
    CHECK (tarifa_cartao_bps BETWEEN 0 AND 10000),
  ADD COLUMN tarifa_pix_bps integer NOT NULL DEFAULT 0
    CHECK (tarifa_pix_bps BETWEEN 0 AND 10000);

-- Histórico imutável: o papel da API insere e lê; só atualiza "resolvido" (operador).
GRANT SELECT, INSERT ON doce.link_pagamento, doce.confirmacao_pagamento TO doce_api;
GRANT UPDATE (resolvido_em, resolvido_por) ON doce.confirmacao_pagamento TO doce_api;
GRANT SELECT ON doce.link_pagamento, doce.confirmacao_pagamento TO doce_backup;
