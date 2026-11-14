# OS-12 Doğrulama (Verification) — Directory-Structure Scaffolder (mkdir -p Templates)

## 1. Çalıştırma Komutları

- Kabuk sözdizimi (syntax) doğrulaması için:
  ```bash
  bash -n linux-lab/scripts/os-12-dir-scaffolder.sh
  ```

- Diske dokunmadan önizleme (`--dry-run`) testi çalıştırmak için:
  ```bash
  bash linux-lab/scripts/os-12-dir-scaffolder.sh --template web-app --target /tmp/os12-demo --dry-run
  ```

- Gerçek dizin ağacını oluşturmak ve sonuçları doğrulamak için:
  ```bash
  bash linux-lab/scripts/os-12-dir-scaffolder.sh --template web-app --target /tmp/os12-demo
  find /tmp/os12-demo -maxdepth 3 | sort
  ```

## 2. Beklenen Çıktı

`--dry-run` önizleme komutu çalıştırıldığında beklenen çıktı:

```text
=== OS-12: Directory-Structure Scaffolder ===
Template : web-app
Target   : /tmp/os12-demo
Mode     : DRY-RUN (preview only, no directories created)

[DRY-RUN] mkdir -p "/tmp/os12-demo/src/components"
[DRY-RUN] mkdir -p "/tmp/os12-demo/src/pages"
[DRY-RUN] mkdir -p "/tmp/os12-demo/src/assets/images"
[DRY-RUN] mkdir -p "/tmp/os12-demo/src/styles"
[DRY-RUN] mkdir -p "/tmp/os12-demo/tests/unit"
[DRY-RUN] mkdir -p "/tmp/os12-demo/tests/e2e"
[DRY-RUN] mkdir -p "/tmp/os12-demo/docs"

Summary: Previewed 7 directories. Re-run without --dry-run to apply.
```

Gerçek oluşturma komutu çalıştırıldığında beklenen çıktı:

```text
=== OS-12: Directory-Structure Scaffolder ===
Template : web-app
Target   : /tmp/os12-demo
Mode     : APPLY (creating nested directories via mkdir -p)

[CREATED] /tmp/os12-demo/src/components
[CREATED] /tmp/os12-demo/src/pages
[CREATED] /tmp/os12-demo/src/assets/images
[CREATED] /tmp/os12-demo/src/styles
[CREATED] /tmp/os12-demo/tests/unit
[CREATED] /tmp/os12-demo/tests/e2e
[CREATED] /tmp/os12-demo/docs

Summary: Successfully created 7 directories under /tmp/os12-demo.
```
