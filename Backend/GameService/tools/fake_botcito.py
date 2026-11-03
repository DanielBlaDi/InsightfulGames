"""Gateway interno falso para probar Single Player sin el gateway ni Stockfish.

Uso:
    pip install chess
    GAME_LOGIC_URL=http://localhost:8082 python fake_botcito.py   # escucha en el puerto 8000
    # y Single Player con GATEWAY_INTERNAL_URL=http://localhost:8000

Atiende lo que Single Player pide al gateway interno (contrato, 7.4.2):
    /internal/logic/*            se reenvía tal cual a GAME_LOGIC_URL (método, cuerpo y query)
    POST /internal/engine/best-move   {"fen": "...", "botLevel": 1-20}  (contrato, 14.4)
      -> 200 {"uci": "e7e5", "san": "e5", "evaluation": {"type": "cp", "value": 0, "perspective": "side_to_move"}}
      -> 400 INVALID_FEN | 422 NO_LEGAL_MOVES   (con la forma { "error": { "code", "message" } })
"""
import json
import os
import random
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

GAME_LOGIC_URL = os.getenv("GAME_LOGIC_URL", "http://localhost:8082").rstrip("/")

import chess


class Handler(BaseHTTPRequestHandler):
    def read_body(self):
        """Lee el cuerpo con Content-Length o con Transfer-Encoding: chunked."""
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            data = b""
            while True:
                line = self.rfile.readline().split(b";")[0].strip()
                size = int(line or b"0", 16)
                if size == 0:
                    self.rfile.readline()  # CRLF final
                    break
                data += self.rfile.read(size)
                self.rfile.readline()  # CRLF después de cada trozo
            return data
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def reply(self, status, payload):
        out = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def error(self, status, code, message):
        self.reply(status, {"error": {"code": code, "message": message}})

    def proxy_logic(self):
        """Reenvía /internal/logic/* a Game Logic y devuelve su respuesta sin cambios."""
        raw = self.read_body() if self.command in ("POST", "PATCH", "PUT") else None
        request = urllib.request.Request(GAME_LOGIC_URL + self.path, data=raw, method=self.command,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status, body = response.status, response.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        except urllib.error.URLError:
            self.error(503, "SERVICES_UNAVAILABLE", "Game Logic no disponible")
            return
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/internal/logic/"):
            self.proxy_logic()
        elif self.path.rstrip("/") == "/health":
            self.reply(200, {"status": "ok"})
        else:
            self.error(404, "NOT_FOUND", "ruta no encontrada")

    def do_PATCH(self):
        if self.path.startswith("/internal/logic/"):
            self.proxy_logic()
        else:
            self.error(404, "NOT_FOUND", "ruta no encontrada")

    def do_POST(self):
        if self.path.startswith("/internal/logic/"):
            self.proxy_logic()
            return
        if self.path.rstrip("/") != "/internal/engine/best-move":
            self.error(404, "NOT_FOUND", "ruta no encontrada")
            return
        raw = self.read_body()
        try:
            body = json.loads(raw)
            board = chess.Board(body["fen"])
        except Exception as e:
            print(f"PETICION INVALIDA ({e}). Cuerpo: {raw!r}")
            self.error(400, "INVALID_FEN", "FEN mal formada")
            return

        legal = list(board.legal_moves)
        if not legal:
            self.error(422, "NO_LEGAL_MOVES", "No hay jugadas posibles")
            return
        move = random.choice(legal)  # el nivel se ignora en este falso
        san = board.san(move)
        print(f"botLevel={body.get('botLevel')} fen={body['fen']} -> {move.uci()} ({san})")
        self.reply(200, {"uci": move.uci(), "san": san,
                         "evaluation": {"type": "cp", "value": 0, "perspective": "side_to_move"}})


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
