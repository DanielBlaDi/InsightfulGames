"""Botcito falso para probar el modo BOT sin Stockfish.

Uso:
    pip install chess
    python fake_botcito.py          # escucha en el puerto 8000

Contrato (el mismo que debe cumplir el Botcito real):
    POST /best-move   {"fen": "...", "level": 1-20}   ->   {"move": "e7e5"}
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
                self.rfile.readline()  # CRLF despues de cada trozo
            return data
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def reply(self, status, payload):
        out = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self):
        if self.path.rstrip("/") != "/best-move":
            self.reply(404, {"error": "ruta no encontrada"})
            return
        raw = self.read_body()
        try:
            body = json.loads(raw)
            board = chess.Board(body["fen"])
        except Exception as e:
            print(f"PETICION INVALIDA ({e}). Headers: {dict(self.headers)} Cuerpo: {raw!r}")
            self.reply(400, {"error": "peticion invalida"})
            return

        legal = list(board.legal_moves)
        if not legal:
            self.reply(409, {"error": "no hay jugadas legales"})
            return
        move = random.choice(legal).uci()  # el nivel se ignora en este falso
        print(f"level={body.get('level')} fen={body['fen']} -> {move}")
        self.reply(200, {"move": move})


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()