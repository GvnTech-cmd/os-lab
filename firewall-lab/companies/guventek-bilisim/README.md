# BGT207 Vize Projesi - GüvenTek Bilişim A.Ş. Ağ Planlaması

> Contributed by G*** Ş*** ([@GvnTech-cmd](https://github.com/GvnTech-cmd)) - BGT207 Güvenlik Duvarı Çözümleri - 2026-2027 Güz midterm project.

Bu proje, GüvenTek Bilişim A.Ş.'nin 3 farklı lokasyonundaki (İstanbul, Ankara, İzmir) ağ altyapısının güvenliğini, VLAN segmentasyonunu ve bant genişliği ihtiyaçlarını planlamak amacıyla hazırlanmıştır. **Proje KVKK (Kişisel Verilerin Korunması Kanunu) ve gizlilik standartlarına tam uyumlu olarak tasarlanmıştır.**

## 1. Senaryo: GüvenTek Bilişim A.Ş.

GüvenTek Bilişim, 3 farklı ofiste toplam 370 çalışanı ile faaliyet gösteren bir teknoloji firmasıdır. Amacımız; ofislerin ihtiyaç duyduğu bant genişliğini hesaplamak, ağları VLAN'lar ile birbirinden izole etmek ve uygun Güvenlik Duvarı (Firewall) cihazlarını konumlandırmaktır.

| Ofis | Lokasyon | Kullanıcı Sayısı | Açıklama |
| --- | --- | --- | --- |
| Merkez Ofis | İstanbul | 200 Personel | Şirket yönetimi, İK, finans ve ana veri merkezi buradadır. |
| Operasyon Şubesi | Ankara | 100 Personel | Satış, saha operasyonları ve teknik destek ekibi. |
| Ar-Ge ve Yazılım | İzmir | 70 Personel | Yazılım geliştiriciler; yüksek bant genişliği ve test sunucuları. |

Tüm ofisler internete ana ve yedek hatlar (LTE/5G veya SD-WAN) üzerinden çıkar ve birbirlerine IPsec VPN ile bağlıdır. Uzaktan çalışan personel için **MFA (Çok Faktörlü Kimlik Doğrulama) destekli, kimlik sağlayıcı (LDAP/SSO) entegreli ve Rol Tabanlı (Role-Based)** Client VPN yapılandırılmıştır.

## 2. Ağ Topolojisi ve VLAN Planı

Güvenlik prensipleri gereği her ofise kendi `/16` IP bloğu atanmış, tüm ağlar (Misafir ağları dahil olmak üzere) kesinlikle bu şube bloklarının içinden (subnet) dağıtılmıştır. Yönetim (Management) ağları LAN'dan tamamen izole edilmiştir.

| Lokasyon | IP Bloğu | VLAN ID | Ağ | Kullanım Amacı |
| --- | --- | --- | --- | --- |
| İstanbul (Merkez) | 10.10.0.0/16 | 5 | 10.10.5.0/24 | Yönetim (Management) Ağı |
| İstanbul (Merkez) | | 10 | 10.10.10.0/24 | Yönetim ve İdari Personel |
| İstanbul (Merkez) | | 20 | 10.10.20.0/24 | IT ve Güvenlik Ekibi |
| İstanbul (Merkez) | | 30 | 10.10.30.0/24 | Sunucular (ERP, Mail, Veritabanı) |
| İstanbul (Merkez) | | 99 | 10.10.99.0/24 | Misafir Ağı (Sadece İnternet) |
| Ankara (Şube) | 10.20.0.0/16 | 5 | 10.20.5.0/24 | Yönetim (Management) Ağı |
| Ankara (Şube) | | 10 | 10.20.10.0/24 | Satış ve Operasyon Personeli |
| Ankara (Şube) | | 20 | 10.20.20.0/24 | Teknik Destek Ekibi |
| Ankara (Şube) | | 99 | 10.20.99.0/24 | Misafir Ağı (Sadece İnternet) |
| İzmir (Ar-Ge) | 10.30.0.0/16 | 5 | 10.30.5.0/24 | Yönetim (Management) Ağı |
| İzmir (Ar-Ge) | | 10 | 10.30.10.0/24 | Yazılım ve Ar-Ge Ekibi |
| İzmir (Ar-Ge) | | 99 | 10.30.99.0/24 | Misafir Ağı (Sadece İnternet) |

*Not: Firewall, switch ve iDRAC admin arayüzlerine LAN'dan ulaşılamaz; sadece VPN veya Management (Yönetim) VLAN'larından erişilebilir.*

## 3. Bant Genişliği ve Firewall Seçim Matrisi

Hız hesaplamaları şu formüle göre yapılmıştır: `Toplam Hız = (Kullanıcı Sayısı × Eşzamanlılık Oranı × Kişi Başı Ortalama Hız) × 1.25`

| Ofis | Toplam Kişi | Gereksinim | Ana + Yedek İnternet Hattı | Seçilen Firewall (NGFW) | Tahmini Fiyat |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **İstanbul Merkez** | **200** | 350 Mbps | 500 Mbps Fiber + 100 Mbps SD-WAN | **FortiGate 100F (HA)** | ~$3,000 x 2 |
| **Ankara Şube** | **100** | 175 Mbps | 200 Mbps Fiber + 5G/LTE Yedek | **FortiGate 60F** | ~$1,000 |
| **İzmir Ar-Ge** | **70** | 787 Mbps | 1 Gbps Fiber + 200 Mbps SD-WAN | **FortiGate 200F** | ~$4,500 |
| **TOPLAM** | **370** | **1.3 Gbps** | **1.7 Gbps Ana + Yedekler** | | |

## 4. Temel Güvenlik Kuralları ve Operasyonlar

Ağ güvenliği "Default Deny" mantığı ile kurulmuştur. 3 şubenin de kural listesinin en altında, diğer kurallara uymayan her şeyi otomatik düşüren **Any-Any-Drop (Catch-all Deny)** kuralı açıkça yazılıdır.

- **Temel Servisler:** Tüm şubelerde IP dağıtımı ve çözümlemesi için **DHCP (UDP 67/68), DNS (TCP/UDP 53) ve NTP (UDP 123)** erişimlerine açıkça izin veren kurallar tanımlanmıştır.
- **İnternet Çıkışları (Ar-Ge Kısıtlaması):** İzmir Ar-Ge (VLAN 10) ağının internete doğrudan çıkış (direct internet) kuralı yoktur; dışarıya sadece güvenli bir Proxy üzerinden çıkabilirler. Misafir ağı (VLAN 99) ise şirket içine erişemez, sadece internete çıkabilir.
- **Operasyon ve Bakım Rutinleri (Operations):**
  * **Yedekleme (Backup/DR):** Tüm Firewall konfigürasyonları ve kural setleri **haftalık** olarak otomatik dışa aktarılır (config-export) ve yedeklenir.
  * **Güncelleme (Patching/Firmware):** Sistem yamaları ve Firewall firmware güncellemeleri **aylık** rutin olarak test edilip uygulanır.
  * **CVE Takibi:** Ortak güvenlik açıkları (CVE) aylık olarak Nessus vb. araçlarla taranır ve güncel zafiyet izleme listesi (cveWatch) tutulur.
  * **İzleme ve Log Retention:** Loglar merkezdeki FortiAnalyzer (SIEM) sunucusuna gönderilir ve yasal uyumluluk gereği (Log retention) geriye dönük en az **6 ay** boyunca arşivlenir.
