"""Dados de demonstração: cardápio, um operador de desenvolvimento e estoque inicial.

Roda como doce_api (DATABASE_URL) e é idempotente. Tudo aqui é fictício; a chave Pix e o
WhatsApp abaixo são valores de exemplo.

    python -m scripts.seed
"""

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from app.adaptadores import repositorio_sql as repo
from app.dominio.catalogo import ler_cardapio
from app.dominio.estoque import Estado, Movimento, Tipo

CARDAPIO = Path(__file__).resolve().parents[1] / "dados" / "cardapio.csv"
# Mesmo id usado por scripts/token_dev.py para gerar o JWT local.
OPERADOR_DEV = uuid.UUID("00000000-0000-4000-8000-000000000001")
PIX_CHAVE_EXEMPLO = "123e4567-e89b-12d3-a456-426614174000"
WHATSAPP_EXEMPLO = "5511912345678"

ESTOQUE_INICIAL = {
    ("Brigadeiro de Pistache", "Caixa com 12"): ("producao", Estado.PRONTA, 6),
    ("Brigadeiro Tradicional", "Caixa com 12"): ("producao", Estado.PRONTA, 8),
    ("Bolo de Pote Red Velvet", "Individual"): ("producao", Estado.PRONTA, 5),
    ("Bolo de Pote de Cenoura com Brigadeiro", "Individual"): ("producao", Estado.PRONTA, 4),
    ("Torta de Limão", "Fatia"): ("producao", Estado.PRONTA, 6),
    ("Torta de Limão", "Inteira"): ("producao", Estado.CONGELADA, 2),
    ("Cheesecake de Frutas Vermelhas", "Fatia"): ("producao", Estado.PRONTA, 4),
    ("Brownie de Nozes", "Unidade"): ("producao", Estado.PRONTA, 10),
    ("Refrigerante de Guaraná", "Lata 350 ml"): ("entrada", Estado.PRONTA, 12),
    ("Sacola Presente", "Unidade"): ("entrada", Estado.PRONTA, 20),
}


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"prepare_threshold": None})
    agora = datetime.now(UTC)
    with engine.begin() as c:
        repo.carregar_catalogo(c, ler_cardapio(CARDAPIO))
        c.execute(
            text(
                "INSERT INTO doce.operador (id, nome, papel) VALUES (:id, 'Operadora Demo', 'dono')"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"id": OPERADOR_DEV},
        )
        c.execute(
            text("UPDATE doce.configuracao_loja SET pix_chave = :p, whatsapp_negocio = :w"),
            {"p": PIX_CHAVE_EXEMPLO, "w": WHATSAPP_EXEMPLO},
        )
        ja_tem_estoque = c.execute(text("SELECT count(*) FROM doce.movimento")).scalar_one() > 0
        if not ja_tem_estoque:
            for (produto, tamanho), (tipo, estado, qtd) in ESTOQUE_INICIAL.items():
                repo.registrar_movimento(
                    c,
                    Movimento(
                        variante=repo.id_da_variante(c, produto, tamanho),
                        tipo=Tipo(tipo),
                        quantidade=qtd,
                        de_estado=None,
                        para_estado=estado,
                        autor=str(OPERADOR_DEV),
                        criado_em=agora,
                    ),
                )
    print("seed aplicado")


if __name__ == "__main__":
    main()
