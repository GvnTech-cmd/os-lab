# NovaTek Holding — Çok Şubeli Güvenlik Duvarı Tasarımı

> Contributed by `M*** B*** Y***` ([@Berrkle](https://github.com/Berrkle)) · BGT207 Güvenlik Duvarı Çözümleri · 2026-2027 Güz midterm project.

NovaTek Holding hayali bir şirkettir. Bu bölüm, şirketin altı birimini, her birimin kadrosunu ve bant genişliğini, IP/VLAN planını, her parça için en iyi beş güvenlik duvarını (fiyatıyla), kural setlerinin mantığını, uzaktan erişimi ve izlemeyi kimin üstlendiğini anlatır. Yapılandırılmış veri `company.json` içindedir; bu dosya kararların gerekçesidir.

Kadro, IP adresleri ve bant genişliği değerleri proje varsayımıdır. Ürün fiyatları **yaklaşık liste fiyatıdır** (yalnızca donanım, cihaz başına, USD); abonelik (IPS/AV/web filtre) ve destek dahil değildir ve bayiye göre değişir.

## 1. Şirket ve birimler

| Birim | Konum | Rol | Personel | Öğrenci | Yazılım | Ar-Ge | Teknik/IT | Toplam |
|---|---|---|---:|---:|---:|---:|---:|---:|
| İstanbul Genel Merkez | İstanbul | Yönetim, veri merkezi, VPN hub, NOC/SOC | 300 | – | – | – | 25 | **325** |
| Ankara Ofisi | Ankara | Kamu ilişkileri, ihale; ikincil hub / DR | 140 | – | – | – | 10 | **150** |
| Londra Ofisi | Londra | UK/AB operasyonları (UK GDPR) | 75 | – | – | – | 5 | **80** |
| Akademik Şube | İstanbul kampüs | Eğitim (600 akademisyen, 400 idari) | 1.000 | **10.000** | – | – | 40 | **11.040** |
| Yazılım Ekibi | İstanbul teknopark | Ürün geliştirme, CI/CD, bulut | – | – | 150 | – | – | **150** |
| Ar-Ge Merkezi | Ankara teknokent | Araştırma, prototip, GPU/veri | – | – | – | 60 | 10 | **70** |
| **Toplam** | | | **1.515** | **10.000** | **150** | **60** | **90** | **11.815** |

### Kamuya açık web siteleri, uygulamalar ve korumaları

| Varlık | Nerede | Koruma |
|---|---|---|
| Kurumsal web sitesi ve tedarikçi portalı | İstanbul DMZ | WAF (FortiWeb / ModSecurity + OWASP CRS) + reverse proxy, yalnızca 443 |
| Mobil uygulama API'si | İstanbul DMZ (API gateway, 8443) | WAF + API gateway: kimlik doğrulama, rate limit (`limit` kuralı) |
| Kampüs web sitesi, LMS ön yüzü, e-kütüphane | Akademik Şube DMZ | WAF + reverse proxy; LMS/OBS giriş sayfasında rate limit |
| Öğrenci mobil uygulaması (LMS/OBS) | Akademik Şube DMZ API'si | WAF + API gateway, MFA'lı öğrenci girişi |

Firewall uygulama katmanındaki bir açığı (ör. PHP uzaktan kod çalıştırma) tek başına durduramaz. Bu yüzden her kamuya açık site WAF arkasındadır ve kalıcı çözüm her zaman yamadır.

## 2. Ağ tasarımı

**Topoloji:** İstanbul hub, diğer beş birim spoke. Şubeler arası IPsec IKEv2 (AES-256-GCM, DH 20, sertifika). Şubeler birbirine doğrudan geçemez; aynı şehirdeki Ankara Ofisi ile Ar-Ge bile birbirini göremez. İstanbul düşerse Ankara ikincil hub olur.

**Adres planı:** Her birime kendi bloğu verildi, VLAN'lar bu bloktan kesildi. Böylece VPN rotaları ve özetler temiz kalıyor ve bloklar çakışmıyor.

| Birim | Blok | Not |
|---|---|---|
| İstanbul GM | 10.10.0.0/16 | Sunucular 10.10.40.0/22, DMZ 10.10.80.0/24, yönetim 10.10.250.0/24 |
| Ankara | 10.20.0.0/16 | |
| Londra | 10.30.0.0/16 | |
| Akademik Şube | 10.40.0.0/14 | Öğrenci Wi-Fi 10.42.0.0/16, eduroam 10.43.0.0/18 |
| Yazılım | 10.50.0.0/16 | Bastion 10.50.60.0/28 |
| Ar-Ge | 10.60.0.0/16 | İzole lab 10.60.100.0/24 (hiçbir ağa rota yok) |

**Alt ağları cihaza göre boyutlandırdık, kişiye göre değil.** 10.000 öğrenci ortalama 2-3 cihaz taşıyor (telefon, dizüstü, tablet). Bu yüzden öğrenci Wi-Fi'ı bir /16 (65.534 adres): 25.000 cihaz için ~%60 boşluk bırakıyor. Bina başına /20 ayrılıyor, kablosuzda istemci izolasyonu açık. Akademik Şube bloğu da bu yüzden /14.

**Rol bazlı segmentasyon:** Her birimde aynı numaralandırma kullanılıyor (10 yönetim, 20 personel, 30 IT, 40 sunucu, 50 VoIP, 60 IoT/yazıcı, 70 misafir, 80 DMZ, 99 karantina). Birime özel ek VLAN'lar:

- **Akademik:** öğrenci Wi-Fi, akademisyen, laboratuvar, sınav, kütüphane, eduroam, kamera/IoT
- **Yazılım:** dev, devops, QA, CI/CD, staging, bastion
- **Ar-Ge:** araştırma, GPU/veri, transfer, proxy, izole laboratuvar

Kamera ödeme veya ERP sunucularını göremez, misafir iç ağı göremez, öğrenci sınav ağını göremez.

## 3. Bant genişliği

Formül her birim için aynı:

```
Ham ihtiyaç  = Σ (kullanıcı × eşzamanlılık × kişi başı ortalama Mbps)
Gerekli      = Ham × 1,3 (3 yıllık büyüme) + servis payı (sunucu, VPN hub, bulut)
Hat          = gerekliyi karşılayan bir sonraki standart kademe
Firewall     = threat protection (UTM/IPS açık) ≥ hat hızı
```

| Birim | Hesap | Gerekli | Birincil hat | Yedek hat |
|---|---|---:|---|---|
| İstanbul GM | 325 × %75 × 4 = 975 → ×1,3 + 500 | 1,77 Gbps | 2 Gbps fiber | 1 Gbps, 2. operatör |
| Ankara | 150 × %75 × 3 = 338 → ×1,3 + 50 | 489 Mbps | 500 Mbps | 200 Mbps |
| Londra | 80 × %75 × 3 = 180 → ×1,3 + 50 | 284 Mbps | 500 Mbps leased line | 200 Mbps FTTP |
| Akademik | 10.000 × %35 × 1,5 + 1.040 × %70 × 3 = 7.434 → ×1,3 + 1.000 | 10,7 Gbps | 2 × 10 Gbps aktif-aktif | (iki operatör birbirinin yedeği) |
| Yazılım | 150 × %90 × 8 = 1.080 → ×1,3 + 500 | 1,9 Gbps | 2 Gbps | 1 Gbps |
| Ar-Ge | 70 × %90 × 10 = 630 → ×1,3 + 100 | 919 Mbps | 1 Gbps | 500 Mbps |

Her sitede iki farklı operatör ve SD-WAN var. Tek ISP, tek hata noktası demektir. Ankara (%2 boşluk) ve Yazılım (%5 boşluk) sınırda kalıyor; ilk 3 ay NetFlow ile ölçülecek ve hat sürekli %80'i geçerse bir üst kademeye çıkılacak. Yazılım tarafında yerel Artifactory önbelleği tekrarlı konteyner indirmelerini azaltıyor. Akademik Şube'de bir hat koparsa QoS devreye giriyor: sunucular ve personel korunuyor, öğrenci üst limiti %60'a iniyor.

**İç dağıtım (QoS):** Ses EF, video AF41, iş kritik (ERP/LMS/sınav/Git) AF31, toplu veri (yedek) AF11, misafir/video akışı CS1. Kişi başı limitler:

| Grup | Limit |
|---|---|
| Öğrenci | 20/5 Mbps, en fazla 300 oturum |
| Akademisyen | 50 Mbps |
| İdari personel | 30 Mbps |
| Misafir | 5 Mbps |

Sınav saatlerinde sınav VLAN'ı ve LMS en yüksek önceliğe çıkıyor. Yedekleme 01:00-06:00 arasında çalışıyor.

## 4. Ürün seçimi: her parça için en iyi beş

Seçimi datasheet'in en üstündeki "firewall throughput" ile değil, **threat protection (IPS + AV + uygulama kontrolü açık)** değeriyle yaptık. Örneğin FortiGate 200G'nin firewall throughput değeri 39 Gbps, threat protection değeri ise 6 Gbps. Cisco için datasheet'te öne çıkan değer FW+AVC (IPS kapalı) olduğundan tablolarda bunu açıkça yazdık.

| Birim | Seçilen (HA çift) | TP Gbps | ≈ Fiyat | Alternatifler (neden seçilmedi) |
|---|---|---:|---:|---|
| İstanbul GM | **FortiGate 200G** | 6 | $6.9k | PA-1420 (≈2 kat fiyat, SD-WAN ek lisans), Check Point QF 9100 (pahalı), Cisco 3110 (IPS açık değer düşük, yönetim dağınık), Sophos XGS 4300 (ölçek referansı az) |
| Ankara | **FortiGate 120G** | 2,8 | $3.3k | PA-1410 (3 kat fiyat), Check Point 3920 (lisans maliyeti), Cisco 1230, Sophos XGS 118 (masaüstü, rack/çift PSU yok) |
| Londra | **FortiGate 90G** | 2,2 | $1.9k | PA-1410 (kapasite fazlası), Check Point 3920, Cisco 1220, Sophos XGS 108 (tek üretici standardından sapma) |
| Akademik | **FortiGate 900G** | 20 | $38k | PA-5410 (~5 M oturum dar, ≈2,5 kat fiyat), Check Point QF 19100 (≈3 kat), Cisco 4215 (IPS açık değer düşük, pahalı), Sophos XGS 8500 (TR referansı az) |
| Yazılım | **Palo Alto PA-3410** | 7,5 | $27k | FortiGate 200G (tek üretici olurdu), Check Point QF 9300, Cisco 3120, Sophos XGS 4300 |
| Ar-Ge | **Palo Alto PA-1420** | ~6 | $14k | FortiGate 120G (tek üretici), Check Point QF 9100, Cisco 1240 (DLP ayrı ürün), Sophos XGS 118 |

**Neden iki üretici?** Çevre ve şubelerde FortiGate kullanıyoruz: tek FortiManager ile tek ekrandan yönetim, yerleşik SD-WAN, Türkiye'de güçlü destek ve iyi fiyat/performans. Kaynak kodun ve fikri mülkiyetin bulunduğu Yazılım ve Ar-Ge birimlerinde ise bilerek Palo Alto seçtik. Bir üreticide çıkan sıfırıncı gün açığı iki katmanı birden geçemiyor (derinlemesine savunma). Palo Alto'nun App-ID özelliği "443'e izin ver" yerine "github, npm, docker-registry'ye izin ver" demeyi sağlıyor. Bunun maliyeti iki yönetim aracı ve iki eğitim seti; bu maliyeti yalnızca bu iki birimde kabul ettik.

**Ana listeye hiç girmeyenler:**
- **pfSense/OPNsense:** Lab ve küçük ofis için harika. Ancak 10.000 öğrencili kampüste SLA'lı destek, merkezi çoklu cihaz yönetimi ve ticari tehdit istihbaratı yok.
- **MikroTik:** Tam bir NGFW değil; IPS, sandbox ve SSL inceleme eksik.
- **Juniper SRX:** HPE'ye geçiş sonrası yol haritası belirsizliği var ve Türkiye'de uzman sayısı az.
- **WatchGuard/SonicWall:** Kampüs çekirdeği sınıfında zayıf; bulut yönetim servislerindeki geçmiş olaylar tedarikçi riski olarak değerlendirildi.
- **Huawei:** Londra için UK tedarik zinciri riski taşıyor.
- **Yalnızca SASE:** Kampüs içi segmentasyonu ve 5651 kapsamındaki yerel log yükümlülüğünü tek başına karşılamıyor.

Bütün siteler **active-passive HA** çifti olarak kurulu, oturum senkronizasyonu açık. Akademik Şube'de bağlantısız oturumlar da senkronize ediliyor.

## 5. Kural setleri: okuma rehberi

Her firewall'ın kuralları `company.json` içinde değerlendirme sırasıyla yazılıdır ve her kuralın `note` alanı "neden var, olmazsa ne bozulur" sorusunu cevaplar. Hepsi aynı iskeleti izler:

1. **Tehdit-IP engeli ve sahte RFC1918 kaynak engeli** en üstte. En çok eşleşen gürültü baştan düştüğü için flood altında CPU boşa harcanmıyor.
2. **DHCP 67/68, DNS 53, NTP 123** açıkça veriliyor ve yalnızca şubenin iç sunucusuna gidiyor. "Her şeyi reddet" DHCP'yi de keser. İstemcilerin doğrudan dış DNS/DoT kullanması engelleniyor, böylece DNS filtresi atlatılamıyor.
3. **IKEv2/NAT-T `limit` ile** açılıyor: brute-force ve DDoS oturum tablosunu dolduramıyor. Kamuya açık login/API uç noktalarında da `limit` var. Upstream'de ISP scrubbing (DDoS temizleme) kullanılıyor.
4. **Yönetim VLAN'ı** yalnızca MFA'lı VPN'den gelen admin grubuna ve jump host'a açık; başka her segmentten kapalı. İnternete açık SSH yok.
5. **DMZ:** İnternetten yalnızca 443 (ve rate-limit'li API portu) WAF/proxy'ye geliyor. DMZ'den içeriye tek yol var: proxy'den uygulama sunucusuna, tek host ve tek port. Gerisi reddediliyor.
6. **Segmentler arası iş kuralları** (personel → AD/ERP/dosya portları, VoIP → santral, IoT → yazdırma sunucusu). Misafir, IoT ve karantina VLAN'ları iç ağa erişemiyor.
7. **Çıkış:** SMB/RDP/SMTP dışarı kapalı (fidye yazılımı ve spam botu). Personel interneti IPS + AV + web filtre + SSL derin inceleme ile çıkıyor; bankacılık/sağlık KVKK, Londra'da UK GDPR gereği muaf. Öğrenci trafiğinde yalnızca sertifika incelemesi yapılıyor (gizlilik + performans).
8. **Açık default-deny:** En son kural portsuz, kaynaksız `deny any`. Loglanıyor. First match olduğu için her zaman en altta.

Birime özel öne çıkanlar:
- **Ankara:** Kamu/ihale iş istasyonları yalnızca EKAP, KEP ve e-imza OCSP/CRL adreslerine çıkıyor. İmza zinciri bozulmasın diye bu trafikte derin SSL inceleme yapılmıyor.
- **Londra:** M365 ve SaaS yerel olarak çıkıyor (local breakout). Kişisel veri gereksiz yere ülke dışına taşınmıyor.
- **Akademik:** Sınav VLAN'ı sınav saatlerinde yalnızca sınav sunucusunu görüyor. P2P/Tor engelli. Öğrenci-öğrenci trafiği kapalı. NAC tehdit gördüğü cihazı otomatik olarak karantinaya alıyor.
- **Yazılım:** Dev/QA/CI'dan üretime doğrudan yol yok. Üretime yalnızca bastion üzerinden (PAM + MFA + oturum kaydı) giriliyor. Kişisel bulut depolama ve tünelleme araçları engelli. Kurallar AD gruplarına (User-ID) yazılı.
- **Ar-Ge:** Doğrudan internet yok; tek çıkış izin listeli proxy (akademik yayınlar, standart kuruluşları, patent veritabanları). GPU/veri sunucuları internete kapalı. İzole laboratuvar yalnızca transfer sunucusuna SFTP ile ve dört göz onayıyla veri aktarıyor. DLP; CAD dosyası, model ağırlığı ve kaynak arşivi yüklemesini engelliyor.

## 6. Uzaktan erişim

Uzaktan erişim **MFA'lı rol tabanlı VPN** ile yapılıyor (IKEv2 istemci VPN veya ZTNA; sertifika + FortiToken/Authenticator + Active Directory grupları). Her rol yalnızca kendi segmentine ulaşıyor:

| Rol | Erişebildiği yer |
|---|---|
| net-admins | Yönetim VLAN'larındaki jump host |
| yzl-prod-yetkili | Yazılım bastion'u |
| Geliştiriciler | Git ve CI |
| Personel | ERP ve dosya sunucusu |

Bağlanmadan önce cihaz uyumluluğu (EDR, disk şifreleme) kontrol ediliyor. İnternetten SSH, RDP veya yönetim arayüzü erişimi yok.

## 7. İzleme: kim bakıyor, kim sorumlu

**Sistematik taraf:** Loglar FortiAnalyzer'a (FortiGate'ler) ve Panorama'ya (Palo Alto'lar) gidiyor, oradan **Wazuh SIEM**'e (korelasyon, MITRE ATT&CK eşlemesi) aktarılıyor. SOAR (Shuffle/TheHive) otomatik karantina yapıyor. Sağlık ve kapasite Zabbix + Grafana ile, akışlar NetFlow/IPFIX ile izleniyor.

**Uygulama ve güvenlik izlemesi ayrı:** Uptime, CPU, oturum tablosu, HA, VPN tüneli ve hat doluluğu Zabbix üzerinden NOC kuyruğuna gidiyor. IPS, botnet/C2 DNS, başarısız admin girişi, mesai dışı konfigürasyon değişikliği ve Ar-Ge/Yazılım'dan saatte 2 GB üzeri dış veri ise Wazuh üzerinden SOC kuyruğuna gidiyor. Kritik alarmlar ayrıca Telegram SOC kanalına ve nöbetçi telefonuna (PagerDuty) düşüyor.

**İnsan tarafı:**
- NOC: 6 kişi, 7/24 üç vardiya
- SOC L1: 6 kişi, 7/24 üç vardiya
- SOC L2: 3 kişi, nöbetli
- SOC L3: 2 kişi
- Firewall mühendisi: 3 kişi; kural değişikliğini yalnızca ticket + CAB onayıyla yapıyor ve 3 ayda bir kural sahipleriyle yeniden sertifikasyon yürütüyor.

Güvenlik alarmlarının sahibi **SOC Lead** (CISO'ya bağlı), erişilebilirlik alarmlarının sahibi **NOC Lead**. Hedefler: kritik alarmda ilk yanıt 15 dakika, müdahale 4 saat.

**Log saklama:**

| Log | Süre |
|---|---|
| Tüm loglar (sıcak, hızlı arama) | 90 gün |
| Akademik Şube öğrenci/misafir erişim ve DHCP kayıtları | 5651 gereği **2 yıl**, değiştirilemez arşiv, günlük hash + zaman damgası |
| Tehdit ve yönetici logları | 2 yıl |
| Londra logları | UK GDPR için ayrı ADOM'da 1 yıl |

**Yedekleme ve yama:**
- Firewall konfigürasyonları her gece şifreli olarak Git + nesne deposuna yedekleniyor; 3 ayda bir geri yükleme testi yapılıyor.
- FortiOS/PAN-OS firmware ve yamaları aylık bakım penceresinde uygulanıyor; aktif istismar edilen açıklar 72 saat içinde kapatılıyor (Fortinet PSIRT ve Palo Alto Security Advisories takibi).

**Bir gece senaryosu:** Saat 03:12'de bir öğrenci cihazı bilinen bir botnet C2 alan adını sorguluyor.
1. FortiGate DNS filtresi sorguyu engelliyor.
2. Wazuh, "10 dakika içinde aynı cihazdan 3+ C2 sorgusu" kuralıyla kritik alarm üretiyor.
3. SOAR, cihazın MAC adresini NAC üzerinden karantina VLAN'ına taşıyor ve ticket açıyor.
4. SOC L1 alarmı doğruluyor; sabah L2, yardım masası üzerinden öğrenciye ulaşıyor.
5. Cihaz temizleniyor ve karantinadan çıkarılıyor.

Tespit süresi (MTTD) 2 dakika.

## 8. CVE takibi (bonus)

- **CVE-2024-55591 — FortiOS yönetim arayüzü kimlik doğrulama atlatma** (aktif istismar edildi). Geçici önlem: yönetim arayüzü internete kapalı, yalnızca yönetim VLAN'ı + VPN; local-in policy ile kaynak IP kısıtlaması; şüpheli admin hesabı taraması. Kalıcı çözüm: düzeltilmiş FortiOS sürümüne 72 saat kuralıyla yükseltme. Bu, firewall'ın kendi açığı olduğu için başka bir firewall kuralı yetmez; yama şarttır.
- **CVE-2025-0108 — PAN-OS yönetim web arayüzü kimlik doğrulama atlatma.** Geçici önlem: yönetim arayüzü yalnızca jump host'tan erişilebilir. Kalıcı çözüm: düzeltilmiş PAN-OS sürümü, ardından Panorama'dan sürüm doğrulaması.
- **CVE-2024-3400 — PAN-OS GlobalProtect komut enjeksiyonu.** Etkilenmiyoruz: GlobalProtect açık değil, uzaktan erişim FortiGate IKEv2 + MFA ile yapılıyor. Yine de PAN-OS yamalı sürümde tutuluyor.

## 9. Mevzuat

| Düzenleme | Kapsam | Tasarıma etkisi |
|---|---|---|
| 5651 / Toplu Kullanım Sağlayıcıları Yönetmeliği | Akademik Şube ve tüm misafir ağları | Erişim ve IP dağıtım kayıtları 2 yıl saklanıyor; suç teşkil eden içeriğe karşı web filtresi uygulanıyor |
| KVKK | Türkiye birimleri | SSL incelemede sağlık/bankacılık hariç tutuluyor; loglara erişim yetkilendirmeli |
| UK GDPR | Londra | Yerel internet çıkışı, ayrı log alanı, DPO onaylı log erişimi |
| ISO/IEC 27001:2022 | Tüm şirket | Ağ ayrıştırma, izleme, değişiklik yönetimi |
