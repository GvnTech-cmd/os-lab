# PENT-23 · Windows No-Admin Lab Preflight (VT-x/Podman/VirtualBox/WSL)

| | |
|---|---|
| Öğrenci | Deniz Pekova · 2520191029 (`denizpekova`) |
| Ders | MYO062 — vize projesi |
| Görev | [PENT-23](../../../CONTRIBUTING.md) · Rezervasyon: [`reservations/PENT-23.json`](../../../reservations/PENT-23.json) |
| Kanıt videosu | https://youtu.be/O3jTPOKgfsY (2 dk 19 sn: canlı kontrol, JSON, 3 senaryo, pytest, Linux run-tests karşılaştırması) |

## 1. Amaç

Yönetici yetkisi olmayan bir Windows makinesinde lab'ın hangi modelle (Model 1 native userland,
Model 2 VirtualBox, Model 3 Podman/WSL2) çalışabileceğini **hiçbir şey değiştirmeden** tespit etmek.
Bulunan her soruna bir çözüm yazmak ve bu çözümün **admin gerektirip gerektirmediğini** belirtmek.
Böylece öğrenci, neyi kendisinin düzeltebileceğini ve neyi IT'den istemesi gerektiğini bilir.

## 2. Yapılanlar

| Dosya | Açıklama |
|---|---|
| [`android-lab/lab/scripts/win_preflight.py`](../../../android-lab/lab/scripts/win_preflight.py) | Yalnızca standart kütüphane kullanan araç: `gather_facts()` (Windows probe), `evaluate()` (saf mantık), CLI |
| [`android-lab/lab/lab.ps1`](../../../android-lab/lab/lab.ps1) | Yeni komut: `.\lab.ps1 win-preflight [-Json]` (UTF-8 BOM korundu, PS 5.1'de parse hatası yok) |
| [`android-lab/lab/tests/test_win_preflight.py`](../../../android-lab/lab/tests/test_win_preflight.py) | 47 test: senaryo golden testleri, parser'lar, CLI çıkış kodları, güvenli program yolu, kod incelemesi bulguları, canlı Windows probe |
| [`android-lab/lab/tests/fixtures/win_preflight/`](../../../android-lab/lab/tests/fixtures/win_preflight/) | Sorun senaryolarını yeniden üreten 6 adet host-facts dosyası |
| [`android-lab/lab/README-WINDOWS.md`](../../../android-lab/lab/README-WINDOWS.md), [`lat.md/android-lab.md`](../../../lat.md/android-lab.md) | Dokümantasyon |

### Kontroller

| Kontrol | Nasıl okunuyor (yetki gerekmez) | Örnek bulgu → çözüm |
|---|---|---|
| `vtx` | `Win32_Processor`, `Win32_ComputerSystem.HypervisorPresent` | BIOS'ta kapalı → firmware'den aç **[admin/IT]**; o zamana kadar Model 1 |
| `virtualbox` | `VBoxManage --version` | Hyper-V açık → NEM modu (yavaş, nested VT-x yok) → Podman/WSL2 tercih et; < 6.1.16 → güncelle |
| `wsl` | `wsl -l -v` (UTF-16 çıktı çözülüyor) | Kurulu değil → `wsl --install` **[admin/IT]**; yalnızca WSL1 → `wsl --set-version <distro> 2` |
| `podman` | `podman machine list --format json` | Makine yok → `podman machine init`; durmuş → `podman machine start` |
| `execution_policy` | `Get-ExecutionPolicy -List` (Process kapsamı hariç) | Restricted → `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (admin gerekmez) |
| `ram` / `disk` / `python` | CIM, boş alan, yorumlayıcı | < 8 GB RAM, < 20 GB disk, < Python 3.11 |

Çıktının sonunda modellerin durumu (`ready` / `degraded` / `needs-setup` / `unavailable`),
önerilen model ve "IT/admin gerektiren düzeltmeler" listesi yer alır. Çıkış kodu, FAIL varsa 1 olur
(`--strict` verilirse WARN durumunda da 1 olur).

### Tasarım kararları

- **Probe ile değerlendirme ayrı.** `--save-facts` makinenin durumunu JSON olarak kaydeder,
  `--facts` ise bu dosyayı başka bir makinede değerlendirir. Böylece Windows'a özgü durumlar
  Linux CI'da da test edilebilir.
- **Güvenli program yolu.** `powershell.exe` ve `wsl.exe` her zaman `%SystemRoot%\System32` içinden çağrılır; `podman` / `VBoxManage` için PATH'te bulunan dosya mevcut klasörde ya da lab klasöründeyse reddedilir (oraya bırakılmış sahte bir `.exe` çalıştırılamaz). Komutlar liste olarak, shell olmadan ve yalnızca sabit argümanlarla çalışır.
- **Salt okunur.** Araç hiçbir ayarı değiştirmez. CIM sorgusu yalnızca kendi alt sürecinde
  `-ExecutionPolicy Bypass` ile çalışır.
- **Kanıta dayalı.** Mümkün olduğunca makinede doğrulanan davranışa dayanır (aşağıdaki iki hata
  bu sayede bulundu).

## 3. Geliştirme sırasında bulunan gerçek sorunlar

1. **Hyper-V, VT-x bayraklarını gizliyor.** Windows 11 build 26300'de (AMD Ryzen 5 5600)
   Hyper-V/WSL2 açıkken `VMMonitorModeExtensions=False` ve `SLAT=False` dönüyor.
   Bu değerlere bakan basit bir kontrol "CPU VT-x desteklemiyor" der ve yanılır. Bu yüzden
   `HypervisorPresent` değeri önce okunuyor. Durum, `ready_podman` fixture'ı ve
   `test_hypervisor_hides_vtx_flags_but_counts_as_enabled` testiyle sabitlendi.
2. **Yürütme ilkesi yanlış okunuyordu.** İlk sürüm `Get-ExecutionPolicy` kullanıyordu ve sonuç
   her zaman "Bypass" çıkıyordu, çünkü probe'un kendisi `-ExecutionPolicy Bypass` ile çalışıyor.
   Düzeltmeden sonra kapsam listesinden Process hariç tutuluyor. Hiçbir kapsam tanımlı değilse
   Windows istemci varsayılanı olan Restricted kabul ediliyor. Bu makinede doğru değer okundu:
   CurrentUser = `RemoteSigned`.
3. **`-Json` çıktısı pipeline'a ulaşmıyordu.** Demo videosunu kaydederken fark edildi:
   `.\lab.ps1 win-preflight -Json | ConvertFrom-Json` çalışmıyordu, çünkü çıktı `Out-Host`'a
   gidiyordu. Artık çıktı pipeline'a akıyor ve çıkış kodu (`1` = FAIL) `exit` ile korunuyor.

## 4. Senaryolar (fixtures)

| Senaryo | Genel | Önerilen model | Admin gereken |
|---|---|---|---|
| `ready_podman` | OK | Model 3: Podman/WSL2 | — |
| `vtx_disabled_bios` | FAIL | Model 1 | `vtx` |
| `hyperv_blocks_virtualbox` | WARN | Model 1 (VirtualBox `degraded`) | — |
| `wsl_missing_needs_admin` | WARN | Model 1 | `wsl` |
| `podman_machine_stopped` | WARN | Model 1 | — |
| `execution_policy_restricted` | WARN | Model 1 | — |

Not: `execution_policy_restricted` senaryosu, bu makinede `.\lab.ps1` çalıştırılırken alınan
"running scripts is disabled" hatasından alındı. Diğer senaryolar, 26.10 dersinde anlatılan sorun
sınıflarına (BIOS'ta kapalı VT-x, Hyper-V ile VirtualBox çakışması, admin gerektiren WSL kurulumu,
Podman makinesi) göre hazırlandı. Bunlar o derste kaydedilmiş birebir makine dökümleri değildir.

## 5. Doğrulama

```powershell
cd android-lab\lab
.\lab.ps1 win-preflight            # insan okunur rapor
.\lab.ps1 win-preflight -Json      # JSON rapor
python scripts\win_preflight.py --facts tests\fixtures\win_preflight\vtx_disabled_bios.json   # çıkış kodu 1
python -m pytest tests\test_win_preflight.py -q
```

Bu makinedeki gerçek çıktı (Windows 11 Pro 26300, standart kullanıcı):

```
=== Windows No-Admin Lab Preflight (PENT-23) ===
  [OK]   platform          Microsoft Windows 11 Pro (build 26300), AMD64
  [OK]   privilege         Standard user (non-admin) confirmed.
  [OK]   vtx               Hardware virtualization is on and owned by the Windows hypervisor (Hyper-V / WSL2 / VBS).
  [INFO] virtualbox        VirtualBox not installed (Model 2 unavailable).
  [OK]   wsl               WSL2 ready: docker-desktop (Stopped)
  [INFO] podman            Podman not installed (Model 3 unavailable).
  [OK]   execution_policy  Execution policy 'RemoteSigned' allows lab.ps1.
  [OK]   ram               15.9 GB RAM (recommended 16 GB).
  [OK]   disk              546.4 GB free.
  [OK]   python            Python 3.15.0.
Recommended: Model 1: native userland
Overall: OK
```

### Test sonuçları

- `tests/test_win_preflight.py`: **47 passed** (Windows), 45 passed + 2 skipped (Linux; yalnızca Windows'ta çalışan canlı probe ve NTFS stream testleri atlanır).
- `android-lab/lab` test paketinin tamamı Windows'ta: değişiklikten önce 152 passed / 6 failed,
  değişiklikten sonra **176 passed** / aynı 6 failed. Düşen 6 test (`test_oslab_console`,
  `test_cleanup_console`, `test_web_ui`) bu değişiklikten önce de düşüyordu ve Windows hostuna
  özgü. Bu PR yeni bir hataya yol açmıyor.
- `./scripts/run-tests.sh` Linux'ta (Docker `python:3.12-bookworm`, repo salt okunur bağlanıp
  kopyalandı) bu dalda ve temiz `master` (`90f571f`) üzerinde çalıştırıldı:

  | Aşama | Bu dal (PENT-23) | Temiz master |
  |---|---|---|
  | android-lab/lab (pytest) | **213 passed**, 1 failed | 168 passed, 1 failed |
  | source-lab/engine | ok (176 passed) | ok |
  | cleanup-lab/reference/python | ok | ok |
  | cleanup-lab/engine | 2 failed | 2 failed (root olmayan kullanıcıyla: 1) |
  | sample analysis smoke | ok | ok |
  | shell syntax (bash -n) | ok (71 script) | ok |
  | lat / dashboard / cargo | skip (araç kurulu değil) | skip |

  Düşen testler (`test_web_ui::test_lab_start_requires_a_previewed_plan`,
  `cleanup-lab/engine` içindeki `test_refusal_codes_are_stable` ve `test_unusable_trash_needs_setup`)
  **temiz master'da da aynı şekilde düşüyor**. Bunlar PENT-23 kapsamı dışında, bu yüzden bu PR'da
  düzeltilmedi (AGENTS.md: her PR tek bir mantıksal değişiklik). Bu PR yeni bir hataya yol açmıyor;
  45 yeni test geçiyor (yalnızca Windows'ta çalışan 2 test Linux'ta skip ediliyor).

## 6. Kod incelemesi (Sourcery) sonrası düzeltmeler

PR'daki otomatik inceleme 16 bulgu bildirdi. Her biri koda karşı tek tek kontrol edildi.

**Düzeltilenler:**
- Önerilen model artık RAM, disk, mimari (ARM64) ve Python koşullarını da sağlamak zorunda.
- Zaman aşımına uğrayan ya da hata veren WSL / Podman / VirtualBox probe'u "kurulu değil" sayılmıyor, hata olarak raporlanıyor (model durumu `unknown`).
- Group Policy (MachinePolicy / UserPolicy) ile zorlanan yürütme ilkesi için IT'ye yönlendiriliyor, çünkü bu durumda kullanıcı ayarı işe yaramaz.
- İnternetten indirilmiş (Mark-of-the-Web) `lab.ps1` RemoteSigned altında engelleniyor; bu durumda `Unblock-File` öneriliyor.
- `[admin]` etiketi artık her adım için ayrı: geçici çözümler yanlışlıkla "admin" görünmüyor.
- VM diski kontrolü: VirtualBox VM'leri ve WSL imajları kullanıcı profilinin bulunduğu sürücüde, bu sürücü ayrıca kontrol ediliyor.
- `--save-facts` dosyayı atomik yazıyor (geçici dosya + `os.replace`).
- Hyper-V'yi kapatma önerisi açıkça "SECURITY DOWNGRADE" olarak etiketlendi (VBS/HVCI korumasını kaldırır).
- WSL dağıtım adları PowerShell için tırnaklanıyor; rapor çıktısında kontrol karakterleri ve ANSI kodları temizleniyor.
- VirtualBox varsayılan klasör dışındaysa (lab.ps1 onu bulamaz) "hazır" sayılmıyor.
- Restricted ilke için önerilen tek seferlik komut artık `win-preflight` çalıştırıyor.

**Kanıtla yanlış olduğu gösterilenler:**
- "`exit` PowerShell oturumunu kapatıyor": `.\lab.ps1` ile çağrılan script'teki `exit` yalnızca script'i bitirir. PowerShell 5.1.26100'de denendi, oturum açık kaldı ve `$LASTEXITCODE=1` döndü.
- "PS 5.1'de `-Json | ConvertFrom-Json` bozuluyor": PowerShell 5.1.26100'de çalıştırıldı ve sorunsuz ayrıştırıldı.
- "subprocess komut enjeksiyonu": Komutlar liste olarak, shell olmadan ve sabit argümanlarla çalışıyor. Satır `nosemgrep` ile gerekçesiyle işaretlendi.
- "`admin_only_fixes` INFO maddelerini içermiyor": Bu bilinçli bir tercih. Liste yalnızca sorunları (WARN/FAIL) içeriyor, isteğe bağlı INFO maddelerinin adımları yine kendi `[admin]` etiketini taşıyor.

## 7. Yapay zekâ kullanımı

Bu çalışmada kodun, testlerin ve bu raporun taslağı Claude Code (Anthropic) ile birlikte yazıldı.
Tüm çıktılar bu makinede çalıştırılarak doğrulandı. Hyper-V bayrak davranışı ve yürütme ilkesi
hatası bu doğrulama sırasında bulunup düzeltildi.
