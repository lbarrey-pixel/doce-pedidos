-- Configuração da loja: uma linha só (id = 1), editada por SQL ou por uma tela de admin.
-- Endereço, chave Pix e WhatsApp abaixo são fictícios; troque no seu ambiente.

CREATE TABLE doce.configuracao_loja (
  id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  horario_abertura time NOT NULL DEFAULT '12:00',
  horario_fechamento time NOT NULL DEFAULT '00:00',  -- 00:00 = meia-noite
  faixas_distancia jsonb NOT NULL DEFAULT
    '[[3000,1000],[6000,1400],[8000,1700],[10000,2000],[12000,2500]]',
  pedido_minimo_centavos integer NOT NULL DEFAULT 800 CHECK (pedido_minimo_centavos >= 0),
  desconto_app_percentual integer NOT NULL DEFAULT 0
    CHECK (desconto_app_percentual BETWEEN 0 AND 100),
  expiracao_pagamento_min integer NOT NULL DEFAULT 30,
  tempo_preparo_min integer NOT NULL DEFAULT 30 CHECK (tempo_preparo_min BETWEEN 5 AND 240),
  endereco_origem jsonb NOT NULL DEFAULT
    '{"cep":"12345678","logradouro":"Rua das Palmeiras","numero":"100","bairro":"Centro","cidade":"Campinas","uf":"SP","lat":-22.9,"lon":-47.0}',
  pix_chave text NOT NULL DEFAULT '',
  pix_nome text NOT NULL DEFAULT 'DOCE ATELIE' CHECK (length(pix_nome) <= 25),
  pix_cidade text NOT NULL DEFAULT 'CAMPINAS' CHECK (length(pix_cidade) <= 15),
  whatsapp_negocio text NOT NULL DEFAULT ''
);
INSERT INTO doce.configuracao_loja (id) VALUES (1);
