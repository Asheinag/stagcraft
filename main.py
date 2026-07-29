import argparse
import functools
import threading
import webbrowser

from dataset import Dataset
from server import Handler, Server


def main():
    ap = argparse.ArgumentParser(description="Редактор кэпшенов для LoRA-датасета")
    ap.add_argument("directory", help="папка с картинками и .txt")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    ds = Dataset(args.directory)

    if not ds.root.is_dir():
        raise SystemExit(f"нет такой папки: {ds.root}")

    if not ds.image_files():
        raise SystemExit(f"в {ds.root} не найдено картинок")

    url = f"http://127.0.0.1:{args.port}/"
    print(f"папка : {ds.root}")
    print(f"кадров: {len(ds.image_files())}")
    print(f"адрес : {url}   (Ctrl+C — выход)")

    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    with Server(("127.0.0.1", args.port), functools.partial(Handler, ds)) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nпока")


if __name__ == "__main__":
    main()
