"""Small pure helpers with no app dependencies."""


def mask_name(name: str) -> str:
    """김철수 -> 김*수, 김수 -> 김*, 남궁민수 -> 남**수."""
    if len(name) <= 1:
        return name
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def pct(part: int, whole: int) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0
