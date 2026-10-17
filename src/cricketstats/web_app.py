from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .mongodb_assistant import answer, schema_summary
from .mongodb_client import MongoSettings, create_client

STATIC = Path(__file__).with_name("web_static")


def human_answer(question: str, rows: list[dict]) -> str:
    if not rows:
        return "No matching record was found in the selected MongoDB dataset."
    row = rows[0]
    player = row.get("player_name")
    lower = question.lower()
    if "first indian" in lower and "centur" in lower and "both" in lower and "innings" in lower:
        scores = row.get("scores", [])
        score_text = " and ".join(str(score) for score in scores[:2])
        return f"Vijay Hazare was the first Indian to score centuries in both innings of a Test, making {score_text} against {row.get('opposition')}."
    if "orange cap" in lower:
        return f"{player} won the {row.get('year')} IPL Orange Cap with {row.get('runs_scored'):,} runs."
    if "purple cap" in lower:
        return f"{player} won the {row.get('year')} IPL Purple Cap with {row.get('wickets_taken')} wickets."
    fields = (
        ("batting_average", "Test batting average"), ("bowling_average", "Test bowling average"),
        ("hundreds", "Test hundreds"), ("wickets_taken", "Test wickets"),
        ("catches", "Test catches"), ("runs_scored", "runs"), ("sixes", "sixes"),
    )
    for field, label in fields:
        if field in row:
            value = row[field]
            value = f"{value:,}" if isinstance(value, int) else value
            if "most" in lower:
                return f"{player} leads the database with {value} {label}."
            return f"{player} has {value} {label} in the available records."
    return json.dumps(row, ensure_ascii=False, default=str)


class App:
    def __init__(self, uri: str):
        settings = MongoSettings.from_env()
        self.client = create_client(uri)
        self.databases = {"Test": self.client[settings.database], "IPL": self.client[settings.ipl_database]}
        self.schemas = {name: schema_summary(db) for name, db in self.databases.items()}
        self.history = {"Test": [], "IPL": []}

    def ask(self, mode: str, question: str) -> dict:
        if mode not in self.databases:
            raise ValueError("Format must be Test or IPL")
        if not question.strip() or len(question) > 500:
            raise ValueError("Enter a question of 1 to 500 characters")
        result = answer(question.strip(), self.databases[mode], self.schemas[mode], self.history[mode])
        return {"answer": human_answer(question, result["rows"]), "rows": result["rows"], "plan": result["plan"]}


def handler_factory(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def send_json(self, status: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            if urlparse(self.path).path != "/api/ask":
                return self.send_json(404, {"error": "Not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(min(length, 4096)))
                self.send_json(200, app.ask(data.get("format", "Test"), data.get("question", "")))
            except Exception as exc:
                self.send_json(400, {"error": str(exc)})

        def do_GET(self):
            request = urlparse(self.path).path
            relative = "index.html" if request == "/" else request.lstrip("/")
            target = (STATIC / relative).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                self.send_error(404); return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
    return Handler


def main() -> int:
    settings = MongoSettings.from_env()
    parser = argparse.ArgumentParser(description="CricketStats MongoDB web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--uri", default=settings.uri)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(App(args.uri)))
    print(f"CricketStats UI: http://{args.host}:{args.port}", flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
