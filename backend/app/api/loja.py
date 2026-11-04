"""Rotas públicas da loja: cardápio, cotação de entrega, pedido e acompanhamento."""

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.adaptadores import repositorio_pedidos as pedidos
from app.adaptadores import repositorio_sql as repo
from app.api.erros import ErroDeNegocio
from app.dominio.cliente import endereco_reconhecido, mascarar
from app.dominio.dinheiro import formatar
from app.dominio.entrega import taxa_de_entrega
from app.dominio.horario import abre_as, loja_aberta, primeira_encomenda, primeiro_agendamento
from app.dominio.mensagem import mensagem_do_pedido, url_whatsapp
from app.dominio.pedido import Escolha, Recusa, montar_pedido
from app.portas.pagamento import PagamentoNaoConfigurado
from app.portas.roteador import Coordenadas

router = APIRouter(prefix="/loja")
log = logging.getLogger("doce.loja")

MENSAGENS = {
    "carrinho_vazio": "Escolha pelo menos um item.",
    "variante_indisponivel": "Um dos itens saiu do cardápio.",
    "endereco_nao_encontrado": "Não achamos esse endereço no mapa. Combine pelo WhatsApp.",
    "sob_consulta": "Para essa distância a entrega é combinada pelo WhatsApp.",
    "loja_fechada": "A loja está fechada agora. Dá para fazer uma Encomenda.",
    "sem_estoque": "Não há pronta entrega suficiente. Dá para fazer uma Encomenda.",
    "encomenda_antecedencia": "A Encomenda precisa de 12 horas de antecedência.",
    "cep_nao_encontrado": "Não achamos esse CEP. Confira os números.",
    "agendamento_horario": "Esse horário não está mais disponível. Escolha outro.",
}
MENSAGEM_FALAR_COM_A_LOJA = "Olá! Vim pelo app da Doce Ateliê e quero falar com a loja."
COM_WHATSAPP = {"sob_consulta", "endereco_nao_encontrado"}


class Cliente(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    telefone: str = Field(min_length=10, max_length=20)
    cpf: str | None = Field(default=None, max_length=14)


class EnderecoInformado(BaseModel):
    cep: str = Field(max_length=9)
    numero: str = Field(min_length=1, max_length=10)
    complemento: str = Field(default="", max_length=60)


class Item(BaseModel):
    variante_id: str
    quantidade: int = Field(gt=0, le=50)


class NovoPedido(BaseModel):
    cliente: Cliente
    recebimento: Literal["entrega", "retirada"]
    endereco: EnderecoInformado | None = None
    usar_endereco_anterior: bool = False
    itens: list[Item] = Field(max_length=50)
    tipo_entrega: Literal["pronta_entrega", "encomenda"]
    entrega_em: datetime | None = None
    # Detalhes da entrega: quem recebe, portaria, ponto de referência.
    observacao: str | None = Field(default=None, max_length=300)


class Reconhecer(BaseModel):
    telefone: str = Field(max_length=20)
    nome: str = Field(max_length=80)


def _recusa(r: Recusa, whatsapp: str) -> ErroDeNegocio:
    dados = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in r.dados.items()}
    if r.codigo in COM_WHATSAPP and whatsapp:
        dados["whatsapp_url"] = url_whatsapp(whatsapp, "Olá! Quero combinar uma entrega.")
    mensagem = MENSAGENS.get(r.codigo, "Não deu para fechar.")
    if r.codigo == "abaixo_do_minimo":
        mensagem = f"Faltam {formatar(r.dados['falta_centavos'])} para o pedido mínimo."
    return ErroDeNegocio(r.codigo, mensagem, **dados)


def _cotar(request: Request, origem, cep: str, numero: str, complemento: str = ""):
    """Endereço completo e distância de rua; Recusa quando não acha ou passa de 12 km."""
    roteador = request.app.state.roteador
    try:
        endereco = roteador.endereco_do_cep(cep)
        pos = roteador.geocodificar(endereco, numero) if endereco else None
        if pos is None:
            raise Recusa("endereco_nao_encontrado")
        distancia = roteador.distancia_metros(Coordenadas(*origem), pos)
    except RuntimeError as e:
        log.warning("mapa indisponível: %s", e)  # só serviço e código HTTP, sem endereço
        raise ErroDeNegocio("mapa_indisponivel", "O mapa não respondeu. Tente de novo.", 503) from e
    dados = {
        "cep": endereco.cep,
        "logradouro": endereco.logradouro,
        "numero": numero,
        "complemento": complemento,
        "bairro": endereco.bairro,
        "cidade": endereco.cidade,
        "uf": endereco.uf,
        "lat": pos.latitude,
        "lon": pos.longitude,
    }
    return dados, distancia


