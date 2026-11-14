#!/usr/bin/env python3
import time

def main():
    counter = 1
    while True:
        print(f"[OS-21] Python systemd servisi aktif! Sayac: {counter}", flush=True)
        counter += 1
        time.sleep(5)

if __name__ == "__main__":
    main()
