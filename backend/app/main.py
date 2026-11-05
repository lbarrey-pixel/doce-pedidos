"""API da Doce Ateliê, montada em /api/v1."""

import logging
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine, create_engine, text

from app.adaptadores.gateway_checkout import GatewayCheckout
from app.adaptadores.gateway_simulado import GatewaySimulado
from app.adaptadores.pix_manual import PixManual
from app.adaptadores.roteador_fake import RoteadorFake
from app.adaptadores.roteador_google import RoteadorGoogle
from app.api import (
    erros,
    gateway_aviso,
    gateway_simulado,
    loja,
    painel,
    painel_configuracao,
    painel_pagamentos,
    painel_pedidos,
    painel_producao,
    painel_resumos,
    painel_vendas,
)
from app.api.auth import Operador, OperadorAtual, VerificadorJWT
from app.portas.pagamento import FabricaDePagamento, GatewayDePagamento
from app.portas.roteador import Roteador

# Logs só com método, caminho e status; corpo de requisição nunca vai para o log
# (nome, telefone, endereço e CPF do cliente).
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


class _SemQueryDoAviso(logging.Filter):
    """O access log do uvicorn traz a query string; o código `?c=` do aviso não pode ir junto."""

    _QUERY = re.compile(r"(/gateway/checkout/aviso)\?[^\s\"]*")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                self._QUERY.sub(r"\1", a) if isinstance(a, str) else a for a in record.args
            )
        if isinstance(record.msg, str):
            record.msg = self._QUERY.sub(r"\1", record.msg)
        return True


logging.getLogger("uvicorn.access").addFilter(_SemQueryDoAviso())
# httpx registra a URL de cada chamada (CEP, endereço): fora do log.
for _ruidoso in ("httpx", "httpcore"):
    logging.getLogger(_ruidoso).setLevel(logging.WARNING)


def _verificador_do_ambiente() -> VerificadorJWT:
    """Supabase Auth em produção; `JWT_SECRET` (HS256) só para desenvolvimento local."""
    supabase = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if supabase:
        return VerificadorJWT(
            emissor=f"{supabase}/auth/v1", jwks_url=f"{supabase}/auth/v1/.well-known/jwks.json"
        )
    segredo = os.environ.get("JWT_SECRET", "")
    if not segredo:
        raise RuntimeError("Defina SUPABASE_URL (produção) ou JWT_SECRET (desenvolvimento local)")
    return VerificadorJWT(segredo=segredo)


def _roteador_do_ambiente() -> Roteador:
    if os.environ.get("ROTEADOR") == "fake":
        return RoteadorFake()
    return RoteadorGoogle(os.environ.get("GOOGLE_MAPS_API_KEY", ""))


def _gateway_do_ambiente() -> GatewayDePagamento | None:
    """Gateway real com GATEWAY_API_URL e GATEWAY_API_KEY; simulado com GATEWAY=simulado.
    Sem nenhum dos dois não há pagamento online: o pedido nasce com o Pix copia e cola."""
    segredo = os.environ.get("GATEWAY_AVISO_CODIGO", "")
    url, chave = os.environ.get("GATEWAY_API_URL", ""), os.environ.get("GATEWAY_API_KEY", "")
    if url and chave:
        if not segredo:
            raise RuntimeError(
                "GATEWAY_API_URL e GATEWAY_API_KEY exigem GATEWAY_AVISO_CODIGO, um segredo "
                "próprio para o código do aviso (não reaproveite a chave da API)"
            )
        return GatewayCheckout(url, chave, segredo)
    if os.environ.get("GATEWAY") == "simulado":
        origem = (os.environ.get("CORS_ORIGENS", "").split(",") + [""])[0].strip().rstrip("/")
        return GatewaySimulado(
            f"{origem}/simulador" if origem else "https://doceatelie.example/pagar",
            segredo or "segredo-do-simulador",
        )
    return None


def criar_app(
    engine: Engine | None = None,
    verificador: VerificadorJWT | None = None,
    relogio: Callable[[], datetime] | None = None,
    roteador: Roteador | None = None,
    pagamento: FabricaDePagamento | None = None,
    gateway: GatewayDePagamento | None = None,
    url_externa: str | None = None,
) -> FastAPI:
    app = FastAPI(title="Doce Ateliê API", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.engine = engine or create_engine(
        os.environ["DATABASE_URL"],
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        # Pooler em modo transação (porta 6543) não aceita prepared statements.
        connect_args={"prepare_threshold": None},
    )
    app.state.verificador = verificador or _verificador_do_ambiente()
    app.state.relogio = relogio or (lambda: datetime.now(UTC))
    # Sem chave do Google o mapa responde erro e a loja mostra "mapa indisponível".
    app.state.roteador = roteador or _roteador_do_ambiente()
    app.state.pagamento = pagamento or PixManual
    app.state.gateway = gateway or _gateway_do_ambiente()
    if isinstance(app.state.gateway, GatewaySimulado) and os.environ.get("SUPABASE_URL"):
        # SUPABASE_URL indica ambiente real: lá o simulador deixaria qualquer um "pagar" pedido.
        raise RuntimeError("GATEWAY=simulado não pode rodar com SUPABASE_URL (ambiente real)")
    # URL pública da API, para o gateway avisar o pagamento; sem ela, o link sai sem webhook.
    app.state.url_externa = (
        url_externa if url_externa is not None else os.environ.get("API_URL_PUBLICA", "")
    ).rstrip("/")
    origens = [o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGENS", "").split(",") if o]
    app.state.origens = origens  # também escolhem a redirect_url do link de pagamento
    if origens:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origens,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Authorization", "Content-Type"],
        )
    erros.registrar(app)

    v1 = APIRouter(prefix="/api/v1")

    @v1.get("/saude")
    def saude() -> dict[str, bool]:
        with app.state.engine.connect() as c:
            banco = c.execute(text("SELECT 1")).scalar_one() == 1
        return {"ok": True, "banco": banco}

    @v1.get("/painel/eu")
    def eu(operador: Operador = OperadorAtual) -> dict[str, str | bool]:
        return {
            "id": operador.id,
            "nome": operador.nome,
            "trocar_senha": operador.trocar_senha,
            "papel": operador.papel,
        }

    @v1.post("/painel/senha-trocada")
    def senha_trocada(operador: Operador = OperadorAtual) -> dict[str, bool]:
        # O front chama depois de trocar a senha no Supabase Auth.
        with app.state.engine.begin() as c:
            c.execute(
                text("UPDATE doce.operador SET trocar_senha = false WHERE id::text = :id"),
                {"id": operador.id},
            )
        return {"trocar_senha": False}

    v1.include_router(painel.router)
    v1.include_router(painel_pedidos.router)
    v1.include_router(painel_producao.router)
    v1.include_router(painel_pagamentos.router)
    v1.include_router(painel_vendas.router)
    v1.include_router(painel_resumos.router)
    v1.include_router(painel_configuracao.router)
    v1.include_router(gateway_aviso.router)
    if isinstance(app.state.gateway, GatewaySimulado):
        v1.include_router(gateway_simulado.router)
    v1.include_router(loja.router)
    app.include_router(v1)
    return app


def app_de_producao() -> FastAPI:  # uvicorn app.main:app_de_producao --factory
    return criar_app()
