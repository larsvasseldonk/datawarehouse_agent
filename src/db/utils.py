import random
from hashlib import sha256
from datetime import date, timedelta


def make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def random_date(rng: random.Random, start: date, end: date) -> date:
    span = (end - start).days
    return start + timedelta(days=rng.randint(0, span))


def stable_hash_int(*parts: str, modulo: int = 10**15) -> int:
    joined = "|".join(parts)
    return int(sha256(joined.encode("utf-8")).hexdigest(), 16) % modulo
