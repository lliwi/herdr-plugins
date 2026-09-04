# herdr-postit

Tablero de postits en el terminal. Cada tarjeta es una lista que va creciendo. La
app funciona sola en cualquier terminal; el plugin de herdr será solo el
envoltorio que la abre en un panel.

**Estado: fases 1 a 5.** Almacenamiento, CLI, tablero, edición dentro de la
propia TUI —se escribe en la tarjeta, en el sitio del ítem, sin salir a un
editor—, búsqueda con filtros y plugin de herdr. La app sigue funcionando sola
en cualquier terminal: el plugin solo la abre en el sitio correcto.

```
┏━━━━━━━━━━━━━━━━━━━━━━━━┓┌───────────────────────┐
┃ trabajo             *  ┃│ casa                  │
┃ ✓ Llamar a soporte     ┃│ · Comprar café        │
┃ · Firmar el contrato   ┃│ · Filtros cafetera    │
┃                        ┃│                       │
┃ 1/2 hechos       ahora ┃│ 2 ítems         ahora │
┗━━━━━━━━━━━━━━━━━━━━━━━━┛└───────────────────────┘
```

La seleccionada es la de la izquierda: es la única encendida.

## Uso

```sh
./bin/postit                                  # abre el tablero
./bin/postit add trabajo "llamar a soporte"   # crea la tarjeta si no existe
./bin/postit add trabajo "firmar el contrato" # se añade a la MISMA tarjeta
printf 'café\nfiltros\n' | ./bin/postit add casa   # una línea = un ítem
./bin/postit new recados --color azul         # tarjeta vacía
./bin/postit set trabajo --color rosa --pin
./bin/postit ls                               # tarjetas
./bin/postit ls trabajo                       # ítems, numerados
./bin/postit ls --here                        # solo las de este proyecto
./bin/postit ls --sort nombre                 # fecha (por defecto), nombre, pendientes
./bin/postit find cafe                        # busca en nombres e ítems
./bin/postit find soporte impresora --here    # todas las palabras, en este proyecto
./bin/postit done trabajo 1                   # marca el ítem 1 como hecho
./bin/postit done trabajo 1 3                 # alterna varios
./bin/postit rm trabajo 2                     # borra el ítem 2
./bin/postit rm trabajo 2 4 5                 # varios de golpe
./bin/postit rm trabajo                       # borra la tarjeta (pregunta)
./bin/postit show trabajo [--raw]
nvim "$(./bin/postit path trabajo)"           # editar la lista entera a mano
```

El nombre de la tarjeta admite prefijos y trozos: `postit ls trab` vale. Y da
igual cómo lo escribas: `trabajo` y `Trabajo` son la misma tarjeta, porque el
fichero se llama por el slug del nombre.

### Teclas

En el tablero:

| | |
|---|---|
| `hjkl` / flechas | moverse entre tarjetas |
| `g` / `G` | primera / última |
| `enter` | abrir la tarjeta |
| `/` | buscar: el tablero se reduce mientras escribes |
| `p` | ver solo las de este proyecto |
| `s` | cambiar el orden: fecha → nombre → pendientes |
| `esc` | quitar los filtros (y si no hay, salir) |
| `n` | tarjeta nueva: pide el nombre y entra a escribir el primer ítem |
| `a` | abrir la tarjeta y empezar un ítem nuevo |
| `e` | abrir la tarjeta en `$EDITOR` |
| `c` | siguiente color |
| `espacio` | fijar / soltar |
| `d` | borrar la tarjeta (pregunta) |
| `r` | recargar del disco |
| `q` | salir |

Dentro de una tarjeta:

| | |
|---|---|
| `j` / `k` | moverse entre ítems |
| `g` / `G` | primero / último |
| `enter` o `i` | editar el ítem donde está |
| `a` | ítem nuevo al final |
| `o` / `O` | ítem nuevo debajo / encima del seleccionado |
| `t` | cambiar el nombre de la tarjeta |
| `x` | marcar / desmarcar hecho |
| `J` / `K` | mover el ítem abajo / arriba |
| `d` | borrar el ítem |
| `u` | deshacer (borrados, ediciones, movimientos) |
| `e` | abrir la tarjeta en `$EDITOR` |
| `q` | cerrar |

Escribiendo un ítem (el cursor está sobre la línea, en la tarjeta):

| | |
|---|---|
| `enter` | guarda y abre otro ítem debajo — encadena la lista |
| `esc` | guarda y sale del modo escritura |
| `↑` / `↓` | guarda y salta a escribir en otro ítem |
| `←` `→` `inicio` `fin` | mover el cursor (también `ctrl-a` / `ctrl-e`) |
| `retroceso` / `supr` | borrar a un lado y a otro |
| `ctrl-w` | borrar la palabra anterior |
| `ctrl-u` / `ctrl-k` | borrar hasta el principio / hasta el final |
| `tab` / `shift-tab` | sangrar el ítem: así se hacen sub-ítems |

