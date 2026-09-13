"""Cliente del gateway de OpenClaw: handshake, peticiones y eventos.

El protocolo va todo por un websocket, en cualquier ruta del puerto del gateway
(la ruta que se ve en el navegador, /chat/main, es solo la SPA). Los sobres son:

    ->  {"type":"req",   "id": "...", "method": "chat.send", "params": {...}}
    <-  {"type":"res",   "id": "...", "ok": true, "payload": {...}}
    <-  {"type":"res",   "id": "...", "ok": false, "error": {"code", "message"}}
    <-  {"type":"event", "event": "session.message", "payload": {...}, "seq": N}

Al abrir, el servidor manda el evento `connect.challenge` con un nonce, y el
cliente responde con una petición `connect`. Ahí está toda la autenticación:

  * `auth.token`  — el token del gateway (el mismo que se pega en Control UI).
  * `device`      — identidad ed25519 del cliente, firmando el nonce. No es
                    opcional: sin ella el gateway responde DEVICE_IDENTITY_REQUIRED.

La cadena que se firma es, literalmente:

    v2|deviceId|clientId|clientMode|role|scopes|signedAtMs|token|nonce

Un dispositivo nuevo queda en «pendiente de aprobar»: el primer connect devuelve
NOT_PAIRED y crea una solicitud que hay que aceptar en Control UI → Settings →
Devices. A partir de ahí el mismo par de claves entra sin más. El `hello` trae un
`auth.deviceToken` que guardamos: es lo que permite reconectar si algún día
cambia el token del gateway.

La identidad vive en ~/.local/state/herdr-claw/device.json. Borrar ese fichero
equivale a presentarse como un dispositivo nuevo, con su aprobación otra vez.
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import os
import platform
import time
import urllib.parse
from pathlib import Path

import ed25519
from wsclient import WebSocket, WebSocketClosed, WebSocketError

# Protocolo que habla la Control UI de esta versión de OpenClaw. Si el gateway
# se actualiza a uno incompatible responde PROTOCOL_MISMATCH diciendo cuál pide.
PROTOCOL_MIN = 4
PROTOCOL_MAX = 4

# Identificador de cliente del enum del gateway: `openclaw-tui` existe ahí, y es
# lo que somos. Uno inventado se rechaza por esquema.
CLIENT_ID = "openclaw-tui"
CLIENT_MODE = "cli"
ROLE = "operator"
SCOPES = ["operator.read", "operator.write"]

# Capacidades del protocolo que entendemos. Declarar de menos es seguro (el
# gateway simplemente no manda esos eventos); declarar de más, no.
CAPS = ["agent-kind", "tool-events"]

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "herdr-claw"
DEVICE_PATH = STATE_DIR / "device.json"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class GatewayError(RuntimeError):
    """Error devuelto por el gateway, con su código para poder distinguirlo."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    @property
    def detail_code(self) -> str:
        return str(self.details.get("code") or self.code)


class PairingRequired(GatewayError):
    """El dispositivo existe pero nadie lo ha aprobado todavía."""

    @property
    def device_id(self) -> str:
        return str(self.details.get("deviceId") or "")


