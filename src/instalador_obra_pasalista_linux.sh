#!/usr/bin/env bash
set -euo pipefail

APP_NAME="ObraPasaLista"
APP_FILENAME_DEFAULT="ObraPasaLista v1.0 - app.py"
INSTALL_BASE_DEFAULT="$HOME/ObraPasaLista"
DESKTOP_FILE_NAME="obra-pasa-lista.desktop"
ICON_FILE_NAME="obra-pasa-lista.png"

say(){ printf '\n==> %s\n' "$1"; }
warn(){ printf '\n[AVISO] %s\n' "$1"; }
fail(){ printf '\n[ERROR] %s\n' "$1" >&2; exit 1; }
ask(){ read -r -p "$1" REPLY; printf '%s' "$REPLY"; }

need_cmd(){ command -v "$1" >/dev/null 2>&1 || return 1; }

install_deps(){
  if need_cmd apt-get; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip unzip python3-tk
  elif need_cmd dnf; then
    sudo dnf install -y python3 python3-pip python3-tkinter unzip
  elif need_cmd pacman; then
    sudo pacman -Sy --noconfirm python python-pip tk unzip
  else
    fail "No reconozco el gestor de paquetes. Instala manualmente: python3, python3-venv, python3-pip y unzip."
  fi
}

create_icon(){
  local icon_path="$1"
  ICON_TARGET="$icon_path" python3 - <<'PY'
from PIL import Image, ImageDraw, ImageFont
import os
p = os.environ['ICON_TARGET']
img = Image.new('RGBA', (256,256), (24,31,42,255))
d = ImageDraw.Draw(img)
d.rounded_rectangle((18,18,238,238), radius=40, fill=(34,197,94,255))
d.rounded_rectangle((42,42,214,214), radius=28, fill=(249,115,22,255))
d.text((72,88), 'OPL', fill=(255,255,255,255))
img.save(p)
PY
}

say "Instalador Linux de $APP_NAME"
printf 'Este script descomprime el ZIP, crea el entorno Python, instala dependencias y deja un acceso para arrancar la app.\n'

if ! need_cmd python3 || ! need_cmd unzip; then
  ans=$(ask "Faltan dependencias del sistema. ¿Intento instalarlas automáticamente? [s/N]: ")
  if [[ "${ans,,}" == "s" || "${ans,,}" == "si" ]]; then
    install_deps
  else
    fail "Sin python3/unzip no puedo continuar."
  fi
fi

ZIP_PATH="${1:-}"
if [ -z "$ZIP_PATH" ]; then
  ZIP_PATH=$(ask "Ruta del ZIP de ObraPasaLista: ")
fi
[ -f "$ZIP_PATH" ] || fail "No existe el ZIP: $ZIP_PATH"

INSTALL_DIR="${2:-}"
if [ -z "$INSTALL_DIR" ]; then
  printf 'Carpeta de instalación por defecto: %s\n' "$INSTALL_BASE_DEFAULT"
  ans=$(ask "Pulsa Enter para aceptar o escribe otra ruta: ")
  INSTALL_DIR="${ans:-$INSTALL_BASE_DEFAULT}"
fi

say "Preparando carpetas"
mkdir -p "$INSTALL_DIR"
unzip -o "$ZIP_PATH" -d "$INSTALL_DIR" >/dev/null

say "Buscando aplicación principal"
APP_FILE=$(find "$INSTALL_DIR" -type f \( -name "$APP_FILENAME_DEFAULT" -o -name "app.py" \) | head -n 1 || true)
[ -n "$APP_FILE" ] || fail "No encuentro el archivo principal ('$APP_FILENAME_DEFAULT' o 'app.py') dentro del ZIP."
APP_DIR=$(dirname "$APP_FILE")

say "Creando entorno virtual"
if [ ! -d "$APP_DIR/.venv" ]; then
  python3 -m venv "$APP_DIR/.venv"
fi

# shellcheck disable=SC1091
source "$APP_DIR/.venv/bin/activate"

say "Instalando dependencias Python"
python -m pip install --upgrade pip >/dev/null
pip install Flask Jinja2 pillow >/dev/null

say "Creando lanzadores"
cat > "$APP_DIR/arrancar.sh" <<RUNEOF
#!/usr/bin/env bash
set -e
cd "$APP_DIR"
source "$APP_DIR/.venv/bin/activate"
python "$APP_FILE"
RUNEOF
chmod +x "$APP_DIR/arrancar.sh"

cat > "$APP_DIR/requirements.txt" <<REQEOF
Flask
Jinja2
pillow
REQEOF

mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons"
ICON_PATH="$HOME/.local/share/icons/$ICON_FILE_NAME"
create_icon "$ICON_PATH"

DESKTOP_PATH="$HOME/.local/share/applications/$DESKTOP_FILE_NAME"
cat > "$DESKTOP_PATH" <<DESKEOF
[Desktop Entry]
Version=1.0
Type=Application
Name=ObraPasaLista
Comment=Control de presencia en obra
Exec=bash -lc 'cd "$APP_DIR" && source "$APP_DIR/.venv/bin/activate" && python "$APP_FILE"'
Icon=$ICON_PATH
Terminal=true
Categories=Office;Utility;
StartupNotify=true
DESKEOF
chmod +x "$DESKTOP_PATH"

say "Instalación completada"
printf 'Aplicación instalada en: %s\n' "$APP_DIR"
printf 'Lanzador de escritorio: %s\n' "$DESKTOP_PATH"
printf 'Arranque manual: %s\n' "$APP_DIR/arrancar.sh"
printf 'URL local: http://127.0.0.1:5000\n'
warn "El acceso directo abre una terminal porque la app Flask necesita quedarse ejecutándose mientras la uses."
