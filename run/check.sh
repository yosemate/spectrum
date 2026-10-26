#!/usr/bin/env bash
# Diagnóstico: diz o que está pronto e o que falta para abrir o supervisório no navegador.
# Uso: bash run/check.sh   (copie a saída inteira se precisar pedir ajuda)
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$REPO_DIR"
bad=0

echo "== Repositório =="
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
echo "branch: $branch @ $(git rev-parse --short HEAD 2>/dev/null || echo '?')"
[[ -f main.py && -f run/fake_esp32.py ]] && c_ok "arquivos do programa presentes" || { c_err "main.py ou run/fake_esp32.py ausentes: você está na pasta/branch certa?"; bad=1; }
[[ -f assets/cursors/fibra-seta.png ]] && c_ok "cursores presentes" || { c_err "assets novos ausentes: atualize o repositório (git pull) ou troque para a branch feat/ux-acessibilidade-animacoes"; bad=1; }
[[ -f assets/fonts/Arena.ttf && -f assets/fonts/DroplineRegular.otf && -f assets/fonts/Inter-Regular.ttf && -f assets/fonts/IBMPlexMono-Regular.ttf ]] && c_ok "fontes Arena, Dropline, Inter e IBM Plex presentes" || { c_err "fontes novas ausentes (branch antiga?)"; bad=1; }
if file run/*.sh 2>/dev/null | grep -q CRLF; then c_err "scripts com fim de linha do Windows (CRLF). Rode: sed -i 's/\\r$//' run/*.sh"; bad=1; fi

echo; echo "== Ferramentas =="
for pair in "Xvfb:xvfb" "x11vnc:x11vnc" "websockify:websockify" "fluxbox:fluxbox" "python3:python3"; do
  cmd="${pair%%:*}"; pkg="${pair##*:}"
  command -v "$cmd" >/dev/null 2>&1 && c_ok "$cmd" || { c_err "$cmd ausente (pacote $pkg)"; bad=1; }
done
if d="$(novnc_dir)"; then c_ok "noVNC em $d"; else c_err "noVNC ausente (pacote novnc)"; bad=1; fi
"$PYTHON" - <<'PY' || bad=1
import importlib, sys
for name in ("PyQt5.QtCore", "numpy", "matplotlib", "serial", "reportlab"):
    try:
        importlib.import_module(name)
        print("\033[32m✔\033[0m", name)
    except Exception as exc:
        print("\033[31m✘\033[0m", name, "->", exc); sys.exit(1)
PY

echo; echo "== Plugin gráfico Qt =="
DISPLAY=:99 QT_QPA_PLATFORM=xcb "$PYTHON" run/probe_qt.py || bad=1

echo; echo "== Serviços =="
[[ -S /tmp/.X11-unix/X99 ]] && c_ok "display :99 ativo" || { c_warn "display :99 parado (bash run/start_display.sh)"; bad=1; }
for port in 5900 6080 8080; do
  if port_open "$port"; then c_ok "porta $port respondendo"; else c_warn "porta $port sem serviço"; fi
done
pgrep -f "[p]ython[^ ]* .*main[.]py" >/dev/null && c_ok "supervisório em execução" || c_warn "supervisório não está rodando (bash run/start_app.sh)"

echo; echo "== Endereço =="
echo "$(novnc_url)"
if [[ -n "${CODESPACE_NAME:-}" ]] && command -v gh >/dev/null 2>&1; then
  echo; echo "Portas encaminhadas (gh):"; gh codespace ports -c "$CODESPACE_NAME" 2>&1 | head -8 || true
fi

echo; for f in xvfb x11vnc websockify fluxbox; do tail_log "$LOG_DIR/$f.log"; done
tail_log run-data/app.log

echo
[[ "$bad" == 0 ]] && echo "Tudo certo." || { echo "Há itens com ✘ acima."; exit 1; }
