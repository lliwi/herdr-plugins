# herdr-venv-auto: activa el venv del proyecto al entrar en su carpeta (zsh).
#
# El mecanismo es un hook chpwd, no un evento de herdr. herdr sí emite
# pane.updated al hacer cd, pero reaccionar a él obligaría a teclear
# "source .venv/bin/activate" dentro del pane con send-text, que puede caer en
# vim, en un agente o en un comando en marcha. El hook vive dentro del propio
# shell: activa al instante, sin escribir nada y sabiendo qué está pasando.
#
# Sourcea esto desde ~/.zshrc:
#   source ~/Documents/development/herdr-venv-auto/shell/hook.zsh
#
# Config opcional en ~/.config/herdr/plugins/config/herdr-venv-auto/config.sh
# (ver config.example.sh). Se relee en cada shell nuevo.

# Solo shells interactivos: un script que hereda el entorno no debe reactivar nada.
[[ -o interactive ]] || return 0

: ${HVA_CONFIG:="${XDG_CONFIG_HOME:-$HOME/.config}/herdr/plugins/config/herdr-venv-auto/config.sh"}
[[ -r $HVA_CONFIG ]] && source $HVA_CONFIG

# Nombres de carpeta candidatos, en orden de preferencia dentro de un mismo directorio.
: ${HVA_NAMES:=".venv venv env"}
# 1 = al salir del árbol del proyecto, deactivate automático.
: ${HVA_DEACTIVATE_ON_LEAVE:=1}
# 1 = no tocar un venv que no haya activado este hook (activado a mano o heredado).
: ${HVA_RESPECT_MANUAL:=0}
# 1 = no hacer nada fuera de un pane de herdr.
: ${HVA_ONLY_IN_HERDR:=0}
# Tope de niveles al subir buscando el venv; evita recorrer un árbol muy profundo.
: ${HVA_MAX_DEPTH:=32}

# Venv que activó este hook. Distinguirlo de $VIRTUAL_ENV es lo que permite
# respetar (o no) uno puesto a mano.
typeset -g _HVA_OWNED=""

# Imprime la ruta del venv que gobierna $1, subiendo por los padres. Vacío si no hay.
_hva_find() {
  local dir=$1 name depth=0
  while (( depth++ < HVA_MAX_DEPTH )); do
    for name in ${=HVA_NAMES}; do
      [[ -r $dir/$name/bin/activate ]] && { print -r -- $dir/$name; return 0 }
    done
    [[ $dir == / ]] && break
    dir=${dir:h}
  done
  return 1
}

_hva_deactivate() {
  # deactivate es una función que define el propio activate; si no está, el
  # venv se heredó por entorno y no hay nada limpio que ejecutar.
  (( $+functions[deactivate] )) && deactivate 2>/dev/null
  _HVA_OWNED=""
}

_hva_apply() {
  local target
  target=$(_hva_find $PWD) || target=""

  # Ya estamos en el venv correcto.
  [[ -n $target && ${VIRTUAL_ENV:A} == ${target:A} ]] && return

  # Hay un venv puesto que no es nuestro y se pidió no pisarlo.
  if [[ -n $VIRTUAL_ENV && -z $_HVA_OWNED && $HVA_RESPECT_MANUAL == 1 ]]; then
    return
  fi

  if [[ -n $target ]]; then
    [[ -n $VIRTUAL_ENV ]] && _hva_deactivate
    # VIRTUAL_ENV_DISABLE_PROMPT: p10k ya pinta el venv; dejar que activate
    # además prefije el PS1 lo duplicaría.
    VIRTUAL_ENV_DISABLE_PROMPT=1 source $target/bin/activate
    _HVA_OWNED=$target
  elif [[ -n $VIRTUAL_ENV && $HVA_DEACTIVATE_ON_LEAVE == 1 ]]; then
    _hva_deactivate
  fi
}

if [[ $HVA_ONLY_IN_HERDR != 1 || -n ${HERDR_PANE_ID:-} ]]; then
  autoload -Uz add-zsh-hook
  add-zsh-hook chpwd _hva_apply   # add-zsh-hook es idempotente al re-sourcear
  _hva_apply                      # y una pasada para el directorio de arranque
fi
