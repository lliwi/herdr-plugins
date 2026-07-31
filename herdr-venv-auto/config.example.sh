# herdr-venv-auto — copiar a:
#   ~/.config/herdr/plugins/config/herdr-venv-auto/config.sh
# Se lee al arrancar cada shell. Todo es opcional.

# Carpetas candidatas, en orden de preferencia dentro de un mismo directorio.
HVA_NAMES=".venv venv env"

# Al salir del árbol del proyecto, deactivate automático.
HVA_DEACTIVATE_ON_LEAVE=1

# No tocar un venv activado a mano o heredado del entorno.
HVA_RESPECT_MANUAL=0

# Actuar solo dentro de un pane de herdr (fuera, ningún venv se activa).
HVA_ONLY_IN_HERDR=0

# Niveles máximos que sube buscando el venv.
HVA_MAX_DEPTH=32
