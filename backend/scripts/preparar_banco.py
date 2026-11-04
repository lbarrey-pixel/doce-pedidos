"""Define a senha do papel doce_api depois das migrations (a migration cria o papel sem senha).

Uso: MIGRATIONS_DATABASE_URL=... DOCE_API_SENHA=... python -m scripts.preparar_banco
Sem DOCE_API_SENHA não faz nada (útil com Postgres local em modo trust).
"""

import os

from sqlalchemy import create_engine, text


def main() -> None:
    senha = os.environ.get("DOCE_API_SENHA", "")
    if not senha:
        print("DOCE_API_SENHA vazia: senha do papel doce_api mantida")
        return
    engine = create_engine(os.environ["MIGRATIONS_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    with engine.connect() as c:
        # ALTER ROLE não aceita parâmetro; o literal é montado pelo próprio Postgres.
        literal = c.execute(text("SELECT quote_literal(:s)"), {"s": senha}).scalar_one()
        c.execute(text(f"ALTER ROLE doce_api PASSWORD {literal}"))
    print("senha do papel doce_api definida")


if __name__ == "__main__":
    main()