@router.get("/cardapio")
def cardapio(request: Request) -> dict:
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)
        repo.atualizar_descongelamentos(c, agora)
        cfg = pedidos.configuracao(c)
        linhas = c.execute(
            text(
                """
                SELECT v.id, p.nome AS produto, v.tamanho, c.nome AS categoria, v.descricao,
                       v.ingredientes, v.porcoes, v.peso_g, v.foto, v.preco_centavos, s.pronta
                FROM doce.variante v JOIN doce.produto p ON p.id = v.produto_id
                JOIN doce.categoria c ON c.id = v.categoria_id
                JOIN doce.saldo s ON s.variante_id = v.id
                WHERE v.ativa ORDER BY c.ordem, v.ordem
                """
            )
        ).all()
    categorias: dict[str, list] = {}
    for r in linhas:
        categorias.setdefault(r.categoria, []).append(
            {
                "id": str(r.id),
                "produto": r.produto,
                "tamanho": r.tamanho,
                "descricao": r.descricao,
                "ingredientes": r.ingredientes,
                "porcoes": r.porcoes,
                "peso_g": r.peso_g,
                "foto": r.foto,
                "preco_centavos": r.preco_centavos,
                "pronta": r.pronta,
                "estado_disponibilidade": "pronta_entrega" if r.pronta > 0 else "encomenda",
            }
        )
    return {
        "loja_aberta": loja_aberta(agora, cfg.horario),
        "abre_as": abre_as(agora, cfg.horario).isoformat(),
        "abre_as_hora": cfg.horario.abre.strftime("%H:%M"),
        "fecha_as_hora": cfg.horario.fecha.strftime("%H:%M"),
        "primeira_encomenda": primeira_encomenda(agora, cfg.horario).isoformat(),
        "primeiro_agendamento": (
            p.isoformat()
            if (p := primeiro_agendamento(agora, cfg.horario, cfg.tempo_preparo_min))
            else None
        ),
        "tempo_preparo_min": cfg.tempo_preparo_min,
        # Botão "Falar no WhatsApp" da loja; sem número cadastrado, sem botão.
        "whatsapp_url": (
            url_whatsapp(cfg.whatsapp_negocio, MENSAGEM_FALAR_COM_A_LOJA)
            if cfg.whatsapp_negocio
            else None
        ),
        "pedido_minimo_centavos": cfg.pedido_minimo_centavos,
        "desconto_app_percentual": cfg.desconto_app_percentual,
        "categorias": [{"nome": n, "variantes": v} for n, v in categorias.items()],
    }


@router.get("/cep/{cep}")
def endereco_do_cep(cep: str, request: Request) -> dict:
    """Rua, bairro e cidade do CEP, antes do número e do complemento."""
    try:
        e = request.app.state.roteador.endereco_do_cep(cep)
    except RuntimeError as erro:
        log.warning("CEP indisponível: %s", erro)
        raise ErroDeNegocio(
            "mapa_indisponivel", "O CEP não respondeu. Tente de novo.", 503
        ) from erro
    if e is None:
        raise ErroDeNegocio("cep_nao_encontrado", MENSAGENS["cep_nao_encontrado"])
    return {
        "cep": e.cep,
        "logradouro": e.logradouro,
        "bairro": e.bairro,
        "cidade": e.cidade,
        "uf": e.uf,
    }


@router.post("/entrega/cotacao")
def cotacao(endereco: EnderecoInformado, request: Request) -> dict:
    with request.app.state.engine.connect() as c:
        cfg = pedidos.configuracao(c)
    try:
        dados, distancia = _cotar(request, cfg.origem, endereco.cep, endereco.numero)
        taxa = taxa_de_entrega(distancia, cfg.faixas)
        if taxa is None:
            raise Recusa("sob_consulta")
    except Recusa as r:
        raise _recusa(r, cfg.whatsapp_negocio) from r
    return {
        "endereco": {k: dados[k] for k in ("logradouro", "numero", "bairro", "cidade", "uf")},
        "distancia_m": distancia,
        "taxa_entrega_centavos": taxa,
    }


@router.post("/cliente/reconhecer")
def reconhecer(dados: Reconhecer, request: Request) -> dict:
    """Só o endereço mascarado e a taxa até ele; nada mais do pedido anterior sai daqui.

    A taxa vem junto para o cliente ver o valor antes de pagar ao escolher "mesmo endereço"."""
    with request.app.state.engine.connect() as c:
        cfg = pedidos.configuracao(c)
        achado = endereco_reconhecido(
            pedidos.anteriores(c, dados.telefone, dados.nome), dados.telefone, dados.nome
        )
    if not achado:
        return {}
    resposta: dict = {"endereco_mascarado": mascarar(achado)}
    try:
        distancia = request.app.state.roteador.distancia_metros(
            Coordenadas(*cfg.origem), Coordenadas(achado["lat"], achado["lon"])
        )
        taxa = taxa_de_entrega(distancia, cfg.faixas)
        if taxa is not None:  # acima da última faixa: o pedido recusa com o WhatsApp, como antes
            resposta["taxa_entrega_centavos"] = taxa
    except (RuntimeError, KeyError, TypeError) as e:  # sem mapa: a taxa sai no pedido, como antes
        log.warning("taxa do endereço anterior indisponível: %s", type(e).__name__)
    return resposta


