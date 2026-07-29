import os
from pathlib import Path

from utilities import similar_map, split_tags

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class Dataset:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def image_files(self):
        """Отсортированный список картинок в рабочей папке."""
        return sorted(
            p
            for p in self.root.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXT
        )

    def caption_path(self, img: Path) -> Path:
        return img.with_suffix(".txt")

    def read_caption(self, img: Path) -> str:
        cp = self.caption_path(img)
        if cp.exists():
            return cp.read_text(encoding="utf-8").strip()
        return ""

    def write_caption(self, img: Path, text: str) -> None:
        self.caption_path(img).write_text(text.strip() + "\n", encoding="utf-8")

    def safe_image(self, name: str) -> Path:
        """Не выпускаем за пределы рабочей папки."""
        candidate = (self.root / os.path.basename(name)).resolve()
        if candidate.parent != self.root.resolve() or not candidate.is_file():
            raise ValueError("bad path")
        return candidate

    def build_state(self):
        items = []
        counts = {}
        for img in self.image_files():
            cap = self.read_caption(img)
            tags = split_tags(cap)
            # считаем кадры, а не вхождения: дубль внутри одного .txt
            # не должен накручивать частоту
            for t in dict.fromkeys(tags):
                counts[t] = counts.get(t, 0) + 1
            items.append(
                {
                    "name": img.name,
                    "caption": cap,
                    "hasCaption": self.caption_path(img).exists(),
                }
            )
        tags_sorted = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return {
            "items": items,
            "tags": tags_sorted,
            "similar": similar_map(sorted(counts)),
            "dir": str(self.root),
        }

    def get_tags(self, img: Path) -> list[str]:
        return split_tags(self.read_caption(img))
