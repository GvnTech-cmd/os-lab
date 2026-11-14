#!/usr/bin/env bash
set -euo pipefail

# OS-21: Boot-Time Python Service Starter (systemd)
SERVICE_NAME="os21-python-loop.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOOP_PY="${SCRIPT_DIR}/loop.py"
UNIT_OUT="/tmp/${SERVICE_NAME}"

echo "=== [1/4] loop.py dosyasi kontrol ediliyor ==="
if [[ ! -f "$LOOP_PY" ]]; then
    echo "Hata: $LOOP_PY bulunamadi!" >&2
    exit 1
fi

echo "=== [2/4] Systemd .service birim dosyasi olusturuluyor ==="
cat << UNIT > "$UNIT_OUT"
[Unit]
Description=OS-21 Boot-Time Python Loop Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $LOOP_PY
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

echo "Olusturulan servis dosyasi ($UNIT_OUT):"
cat "$UNIT_OUT"
echo "----------------------------------------"

if [[ "${1:-}" == "--install" ]]; then
    echo "=== [3/4] Servis sisteme kuruluyor ve etkinlestiriliyor (enable & start) ==="
    sudo cp "$UNIT_OUT" "/etc/systemd/system/${SERVICE_NAME}"
    sudo systemctl daemon-reload
    sudo systemctl enable --now "${SERVICE_NAME}"

    echo "=== [4/4] Dogrulama: enable / status / journalctl ==="
    echo "-> Enabled durumu:"
    systemctl is-enabled "${SERVICE_NAME}"
    echo "-> Servis durumu (status):"
    sudo systemctl status "${SERVICE_NAME}" --no-pager -l || true
    echo "-> Servis loglari (journalctl):"
    sleep 2
    sudo journalctl -u "${SERVICE_NAME}" -n 5 --no-pager
else
    echo "Bilgi: Servis dosyasi basariyla uretildi."
    echo "Sisteme kurmak ve canli dogrulamak icin: sudo $0 --install komutunu calistirin."
fi