`t` cambia el nombre que se ve, no el fichero: el id sigue siendo el slug con el
que nació la tarjeta (`postit ls` lo enseña en la primera columna).

Un ítem que se queda vacío se borra al salir, y `enter` sobre uno vacío termina
la lista. Nada se escribe en el disco hasta que confirmas la línea, así que un
ítem nuevo abandonado con `esc` no deja rastro.

`e` sigue ahí para lo que un editor de línea no hace: pegar algo largo, escribir
un párrafo, reordenar a lo bestia (`$VISUAL` tiene prioridad; sin ninguno de los
dos, el primero que exista de `nvim`, `vim`, `vi`). Pero ya no hace falta para el
día a día.

Colores: `amarillo`, `rosa`, `naranja`, `verde`, `azul`, `morado`, `gris`.

La tarjeta seleccionada se distingue de tres formas a la vez, porque solo con el
borde costaba encontrarla: lleva su color **vivo** mientras las demás lo llevan
apagado (`MUTED` en el código), **crece** una fila y una columna por cada lado
—hacia el hueco que la separa de las vecinas, sin comérselas— y el borde pasa a
línea doble. Se pinta la última, así que siempre queda por encima. Sin 256
colores no hay medio tono y quedan el tamaño y el borde.

## Buscar y filtrar

`/` filtra en vivo: cada tecla vuelve a dibujar el tablero con lo que queda.
`Enter` se queda con el filtro puesto y `Esc` lo deja como estaba. La barra de
abajo dice siempre qué hay puesto (`3/9 tarjetas · /cafe · aquí`).

- **Se busca sin acentos y en minúsculas**: `cafe` encuentra `café`.
- **Todas las palabras, en cualquier orden**: `soporte impresora` encuentra
  `Llamar al soporte de la impresora`, y `impresora soporte` también.
- **Se busca en el nombre y en los ítems**, así que buscar `trabajo` saca la
  tarjeta entera y buscar `impresora` saca la tarjeta que tiene ese ítem.
- **La tarjeta enseña primero lo que casa.** Si no, buscas `café` y ves una
  tarjeta que no enseña por qué ha salido.

`p` deja solo las tarjetas de este proyecto. Proyecto es *el repo*: se sube
desde el directorio actual hasta encontrar un `.git`, y la tarjeta entra si
nació en ese mismo repo. Comparar directorios a secas no sirve —una tarjeta
creada en la raíz del repo no saldría estando en un subdirectorio, y una creada
en `$HOME` saldría en todos los proyectos, porque `$HOME` está por encima de
todo. Sin repo, el proyecto es el directorio a secas.

`s` cambia el orden: `fecha` (la última tocada arriba), `nombre` o `pendientes`
(las que más cosas tienen sin marcar). Las fijadas van arriba siempre, con
cualquier orden.

Los filtros se mantienen al crear, editar y borrar, y no se meten dentro de una
tarjeta abierta: si editas un ítem y deja de casar con la búsqueda, la tarjeta
no se te cierra en las narices — se irá del tablero al volver.

## Como plugin de herdr

```sh
cp -r . ~/.config/herdr/plugins/local/herdr-postit
herdr plugin link ~/.config/herdr/plugins/local/herdr-postit
herdr server reload-config
```

Los plugins locales se ejecutan desde `~/.config/herdr/plugins/local`; esta
carpeta de `Documents` es la copia de desarrollo. Después de tocar el código hay
que volver a copiar.

| | |
|---|---|
| `prefix+o` | abrir el tablero en un split |
| `prefix+O` | abrirlo en una pestaña, llamada `herdr-postit` |
| `postit: el tablero en un popup` | desde el menú de acciones, sin tocar la distribución |
| `postit: comprobar la instalación` | qué paneles ve y qué número publicaría en cada uno |

`prefix+n` sería la tecla obvia, pero de serie ya es «pestaña siguiente», así que
el tablero va en `prefix+o` (de nOtas) y `prefix+O` en pestaña, igual que
`prefix+y` / `prefix+Y` con yazi.

El tablero se abre **en el directorio del panel que tuvieras enfocado**, así que
`p` (ver solo lo de este proyecto) ya arranca apuntando donde estabas.

La pestaña de `prefix+O` se renombra a `herdr-postit` (`POSTIT_TAB_NAME` lo
cambia). Nacería llamándose `python3`, por el programa que corre dentro, y el
plugin de renombrado automático llega a bautizarla justo después que nosotros:
no se puede ganar esa carrera, así que `postit-open` insiste hasta que el nombre
se queda. En cuanto ese plugin ve un nombre que no puso él, da la pestaña por
bautizada a mano y deja de tocarla.

