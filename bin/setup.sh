#!/bin/bash
# =============================================================================
# daita-studio Setup-Skript
# =============================================================================
# Richtet die Python-Umgebung ein und prüft die Konfiguration.
#
# Verwendung:
#   ./bin/setup.sh              - Standard-Installation (shared venv)
#   ./bin/setup.sh --local      - Lokale .venv im Projektverzeichnis
#   ./bin/setup.sh --offline    - Offline-Installation aus ./wheels/
#
# Standard-Venv: /mnt/user/venv/daita-lakehouse (geteilt mit anderen Services)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$INSTALL_DIR/backend"

OFFLINE=false
LOCAL_VENV=false

for arg in "$@"; do
    case $arg in
        --offline) OFFLINE=true ;;
        --local)   LOCAL_VENV=true ;;
    esac
done

# Venv-Pfad bestimmen
if [ "$LOCAL_VENV" = true ]; then
    VENV_PATH="$INSTALL_DIR/.venv"
else
    VENV_PATH="/mnt/user/venv/daita-lakehouse"
fi

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                 🎨 daita-studio Setup                        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo "  Install-Dir: $INSTALL_DIR"
    echo "  Venv:        $VENV_PATH"
    echo "  Offline:     $OFFLINE"
    echo ""
}

# ---------------------------------------------------------------------------
# STEP 1: Python prüfen
# ---------------------------------------------------------------------------

find_python() {
    for py in python3.12 python3.11 python3.10 python3; do
        if command -v "$py" >/dev/null 2>&1; then
            echo "$py"
            return
        fi
    done
    echo ""
}

is_venv_healthy() {
    local venv="$1"
    [ -x "$venv/bin/python" ] && "$venv/bin/python" -c "import encodings" >/dev/null 2>&1
}

print_header

PYTHON_BIN="$(find_python)"
if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}❌ Kein Python 3.10+ gefunden!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python: $($PYTHON_BIN --version 2>&1)${NC}"

# ---------------------------------------------------------------------------
# STEP 2: Venv einrichten
# ---------------------------------------------------------------------------

echo ""
echo -e "${BLUE}📦 Python-Umgebung einrichten...${NC}"

if is_venv_healthy "$VENV_PATH"; then
    echo -e "${GREEN}✅ Venv bereits vorhanden und gesund: $VENV_PATH${NC}"
else
    if [ "$LOCAL_VENV" = true ] || [[ "$VENV_PATH" == "$INSTALL_DIR"* ]]; then
        echo "   Erstelle neue lokale .venv..."
        rm -rf "$VENV_PATH"
        "$PYTHON_BIN" -m venv "$VENV_PATH"
        echo -e "${GREEN}✅ Neue .venv erstellt${NC}"
    else
        echo -e "${RED}❌ Venv nicht gefunden: $VENV_PATH${NC}"
        echo "   Bitte zuerst die geteilte Umgebung einrichten oder --local verwenden"
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# STEP 3: Dependencies installieren
# ---------------------------------------------------------------------------

echo ""
echo -e "${BLUE}📦 Dependencies installieren...${NC}"

if [ "$OFFLINE" = true ]; then
    if [ ! -d "$INSTALL_DIR/wheels" ]; then
        echo -e "${RED}❌ Kein wheels/-Verzeichnis gefunden!${NC}"
        echo "   Bitte Wheels auf Entwicklungsmaschine exportieren:"
        echo "   pip download -r backend/requirements.txt -d wheels/"
        exit 1
    fi
    echo "   Offline-Installation aus ./wheels/ ..."
    "$VENV_PATH/bin/pip" install \
        --no-index \
        --find-links "$INSTALL_DIR/wheels" \
        -r "$BACKEND_DIR/requirements.txt" \
        --quiet
else
    echo "   Online-Installation aus PyPI..."
    "$VENV_PATH/bin/pip" install \
        -r "$BACKEND_DIR/requirements.txt" \
        --quiet
fi

echo -e "${GREEN}✅ Dependencies installiert${NC}"

# ---------------------------------------------------------------------------
# STEP 4: Konfiguration prüfen
# ---------------------------------------------------------------------------

echo ""
echo -e "${BLUE}🔧 Konfiguration prüfen...${NC}"

CFG_DIR="$INSTALL_DIR/cfg"
MISSING_CFG=false

# database.yml
if [ ! -f "$CFG_DIR/database.yml" ]; then
    echo -e "${YELLOW}⚠️  cfg/database.yml fehlt!${NC}"
    if [ -f "$CFG_DIR/database.yml.template" ]; then
        cp "$CFG_DIR/database.yml.template" "$CFG_DIR/database.yml"
        echo "   → Kopiert aus database.yml.template"
        echo "   ⚠️  BITTE ANPASSEN: $CFG_DIR/database.yml"
        MISSING_CFG=true
    else
        echo -e "${RED}   ❌ Kein Template gefunden! Bitte manuell anlegen.${NC}"
        MISSING_CFG=true
    fi
else
    echo -e "${GREEN}✅ cfg/database.yml vorhanden${NC}"
fi

# config.yml
if [ ! -f "$CFG_DIR/config.yml" ]; then
    echo -e "${RED}❌ cfg/config.yml fehlt!${NC}"
    MISSING_CFG=true
else
    echo -e "${GREEN}✅ cfg/config.yml vorhanden${NC}"
fi

# Ausgabeverzeichnisse sicherstellen
mkdir -p "$INSTALL_DIR/log/tpt"
mkdir -p "$INSTALL_DIR/ddl/generated"
mkdir -p "$INSTALL_DIR/tpt/generated"
mkdir -p "$INSTALL_DIR/sql/generated"
mkdir -p "$INSTALL_DIR/diagrams"
echo -e "${GREEN}✅ Ausgabeverzeichnisse sichergestellt${NC}"

# ---------------------------------------------------------------------------
# STEP 5: Schnelltest
# ---------------------------------------------------------------------------

echo ""
echo -e "${BLUE}🧪 Import-Test...${NC}"

if PYTHONPATH="$BACKEND_DIR" "$VENV_PATH/bin/python" \
        -c "from app.config import PATHS, TERADATA_CONFIG; print('  root:', PATHS['root'])" 2>&1; then
    echo -e "${GREEN}✅ Backend-Import OK${NC}"
else
    echo -e "${RED}❌ Backend-Import fehlgeschlagen – Log prüfen${NC}"
fi

# ---------------------------------------------------------------------------
# Zusammenfassung
# ---------------------------------------------------------------------------

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║               Setup abgeschlossen!                           ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$MISSING_CFG" = true ]; then
    echo -e "${YELLOW}⚠️  Konfiguration anpassen, dann:${NC}"
    echo "   1. cfg/database.yml – Teradata Host, User, Password eintragen"
    echo "   2. ./bin/start.sh"
else
    echo "Nächste Schritte:"
    echo "   ./bin/start.sh          - Services starten"
    echo "   ./bin/start.sh status   - Status prüfen"
    echo ""
    echo "URLs nach Start:"
    local_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
    echo "   Frontend:  http://$local_ip:9015/"
    echo "   API Docs:  http://$local_ip:8015/docs"
fi
echo ""
