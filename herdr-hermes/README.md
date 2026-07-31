# herdr-hermes

Plugin de [herdr](https://herdr.dev) que abre la TUI de una instancia **remota** de
Hermes Agent en un panel, hablando con el dashboard (`hermes dashboard`, puerto
9119 por defecto).

## Cómo funciona

El dashboard expone la pestaña Chat sobre un websocket PTY. El plugin se engancha
a ese mismo websocket desde el terminal, así que lo que ves es la TUI real de
Hermes, no un cliente de chat reimplementado:

1. `POST /auth/password-login` → cookies de sesión
2. `POST /api/auth/ws-ticket` → ticket de un solo uso (TTL 30 s)
3. `WS /api/pty?ticket=…&attach=…&channel=herdr` → PTY

El parámetro `attach` mantiene el proceso de Hermes vivo aunque cierres el panel:
al reabrirlo te reenganchas a la misma sesión. El token se deriva del workspace de
herdr, así que cada workspace tiene su sesión.

Solo biblioteca estándar de Python — el cliente websocket va incluido.

### Qué sesión se reanuda

Cuando el servidor tiene que arrancar un PTY nuevo, decide qué sesión reanudar
leyendo un fichero temporal propio de cada `channel` donde la TUI apunta su sesión
actual. Ese rastro no se valida contra la base de datos, así que si la sesión que
nombra ya no existe la TUI arranca con `error: session not found` y sin historial.
El caso habitual es abrir el panel, no escribir nada y cerrarlo: una sesión vacía
nunca llega a persistirse. Y como el rastro solo se reescribe al crear o reanudar
una sesión, el error se queda pegado en todas las aperturas siguientes.

Para no depender de ese rastro a ciegas, el plugin anota la última sesión conocida
de cada workspace en
`~/.local/state/herdr/plugins/hermes/session-<workspace>.json` y la valida con
`GET /api/sessions/<id>` antes de conectar:

- sigue viva → conecta normal y deja que el servidor la reanude;
- no existe (o no hay ninguna anotada) → manda `fresh=1`, que borra el rastro
  podrido en el servidor y arranca limpio en vez de enseñar el error.

Solo se anota la sesión si durante la conexión ha aparecido una sesión de TUI
nueva; si no se llegó a escribir nada, el registro se queda vacío y la próxima
apertura vuelve a arrancar limpia. Borrar el fichero no rompe nada: como mucho se
arranca una sesión limpia de más.

`fresh=1` no cambia la clave del keep-alive, así que el panel sigue siendo
persistente aunque arranque limpio. Reanudar con `resume=<id>` sí la cambiaría y
dejaría dos Hermes sobre la misma sesión, por eso el plugin no lo usa.

Queda un caso que el plugin no puede ver: si abres una sesión nueva **desde dentro
de la TUI** y la cierras sin escribir nada, el rastro del servidor apunta a esa
sesión vacía mientras que la anotada sigue siendo válida. Se arregla con
**Hermes: reiniciar sesión**.

### Cuando el PTY guardado se queda atascado

Un PTY que ya arrancó mal se queda así: el error vive en su scrollback y
reengancharse lo vuelve a pintar. El servidor lo recoge tras 30 minutos sin uso,
pero cada apertura reinicia esa cuenta, así que un panel que se abre a menudo no
caduca nunca. Desde el cliente no se puede matar un PTY vivo, solo dejar de usarlo:
por eso **Hermes: reiniciar sesión** (`--reset`) sube una generación que va en el
token de `attach`, con lo que el servidor no encuentra nada con esa clave y arranca
un PTY nuevo. La generación se guarda, así que las aperturas siguientes se
reenganchan a él con normalidad y el panel sigue siendo persistente.

## Requisitos

- Python 3.9+
- En el servidor: extras `web` y `pty` de Hermes (`uv pip install -e '.[web]'`).
  Sin `pty` el dashboard rechaza el websocket con código 4404.

## Configuración

`~/.config/herdr/plugins/config/hermes/.env` (permisos 600):

```
HERMES_URL=http://hermes.home:9119
HERMES_USER=usuario
HERMES_PASSWORD=contraseña
HERMES_PROVIDER=basic
```

Las variables del entorno tienen prioridad sobre el fichero.

## Uso

```sh
herdr plugin link /ruta/a/herdr-hermes
```

- Panel **Hermes** — se adjunta a la sesión persistente.
- Panel **Hermes (nueva sesión)** — descarta la sesión guardada y fuerza un Hermes
  nuevo aunque haya uno vivo. Ese PTY no sobrevive al cierre del panel.
- Acción **Hermes: reiniciar sesión** — descarta el PTY persistente atascado y abre
  el panel sobre uno nuevo, que sí sobrevive al cierre.
- Acción **Hermes: comprobar conexión** — prueba login, ticket y handshake, y dice
  qué sesión se reanudará.

Desde la línea de comandos:

```sh
herdr plugin action list --plugin hermes
herdr plugin pane open --plugin hermes --pane chat
./bin/hermes-term --check
./bin/hermes-term --reset
```

## Identificación como agente

herdr decide si un panel es un agente mirando el `argv[0]` del proceso en primer
plano y comparándolo con sus manifiestos
(`~/.local/state/herdr/agent-detection/remote/hermes.toml`). El proceso de este
plugin es un puente en Python, así que el panel aparecería solo en **spaces** y
nunca en **agents**; por eso `hermes-term` se relanza a sí mismo con
`argv[0] = "hermes"` nada más arrancar.

Con eso herdr aplica el manifiesto de Hermes y saca idle/working/blocked de lo
que pinta la TUI remota (título OSC y contenido de pantalla), sin que el plugin
tenga que reportar estados a mano.