### La fila del sidebar

El plugin publica un token `notes` en cada panel con agente, con lo que queda
por hacer en las tarjetas *de ese proyecto*:

```toml
[ui.sidebar.agents]
rows = [
  ["state_icon", "$title"],
  ["agent", "$limit"],
  ["$context"],
  ["$notes"],          # ← postit
]
```

Cada panel ve lo suyo, que es la gracia de que el dato vaya por panel y no sea un
número global: el panel que trabaja en `case-manager` enseña lo de
`case-manager`. Si en ese proyecto no queda nada, el token se retira y la fila no
aparece. Se recalcula cuando cambia el foco o muere un panel, y solo llama a
herdr cuando el número cambia de verdad.

Fuera de herdr, `postit sidebar` no hace nada y sale con 0: un hook de evento que
falla solo sirve para llenar el log.

## Cómo se guarda

Un fichero Markdown por tarjeta en `~/.local/share/postit/notes/`:

```markdown
---
color: rosa
pinned: true
created: 2026-09-03T21:49
scope: /home/llibert/Documents/development
---
trabajo

- [x] Llamar a soporte de la impresora
- Firmar el contrato
```

Un ítem sin casilla está pendiente; la casilla solo aparece cuando se marca con
`x`, así que una tarjeta que nunca se marca se queda como una lista limpia. Un
ítem sangrado dos espacios es un sub-ítem: sigue siendo una línea de lista
normal de Markdown, así que se ve bien en cualquier otra herramienta.

Ficheros sueltos y no una base de datos para que las tarjetas se puedan editar
con nvim, mirar desde yazi, buscar con `grep` y versionar con git — que es justo
lo que se pierde si el contenido vive dentro de un SQLite.

Cuatro decisiones que conviene no deshacer sin pensarlo:

- **El id es el nombre del fichero** (el slug del nombre de la tarjeta), no un
  campo del frontmatter. Así renombrar o mover desde fuera no deja el fichero
  contradiciéndose a sí mismo.
- **La fecha de la tarjeta es el `mtime`**, no un campo `updated`. Un campo así
  solo lo actualiza esta app, así que empezaría a mentir en cuanto editaras la
  tarjeta con nvim por fuera; el `mtime` siempre dice la verdad.
- **Las escrituras son atómicas** (fichero temporal + `rename`). Dos tableros
  abiertos a la vez no pueden dejar una tarjeta a medias.
- **Un `Esc` suelto no es un `Esc` del usuario.** Un panel recibe secuencias que
  curses no reconoce (respuestas a consultas del terminal, eventos de foco) y
  todas empiezan por `Esc`. `read_key` mira si detrás viene algo más antes de
  creérselo; sin eso, el tablero se cerraba solo a los dos segundos de abrirlo
  dentro de herdr.
- **El cuerpo es texto libre.** Las líneas que empiezan por `-` cuentan como
  ítems, se numeran para `rm` y `done` y son las que se seleccionan en la TUI;
  pero si editas la tarjeta con nvim y escribes un párrafo suelto, se conserva y
  se muestra igual.

`scope` guarda dónde nació la tarjeta. Todavía no se usa: es lo que en la fase 4
permitirá filtrar por el proyecto actual sin encerrar las tarjetas en tableros
separados.

## Migrar del formato viejo

La primera versión guardaba una nota por fichero y el tag en el frontmatter, así
que dos `add` con el mismo tag daban dos tarjetas. `postit migrate` junta esas
notas en una tarjeta por tag:

```sh
./bin/postit migrate            # solo enseña qué haría
./bin/postit migrate --force    # lo aplica
```

Los ficheros originales no se borran: se mueven a `notes/.migrado/`.

## La caché

`~/.local/state/postit/index.json` guarda el frontmatter y las primeras líneas ya
parseadas de cada tarjeta, con su `mtime` y su tamaño. Si el fichero no ha
cambiado se reutiliza; si cambió, se reparsea solo ese. El cuerpo entero se lee
del disco al ampliar la tarjeta, no se cachea.

Es prescindible del todo: borrarla no pierde nada, se reconstruye al arrancar. Si
`POSTIT_HOME` apunta a otra carpeta, la caché entera se descarta (guarda dentro a
qué directorio pertenece), así que no hay forma de que enseñe tarjetas de otro
sitio.

## Requisitos

Python 3 y nada más — solo biblioteca estándar, como `herdr-hermes`. Un plugin
que necesita un venv es un plugin que se rompe en silencio dentro de un panel.

`POSTIT_HOME` cambia dónde viven las tarjetas (útil para probar sin tocar las
buenas).