class DeviceIdentity:
    """Par de claves del dispositivo, persistido entre ejecuciones."""

    def __init__(self, data: dict):
        self.device_id: str = data["deviceId"]
        self.public_key: str = data["publicKey"]
        self.private_key: str = data["privateKey"]
        self._data = data

    @classmethod
    def load(cls, path: Path = DEVICE_PATH) -> "DeviceIdentity":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") == 1 and data.get("privateKey"):
                return cls(data)
        except (OSError, ValueError, KeyError):
            pass
        return cls.create(path)

    @classmethod
    def create(cls, path: Path = DEVICE_PATH) -> "DeviceIdentity":
        secret = os.urandom(32)
        public = ed25519.public_key(secret)
        data = {
            "version": 1,
            # El gateway identifica el dispositivo por el sha256 de la clave
            # pública, no por un id que elijamos nosotros.
            "deviceId": hashlib.sha256(public).hexdigest(),
            "publicKey": _b64u(public),
            "privateKey": _b64u(secret),
            "createdAtMs": int(time.time() * 1000),
            "tokens": {},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        path.chmod(0o600)
        return cls(data)

    def device_token(self, gateway_url: str) -> str | None:
        entry = (self._data.get("tokens") or {}).get(gateway_url)
        return entry.get("token") if isinstance(entry, dict) else None

    def remember_device_token(self, gateway_url: str, token: str, scopes: list[str]) -> None:
        if self.device_token(gateway_url) == token:
            return
        self._data.setdefault("tokens", {})[gateway_url] = {"token": token, "scopes": scopes}
        try:
            DEVICE_PATH.parent.mkdir(parents=True, exist_ok=True)
            DEVICE_PATH.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            DEVICE_PATH.chmod(0o600)
        except OSError:
            pass  # sin token guardado se vuelve a entrar con el del gateway

    def sign_connect(self, *, nonce: str, signed_at: int, token: str | None,
                     role: str, scopes: list[str]) -> dict:
        payload = "|".join([
            "v2", self.device_id, CLIENT_ID, CLIENT_MODE, role,
            ",".join(scopes), str(signed_at), token or "", nonce,
        ])
        signature = ed25519.sign(_unb64u(self.private_key), payload.encode("utf-8"),
                                 _unb64u(self.public_key))
        return {
            "id": self.device_id,
            "publicKey": self.public_key,
            "signature": _b64u(signature),
            "signedAt": signed_at,
            "nonce": nonce,
        }


def ws_url(base_url: str) -> str:
    """http://host:puerto/lo-que-sea -> ws://host:puerto/ (la ruta da igual)."""
    parts = urllib.parse.urlsplit(base_url if "://" in base_url else f"http://{base_url}")
    scheme = "wss" if parts.scheme in ("https", "wss") else "ws"
    return urllib.parse.urlunsplit((scheme, parts.netloc, "/", "", ""))


def http_origin(base_url: str) -> str:
    parts = urllib.parse.urlsplit(base_url if "://" in base_url else f"http://{base_url}")
    scheme = "https" if parts.scheme in ("https", "wss") else "http"
    return f"{scheme}://{parts.netloc}"


class Gateway:
    """Conexión al gateway. Una petición a la vez; los eventos se van encolando."""

    def __init__(self, base_url: str, token: str | None, *, version: str = "0.1.0",
                 timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.token = (token or "").strip() or None
        self.version = version
        self.timeout = timeout
        self.identity = DeviceIdentity.load()
        self.hello: dict = {}
        self.events: list[dict] = []
        self._ws: WebSocket | None = None
        self._ids = itertools.count(1)

    # ------------------------------------------------------------------ conexión

    def connect(self) -> dict:
        url = ws_url(self.base_url)
        self._ws = WebSocket(url, origin=http_origin(self.base_url), timeout=self.timeout)

        challenge = self._await_challenge()
        nonce = str(challenge.get("nonce") or "")
        signed_at = challenge.get("ts")
        if not isinstance(signed_at, int):
            signed_at = int(time.time() * 1000)

        # El token que firmamos tiene que ser el mismo que mandamos: el gateway
        # rehace la cadena con lo que recibe y compara.
        device_token = self.identity.device_token(self.base_url)
        auth: dict[str, str] = {}
        if self.token:
            auth["token"] = self.token
            signing_token = self.token
        elif device_token:
            auth["deviceToken"] = device_token
            signing_token = device_token
        else:
            signing_token = None
        if device_token and self.token:
            auth["deviceToken"] = device_token

        client = {
            "id": CLIENT_ID,
            "version": self.version,
            "platform": platform.system().lower(),
            "mode": CLIENT_MODE,
        }
        params = {
            "minProtocol": PROTOCOL_MIN,
            "maxProtocol": PROTOCOL_MAX,
            "client": client,
            "role": ROLE,
            "scopes": list(SCOPES),
            "caps": list(CAPS),
            "device": self.identity.sign_connect(
                nonce=nonce, signed_at=signed_at, token=signing_token,
                role=ROLE, scopes=SCOPES),
        }
        if auth:
            params["auth"] = auth

        self.hello = self.request("connect", params)
        issued = (self.hello.get("auth") or {}).get("deviceToken")
        if isinstance(issued, str) and issued:
            self.identity.remember_device_token(
                self.base_url, issued, (self.hello.get("auth") or {}).get("scopes") or [])
        return self.hello

    def _await_challenge(self) -> dict:
        while True:
            message = json.loads(self._ws.recv(self.timeout))
            if message.get("type") == "event" and message.get("event") == "connect.challenge":
                return message.get("payload") or {}
            if message.get("type") == "event":
                self.events.append(message)

    # ------------------------------------------------------------------ peticiones

    def request(self, method: str, params: dict | None = None,
                timeout: float | None = None) -> dict:
        if self._ws is None:
            raise WebSocketError("no hay conexión con el gateway")
        request_id = f"r{next(self._ids)}"
        self._ws.send_json({"type": "req", "id": request_id, "method": method,
                            "params": params or {}})
        deadline = time.monotonic() + (timeout or self.timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GatewayError("TIMEOUT", f"el gateway no contestó a {method}")
            try:
                message = json.loads(self._ws.recv(remaining))
            except TimeoutError:
                raise GatewayError("TIMEOUT", f"el gateway no contestó a {method}") from None
            if message.get("type") == "event":
                self.events.append(message)
                continue
            if message.get("id") != request_id:
                continue  # respuesta a una petición que ya caducó
            if message.get("ok"):
                payload = message.get("payload")
                return payload if isinstance(payload, dict) else {"value": payload}
            error = message.get("error") or {}
            code = str(error.get("code") or "UNKNOWN")
            details = error.get("details") or {}
            message_text = str(error.get("message") or "petición rechazada")
            if details.get("code") == "PAIRING_REQUIRED" or code == "NOT_PAIRED":
                raise PairingRequired(code, message_text, details)
            raise GatewayError(code, message_text, details)

    # ------------------------------------------------------------------ eventos

    # Cuántos mensajes se atienden como mucho en una pasada. Un turno del
    # agente llega a mandar cientos de eventos seguidos: sin este tope, quien
    # llama se queda aquí dentro mientras el flujo no pare, y en la TUI eso son
    # teclas que no se pintan hasta que el agente se calla.
    PUMP_BUDGET = 48

    def pump(self) -> list[dict]:
        """Eventos que ya han llegado. No espera por ninguno."""
        if self._ws is None:
            return []
        drained: list[dict] = []
        drained.extend(self.events)
        self.events.clear()
        for _ in range(self.PUMP_BUDGET):
            raw = self._ws.poll()
            if raw is None:
                break
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if message.get("type") == "event":
                drained.append(message)
        return drained

    def close(self) -> None:
        if self._ws is not None:
            self._ws.close()
            self._ws = None
