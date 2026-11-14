# Nraphy

## Şirket

Ankara, İstanbul ve Londra'da ofisleri olan, ayrıca 10.000 öğrencili bir **Akademik Şubesi** bulunan eğitim-teknoloji grubu. Her şubede personel, yazılım ekibi ve Ar-Ge ekibi vardır. Halka açık yüzü: web portalı, LMS, mobil uygulama ve bunların API'leri.

| Şube | Personel | Öğrenci | Yazılım | Ar-Ge | Hat (↓/↑) |
|---|---|---|---|---|---|
| İstanbul Ofisi (Genel Merkez) | 120 | – | 60 | 40 | 1 Gbps |
| Ankara Ofisi | 45 | – | 35 | 15 | 500 Mbps |
| Londra Ofisi | 25 | – | 15 | 10 | 300 Mbps |
| Akademik Şube | 850 (600 hoca + 250 idari) | 10.000 | 10 | 20 | 10 Gbps |

Akademik Şube'deki hocalar şema gereği `staff` altında sayılır, ağda ise ayrı `faculty` VLAN'ındadır.

## Ağ mantığı

- **Rol bazlı segmentasyon:** staff, rnd, software, servers, management; Akademik Şube'de ek olarak faculty, students-wifi ve students-lab.
- **Misafir ve IoT/kamera VLAN'ı her şubede var:** misafir (60) yalnızca web çıkışı alır, IoT (70) iç ağa hiç erişemez. Bir kamera ele geçirilirse ERP'ye ulaşamaz, bir ziyaretçi personel ağını göremez.
- **Alt ağlar kişiye değil cihaza göre boyutlandırıldı:** 10.000 öğrenci × ~1,5 cihaz için `students-wifi` bir /18 (16.380 adres); kısa DHCP kira süresiyle.
- **DMZ ve WAF:** halka açık servisler (İstanbul'da reverse proxy/portal, Akademik Şube'de LMS) yalnızca DMZ VLAN'ında; önlerinde WAF var. Origin yalnızca WAF'ın (Cloudflare edge) IP aralıklarını kabul eder, yani WAF atlanamaz. DMZ'den içeri açılan tek yol proxy → uygulama sunucusu, tek host ve tek port (8443).
- **Yönetim VLAN'ı (99):** dışarıdan hiçbir erişim yok, sadece VPN + bastion.
- **Taban servisler her şubede açık:** DHCP (67/68), DNS (53), NTP (123). "Hepsini kapat" ağı da kapatır.
- **Varsayılan reddet:** her güvenlik duvarının son kuralı loglu `deny any → any`; izin vermediğimiz her şey bilerek engelli.
- **Kenarda sessiz `deny`:** herkese açık SSH gibi dış trafiğe cevap verilmez, `reject` yalnızca iç kullanıcılar için düşünülür (şemada `drop` yok, `deny` sessiz düşürmedir).
- **Şubeler arası:** her şube HQ'ya kendi IPsec tüneliyle bağlanır (SD-WAN, ikincil ISP ile failover); Londra Ar-Ge verisi bölgesel kalır.
- **Yüksek erişilebilirlik:** İstanbul ve kampüs çevre güvenlik duvarları active/passive HA çiftidir; tek kutu tek arıza noktası olmasın diye.

## Bant genişliği

- **Akademik Şube – 10 Gbps:** sınav günü eşzamanlı ~%30 kullanıcı × ~3 Mbps video/LMS ≈ 9 Gbps. Kenar güvenlik duvarı IPS açıkken bu yükü taşımalı, bu yüzden hat hızının üzerinde verimli modeller seçildi (aşağıya bak).
- **İstanbul – 1 Gbps:** Zoom, IP telefon, ERP, git/CI-CD ve üç şubenin VPN trafiği HQ'da birleşir.
- **Ankara – 500 Mbps / Londra – 300 Mbps:** daha çok Zoom, e-posta, git ve yedekleme.
- Hatlar simetriktir; yedekleme ve git push yukarı yönde de yük bindirir.

## Ürün seçimi

Her güvenlik duvarı için seçilen ürün + 4 alternatif (toplam 5) `company.json` içinde fiyat ve gerekçesiyle yer alır. Ana kriter **IPS/UTM açıkken** verim, sonra fiyat ve operasyon kolaylığı. Fortinet'te ortak karar şuydu: tüm şubelerde aynı işletim sistemi ve tek yönetim paneli ile eğitim maliyeti ve yapılandırma hatası azalır.

