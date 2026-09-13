"""Ed25519 en Python puro (RFC 8032), porque el gateway de OpenClaw firma así.

El handshake del gateway no acepta usuario y contraseña a secas: cada cliente es
un «dispositivo» con su par de claves, y el `connect` va firmado sobre el nonce
que manda el servidor. La implementación de referencia cabe en esta página y
evita añadir PyNaCl o cryptography, que no están instalados y obligarían a
mantener un venv para el plugin.

Firmar cuesta unos milisegundos: se hace una vez por conexión, no en el bucle de
la TUI, así que la lentitud de la aritmética en Python no se nota.

Verificado contra los vectores 1 y 2 del RFC 8032 (ver tests al final).
"""

from __future__ import annotations

import hashlib

# Curva edwards25519.
P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493


def _inv(x: int) -> int:
    return pow(x, P - 2, P)


D = -121665 * _inv(121666) % P
_SQRT_M1 = pow(2, (P - 1) // 4, P)


def _recover_x(y: int) -> int:
    xx = (y * y - 1) * _inv(D * y * y + 1)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = x * _SQRT_M1 % P
    return P - x if x % 2 else x


# Puntos en coordenadas extendidas (X, Y, Z, T): así la suma no necesita
# inversiones modulares, que son lo caro.
_BY = 4 * _inv(5) % P
_B = (_recover_x(_BY), _BY, 1, _recover_x(_BY) * _BY % P)


def _add(p: tuple, q: tuple) -> tuple:
    a = (p[1] - p[0]) * (q[1] - q[0]) % P
    b = (p[1] + p[0]) * (q[1] + q[0]) % P
    c = 2 * p[3] * q[3] * D % P
    d = 2 * p[2] * q[2] % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _mul(point: tuple, scalar: int) -> tuple:
    out = (0, 1, 1, 0)
    while scalar > 0:
        if scalar & 1:
            out = _add(out, point)
        point = _add(point, point)
        scalar >>= 1
    return out


def _encode(point: tuple) -> bytes:
    zi = _inv(point[2])
    x = point[0] * zi % P
    y = point[1] * zi % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _clamp(digest: bytes) -> int:
    a = int.from_bytes(digest[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a


def public_key(secret: bytes) -> bytes:
    """Clave pública (32 bytes) de una semilla de 32 bytes."""
    return _encode(_mul(_B, _clamp(hashlib.sha512(secret).digest())))


def sign(secret: bytes, message: bytes, public: bytes | None = None) -> bytes:
    """Firma de 64 bytes. `public` se pasa si ya se tiene, para no recalcularla."""
    digest = hashlib.sha512(secret).digest()
    a = _clamp(digest)
    if public is None:
        public = _encode(_mul(_B, a))
    r = int.from_bytes(hashlib.sha512(digest[32:] + message).digest(), "little") % L
    big_r = _encode(_mul(_B, r))
    k = int.from_bytes(hashlib.sha512(big_r + public + message).digest(), "little") % L
    return big_r + int.to_bytes((r + k * a) % L, 32, "little")


if __name__ == "__main__":
    # Vectores 1 y 2 del RFC 8032, sección 7.1.
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    assert public_key(seed).hex() == (
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    assert sign(seed, b"").hex() == (
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555f"
        "b8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
    seed = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
    assert sign(seed, bytes([0x72])).hex() == (
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da0"
        "85ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")
    print("ed25519: vectores del RFC 8032 OK")
