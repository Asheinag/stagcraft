import json
from collections.abc import Callable

# ------------------------------------------------------------------- Similarity
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

# ------------------------------------------------------------------- Metadata

# Граф обязан быть ациклическим, но битые метаданные могут содержать петлю,
# а рекурсия без ограничения роняет процесс.
MAX_DEPTH = 30 
Resolver = Callable[[object], str]

def load_png_metadata(path:str) -> dict:
    """Load metadata from a PNG file."""
    result = {}

    with open(path, "rb") as f:
        head = f.read(8).hex()
        if head != "89504e470d0a1a0a":
            raise ValueError("Файл должен быть стандартного формата PNG")
        while True:
            chunk_len = int.from_bytes(f.read(4), "big")
            ch_type = f.read(4).decode()
            if ch_type == "IEND":
                break
            if ch_type == "tEXt":
                raw_data = f.read(chunk_len)
                result = json.loads(raw_data.decode()[7:])
                break
            else:
                f.seek(chunk_len + 4, 1)

    return result

# ------------------- обработчики
#
# Каждый обработчик умеет вычислить ОДИН тип узла: берёт его inputs и
# функцию resolve, возвращает строку. Про остальной граф он не знает ничего.
#
# Ключевая идея: обработчику всё равно, лежит во входе литерал или ссылка.
# Он всегда зовёт resolve(), а тот сам решает — вернуть значение как есть
# или спуститься в соседний узел.


def is_link(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
    )

def _text_encode(inputs: dict, resolve: Resolver) -> str:
    return resolve(inputs.get("text", ""))


def _string_const(inputs: dict, resolve: Resolver) -> str:
    return resolve(inputs.get("string", ""))


def _concat(inputs: dict, resolve: Resolver) -> str:
    left = resolve(inputs.get("string_a", ""))
    right = resolve(inputs.get("string_b", ""))
    return left + inputs.get("delimiter", "") + right


def _reroute(inputs: dict, resolve: Resolver) -> str:
    if not inputs:
        return ""
    return resolve(next(iter(inputs.values())))


# Таблица: class_type -> обработчик.
HANDLERS: dict[str, Callable[[dict, Resolver], str]] = {
    "CLIPTextEncode": _text_encode,
    "CLIPTextEncodeSDXL": _text_encode,
    "StringConstantMultiline": _string_const,
    "StringConstant": _string_const,
    "String Literal": _string_const,
    "StringConcatenate": _concat,
    "Reroute": _reroute,
}

# ------------------- вычисление
def eval_node(graph: dict, node_id: str, depth: int = 0) -> str:
    if depth > MAX_DEPTH:
        return "<слишком глубокая вложенность>"

    node = graph.get(node_id)
    if node is None:
        return f"<нет узла {node_id}>"

    class_type = node.get("class_type", "?")
    handler = HANDLERS.get(class_type)
    if handler is None:
        title = node.get("_meta", {}).get("title", "")
        return f"<узел {node_id}: {class_type} «{title}» — вычислять не умею>"

    def resolve(value: object) -> str:
        if is_link(value):
            return eval_node(graph, value[0], depth + 1)  # type: ignore[index]
        return str(value)

    return handler(node.get("inputs", {}), resolve)


# ------------------- поиск точек входа

def find_samplers(graph: dict) -> list[tuple[str, dict]]:
    return [
        (node_id, node)
        for node_id, node in graph.items()
        if isinstance(node, dict)
        and "positive" in node.get("inputs", {})
        and "negative" in node.get("inputs", {})
    ]


def extract_prompts(graph: dict) -> list[dict]:
    """Главная функция модуля: граф -> список промптов по одному на семплер.

    Семплеров в графе может быть несколько (например, базовый проход и
    хайрез-фикс), поэтому возвращается список, а не одна пара строк.
    """
    result = []
    for node_id, node in find_samplers(graph):
        inputs = node["inputs"]
        result.append({
            "sampler_id": node_id,
            "sampler_class": node.get("class_type", "?"),
            "title": node.get("_meta", {}).get("title", ""),
            "positive": _eval_input(graph, inputs["positive"]),
            "negative": _eval_input(graph, inputs["negative"]),
        })
    return result


def _eval_input(graph: dict, value: object) -> str:
    """Вход семплера — почти всегда ссылка, но подстрахуемся на литерал."""
    if is_link(value):
        return eval_node(graph, value[0])  # type: ignore[index]
    return str(value)
