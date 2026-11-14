// The launcher: ask the native side to start the os-lab console, then hand the window to the
// dashboard it serves. Plain JS on purpose — no build step, nothing to bundle.
(function () {
  "use strict";
  var invoke = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
  var $ = function (id) { return document.getElementById(id); };
  var statusEl = $("status"), spinner = $("spinner"), problem = $("problem");
  var detail = $("detail"), where = $("where"), filesWhere = $("files-where"), resetBtn = $("reset"), pythonBtn = $("python");
  var containerBtn = $("container"), recoverBtn = $("recover"), continueBtn = $("continue"), consoleInfo = null;
  var dontShowRow = $("dont-show-row"), dontShow = $("dont-show");
  var warningHidden = false, skipContainerWarning = false;
  var language = (navigator.languages || [navigator.language || "en"])
    .map(function (value) { return value.toLowerCase().split("-")[0]; })
    .find(function (value) { return ["en", "tr", "de", "fr", "es", "it", "fa", "ar"].indexOf(value) !== -1; }) || "en";
  document.documentElement.lang = language;
  document.documentElement.dir = language === "fa" || language === "ar" ? "rtl" : "ltr";
  var strings = {
    en: { starting: "Starting the console…", opening: "Opening the dashboard…", failed: "The os-lab console could not start.", bridge: "The Tauri bridge is missing; open this app from its window, not a browser.", retry: "Retry", choose: "Use my os-lab checkout…", reset: "Use bundled copy", files: "Change files folder…", filesLabel: "Files folder" },
    tr: { starting: "Konsol başlatılıyor…", opening: "Pano açılıyor…", failed: "os-lab konsolu başlatılamadı.", bridge: "Tauri bağlantısı bulunamadı; bu uygulamayı tarayıcı yerine kendi penceresinde açın.", retry: "Yeniden dene", choose: "Kendi os-lab kopyamı kullan…", reset: "Paketlenmiş kopyayı kullan" },
    de: { starting: "Konsole wird gestartet…", opening: "Dashboard wird geöffnet…", failed: "Die os-lab-Konsole konnte nicht gestartet werden.", bridge: "Die Tauri-Verbindung fehlt. Öffne diese App im eigenen Fenster, nicht im Browser.", retry: "Erneut versuchen", choose: "Meine os-lab-Arbeitskopie verwenden…", reset: "Mitgelieferte Kopie verwenden" },
    fr: { starting: "Démarrage de la console…", opening: "Ouverture du tableau de bord…", failed: "La console os-lab n’a pas pu démarrer.", bridge: "La connexion Tauri est absente. Ouvrez cette application dans sa fenêtre, et non dans un navigateur.", retry: "Réessayer", choose: "Utiliser ma copie de travail os-lab…", reset: "Utiliser la copie intégrée" },
    es: { starting: "Iniciando la consola…", opening: "Abriendo el panel…", failed: "No se pudo iniciar la consola de os-lab.", bridge: "Falta la conexión de Tauri. Abre esta aplicación en su propia ventana, no en un navegador.", retry: "Reintentar", choose: "Usar mi copia de trabajo de os-lab…", reset: "Usar la copia incluida" },
    it: { starting: "Avvio della console…", opening: "Apertura della dashboard…", failed: "Impossibile avviare la console os-lab.", bridge: "Manca la connessione Tauri. Apri questa app nella sua finestra, non in un browser.", retry: "Riprova", choose: "Usa la mia copia di lavoro di os-lab…", reset: "Usa la copia inclusa" },
    fa: { starting: "کنسول در حال راه‌اندازی است…", opening: "داشبورد در حال باز شدن است…", failed: "کنسول os-lab راه‌اندازی نشد.", bridge: "اتصال Tauri موجود نیست؛ این برنامه را در پنجره خودش باز کنید، نه در مرورگر.", retry: "تلاش دوباره", choose: "استفاده از نسخه کاری os-lab من…", reset: "استفاده از نسخه همراه برنامه" },
    ar: { starting: "جارٍ تشغيل وحدة التحكم…", opening: "جارٍ فتح لوحة المعلومات…", failed: "تعذّر تشغيل وحدة تحكم os-lab.", bridge: "اتصال Tauri غير موجود؛ افتح هذا التطبيق في نافذته الخاصة، وليس في المتصفح.", retry: "إعادة المحاولة", choose: "استخدام نسخة العمل الخاصة بي من os-lab…", reset: "استخدام النسخة المضمّنة" }
  };
  var t = strings[language] || strings.en;
  if (!t.files) { t.files = strings.en.files; t.filesLabel = strings.en.filesLabel; }
  var pythonStrings = {
    en: ["Get Python", "Getting Python for os-lab…"],
    tr: ["Python'u edin", "os-lab için Python indiriliyor…"],
    de: ["Python laden", "Python für os-lab wird geladen…"],
    fr: ["Obtenir Python", "Téléchargement de Python pour os-lab…"],
    es: ["Obtener Python", "Descargando Python para os-lab…"],
    it: ["Scarica Python", "Download di Python per os-lab…"],
    fa: ["دریافت پایتون", "پایتون برای os-lab دریافت می‌شود…"],
    ar: ["الحصول على Python", "جارٍ تنزيل Python لـ os-lab…"]
  };
  var pt = pythonStrings[language] || pythonStrings.en;
  var containerStrings = {
    en: ["Get container runtime", "Continue to dashboard", "A container runtime is needed for the VM and Android labs. Get the verified Docker Desktop installer, complete its setup, then retry. Host virtualization may need enabling.", "Downloading Docker Desktop…", "Docker Desktop installer opened. Complete its setup, then retry.", "Don't show this warning next time"],
    tr: ["Konteyner çalışma ortamını edin", "Panoya devam et", "VM ve Android laboratuvarları için bir konteyner çalışma ortamı gerekir. Doğrulanmış Docker Desktop yükleyicisini edinip kurulumu tamamlayın, ardından yeniden deneyin.", "Docker Desktop indiriliyor…", "Docker Desktop yükleyicisi açıldı. Kurulumu tamamlayıp yeniden deneyin.", "Bu uyarıyı bir daha gösterme"],
    de: ["Container-Laufzeit laden", "Zum Dashboard", "Für VM- und Android-Labs wird eine Container-Laufzeit benötigt. Laden Sie den geprüften Docker-Desktop-Installer, schließen Sie die Einrichtung ab und versuchen Sie es erneut.", "Docker Desktop wird geladen…", "Docker-Desktop-Installer geöffnet. Schließen Sie die Einrichtung ab und versuchen Sie es erneut.", "Diese Warnung nicht mehr anzeigen"],
    fr: ["Obtenir le moteur de conteneurs", "Continuer vers le tableau de bord", "Les labs VM et Android nécessitent un moteur de conteneurs. Obtenez l’installateur Docker Desktop vérifié, terminez l’installation, puis réessayez.", "Téléchargement de Docker Desktop…", "Installateur Docker Desktop ouvert. Terminez l’installation, puis réessayez.", "Ne plus afficher cet avertissement"],
    es: ["Obtener motor de contenedores", "Continuar al panel", "Los laboratorios de VM y Android necesitan un motor de contenedores. Obtén el instalador verificado de Docker Desktop, completa la instalación y reintenta.", "Descargando Docker Desktop…", "Se abrió el instalador de Docker Desktop. Completa la instalación y reintenta.", "No volver a mostrar este aviso"],
    it: ["Scarica il runtime container", "Continua alla dashboard", "I lab VM e Android richiedono un runtime container. Scarica il programma di installazione verificato di Docker Desktop, completa l'installazione e riprova.", "Download di Docker Desktop…", "Installer di Docker Desktop aperto. Completa l'installazione e riprova.", "Non mostrare più questo avviso"],
    fa: ["دریافت محیط کانتینر", "ادامه به داشبورد", "آزمایشگاه‌های VM و Android به محیط کانتینر نیاز دارند. نصب‌کنندهٔ تأییدشدهٔ Docker Desktop را دریافت و نصب کنید، سپس دوباره تلاش کنید.", "Docker Desktop در حال دریافت است…", "نصب‌کنندهٔ Docker Desktop باز شد. نصب را کامل کنید و دوباره تلاش کنید.", "این هشدار را دیگر نشان نده"],
    ar: ["الحصول على بيئة الحاويات", "المتابعة إلى لوحة المعلومات", "تحتاج مختبرات VM وAndroid إلى بيئة حاويات. احصل على مُثبّت Docker Desktop المتحقق منه وأكمل الإعداد ثم أعد المحاولة.", "جارٍ تنزيل Docker Desktop…", "فُتح مُثبّت Docker Desktop. أكمل الإعداد ثم أعد المحاولة.", "عدم إظهار هذا التحذير مرة أخرى"]
  };
  var ct = containerStrings[language] || containerStrings.en;
  var existingEngine = {
    en: "Docker or Podman is installed, but its engine or Compose command is unavailable. Start or reconnect your engine (for example Colima or a Podman machine), check that `docker compose version` or `podman compose version` works, then retry. You can continue to labs that do not need containers.",
    tr: "Docker veya Podman kurulu, ancak motoru ya da Compose komutu kullanılamıyor. Motorunuzu (örneğin Colima veya Podman makinesi) başlatıp bağlayın, `docker compose version` veya `podman compose version` komutunu kontrol edin ve yeniden deneyin. Konteyner gerektirmeyen laboratuvarlara devam edebilirsiniz."
  };
  var recoverText = {
    en: ["Start installed engine", "Starting the installed container engine…"],
    tr: ["Kurulu motoru başlat", "Kurulu konteyner motoru başlatılıyor…"]
  }[language] || ["Start installed engine", "Starting the installed container engine…"];
  var dockerInstallText = { en: "Get Docker Desktop", tr: "Docker Desktop'u edin" }[language] || "Get Docker Desktop";
  var containerHeading = { en: "Container runtime needs attention", tr: "Konteyner çalışma zamanı için işlem gerekiyor" }[language] || "Container runtime needs attention";
  $("retry").textContent = t.retry;
  $("choose").textContent = t.choose;
  resetBtn.textContent = t.reset;
  $("files").textContent = t.files;
  pythonBtn.textContent = pt[0];
  containerBtn.textContent = dockerInstallText;
  recoverBtn.textContent = recoverText[0];
  continueBtn.textContent = ct[1];
  $("dont-show-label").textContent = ct[5];

  function show(message, isError) {
    statusEl.textContent = message;
    spinner.hidden = !!isError;
    problem.hidden = !isError;
    dontShowRow.hidden = true;
  }

  function fail(err) {
    show(t.failed, true);
    var message = String(err && err.message ? err.message : err);
    pythonBtn.hidden = message.indexOf("Python 3.11 or newer was not found") === -1;
    containerBtn.hidden = true;
    recoverBtn.hidden = true;
    continueBtn.hidden = !consoleInfo;
    detail.textContent = message;
    if (invoke) invoke("console_logs").then(function (log) {
      if (log) detail.textContent += "\n\n— console.log —\n" + log;
    }, function () {});
  }

  function openDashboard() {
    if (!consoleInfo) return;
    show(t.opening, false);
    window.location.replace(consoleInfo.url + (language === "en" ? "" : language + "/"));
  }

  function showContainerSetup(message, canDownload, canRecover) {
    show(t.starting, true);
    statusEl.textContent = containerHeading;
    detail.textContent = message;
    pythonBtn.hidden = true;
    containerBtn.hidden = !canDownload;
    recoverBtn.hidden = !canRecover;
    continueBtn.hidden = false;
    dontShowRow.hidden = false;
    dontShow.checked = warningHidden;
  }

  function start() {
    consoleInfo = null;
    show(t.starting, false);
    if (!invoke) { return fail(t.bridge); }
    var skipWarning = skipContainerWarning;
    skipContainerWarning = false;
    invoke("console_files_dir").then(function (path) { filesWhere.textContent = t.filesLabel + ": " + path; }, fail);
    invoke("console_start").then(function (info) {
      consoleInfo = info;
      where.textContent = info.source + ": " + info.root;
      resetBtn.hidden = info.source !== "chosen";
      invoke("container_status").then(function (status) {
        if (status && !status.ready && !skipWarning) showContainerSetup(status.detail || (status.cli_present ? (existingEngine[language] || existingEngine.en) : ct[2]), status.can_download, Boolean(status.recovery));
        else openDashboard();
      }, openDashboard);
    }, fail);
  }

  $("retry").addEventListener("click", start);
  pythonBtn.addEventListener("click", function () {
    show(pt[1], false);
    invoke("python_install").then(start, fail);
  });
  containerBtn.addEventListener("click", function () {
    show(ct[3], false);
    invoke("container_get").then(function () { showContainerSetup(ct[4], false, false); }, fail);
  });
  recoverBtn.addEventListener("click", function () {
    recoverBtn.disabled = true;
    show(recoverText[1], false);
    invoke("container_recover").then(function () { recoverBtn.disabled = false; start(); }, function (err) {
      recoverBtn.disabled = false;
      var message = String(err && err.message ? err.message : err);
      invoke("container_status").then(function (status) {
        showContainerSetup(message, status.can_download, Boolean(status.recovery));
      }, function () { showContainerSetup(message, false, false); });
    });
  });
  continueBtn.addEventListener("click", openDashboard);
  dontShow.addEventListener("change", function () {
    var hidden = dontShow.checked;
    warningHidden = hidden;
    invoke("container_warning_set_hidden", { hidden: hidden }).then(function () {}, function (err) {
      warningHidden = !hidden;
      dontShow.checked = !hidden;
      detail.textContent = String(err && err.message ? err.message : err);
    });
  });
  $("choose").addEventListener("click", function () {
    invoke("console_choose_root").then(function (path) { if (path) start(); }, fail);
  });
  resetBtn.addEventListener("click", function () {
    invoke("console_reset_root").then(start, fail);
  });
  $("files").addEventListener("click", function () {
    var button = $("files");
    button.disabled = true;
    invoke("console_choose_files_dir").then(function (path) {
      button.disabled = false;
      if (path) start();
    }, function (err) { button.disabled = false; fail(err); });
  });
  function checkAppUpdate() {
    var panel = $("app-update"), check = $("app-update-check"), install = $("app-update-install"), download = $("app-update-download"), message = $("app-update-detail");
    panel.hidden = false;
    problem.hidden = true;
    spinner.hidden = false;
    statusEl.textContent = language === "tr" ? "Uygulama güncellemeleri kontrol ediliyor…" : "Checking for app updates…";
    message.textContent = "";
    check.disabled = true;
    install.hidden = true;
    download.hidden = true;
    if (!invoke) { fail(t.bridge); return; }
    invoke("app_update_check").then(function (offer) {
      spinner.hidden = true;
      check.disabled = false;
      statusEl.textContent = language === "tr" ? "Uygulama güncellemeleri" : "App updates";
      if (offer) {
        message.textContent = (language === "tr" ? "Yeni sürüm hazır: " : "New version available: ") + offer.version;
        install.hidden = !offer.installable;
        download.hidden = !!offer.installable;
        download.dataset.version = offer.version;
      } else {
        message.textContent = language === "tr" ? "os-lab güncel." : "os-lab is up to date.";
      }
    }, function (err) {
      spinner.hidden = true;
      check.disabled = false;
      statusEl.textContent = language === "tr" ? "Güncellemeler kontrol edilemedi" : "Could not check for updates";
      message.textContent = String(err && err.message ? err.message : err);
    });
  }
  $("app-update-check").addEventListener("click", checkAppUpdate);
  $("app-update-download").addEventListener("click", function () {
    var version = $("app-update-download").dataset.version;
    if (version) window.location.href = "https://github.com/keyvanarasteh/os-lab/releases/tag/app-v" + encodeURIComponent(version);
  });
  $("app-update-install").addEventListener("click", function () {
    var button = $("app-update-install"), message = $("app-update-detail"), downloaded = 0;
    button.disabled = true;
    spinner.hidden = false;
    message.textContent = language === "tr" ? "Güncelleme indiriliyor ve kuruluyor…" : "Downloading and installing the update…";
    if (window.__TAURI__ && window.__TAURI__.event) {
      window.__TAURI__.event.listen("app-update-progress", function (event) {
        downloaded += event.payload.chunk || 0;
        if (event.payload.total) {
          message.textContent = Math.min(100, Math.floor(downloaded * 100 / event.payload.total)) + "%";
        }
      }).then(function (unlisten) {
        invoke("app_update_install").then(function () { unlisten(); }, function (err) {
          unlisten(); button.disabled = false; spinner.hidden = true;
          message.textContent = String(err && err.message ? err.message : err);
        });
      }, function (err) {
        button.disabled = false; spinner.hidden = true;
        message.textContent = String(err && err.message ? err.message : err);
      });
    } else {
      invoke("app_update_install").catch(function (err) {
        button.disabled = false; spinner.hidden = true;
        message.textContent = String(err && err.message ? err.message : err);
      });
    }
  });
  $("app-update-back").addEventListener("click", function () { $("app-update").hidden = true; start(); });
  var settings = new URLSearchParams(window.location.search).get("settings");
  if (settings === "updates") {
    $("app-update-back").textContent = language === "tr" ? "Panoya dön" : "Return to dashboard";
    $("app-update-check").textContent = language === "tr" ? "Yeniden kontrol et" : "Check again";
    $("app-update-install").textContent = language === "tr" ? "Uygulama güncellemesini kur" : "Install app update";
    $("app-update-download").textContent = language === "tr" ? "Uygulama sürümünü aç" : "Open app release";
    checkAppUpdate();
  } else if (settings === "files") {
    show(t.filesLabel, true);
    detail.textContent = "";
    if (invoke) invoke("console_files_dir").then(function (path) { filesWhere.textContent = t.filesLabel + ": " + path; }, fail);
    else fail(t.bridge);
  } else if (!invoke) {
    start();
  } else {
    invoke("container_warning_hidden").then(function (hidden) {
      warningHidden = !!hidden;
      dontShow.checked = warningHidden;
      if (settings !== "container") skipContainerWarning = warningHidden;
      start();
    }, start);
  }
})();
