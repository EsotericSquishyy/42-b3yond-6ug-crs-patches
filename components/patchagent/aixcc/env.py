import os


class EnvNotSetError(Exception): ...


def getenv_or_raise(var: str) -> str:
    value = os.getenv(var)
    if value is None:
        raise EnvNotSetError(f"Environment variable {var} is not set")
    return value


DB_URL: str = getenv_or_raise("AIXCC_DB_URL")
