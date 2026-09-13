# herdr-claw

Cliente TUI de **OpenClaw** para un panel de herdr. Habla directamente con el
gateway por websocket: ni ssh ni navegador, que la instancia vive en un docker
(`http://openclaw.home:18789`) y no hay shell a la que entrar.

La conversación es la misma que se ve en `/chat/main`: las sesiones viven en el
servidor, así que cerrar el panel no pierde nada y volver a abrirlo continúa
donde estaba, aunque el último mensaje lo hayas escrito desde el móvil.

```
┌ claw · main · openclaw.home ───────────────────── conectado ┐
│ tú 17:41                                                    │
│   ¿en qué andas?                                            │
│ claw 17:41                                                  │
│   Acabo de cerrar el backup de las 17:00…                   │
├─────────────────────────────────────────────────────────────┤
│ › se me ocurre que                                          │
└ Enter enviar · Ctrl+J salto · Ctrl+O sesiones · Ctrl+C salir ┘
```

## Instalación

```sh
cp -r herdr-claw ~/.config/herdr/plugins/local/herdr-claw
herdr plugin link ~/.config/herdr/plugins/local/herdr-claw
```

La copia de `Documents/development/herdr plugins` es la de desarrollo: herdr
ejecuta la de `local`. Mover la carpeta obliga a `unlink` + `link`.

## Configuración

```sh
cp config.example.env "$(herdr plugin config-dir claw)/.env"
chmod 600 "$(herdr plugin config-dir claw)/.env"
```

| Variable | Qué es |
| --- | --- |
| `CLAW_URL` | URL del gateway. Vale la del navegador: la ruta sobra, el websocket va contra la raíz del puerto. |
| `CLAW_TOKEN` | Token del gateway (Control UI → Settings → Connection, o `openclaw doctor --generate-gateway-token` dentro del docker). |
| `CLAW_SESSION` | Sesión que abre el panel. `main` es la de `/chat/main`. |

El entorno manda sobre el fichero, así que `CLAW_SESSION=otra claw` abre otra
sesión sin tocar nada.

`main` no es la clave que usa el gateway por dentro. Con varios agentes
configurados contesta *«session key "main" has no explicit owner»*, así que el
panel resuelve la clave contra `sessions.list` al arrancar: `main` acaba siendo
`agent:main:main` con `agentId = main`. Vale escribir cualquiera de las dos.

## Emparejar el dispositivo (una vez)

El gateway no se conforma con el token: cada cliente es un **dispositivo** con
su par de claves ed25519, y el `connect` va firmado sobre un nonce del servidor.
La primera conexión deja una solicitud pendiente:

```sh
herdr plugin action invoke claw.pair     # o: bin/claw --pair
```

Imprime el id del dispositivo; hay que aprobarlo en
`http://openclaw.home:18789/settings/devices`. A partir de ahí el mismo par de
claves entra solo.

La identidad vive en `~/.local/state/herdr-claw/device.json` (0600). Borrarlo
equivale a presentarse como un dispositivo nuevo, con su aprobación otra vez.

## Uso

| Tecla | Qué hace |
| --- | --- |
| `prefix+a` | Abre el chat en un split (configurado en `~/.config/herdr/config.toml`). |
| `Enter` | Envía. |
| `Ctrl+J` | Salto de línea dentro del mensaje. |
| `Ctrl+O` | Selector de sesiones (`j`/`k`, `Enter` entra, `n` crea una, `Esc` cierra). |
| `Ctrl+G` | Sesión nueva. |
| `Ctrl+R` | Recarga el historial. |
| `PgUp` / `PgDn` | Desplaza el transcript. |
| `Ctrl+U` / `Ctrl+W` / `Ctrl+K` | Borrar línea / palabra / hasta el final. |
| `Ctrl+C` | Salir del panel. |

Acciones del plugin (paleta de herdr o `herdr plugin action invoke`):

- `claw.open-chat` — el chat en un split.
- `claw.open-tab` — en una pestaña, reaprovechándola si ya existe.
- `claw.open-popup` — en un popup, sin tocar la distribución de paneles.
- `claw.check` — diagnóstico: configuración, handshake, permisos, sesiones.
- `claw.pair` — id del dispositivo y solicitud de emparejamiento.

## En la barra de agentes

El panel se declara como agente `claw` y le va contando su estado a herdr con
`herdr pane report-agent`, así que sale en **agents** y no en **spaces**, con su
icono de estado como cualquier otro agente:

| Lo que pasa en OpenClaw | Estado en herdr |
| --- | --- |
| Nada en marcha | `idle` |
| El agente escribe, piensa o usa una herramienta | `working` |
| El agente espera una aprobación (`lifecycle: waiting-approval`) | `blocked` |
| Termina el turno (`stopReason` distinto de `toolUse`) | vuelve a `idle`, que herdr enseña como *done* |
| Se cae la conexión con el gateway | `unknown` |

