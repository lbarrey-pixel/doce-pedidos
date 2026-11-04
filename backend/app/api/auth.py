"""Acesso ao painel: JWT (Supabase Auth ou segredo local) de um operador ativo."""

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, Request
from sqlalchemy import text

from app.api.erros import ErroDeNegocio


@dataclass
class VerificadorJWT:
    """Valida assinatura, validade e audiência do token e devolve o `sub`.

    Três modos, do mais ao menos usado:
    - `jwks_url` (produção): chaves públicas do Supabase Auth, ES256/RS256, com emissor.
    - `chave_publica` fixa: usada pelos testes de integração.
    - `segredo` (desenvolvimento local): HS256 com `JWT_SECRET`, sem Supabase. O modo
      simétrico nunca é combinado com os assimétricos, para não abrir confusão de algoritmo.
    """

    emissor: str | None = None
    chave_publica: Any = None
    jwks_url: str | None = None
    audiencia: str = "authenticated"
    segredo: str | None = None

    def __post_init__(self) -> None:
        if self.segredo and (self.jwks_url or self.chave_publica):
            raise ValueError("segredo HS256 não combina com chave pública ou JWKS")
        self._jwks = jwt.PyJWKClient(self.jwks_url, cache_keys=True) if self.jwks_url else None

    def sub(self, token: str) -> str:
        try:
            if self.segredo:
                dados = jwt.decode(
                    token, self.segredo, algorithms=["HS256"], audience=self.audiencia
                )
            else:
                chave = (
                    self._jwks.get_signing_key_from_jwt(token).key
                    if self._jwks
                    else self.chave_publica
                )
                dados = jwt.decode(
                    token,
                    chave,
                    algorithms=["ES256", "RS256"],
                    audience=self.audiencia,
                    issuer=self.emissor,
                )
        except jwt.PyJWTError as e:
            raise ErroDeNegocio("nao_autenticado", "Faça login de novo.", 401) from e
        return dados["sub"]


@dataclass(frozen=True)
class Operador:
    id: str
    nome: str
    trocar_senha: bool = False
    papel: str = "operador"  # "dono" ou "operador"

    @property
    def dono(self) -> bool:
        return self.papel == "dono"


def operador_atual(request: Request) -> Operador:
    cabecalho = request.headers.get("Authorization", "")
    if not cabecalho.startswith("Bearer "):
        raise ErroDeNegocio("nao_autenticado", "Faça login de novo.", 401)
    sub = request.app.state.verificador.sub(cabecalho.removeprefix("Bearer "))
    with request.app.state.engine.connect() as c:
        linha = c.execute(
            text(
                "SELECT id, nome, trocar_senha, papel FROM doce.operador"
                " WHERE id::text = :sub AND ativo"
            ),
            {"sub": sub},
        ).one_or_none()
    if linha is None:
        raise ErroDeNegocio("sem_acesso", "Sem acesso ao painel.", 403)
    return Operador(
        id=str(linha.id), nome=linha.nome, trocar_senha=linha.trocar_senha, papel=linha.papel
    )


OperadorAtual = Depends(operador_atual)
