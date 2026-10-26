#!/usr/bin/env bash
# Sobe o display virtual e o acesso pelo navegador (noVNC na porta 6080) e mostra o endereço para abrir.
# Uso: bash run/start_display.sh                       (ajuste automático pelo noVNC)
#      RESOLUTION=1366x768 bash run/start_display.sh
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
RES="${RESOLUTION:-1366x768}"
# Com TigerVNC, resize=remote faz o monitor virtual acompanhar a janela do navegador.
VNC_SERVER="$(command -v Xtigervnc || command -v Xvnc || true)"

# Codespaces existentes não executam postCreateCommand quando a branch muda.
# Se os pacotes não estiverem presentes, recupera o ambiente automaticamente.
cd "$REPO_DIR"
echo "==> Conferindo ferramentas"
missing=()
command -v Xvfb >/dev/null 2>&1 || missing+=(xvfb)
command -v x11vnc >/dev/null 2>&1 || missing+=(x11vnc)
command -v websockify >/dev/null 2>&1 || missing+=(websockify)
command -v fluxbox >/dev/null 2>&1 || missing+=(fluxbox)
command -v xdpyinfo >/dev/null 2>&1 || missing+=(x11-utils)
novnc_dir >/dev/null 2>&1 || missing+=(novnc)

if (( ${#missing[@]} > 0 )); then
  c_warn "Faltam pacotes: ${missing[*]}. Instalando dependências do projeto..."
  if ! bash "$REPO_DIR/run/setup.sh"; then
    c_err "A instalação falhou; consulte a mensagem do apt/pip acima."
    c_err "Se estiver no Codespaces, confira também os logs de criação do contêiner."
    exit 1
  fi
fi

# Confirma que a recuperação funcionou antes de criar o display.
for pair in "Xvfb:xvfb" "x11vnc:x11vnc" "websockify:websockify" "fluxbox:fluxbox" "xdpyinfo:x11-utils"; do
  need "${pair%%:*}" "${pair##*:}" || exit 1
done
NOVNC="$(novnc_dir)" || { c_err "noVNC continua ausente após a instalação."; exit 1; }
c_ok "Xvfb, x11vnc, websockify, fluxbox e noVNC (${NOVNC})"

echo "==> Encerrando uma execução anterior"
pkill -x Xtigervnc 2>/dev/null || true
pkill -x Xvnc 2>/dev/null || true
pkill -x Xvfb 2>/dev/null || true
pkill -x x11vnc 2>/dev/null || true
pkill -x websockify 2>/dev/null || true
pkill -x fluxbox 2>/dev/null || true
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
sleep 1

echo "==> Iniciando o display ${RES}"
export DISPLAY=:99
if [[ -n "$VNC_SERVER" && "${NOVNC_FIXED_DISPLAY:-0}" != "1" ]]; then
  c_ok "TigerVNC: resolução dinâmica pelo navegador"
  setsid nohup "$VNC_SERVER" :99 -geometry "$RES" -depth 24 -localhost yes -SecurityTypes None -rfbport 5900 -AlwaysShared >"$LOG_DIR/tigervnc.log" 2>&1 &
  for _ in $(seq 1 30); do
    DISPLAY=:99 xdpyinfo >/dev/null 2>&1 && wait_port 5900 1 && break
    sleep 0.5
  done
  if ! DISPLAY=:99 xdpyinfo >/dev/null 2>&1 || ! port_open 5900; then
    c_warn "TigerVNC não iniciou; usando modo Xvfb compatível."
    pkill -x Xtigervnc 2>/dev/null || true
    pkill -x Xvnc 2>/dev/null || true
    VNC_SERVER=""
  fi
fi
if [[ -z "$VNC_SERVER" || "${NOVNC_FIXED_DISPLAY:-0}" == "1" ]]; then
  setsid nohup Xvfb :99 -screen 0 "${RES}x24" -ac +extension GLX +render -noreset >"$LOG_DIR/xvfb.log" 2>&1 &
  for _ in $(seq 1 30); do DISPLAY=:99 xdpyinfo >/dev/null 2>&1 && break; sleep 0.5; done
  if ! DISPLAY=:99 xdpyinfo >/dev/null 2>&1; then c_err "O display :99 não subiu."; tail_log "$LOG_DIR/xvfb.log"; exit 1; fi
  setsid nohup x11vnc -display :99 -forever -shared -nopw -localhost -cursor most -quiet -rfbport 5900 >"$LOG_DIR/x11vnc.log" 2>&1 &
fi
setsid nohup fluxbox >"$LOG_DIR/fluxbox.log" 2>&1 &
if ! wait_port 5900 15; then c_err "Servidor VNC indisponível"; exit 1; fi
c_ok "Display virtual e VNC prontos (porta 5900 local)"
setsid nohup websockify --web "$NOVNC" "${NOVNC_BIND:-127.0.0.1}:6080" 127.0.0.1:5900 >"$LOG_DIR/websockify.log" 2>&1 &
if ! wait_port 6080 15; then c_err "O noVNC não abriu a porta 6080."; tail_log "$LOG_DIR/websockify.log"; exit 1; fi
c_ok "noVNC na porta 6080"

echo
echo "Pronto. Abra este endereço no navegador em que você está logado no GitHub:"
echo
echo "    $(novnc_url)"
echo
if [[ -n "${CODESPACE_NAME:-}" ]]; then
  echo "Se aparecer erro 502 ou 404: aguarde 10 s e atualize a página; confira a aba PORTS (porta 6080 deve"
  echo "estar listada, visibilidade Private). Não é preciso torná-la Public: a área de trabalho não tem senha."
else
  echo "Fora do Codespaces o endereço acima só funciona nesta própria máquina."
fi
echo "Próximo passo: bash run/start_app.sh      (diagnóstico: bash run/check.sh)"
