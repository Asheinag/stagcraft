def levenshtein(a: str, b: str, cap: int) -> int:
    """Расстояние Левенштейна с ранним выходом: если явно больше cap — не считаем."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            best = min(best, v)
        if best > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def looks_similar(a: str, toks_a, b: str, toks_b) -> bool:
    """Три правила: перестановка слов, хвост слова, опечатка."""
    if a == b:
        return False

    # 1. те же слова в другом порядке: eyes closed / closed eyes
    if toks_a == toks_b:
        return True

    short, long_ = (a, b) if len(a) <= len(b) else (b, a)

    # 2. один тег — продолжение другого внутри последнего слова:
    #    looking down / looking downwards, 1girl / 1girls.
    #    Если дописано целое новое слово (blue eyes / blue eyes closed) —
    #    это обычно разные легитимные теги, не трогаем.
    if len(short) >= 3 and long_.startswith(short):
        rest = long_[len(short) :]
        if " " not in rest:
            return True

    # 2b. общий префикс внутри слова: smile / smiling, cowboy shot / cowboy shoot.
    #     Префикс не должен заканчиваться пробелом, иначе слипнутся заведомо
    #     разные теги (long hair / long sleeves, open mouth / open eyes).
    n = 0
    while n < len(short) and short[n] == long_[n]:
        n += 1
    if n >= 3 and short[n - 1] != " " and n / len(short) >= 0.7:  # noqa: SIM102
        if " " not in short[n:] and " " not in long_[n:]:
            return True

    # 3. опечатка в любом месте строки. Порог зависит от длины,
    #    иначе на коротких тегах ловится всё подряд (solo / sold).
    limit = 1 if max(len(a), len(b)) < 8 else 2
    if abs(len(a) - len(b)) <= limit:
        return levenshtein(a, b, limit) <= limit

    return False


_sim_cache = {}


def similar_map(tags):
    """{тег: [похожие теги]} по всему датасету. Результат кэшируется."""
    key = tuple(tags)
    if key in _sim_cache:
        return _sim_cache[key]

    toks = [(t, tuple(sorted(t.split()))) for t in tags]
    out = {}
    for i, (a, ta) in enumerate(toks):
        for b, tb in toks[i + 1 :]:
            if looks_similar(a, ta, b, tb):
                out.setdefault(a, []).append(b)
                out.setdefault(b, []).append(a)

    _sim_cache.clear()  # держим только последний срез
    _sim_cache[key] = out
    return out

def split_tags(caption: str) -> list[str]:
    return [t.strip() for t in caption.split(",") if t.strip()]
