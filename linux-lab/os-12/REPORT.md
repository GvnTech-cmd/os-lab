# OS-12 Vize Projesi Raporu — Directory-Structure Scaffolder (mkdir -p Templates)

**Öğrenci:** Doruk Yalçın (2620511009)  
**GitHub:** @Dorukylc  
**Ders:** MYO203  

## 1. Projede Ne Yaptım?
Bu çalışmada **OS-12 (Directory-Structure Scaffolder — `mkdir -p` Templates)** görevi kapsamında, belirli bir şablon spesifikasyonundan (template spec) iç içe dizin ağaçları oluşturan ve diske yazmadan önce önizleme testi (`--dry-run`) sunan bir Bash otomasyon aracı geliştirdim:

- **`linux-lab/scripts/os-12-dir-scaffolder.sh`:** Yerleşik şablonları (`web-app`, `python-pkg`, `linux-ops`) veya dışarıdan verilen özel bir şablon dosyasını okuyarak `mkdir -p` komutuyla hedef dizin altında iç içe klasör yapıları oluşturan betik yazdım.
- **`--dry-run` Önizleme Modu:** Gerçek klasörleri oluşturmadan önce hangi dizinlerin açılacağını ekranda güvenli biçimde listeleyen önizleme özelliğini ekledim.
- **Güvenlik ve Hata Kontrolleri:** `set -euo pipefail` standardını uyguladım, boş satırları/yorumları temizledim ve üst dizine çıkış (`..`) veya kök dizin (`/`) gibi güvensiz yolları engelleyen doğrulama kontrolleri ekledim.

## 2. Git ve Pull Request (PR) Sürecinde Ne Öğrendim?
- Açık kaynak bir projeyi kendi hesabıma fork etmeyi ve ana repoyla senkronize tutmayı öğrendim.
- Ana dalı (`master`) temiz tutarak görev özelinde ayrı bir çalışma dalı (`feat/os-12-dir-scaffolder`) açmanın önemini kavradım.
- Değişiklikleri göndermeden önce `bash -n` ile kabuk sözdizimini ve `--dry-run` / gerçek çalıştırma testlerini doğrulamayı deneyimledim.
- Anlamlı commit mesajları yazarak kendi fork depomdan ana projeye Pull Request (PR) açma ve geri bildirimlere göre PR güncelleme akışını uygulamalı olarak öğrendim.
