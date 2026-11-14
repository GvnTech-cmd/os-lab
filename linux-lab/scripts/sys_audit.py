import os
import subprocess

def check_services():
    print("--- SERVİS DURUMLARI ---")
    services = ["ssh", "networking", "ufw"]
    for s in services:
        result = subprocess.run(["systemctl", "is-active", s], capture_output=True, text=True)
        status = result.stdout.strip()
        print(f"[*] Servis {s}: {status if status else 'inactive/unknown'}")

def check_permissions():
    print("\n--- KRİTİK DOSYA İZİNLERİ ---")
    files = ["/etc/passwd", "/etc/shadow"]
    for f in files:
        if os.path.exists(f):
            perms = oct(os.stat(f).st_mode)[-3:]
            print(f"[*] Dosya {f}: İzinler -> **{perms}**")
        else:
            print(f"[!] {f} bulunamadı.")

def check_network():
    print("\n--- AĞ VE DNS KONTROLÜ ---")
    subprocess.run(["ip", "a"])
    if os.path.exists("/etc/resolv.conf"):
        print("\n[i] /etc/resolv.conf içeriği:")
        with open("/etc/resolv.conf", "r") as file:
            print(file.read())

if __name__ == "__main__":
    print("=== Linux Sistem Güvenlik ve Durum Denetimi ===")
    check_services()
    check_permissions()
    check_network()
