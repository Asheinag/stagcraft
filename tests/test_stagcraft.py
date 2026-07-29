import pytest

from dataset import Dataset
from utilities import levenshtein, looks_similar, similar_map, split_tags

# ---------------------------------------------------------------- хелперы


def sim(a: str, b: str) -> bool:
    """looks_similar принимает предпосчитанные токены — в тестах считаем их тут."""
    return looks_similar(
        a,
        tuple(sorted(a.split())),
        b,
        tuple(sorted(b.split())),
    )


@pytest.fixture
def make_ds(tmp_path):
    def _make(captions: dict[str, str | None]) -> Dataset:
        for name, text in captions.items():
            (tmp_path / f"{name}.png").write_bytes(b"")
            if text is not None:
                (tmp_path / f"{name}.txt").write_text(text, encoding="utf-8")
        return Dataset(tmp_path)

    return _make


# ---------------------------------------------------------------- levenshtein


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ("smile", "smile", 0),
        ("smile", "smle", 1),
        ("looking down", "looikng down", 2),
        ("", "abc", 3),
    ],
)
def test_levenshtein(a, b, expected):
    assert levenshtein(a, b, cap=9) == expected


def test_levenshtein_cap():
    """При превышении cap точное значение не считается, возвращается cap + 1."""
    assert levenshtein("indoors", "outdoors", cap=1) == 2


# ---------------------------------------------------------------- looks_similar


@pytest.mark.parametrize(
    "a, b",
    [
        ("eyes closed", "closed eyes"),  # перестановка слов
        ("looking down", "looking downwards"),  # хвост слова
        ("1girl", "1girls"),
        ("smile", "smiling"),  # общий префикс внутри слова
        ("cowboy shot", "cowboy shoot"),
        ("looking down", "looikng down"),  # опечатка в середине
        ("hand on hip", "hands on hips"),
    ],
    ids=[
        "word-order",
        "tail-suffix",
        "plural",
        "common-prefix",
        "typo-tail",
        "typo-midword",
        "plural-two-words",
    ],
)
def test_similar(a, b):
    assert sim(a, b) is True


@pytest.mark.parametrize(
    "a, b",
    [
        ("blue eyes", "blue eyes closed"),  # дописано целое слово — разные теги
        ("long hair", "long hair ornament"),
        ("long hair", "long sleeves"),  # общий префикс кончается на границе слова
        ("open mouth", "open eyes"),
        ("looking down", "looking up"),
        ("1girl", "1boy"),
        ("indoors", "outdoors"),
    ],
    ids=[
        "extra-word",
        "extra-word-2",
        "prefix-at-boundary",
        "prefix-at-boundary-2",
        "different-direction",
        "different-subject",
        "antonym",
    ],
)
def test_not_similar(a, b):
    assert sim(a, b) is False


def test_similar_ignores_identical():
    assert sim("smile", "smile") is False


@pytest.mark.parametrize(
    "a, b",
    [
        ("eyes closed", "closed eyes"),
        ("smile", "smiling"),
        ("1girl", "1boy"),
    ],
)
def test_similar_is_symmetric(a, b):
    assert sim(a, b) == sim(b, a)


# ---------------------------------------------------------------- similar_map


def test_similar_map_links_both_directions():
    m = similar_map(["looking down", "looking downwards", "solo"])
    assert m["looking down"] == ["looking downwards"]
    assert m["looking downwards"] == ["looking down"]
    assert "solo" not in m  # без пары в карту не попадает


# ---------------------------------------------------------------- split_tags


@pytest.mark.parametrize(
    "caption, expected",
    [
        ("1girl, solo", ["1girl", "solo"]),
        ("  1girl ,  solo  ", ["1girl", "solo"]),  # пробелы обрезаются
        ("1girl,, solo", ["1girl", "solo"]),  # пустые куски выкидываются
        ("", []),
        ("1girl, 1girl", ["1girl", "1girl"]),  # дубли сохраняются
    ],
)
def test_split_tags(caption, expected):
    assert split_tags(caption) == expected


# ---------------------------------------------------------------- build_state


@pytest.mark.parametrize(
    "captions, expected",
    [
        ({"0001": "1girl, solo"}, {"1girl": 1, "solo": 1}),
        ({"0001": "1girl, 1girl"}, {"1girl": 1}),  # дубль не накручивает
        ({"0001": "1girl", "0002": "1girl, solo"}, {"1girl": 2, "solo": 1}),
        ({"0001": ""}, {}),
    ],
    ids=["single-frame", "duplicate-in-file", "two-frames", "empty-caption"],
)
def test_tag_counts(make_ds, captions, expected):
    ds = make_ds(captions)
    assert dict(ds.build_state()["tags"]) == expected


def test_counts_sorted_by_frequency(make_ds):
    ds = make_ds({"0001": "rare, common", "0002": "common"})
    names = [t for t, _ in ds.build_state()["tags"]]
    assert names == ["common", "rare"]


def test_items_carry_captions(make_ds):
    ds = make_ds({"0002": "solo", "0001": "1girl"})
    items = ds.build_state()["items"]
    assert [i["name"] for i in items] == ["0001.png", "0002.png"]  # отсортированы
    assert items[0]["caption"] == "1girl"


def test_missing_txt_gives_empty_caption(make_ds):
    ds = make_ds({"0001": None})
    assert ds.build_state()["items"][0]["caption"] == ""


def test_state_includes_similar(make_ds):
    ds = make_ds({"0001": "looking down", "0002": "looking downwards"})
    assert ds.build_state()["similar"]["looking down"] == ["looking downwards"]


# ---------------------------------------------------------------- запись


def test_write_caption_roundtrip(make_ds):
    ds = make_ds({"0001": "1girl"})
    img = ds.root / "0001.png"
    ds.write_caption(img, "solo, indoors")
    assert ds.read_caption(img) == "solo, indoors"


def test_blank_caption_reads_as_empty(make_ds):
    """Пустой кэпшен не удаляет .txt, а оставляет файл с одним переводом строки."""
    ds = make_ds({"0001": "1girl"})
    img = ds.root / "0001.png"
    ds.write_caption(img, "   ")
    assert ds.read_caption(img) == ""
    assert ds.caption_path(img).exists()