@router.post("/pedidos", status_code=201)
def criar(novo: NovoPedido, request: Request) -> dict:
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)
        repo.atualizar_descongelamentos(c, agora)
        cfg = pedidos.configuracao(c)
        endereco, distancia = None, None
        try:
            if novo.recebimento == "entrega":
                anterior = None
                if novo.usar_endereco_anterior:
                    anterior = endereco_reconhecido(
                        pedidos.anteriores(c, novo.cliente.telefone, novo.cliente.nome),
                        novo.cliente.telefone,
                        novo.cliente.nome,
                    )
                if anterior:
                    endereco = anterior
                    distancia = request.app.state.roteador.distancia_metros(
                        Coordenadas(*cfg.origem), Coordenadas(anterior["lat"], anterior["lon"])
                    )
                elif novo.endereco:
                    e = novo.endereco
                    endereco, distancia = _cotar(
                        request, cfg.origem, e.cep, e.numero, e.complemento
                    )
                else:
                    raise Recusa("endereco_nao_encontrado")
            montado = montar_pedido(
                [Escolha(i.variante_id, i.quantidade) for i in novo.itens],
                pedidos.catalogo(c),
                agora=agora,
                recebimento=novo.recebimento,
                distancia_m=distancia,
                desconto_pct=cfg.desconto_app_percentual,
                tipo_entrega=novo.tipo_entrega,
                entrega_em=novo.entrega_em,
                pedido_minimo_centavos=cfg.pedido_minimo_centavos,
                faixas=cfg.faixas,
                horario=cfg.horario,
                expiracao_min=cfg.expiracao_pagamento_min,
                tempo_preparo_min=cfg.tempo_preparo_min,
            )
        except Recusa as r:
            raise _recusa(r, cfg.whatsapp_negocio) from r
        observacao = (novo.observacao or "").strip() or None
        pid, numero = pedidos.criar_pedido_app(
            c, montado, novo.cliente.model_dump(), endereco, distancia, agora, observacao
        )
        try:
            pagamento = request.app.state.pagamento(cfg.pix_chave, cfg.pix_nome, cfg.pix_cidade)
            pix = pagamento.cobrar(numero, montado.total_centavos)
        except PagamentoNaoConfigurado as e:  # desfaz o Pedido e a separação
            raise ErroDeNegocio(
                "pix_nao_configurado", "A loja ainda não cadastrou a chave Pix.", 503
            ) from e
    texto = mensagem_do_pedido(
        numero=numero,
        itens=[(i.nome, i.quantidade) for i in montado.itens],
        cliente_nome=novo.cliente.nome,
        telefone=novo.cliente.telefone,
        endereco=(
            f"{endereco['logradouro']}, {endereco['numero']} — {endereco['bairro']}"
            if endereco
            else None
        ),
        total_centavos=montado.total_centavos,
        entrega_a_partir_de=montado.entrega_a_partir_de,
        observacao=observacao,
    )
    return {
        "id": pid,
        "numero": numero,
        "estado": "aguardando_pagamento",
        "tipo_entrega": montado.tipo_entrega,
        "recebimento": montado.recebimento,
        "subtotal_centavos": montado.subtotal_centavos,
        "desconto_centavos": montado.desconto_centavos,
        "taxa_entrega_centavos": montado.taxa_entrega_centavos,
        "total_centavos": montado.total_centavos,
        "entrega_a_partir_de": montado.entrega_a_partir_de.isoformat(),
        "expira_em": montado.expira_em.isoformat(),
        "pix": {"copia_e_cola": pix.copia_e_cola},
        "whatsapp_url": url_whatsapp(cfg.whatsapp_negocio, texto) if cfg.whatsapp_negocio else None,
    }


@router.get("/pedidos/{pedido_id}")
def acompanhar(pedido_id: str, request: Request) -> dict:
    agora = request.app.state.relogio()
    with request.app.state.engine.begin() as c:
        pedidos.liberar_expirados(c, agora)
        cfg = pedidos.configuracao(c)
        p = c.execute(
            text(
                "SELECT numero, estado, total_centavos, entrega_a_partir_de, recebimento,"
                " tipo_entrega FROM doce.pedido WHERE id::text = :id AND canal = 'app'"
            ),
            {"id": pedido_id},
        ).one_or_none()
    if p is None:
        raise ErroDeNegocio("nao_encontrado", "Pedido não encontrado.", 404)
    return {
        "numero": p.numero,
        "estado": p.estado,
        "total_centavos": p.total_centavos,
        "recebimento": p.recebimento,
        "tipo_entrega": p.tipo_entrega,
        "entrega_a_partir_de": p.entrega_a_partir_de.isoformat() if p.entrega_a_partir_de else None,
        "pix": (
            {
                "copia_e_cola": request.app.state.pagamento(
                    cfg.pix_chave, cfg.pix_nome, cfg.pix_cidade
                )
                .cobrar(p.numero, p.total_centavos)
                .copia_e_cola
            }
            if p.estado == "aguardando_pagamento" and cfg.pix_chave
            else None
        ),
    }
