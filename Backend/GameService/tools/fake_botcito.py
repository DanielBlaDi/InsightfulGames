"""Botcito falso para probar el modo vs_bot sin Stockfish (también hace de Gateway).

Uso:
    pip install chess
    python fake_botcito.py          # escucha en el puerto 8000

Contrato (sección 3.6), el mismo que debe cumplir el Botcito real:
    POST /engine/best-move   {"fen": "...", "level": 1-20}
      -> 200 {"uci": "e7e5", "san": "e5", "evaluation": {"type": "cp", "value": 0}}
      -> 400 INVALID_FEN | 422 NO_LEGAL_MOVES   (con la forma { "error": { "code", "message" } })
"""
import json
import random
from http.server import BaseHTTPRequestHandler, HTTPServer

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

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            self.reply(200, {"status": "ok"})
        else:
            self.error(404, "NOT_FOUND", "ruta no encontrada")

    def do_POST(self):
        if self.path.rstrip("/") != "/engine/best-move":
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
        print(f"level={body.get('level')} fen={body['fen']} -> {move.uci()} ({san})")
        self.reply(200, {"uci": move.uci(), "san": san, "evaluation": {"type": "cp", "value": 0}})


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
