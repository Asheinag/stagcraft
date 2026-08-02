import http.server
import json
import mimetypes
import socketserver
import urllib.parse
from pathlib import Path

from dataset import Dataset

STATIC = Path(__file__).resolve().parent / "static"


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, dataset: Dataset, *args, **kw):
        self.dataset = dataset
        super().__init__(*args, **kw)

    # def log_message(self, format, *args):
    #     pass

    # -- утилиты ответа
    def _serve_static(self, rel: str):
        p = (STATIC / rel).resolve()
        if not p.is_file() or STATIC not in p.parents:
            self._send(404, b"not found", "text/plain")
            return
        ctype, _ = mimetypes.guess_type(p.name)
        self._send(200, p.read_bytes(), ctype or "application/octet-stream")

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    # -- маршруты

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send(
                200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8"
            )
            return

        if path.startswith("/static/"):
            self.log_message("Static Loading: start load static")
            self._serve_static(path[len("/static/") :])
            return

        if path == "/api/state":
            self.log_message("State Loading: start load state")
            self._json(self.dataset.build_state())
            return

        if path.startswith("/img/"):
            self.log_message("Img Loading: start load img")
            name = urllib.parse.unquote(path[len("/img/") :])
            try:
                p = self.dataset.safe_image(name)
            except ValueError:
                self._send(404, b"not found", "text/plain")
                return
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            data = p.read_bytes()
            self._send(200, data, ctype)
            return

        if path == "/api/meta":
            self.log_message("Meta Loading: start load meta")
            params = urllib.parse.parse_qs(parsed.query)
            name = params.get("name", [""])[0]
            try:
                image = self.dataset.safe_image(name)
            except ValueError:
                self._json({"error": "bad name"}, 400)
                return
            self._json(self.dataset.get_metadata(image))
            return
        
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            data = self._body()
        except ValueError:
            self._json({"error": "bad json"}, 400)
            return

        if path == "/api/save":
            try:
                img = self.dataset.safe_image(data["name"])
            except (ValueError, KeyError):
                self._json({"error": "bad name"}, 400)
                return
            self.dataset.write_caption(img, data.get("caption", ""))
            st = self.dataset.build_state()
            self._json({"ok": True, "tags": st["tags"], "similar": st["similar"]})
            return

        if path == "/api/rename":
            old = (data.get("old") or "").strip()
            new = (data.get("new") or "").strip()
            if not old:
                self._json({"error": "empty tag"}, 400)
                return
            changed = 0
            for img in self.dataset.image_files():
                tags = self.dataset.get_tags(img)
                if old not in tags:
                    continue
                out = []
                for t in tags:
                    if t == old:
                        if new and new not in out:
                            out.append(new)
                    elif t not in out:
                        out.append(t)
                self.dataset.write_caption(img, ", ".join(out))
                changed += 1
            self._json({"ok": True, "changed": changed, **self.dataset.build_state()})
            return

        if path == "/api/bulk":
            # добавить или убрать тег у списка файлов
            names = data.get("names") or []
            tag = (data.get("tag") or "").strip()
            mode = data.get("mode", "add")
            if not tag:
                self._json({"error": "empty tag"}, 400)
                return
            changed = 0
            for name in names:
                try:
                    img = self.dataset.safe_image(name)
                except ValueError:
                    continue
                tags = self.dataset.get_tags(img)
                if mode == "add":
                    if tag in tags:
                        continue
                    tags.append(tag)
                else:
                    if tag not in tags:
                        continue
                    tags = [t for t in tags if t != tag]
                self.dataset.write_caption(img, ", ".join(tags))
                changed += 1
            self._json({"ok": True, "changed": changed, **self.dataset.build_state()})
            return

        self._json({"error": "unknown route"}, 404)
