#!/bin/bash
# =============================================================================
# daita-studio Startskript
# =============================================================================
# Startet Backend (FastAPI, Port 8015) und Frontend (HTTP Server, Port 9015)
#
# Verwendung:
#   ./bin/start.sh          - Startet beide Services
#   ./bin/start.sh stop     - Stoppt beide Services
#   ./bin/start.sh status   - Zeigt Status der Services
#   ./bin/start.sh restart  - Neustart beider Services
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$INSTALL_DIR/backend"
FRONTEND_DIR="$INSTALL_DIR/frontend"
VENV_PATH="/mnt/user/venv/daita-lakehouse"
CONFIG_FILE="$INSTALL_DIR/cfg/config.yml"

# Ports aus config.yml lesen (Fallback auf defaults)
BACKEND_PORT=$(grep -E "^\s*backend_port:" "$CONFIG_FILE" 2>/dev/null | awk '{print $2}')
FRONTEND_PORT=$(grep -E "^\s*frontend_port:" "$CONFIG_FILE" 2>/dev/null | awk '{print $2}')
BACKEND_PORT=${BACKEND_PORT:-8015}
FRONTEND_PORT=${FRONTEND_PORT:-9015}

BACKEND_LOG="$INSTALL_DIR/log/studio-backend.log"
FRONTEND_LOG="$INSTALL_DIR/log/studio-frontend.log"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logs-Verzeichnis sicherstellen
mkdir -p "$INSTALL_DIR/log"

ensure_runtime_environment() {
    if [ ! -x "$VENV_PATH/bin/python" ]; then
        echo -e "${RED}❌ Python Umgebung nicht gefunden: $VENV_PATH/bin/python${NC}"
        return 1
    fi
    if ! "$VENV_PATH/bin/python" -c "import encodings" >/dev/null 2>&1; then
        echo -e "${RED}❌ Python Umgebung ist defekt (encodings fehlt)${NC}"
        return 1
    fi
    return 0
}

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                    🎨 daita-studio                           ║"
    echo "║        Modeler • ETL Orchestrator • Metadata Platform        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

get_backend_pid() {
    local pid_by_port=$(lsof -ti tcp:$BACKEND_PORT 2>/dev/null | head -1)
    if [ -n "$pid_by_port" ]; then
        echo "$pid_by_port"
        return
    fi
    pgrep -f "uvicorn.*app.main.*$BACKEND_PORT" 2>/dev/null | head -1
}

get_frontend_pid() {
    local pid_by_port=$(lsof -ti tcp:$FRONTEND_PORT 2>/dev/null | head -1)
    if [ -n "$pid_by_port" ]; then
        echo "$pid_by_port"
        return
    fi
    pgrep -f "http.server $FRONTEND_PORT" 2>/dev/null | head -1
}

start_backend() {
    if [ -n "$(get_backend_pid)" ]; then
        echo -e "${YELLOW}⚠️  Backend läuft bereits (PID: $(get_backend_pid))${NC}"
        return 0
    fi

    ensure_runtime_environment || return 1

    echo -e "${BLUE}🚀 Starte Backend auf Port $BACKEND_PORT...${NC}"
    cd "$INSTALL_DIR"
    nohup env PYTHONPATH="$BACKEND_DIR" "$VENV_PATH/bin/python" -m uvicorn app.main:app \
        --host 0.0.0.0 --port $BACKEND_PORT > "$BACKEND_LOG" 2>&1 &

    sleep 2

    if [ -n "$(get_backend_pid)" ]; then
        echo -e "${GREEN}✅ Backend gestartet (PID: $(get_backend_pid))${NC}"
        echo -e "   Log: $BACKEND_LOG"
    else
        echo -e "${RED}❌ Backend konnte nicht gestartet werden${NC}"
        echo -e "   Prüfe Log: $BACKEND_LOG"
        return 1
    fi
}

