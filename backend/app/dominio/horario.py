"""Horário da loja, encomendas e agendamento. Tudo em hora local do Brasil.

Um horário para todos os dias; fechamento 00:00 é meia-noite. Aberta de `abre` até antes
de `fecha` (fim exclusivo).
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.regras.config import ABRE, ANTECEDENCIA_ENCOMENDA_H, FECHA, TEMPO_PREPARO_PADRAO_MIN

FUSO = ZoneInfo("America/Sao_Paulo")
PASSO_ENCOMENDA_MIN = 30  # horários de encomenda e agendamento de meia em meia hora
MEIA_NOITE = time(0, 0)


@dataclass(frozen=True)
class Horario:
    abre: time
    fecha: time  # 00:00 = meia-noite

    def __post_init__(self) -> None:
        if self.fecha != MEIA_NOITE and self.fecha <= self.abre:
            raise ValueError("o fechamento precisa ser depois da abertura ou à meia-noite")

    def contem(self, hora: time) -> bool:
        return hora >= self.abre and (self.fecha == MEIA_NOITE or hora < self.fecha)


HORARIO_PADRAO = Horario(ABRE, FECHA)


def _local(quando: datetime) -> datetime:
    if quando.tzinfo is None:
        raise ValueError("hora sem fuso")
    return quando.astimezone(FUSO)


def _abertura(dia: datetime, h: Horario) -> datetime:
    return dia.replace(hour=h.abre.hour, minute=h.abre.minute, second=0, microsecond=0)


def loja_aberta(quando: datetime, horario: Horario = HORARIO_PADRAO) -> bool:
    return horario.contem(_local(quando).time())


def abre_as(quando: datetime, horario: Horario = HORARIO_PADRAO) -> datetime:
    """Próxima abertura: hoje, se ainda não abriu; senão amanhã."""
    local = _local(quando)
    hoje = _abertura(local, horario)
    return hoje if local < hoje else _abertura(local + timedelta(days=1), horario)


def _meia_hora_seguinte(t: datetime) -> datetime:
    resto = (t.minute % PASSO_ENCOMENDA_MIN) or (1 if t.second or t.microsecond else 0)
    if resto:
        t += timedelta(minutes=PASSO_ENCOMENDA_MIN - t.minute % PASSO_ENCOMENDA_MIN)
    return t.replace(second=0, microsecond=0)


def primeira_encomenda(agora: datetime, horario: Horario = HORARIO_PADRAO) -> datetime:
    """Primeira data e hora com a antecedência mínima, dentro do horário de funcionamento."""
    t = _meia_hora_seguinte(_local(agora) + timedelta(hours=ANTECEDENCIA_ENCOMENDA_H))
    return t if loja_aberta(t, horario) else abre_as(t, horario)


def primeiro_agendamento(
    agora: datetime,
    horario: Horario = HORARIO_PADRAO,
    tempo_preparo_min: int = TEMPO_PREPARO_PADRAO_MIN,
) -> datetime | None:
    """Primeiro horário de hoje para pronta entrega agendada: a meia hora seguinte a agora +
    tempo de preparo (antes de abrir, abertura + tempo de preparo). None quando a loja só
    abre amanhã ou não sobra horário até o fechamento."""
    local = _local(agora)
    base = local if loja_aberta(local, horario) else abre_as(local, horario)
    if base.date() != local.date():
        return None
    t = _meia_hora_seguinte(base + timedelta(minutes=tempo_preparo_min))
    return t if t.date() == local.date() and loja_aberta(t, horario) else None


def agendamento_valido(
    agora: datetime,
    entrega_em: datetime,
    horario: Horario = HORARIO_PADRAO,
    tempo_preparo_min: int = TEMPO_PREPARO_PADRAO_MIN,
) -> bool:
    """Hoje, na meia hora, a partir do primeiro horário e com a loja aberta."""
    primeiro = primeiro_agendamento(agora, horario, tempo_preparo_min)
    e = _local(entrega_em)
    return (
        primeiro is not None
        and e >= primeiro
        and e.date() == primeiro.date()
        and e.minute % PASSO_ENCOMENDA_MIN == 0
        and e.second == 0
        and e.microsecond == 0
        and loja_aberta(e, horario)
    )


def encomenda_valida(
    agora: datetime, entrega_em: datetime, horario: Horario = HORARIO_PADRAO
) -> bool:
    """Com a antecedência mínima e a loja aberta no horário escolhido; sem prazo máximo."""
    antecedencia = timedelta(hours=ANTECEDENCIA_ENCOMENDA_H)
    return entrega_em >= agora + antecedencia and loja_aberta(entrega_em, horario)
