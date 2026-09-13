"""Cliente WebSocket mínimo (RFC 6455) sobre sockets de la biblioteca estándar.

Python no trae cliente websocket y el plugin no lleva dependencias, así que va
aquí. Solo lo que necesita el gateway de OpenClaw: handshake, tramas de texto,
ping/pong y cierre. Sin extensiones ni compresión —el gateway no las pide— y sin
fragmentación de salida, porque los mensajes que mandamos son JSON cortos.

Dos cosas que no son negociables cuando al otro lado hay un agente escupiendo
eventos sin parar:

  * Una trama se consume **entera o nada**. Si se sacan del buffer los bytes de
    la cabecera y luego resulta que el cuerpo todavía no ha llegado, el flujo
    queda descolocado para siempre y a partir de ahí todo lo que se lee es
    basura. Por eso `_take_frame` mira si está completa antes de tocar nada.
  * `poll()` no bloquea. La TUI tiene que volver al teclado aunque sigan
    llegando eventos, así que quien llama decide cuántos mensajes atiende de
    una tacada en vez de vaciar la tubería hasta que se seque.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import time
import urllib.parse

OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class WebSocketError(RuntimeError):
    pass


class WebSocketClosed(WebSocketError):
    """Cierre del otro extremo: trae el código y el motivo."""

    def __init__(self, code: int, reason: str):
        super().__init__(f"websocket cerrado ({code}): {reason}" if reason
                         else f"websocket cerrado ({code})")
        self.code = code
        self.reason = reason


class WebSocket:
    """Conexión websocket de texto. No es thread-safe para lecturas."""

    def __init__(self, url: str, *, origin: str | None = None,
                 headers: dict[str, str] | None = None, timeout: float = 15.0):
        parts = urllib.parse.urlsplit(url)
        secure = parts.scheme in ("wss", "https")
        host = parts.hostname or "localhost"
        port = parts.port or (443 if secure else 80)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"

        key = base64.b64encode(os.urandom(16)).decode()
        lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ]
        # El gateway compara Origin con su bind: sin él responde 4403.
        if origin:
            lines.append(f"Origin: {origin}")
        for name, value in (headers or {}).items():
            lines.append(f"{name}: {value}")

        self.timeout = timeout
        self._sock = socket.create_connection((host, port), timeout)
        if secure:
            context = ssl.create_default_context()
            self._sock = context.wrap_socket(self._sock, server_hostname=host)
        self._sock.settimeout(timeout)
        self._sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())

        self._buf = b""
        while b"\r\n\r\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise WebSocketError("el servidor cerró durante el handshake")
            self._buf += chunk
        head, self._buf = self._buf.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0].decode("latin-1")
        if " 101 " not in status:
            raise WebSocketError(f"el servidor no aceptó el upgrade: {status}")

        self._fragments: list[bytes] = []
        self.closed = False

    def fileno(self) -> int:
        return self._sock.fileno()

    # ------------------------------------------------------------------ lectura

    def _take_frame(self) -> tuple[bool, int, bytes] | None:
        """Saca una trama completa del buffer. None si aún no ha llegado entera."""
        buf = self._buf
        if len(buf) < 2:
            return None
        first, second = buf[0], buf[1]
        length = second & 0x7F
        index = 2
        if length == 126:
            if len(buf) < 4:
                return None
            length = struct.unpack("!H", buf[2:4])[0]
            index = 4
        elif length == 127:
            if len(buf) < 10:
                return None
            length = struct.unpack("!Q", buf[2:10])[0]
            index = 10
        mask = b""
        if second & 0x80:                       # el servidor no debería enmascarar
            if len(buf) < index + 4:
                return None
            mask = buf[index:index + 4]
            index += 4
        if len(buf) < index + length:
            return None
        payload = buf[index:index + length]
        self._buf = buf[index + length:]
        if mask:
            payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        return bool(first & 0x80), first & 0x0F, payload

    def _take_message(self) -> str | None:
        """Siguiente mensaje que ya esté entero en el buffer, o None."""
        while True:
            frame = self._take_frame()
            if frame is None:
                return None
            fin, opcode, payload = frame
            if opcode == OP_PING:
                self._send_frame(payload, OP_PONG)
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else 1005
                self.closed = True
                raise WebSocketClosed(code, payload[2:].decode("utf-8", "replace"))
            if opcode in (OP_TEXT, OP_BIN):
                self._fragments = [payload]
            elif opcode == OP_CONT:
                self._fragments.append(payload)
            if fin and self._fragments:
                data = b"".join(self._fragments)
                self._fragments = []
                return data.decode("utf-8", "replace")

    def _fill(self, timeout: float) -> bool:
        """Mete en el buffer lo que haya en el socket. False si no llegó nada."""
        try:
            self._sock.settimeout(timeout)
            chunk = self._sock.recv(65536)
        except (TimeoutError, socket.timeout, BlockingIOError):
            return False
        except ssl.SSLWantReadError:
            return False
        if not chunk:
            self.closed = True
            raise WebSocketClosed(1006, "conexión cortada")
        self._buf += chunk
        return True

    def poll(self) -> str | None:
        """Un mensaje si lo hay, sin esperar. None si no hay nada listo."""
        message = self._take_message()
        if message is not None:
            return message
        if not self._fill(0.0):
            return None
        return self._take_message()

    def recv(self, timeout: float | None = None) -> str:
        """Siguiente mensaje, esperando hasta `timeout` segundos."""
        limit = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + limit
        while True:
            message = self._take_message()
            if message is not None:
                return message
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("el websocket no trajo nada a tiempo")
            self._fill(remaining)

    # ------------------------------------------------------------------ escritura

    def _send_frame(self, data: bytes, opcode: int) -> None:
        mask = os.urandom(4)
        length = len(data)
        header = bytes([0x80 | opcode])
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", length)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(data))
        self._sock.settimeout(self.timeout)
        self._sock.sendall(header + mask + masked)

    def send(self, text: str) -> None:
        self._send_frame(text.encode("utf-8"), OP_TEXT)

    def send_json(self, payload: dict) -> None:
        self.send(json.dumps(payload, separators=(",", ":")))

    def close(self, code: int = 1000, reason: str = "") -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self._send_frame(struct.pack("!H", code) + reason.encode("utf-8"), OP_CLOSE)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass
