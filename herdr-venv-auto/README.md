# herdr-venv-auto

Activa el virtualenv del proyecto al entrar en su carpeta y lo desactiva al salir.

```
~/dev/proyecto        ❯ cd api
(api) ~/dev/proyecto/api ❯ cd src
(api) ~/dev/proyecto/api/src ❯ cd ~
~                     ❯
```

- Busca `.venv`, `venv` y `env` **subiendo por los directorios padres**, así que funciona desde cualquier subcarpeta del proyecto.
- Al salir del árbol del proyecto ejecuta `deactivate`.
- Al entrar en otro proyecto cambia de venv sin dejar el anterior colgado.

## Por qué un hook de shell y no un evento

herdr emite `pane.updated` con el `cwd` nuevo en cada `cd` — verificado, el evento existe y llega. Pero un plugin de eventos vive fuera del shell: la única forma de activar un venv desde ahí es teclear `source .venv/bin/activate` en el pane con `pane send-text`, y ese texto acaba escrito dentro de `vim`, dentro del prompt de un agente o encima de un comando en marcha.

El hook `chpwd` vive dentro del propio shell: activa en el mismo momento del `cd`, no escribe nada en el terminal y no puede colarse en otro proceso. El manifiesto del plugin empaqueta el hook, su configuración y las acciones.

Solo zsh. Fuera de zsh no hace nada.

## Instalación

```sh
herdr plugin link ~/Documents/development/herdr-venv-auto
herdr plugin action invoke herdr-venv-auto.install-hook
exec zsh
```

`install-hook` añade a `~/.zshrc`:

```zsh
# herdr-venv-auto: activa el venv del proyecto al hacer cd
source ~/Documents/development/herdr-venv-auto/shell/hook.zsh
```

Para quitarlo: `herdr plugin action invoke herdr-venv-auto.uninstall-hook` (deja copia de seguridad del `.zshrc`).

## Configuración

Funciona sin configurar nada. Para cambiar algo:

```sh
mkdir -p ~/.config/herdr/plugins/config/herdr-venv-auto
cp ~/Documents/development/herdr-venv-auto/config.example.sh \
   ~/.config/herdr/plugins/config/herdr-venv-auto/config.sh
```

| Variable | Por defecto | Qué hace |
|---|---|---|
| `HVA_NAMES` | `.venv venv env` | Carpetas candidatas, por orden de preferencia |
| `HVA_DEACTIVATE_ON_LEAVE` | `1` | `deactivate` al salir del proyecto |
| `HVA_RESPECT_MANUAL` | `0` | `1` = no pisar un venv activado a mano |
| `HVA_ONLY_IN_HERDR` | `0` | `1` = actuar solo dentro de un pane de herdr |
| `HVA_MAX_DEPTH` | `32` | Niveles que sube buscando el venv |

## Acciones

| Acción | Qué hace |
|---|---|
| `status` | Qué venv resuelve el pane enfocado, y si el hook está puesto |
| `install-hook` | Añade la línea a `~/.zshrc` |
| `uninstall-hook` | La quita (con copia de seguridad) |

Atar `status` a una tecla en `~/.config/herdr/config.toml`:

```toml
[[keys.command]]
key = "prefix+v"
type = "plugin_action"
command = "herdr-venv-auto.status"
description = "venv auto: estado"
```

## Detalles

- `VIRTUAL_ENV_DISABLE_PROMPT=1`: p10k ya pinta el venv en el prompt; dejar que `activate` además prefije el `PS1` lo duplicaría.
- Solo actúa en shells interactivos, así que un script que herede el entorno no reactiva nada.
- Con `HVA_RESPECT_MANUAL=0` (por defecto) el hook manda: si activaste un venv a mano y haces `cd` a otro proyecto, se cambia; y si sales a una carpeta sin proyecto, se desactiva. Pon `1` si prefieres que un venv puesto a mano sobreviva.