Boyutlandırma kuralı: **seçilen modelin tehdit-koruma verimi hat hızının üstünde olmalı.**

| Yer | Seçim | Verim | Hat |
|---|---|---|---|
| İstanbul çevre + Ar-Ge/yazılım | FortiGate 200F | ~3 Gbps | 1 Gbps |
| Ankara, Londra | FortiGate 60F | ~0,7 Gbps | 500 / 300 Mbps |
| Akademik Şube çevre | FortiGate 1000F | ~13 Gbps | 10 Gbps |
| Akademik Şube öğrenci segmenti | FortiGate 900G | ~12 Gbps | 10 Gbps |

Elenen alternatiflerde Palo Alto fiyat/abonelik nedeniyle, Check Point ve Cisco yönetim sunucusu/lisans yükü nedeniyle, Sophos ve pfSense/OPNsense yüksek yükte verim ve merkezi yönetim sınırı nedeniyle elendi.

**WAF:** İstanbul ve kampüs DMZ'si için Cloudflare WAF (Business, yıllık ~2.400 USD): OWASP kuralları, DDoS emilimi ve bot yönetimi dahil, en ucuz ve hızlı yol. Alternatifler: ModSecurity + OWASP CRS (ücretsiz, ama tek başına DDoS emmez, bu yüzden reverse proxy'de ikinci katman olarak çalışır), FortiWeb, F5 BIG-IP Advanced WAF, Imperva.

> Not: Fiyatlar ve verim değerleri yaklaşık liste fiyatları / üretici datasheet'lerindeki *threat-protection* sınıfı rakamlardır; kesin değerler için ilgili datasheet'e bakılmalıdır.

## Uzaktan erişim ve izleme

- **Herkese açık SSH yok.** Yöneticiler rol bazlı VPN ile bastion'a, oradan yönetim VLAN'larına geçer.
- **Kimlik ve MFA:** kimlik kaynağı Microsoft Entra ID / Active Directory (RADIUS + SAML), her VPN girişi ikinci faktör ister (FortiToken / TOTP). Rol, AD grubundan gelir: `admin-vpn` → bastion/yönetim, `dev-vpn` → git/CI, `staff-vpn` → ERP ve e-posta.
- **Sahiplik:** güvenlik alarmları Akademik Şube SOC ekibinde (2 analist), uptime şube BT sorumlularında, yapılandırma yedeği ve yama rutini ağ yöneticisinde.
- **SIEM:** Wazuh; yüksek önemli engellemeler Telegram'a düşer.
- **Uygulama vs. güvenlik:** ERP/LMS/mobil uygulama sağlığı ops kanalına, güvenlik olayları (engeller, kimlik doğrulama hataları, IPS ve WAF vuruşları) SOC'ye gider.

## Operasyon

- **Log saklama:** 90 gün SIEM'de sıcak, 2 yıl değiştirilemez arşivde (5651 ve KVKK delili; GDPR gereği Londra logları bölgede de tutulur).
- **Yedek:** her gece tüm güvenlik duvarı yapılandırmaları şifreli olarak git deposuna yedeklenir, üç ayda bir geri yükleme testi yapılır. Yedeği olmayan kutu, her kuralı hafızadan yeniden yazmak demektir.
- **Yama ve firmware:** aylık yama penceresi, üretici güvenlik bültenlerine (PSIRT) abonelik, kritik CVE'ler 72 saat içinde yamalanır.

## CVE izleme

**CVE-2024-21762** (FortiOS SSL-VPN, uzaktan kod çalıştırma): durum `mitigated`.

- **Geçici önlem:** SSL-VPN web modu kapalı; uzaktan erişim yalnızca IPsec/IKEv2 ve MFA ile verilir, yani sömürülen servis yüzeyi yok.
- **Kalıcı çözüm:** tüm FortiGate'ler üretici bülteninde (FG-IR-24-015) belirtilen düzeltilmiş firmware'e aylık yama penceresinde çıkarılır.
- **Doğru katman:** bu açığı güvenlik duvarının kendi kuralları durduramaz; çözüm servisi kapatmak ve yamalamaktır.
