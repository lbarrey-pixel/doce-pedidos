"""Gera um JWT HS256 para o operador de desenvolvimento (só com JWT_SECRET, sem Supabase).

JWT_SECRET=... python -m scripts.token_dev
"""

import os
import time

import jwt

from scripts.seed import OPERADOR_DEV


def main() -> None:
    agora = int(time.time())
    token = jwt.encode(
        {"sub": str(OPERADOR_DEV), "aud": "authenticated", "iat": agora, "exp": agora + 12 * 3600},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    print(token)


if __name__ == "__main__":
    main()
