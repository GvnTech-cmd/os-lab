# OS-21 Dogrulama (Verification) — Boot-Time Python Service Starter (systemd)

## 1. Calistirma Komutlari

Servis birim dosyasini (.service) uretmek ve onizlemek icin:
    ./linux-lab/scripts/os-21-service-starter.sh

Servisi systemd altina kurmak, acilista otomatik baslayacak sekilde etkinlestirmek (enable) ve status / journalctl ciktilariyla dogrulamak icin:
    sudo ./linux-lab/scripts/os-21-service-starter.sh --install

## 2. Beklenen Cikti

    === [1/4] loop.py dosyasi kontrol ediliyor ===
    === [2/4] Systemd .service birim dosyasi olusturuluyor ===
    === [3/4] Servis sisteme kuruluyor ve etkinlestiriliyor (enable & start) ===
    === [4/4] Dogrulama: enable / status / journalctl ===
    -> Enabled durumu:
    enabled
    -> Servis durumu (status):
    Active: active (running)
    -> Servis loglari (journalctl):
    [OS-21] Python systemd servisi aktif! Sayac: 1
