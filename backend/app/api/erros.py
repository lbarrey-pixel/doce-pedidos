"""Erros da API no formato {"erro": "<codigo>", "mensagem": "<texto>"}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CODIGOS_HTTP = {
    401: ("nao_autenticado", "Faça login de novo."),
    403: ("sem_acesso", "Sem acesso a esta área."),
    404: ("nao_encontrado", "Não encontrado."),
    405: ("metodo_nao_permitido", "Operação não permitida."),
}


class ErroDeNegocio(Exception):
    def __init__(self, codigo: str, mensagem: str, status: int = 422, **extra: object) -> None:
        super().__init__(mensagem)
        self.codigo, self.mensagem, self.status, self.extra = codigo, mensagem, status, extra


def _resposta(status: int, codigo: str, mensagem: str, **extra: object) -> JSONResponse:
    return JSONResponse(status_code=status, content={"erro": codigo, "mensagem": mensagem} | extra)


def registrar(app: FastAPI) -> None:
    @app.exception_handler(ErroDeNegocio)
    async def _negocio(_: Request, e: ErroDeNegocio) -> JSONResponse:
        return _resposta(e.status, e.codigo, e.mensagem, **e.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException) -> JSONResponse:
        codigo, mensagem = CODIGOS_HTTP.get(e.status_code, ("erro_http", "Erro na requisição."))
        return _resposta(e.status_code, codigo, mensagem)

    @app.exception_handler(RequestValidationError)
    async def _validacao(_: Request, e: RequestValidationError) -> JSONResponse:
        # Só os campos que falharam; nunca o valor enviado (pode ter dado do cliente).
        campos = sorted({".".join(str(p) for p in err["loc"][1:]) for err in e.errors()})
        return _resposta(422, "dados_invalidos", f"Confira: {', '.join(campos)}.")
