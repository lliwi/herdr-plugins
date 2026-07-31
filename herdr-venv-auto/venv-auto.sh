#!/usr/bin/env bash
# herdr-venv-auto: motor de las acciones del plugin.
#
# El trabajo real lo hace shell/hook.zsh dentro de cada shell. Este script solo
# instala/desinstala esa línea en ~/.zshrc y sabe informar de qué venv resolvería
# el pane enfocado, para poder atarlo a una tecla.

set -uo pipefail

PLUGIN_ROOT=${HERDR_PLUGIN_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)}
HOOK="$PLUGIN_ROOT/shell/hook.zsh"
ZSHRC="${ZDOTDIR:-$HOME}/.zshrc"
MARKER="# herdr-venv-auto"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/herdr/plugins/config/herdr-venv-auto"
CONFIG="$CONFIG_DIR/config.sh"

# Igual que _hva_find en el hook: sube por los padres buscando bin/activate.
find_venv() {
  local dir=$1 name depth=0 names=${HVA_NAMES:-".venv venv env"}
  while ((depth++ < 32)); do
    for name in $names; do
      [ -r "$dir/$name/bin/activate" ] && { printf '%s\n' "$dir/$name"; return 0; }
    done
    [ "$dir" = / ] && break
    dir=$(dirname -- "$dir")
  done
  return 1
}

hook_installed() { grep -qF "$MARKER" "$ZSHRC" 2>/dev/null; }

cmd_install_hook() {
  if hook_installed; then
    echo "El hook ya está en $ZSHRC"
    return 0
  fi
  {
    printf '\n%s: activa el venv del proyecto al hacer cd\n' "$MARKER"
    printf 'source %s\n' "$HOOK"
  } >>"$ZSHRC"
  echo "Añadido a $ZSHRC — abre un shell nuevo o ejecuta: exec zsh"
}

cmd_uninstall_hook() {
  hook_installed || { echo "El hook no está en $ZSHRC"; return 0; }
  local backup="$ZSHRC.bak-venv-auto-$(date +%Y%m%d-%H%M%S)"
  cp -- "$ZSHRC" "$backup"
  # Borra la línea del marcador y la del source contiguo.
  sed -i "\#^${MARKER}#,+1d" -- "$ZSHRC"
  echo "Eliminado de $ZSHRC (copia en $backup)"
}

cmd_status() {
  local cwd venv
  # herdr pasa el pane enfocado en el contexto de la acción; sirve igual si la
  # acción viene de una tecla, del menú o de la CLI.
  cwd=$(printf '%s' "${HERDR_PLUGIN_CONTEXT_JSON:-}" | sed -n 's/.*"focused_pane_cwd":"\([^"]*\)".*/\1/p')
  [ -n "$cwd" ] || cwd=$PWD

  if venv=$(find_venv "$cwd"); then
    printf 'venv: %s\n' "$venv"
    herdr notification show "venv detectado" --body "${venv/#$HOME/~}" >/dev/null 2>&1
  else
    printf 'venv: ninguno bajo %s\n' "$cwd"
    herdr notification show "Sin venv" --body "${cwd/#$HOME/~}" >/dev/null 2>&1
  fi

  printf 'hook en .zshrc: %s\n' "$(hook_installed && echo sí || echo no)"
  printf 'config: %s\n' "$([ -r "$CONFIG" ] && echo "$CONFIG" || echo '(por defecto)')"
}

case "${1:-status}" in
  install-hook)   cmd_install_hook ;;
  uninstall-hook) cmd_uninstall_hook ;;
  status)         cmd_status ;;
  *) echo "uso: venv-auto.sh [status|install-hook|uninstall-hook]" >&2; exit 2 ;;
esac
