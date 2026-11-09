"""
Web Visitor Counter Log - Backend REST API
==========================================
Studi Kasus #5 - Ujian Chunin Cloud Computing (Telkom University)

REST API berbasis Python standard library (http.server) tanpa framework berat.
Seluruh data disimpan secara atomik ke file JSON di dalam Docker Named Volume
(/var/lib/backend_data/visitor_logs.json).

Endpoint:
  GET    /logs          -> Total hit, statistik per halaman, dan daftar log kunjungan
  POST   /logs          -> Tambah log kunjungan baru (body JSON: {"page": "...", "visitor": "..."})
  DELETE /logs?index=X  -> Hapus entri log pada indeks ke-X
  GET    /health        -> Health check untuk Docker & Jenkins CI/CD Pipeline Stage 5
"""

import json
import os
import sys
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
DATA_DIR = os.environ.get("DATA_DIR", "/var/lib/backend_data")
DATA_FILE = os.path.join(DATA_DIR, os.environ.get("DATA_FILE", "visitor_logs.json"))
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")

MAX_BODY_BYTES = 16 * 1024  # 16 KB
MAX_FIELD_LEN = 200

_lock = threading.Lock()


def ensure_storage() -> None:
    """Pastikan direktori dan file JSON tersedia saat startup."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        write_logs([])


def read_logs() -> list:
    """Membaca daftar log dari file JSON di dalam Named Volume."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_logs(logs: list) -> None:
    """Atomic write: tulis ke file sementara lalu replace agar JSON tidak pernah korup."""
    tmp_path = f"{DATA_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, DATA_FILE)


def build_summary(logs: list) -> dict:
    """Menghitung statistik total hit, pengunjung unik, dan hit per halaman."""
    pages: dict[str, int] = {}
    for entry in logs:
        page = entry.get("page", "/")
        pages[page] = pages.get(page, 0) + 1
    unique_visitors = len({entry.get("visitor", "anonymous") for entry in logs})
    sorted_pages = dict(sorted(pages.items(), key=lambda kv: kv[1], reverse=True))
    return {
        "total_hits": len(logs),
        "unique_visitors": unique_visitors,
        "hits_per_page": sorted_pages,
        "logs": logs,
    }


class VisitorLogHandler(BaseHTTPRequestHandler):
    server_version = "VisitorLogAPI/1.0"

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": message, "status": int(status)})

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _parse_route(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        return path, parse_qs(parsed.query)

    def _client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0]

    def log_message(self, fmt: str, *args) -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sys.stdout.write(f"[{ts}] {self._client_ip()} - {fmt % args}\n")
        sys.stdout.flush()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        path, _ = self._parse_route()
        if path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "visitor-log-backend",
                    "version": APP_VERSION,
                    "storage": DATA_FILE,
                    "storage_writable": os.access(DATA_DIR, os.W_OK),
                },
            )
            return

        if path == "/logs":
            with _lock:
                logs = read_logs()
            self._send_json(HTTPStatus.OK, build_summary(logs))
            return

        self._send_error(HTTPStatus.NOT_FOUND, f"Endpoint '{path}' tidak ditemukan")

    def do_POST(self) -> None:
        path, _ = self._parse_route()
        if path != "/logs":
            self._send_error(HTTPStatus.NOT_FOUND, f"Endpoint '{path}' tidak ditemukan")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_error(HTTPStatus.BAD_REQUEST, "Header Content-Length tidak valid")
            return

        if length <= 0:
            self._send_error(HTTPStatus.BAD_REQUEST, "Body request kosong, kirimkan JSON object")
            return
        if length > MAX_BODY_BYTES:
            self._send_error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"Ukuran body melebihi batas {MAX_BODY_BYTES} byte",
            )
            return

        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error(HTTPStatus.BAD_REQUEST, "Body bukan format JSON yang valid")
            return

        if not isinstance(payload, dict):
            self._send_error(HTTPStatus.BAD_REQUEST, "Body JSON harus berupa object")
            return

        page = payload.get("page")
        if not isinstance(page, str) or not page.strip():
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "Field 'page' wajib diisi dan harus berupa string tidak kosong",
            )
            return

        visitor = payload.get("visitor")
        if visitor is None or (isinstance(visitor, str) and not visitor.strip()):
            visitor = "anonymous"
        elif not isinstance(visitor, str):
            self._send_error(HTTPStatus.BAD_REQUEST, "Field 'visitor' harus berupa string")
            return

        page = page.strip()
        visitor = visitor.strip()
        if len(page) > MAX_FIELD_LEN or len(visitor) > MAX_FIELD_LEN:
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                f"Panjang field maksimal {MAX_FIELD_LEN} karakter",
            )
            return

        if not page.startswith("/"):
            page = "/" + page

        entry = {
            "page": page,
            "visitor": visitor,
            "ip": self._client_ip(),
            "user_agent": (self.headers.get("User-Agent") or "unknown")[:MAX_FIELD_LEN],
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

        with _lock:
            logs = read_logs()
            logs.append(entry)
            write_logs(logs)
            total = len(logs)

        self._send_json(
            HTTPStatus.CREATED,
            {
                "message": "Log kunjungan berhasil ditambahkan",
                "index": total - 1,
                "total_hits": total,
                "data": entry,
            },
        )

    def do_DELETE(self) -> None:
        path, query = self._parse_route()
        if path != "/logs":
            self._send_error(HTTPStatus.NOT_FOUND, f"Endpoint '{path}' tidak ditemukan")
            return

        if "index" not in query or not query["index"]:
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "Query parameter 'index' wajib diisi, contoh: DELETE /logs?index=0",
            )
            return

        raw_index = query["index"][0]
        try:
            index = int(raw_index)
        except ValueError:
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                f"Parameter index '{raw_index}' harus berupa bilangan bulat",
            )
            return

        if index < 0:
            self._send_error(HTTPStatus.BAD_REQUEST, "Parameter 'index' tidak boleh bernilai negatif")
            return

        with _lock:
            logs = read_logs()
            if index >= len(logs):
                self._send_error(
                    HTTPStatus.NOT_FOUND,
                    f"Log dengan index {index} tidak ditemukan (total entri saat ini: {len(logs)})",
                )
                return
            deleted_entry = logs.pop(index)
            write_logs(logs)
            total = len(logs)

        self._send_json(
            HTTPStatus.OK,
            {
                "message": f"Log pada index {index} berhasil dihapus",
                "total_hits": total,
                "deleted": deleted_entry,
            },
        )

    def _method_not_allowed(self) -> None:
        self._send_error(HTTPStatus.METHOD_NOT_ALLOWED, f"Method {self.command} tidak didukung")

    do_PUT = do_PATCH = _method_not_allowed


def main() -> None:
    ensure_storage()
    server = ThreadingHTTPServer((HOST, PORT), VisitorLogHandler)
    print(f"[startup] Visitor Log API v{APP_VERSION} listening on {HOST}:{PORT}", flush=True)
    print(f"[startup] Persistent storage file: {DATA_FILE}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
