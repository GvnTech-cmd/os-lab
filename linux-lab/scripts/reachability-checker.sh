#!/bin/bash
set -euo pipefail

SUBNET="10.25.130"
ROSTER="roster.txt"

echo "Tarama basliyor: $SUBNET.1 - $SUBNET.254"

for i in {1..254}
do
    IP="$SUBNET.$i"

    if ping -c 1 -W 0.2 "$IP" > /dev/null 2>&1
    then
        if nc -z -w 1 "$IP" 22 > /dev/null 2>&1
        then
            SSH_DURUM="SSH ACIK"
        else
            SSH_DURUM="SSH KAPALI"
        fi

        if [ -f "$ROSTER" ]
        then
            OGRENCI=$(grep "$IP" "$ROSTER" || true)
            echo "[UP] $IP - $SSH_DURUM | Kayit: $OGRENCI"
        else
            echo "[UP] $IP - $SSH_DURUM"
        fi
    fi
done

echo "Tarama bitti."