Los demás plugins de agente se hacen reconocer disfrazándose: se reexecutan con
el `argv[0]` de un agente conocido y dejan que herdr adivine el estado leyendo
la pantalla. Aquí no hace falta adivinar nada —el gateway dice exactamente qué
está pasando—, así que se reporta y punto. Si el panel no corre dentro de herdr
(no hay `HERDR_PANE_ID`), esto no se activa y no molesta.

## Cuando algo no va

```sh
bin/claw --check     # configuración, handshake, rol y permisos, sesiones
bin/claw --raw       # vuelca los eventos del gateway tal y como llegan
```

`--raw` es lo que hay que mirar cuando el panel pinta un mensaje raro o se queda
sin actualizar: enseña el JSON exacto de `session.message` y compañía.

Errores típicos del gateway:

| Código | Qué pasa |
| --- | --- |
| `PAIRING_REQUIRED` | El dispositivo no está aprobado todavía. |
| `AUTH_TOKEN_MISSING` / `AUTH_TOKEN_MISMATCH` | `CLAW_TOKEN` falta o no es el del gateway. |
| `DEVICE_IDENTITY_REQUIRED` | El gateway espera identidad de dispositivo; es un bug del plugin, no de la config. |
| `PROTOCOL_MISMATCH` | OpenClaw se ha actualizado a un protocolo que este cliente no habla (ver `PROTOCOL_MIN`/`PROTOCOL_MAX` en `lib/gateway.py`). |

## Cómo está montado

```
bin/claw          la TUI y los modos de diagnóstico
bin/claw-open     abre el panel en split / pestaña / popup
lib/gateway.py    handshake, peticiones y eventos del gateway
lib/wsclient.py   websocket (RFC 6455) sobre sockets de la stdlib
lib/ed25519.py    firma del dispositivo, en Python puro
```

Sin dependencias: solo biblioteca estándar. No hay venv que mantener ni node en
medio; el protocolo del gateway está implementado aquí.

### Por qué el bucle es como es

Dos cosas que parecen detalles y no lo son, porque juntas hacían que al escribir
no se viera nada:

- `pump()` atiende **como mucho 48 mensajes por pasada** y no espera por
  ninguno. Un turno del agente manda cientos de eventos seguidos; vaciar la
  tubería hasta que se seque deja el teclado sin atender mientras tanto.
- El panel consume **todas las teclas pendientes antes de repintar**, no una por
  vuelta. Cada vuelta pasa por el gateway, así que una tecla por vuelta se nota
  como escritura a cámara lenta.

Y en `wsclient`, una trama se consume entera o nada: sacar del buffer la
cabecera de una trama cuyo cuerpo aún no ha llegado descoloca el flujo para
siempre y todo lo que se lee después es basura.

### El protocolo, en corto

Todo va por un websocket contra la raíz del puerto del gateway (`/chat/main` es
solo la SPA). Sobres:

```
->  {"type":"req",   "id":"r1", "method":"chat.send", "params":{…}}
<-  {"type":"res",   "id":"r1", "ok":true, "payload":{…}}
<-  {"type":"event", "event":"session.message", "payload":{…}, "seq":42}
```

Al abrir, el servidor manda `connect.challenge` con un nonce; el cliente
responde con `connect`, que lleva el token y la firma del dispositivo sobre

```
v2|deviceId|clientId|clientMode|role|scopes|signedAtMs|token|nonce
```

El `hello` de vuelta trae un `deviceToken` que se guarda: sirve para reconectar
si algún día cambia el token del gateway.

Métodos que usa el panel:

| Método | Parámetros | Notas |
| --- | --- | --- |
| `sessions.list` | `{}` | De aquí sale la clave buena y el `agentId`. |
| `chat.history` | `sessionKey`, `agentId`, `limit` | Devuelve `messages[]` con `role` y `content`. |
| `chat.send` | `sessionKey`, `agentId`, `message`, `idempotencyKey` | El `idempotencyKey` acaba siendo el `runId`. |
| `sessions.messages.subscribe` | `key`, `agentId` | Aquí la clave se llama **`key`**, no `sessionKey`: el esquema rechaza el otro nombre. |
| `sessions.create` | `agentId` | Devuelve `{ok, key, sessionId}`. |

Eventos que escucha:

- `session.message` — un mensaje ya confirmado (`message.role` +
  `message.content`, que es texto suelto o una lista de partes: `text`,
  `thinking`, `toolCall`). El texto que llega por aquí manda sobre el borrador.
- `agent` — el turno en directo, con `stream`:
  `assistant` (el texto según se escribe), `thinking`, `item`/`tool` (llamadas a
  herramienta y sus fases), `run_status` (`preparing_context`, `starting_model`,
  `retrying`…), `lifecycle` (`waiting-approval`), `notice`, `usage` y
  `compaction`. Los que traen `isHeartbeat` se ignoran.
- `session.observer` — el `headline` de lo que está haciendo el agente; sale en
  el pie del panel mientras dure el run.
- `sessions.changed` — invalida la lista del selector.

Un mismo `__openclaw.id` cubre varios mensajes (el pensamiento, la llamada a la
herramienta y el texto de una misma respuesta), así que la clave con la que el
panel los distingue lleva pegado un resumen del contenido.