start_frontend() {
    if [ -n "$(get_frontend_pid)" ]; then
        echo -e "${YELLOW}⚠️  Frontend läuft bereits (PID: $(get_frontend_pid))${NC}"
        return 0
    fi

    ensure_runtime_environment || return 1

    echo -e "${BLUE}🌐 Starte Frontend auf Port $FRONTEND_PORT...${NC}"
    cd "$INSTALL_DIR"
    nohup "$VENV_PATH/bin/python" -m http.server $FRONTEND_PORT \
        --directory "$FRONTEND_DIR" > "$FRONTEND_LOG" 2>&1 &
    sleep 1

    if [ -n "$(get_frontend_pid)" ]; then
        echo -e "${GREEN}✅ Frontend gestartet (PID: $(get_frontend_pid))${NC}"
        echo -e "   Log: $FRONTEND_LOG"
    else
        echo -e "${RED}❌ Frontend konnte nicht gestartet werden${NC}"
        return 1
    fi
}

stop_backend() {
    local pids=$(lsof -ti tcp:$BACKEND_PORT 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}🛑 Stoppe Backend (PID: $pids)...${NC}"
        echo "$pids" | xargs kill 2>/dev/null
        sleep 2
        pids=$(lsof -ti tcp:$BACKEND_PORT 2>/dev/null)
        if [ -n "$pids" ]; then
            echo "$pids" | xargs kill -9 2>/dev/null
            sleep 1
        fi
        echo -e "${GREEN}✅ Backend gestoppt${NC}"
    else
        echo -e "${YELLOW}ℹ️  Backend läuft nicht${NC}"
    fi
}

stop_frontend() {
    local pids=$(lsof -ti tcp:$FRONTEND_PORT 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}🛑 Stoppe Frontend (PID: $pids)...${NC}"
        echo "$pids" | xargs kill 2>/dev/null
        sleep 1
        pids=$(lsof -ti tcp:$FRONTEND_PORT 2>/dev/null)
        if [ -n "$pids" ]; then
            echo "$pids" | xargs kill -9 2>/dev/null
            sleep 1
        fi
        echo -e "${GREEN}✅ Frontend gestoppt${NC}"
    else
        echo -e "${YELLOW}ℹ️  Frontend läuft nicht${NC}"
    fi
}

show_status() {
    echo ""
    echo -e "${BLUE}📊 Service Status:${NC}"
    echo "─────────────────────────────────────────"

    local backend_pid=$(get_backend_pid)
    if [ -n "$backend_pid" ]; then
        echo -e "   Backend:  ${GREEN}● Running${NC} (PID: $backend_pid, Port: $BACKEND_PORT)"
    else
        echo -e "   Backend:  ${RED}○ Stopped${NC}"
    fi

    local frontend_pid=$(get_frontend_pid)
    if [ -n "$frontend_pid" ]; then
        echo -e "   Frontend: ${GREEN}● Running${NC} (PID: $frontend_pid, Port: $FRONTEND_PORT)"
    else
        echo -e "   Frontend: ${RED}○ Stopped${NC}"
    fi

    echo "─────────────────────────────────────────"

    if [ -n "$backend_pid" ] || [ -n "$frontend_pid" ]; then
        local ip=$(hostname -I | awk '{print $1}')
        echo ""
        echo -e "${BLUE}🔗 URLs:${NC}"
        if [ -n "$frontend_pid" ]; then
            echo -e "   Dashboard:  ${GREEN}http://$ip:$FRONTEND_PORT/${NC}"
            echo -e "   Data Flow:  http://$ip:$FRONTEND_PORT/data-flow.html"
            echo -e "   Modeler:    http://$ip:$FRONTEND_PORT/modeler.html"
            echo -e "   ETL:        http://$ip:$FRONTEND_PORT/etl-dashboard.html"
            echo -e "   Metadaten:  http://$ip:$FRONTEND_PORT/metadata-dashboard.html"
        fi
        if [ -n "$backend_pid" ]; then
            echo -e "   API Docs:   http://$ip:$BACKEND_PORT/docs"
        fi
    fi
    echo ""
}

# =============================================================================
# Main
# =============================================================================

case "${1:-start}" in
    start)
        print_header
        start_backend
        start_frontend
        show_status
        ;;
    stop)
        print_header
        stop_backend
        stop_frontend
        show_status
        ;;
    restart)
        print_header
        stop_backend
        stop_frontend
        sleep 1
        start_backend
        start_frontend
        show_status
        ;;
    status)
        print_header
        show_status
        ;;
    *)
        echo "Verwendung: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
