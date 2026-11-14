# os-lab knowledge graph

`os-lab` is a monorepo of four reproducible, isolated operating-system security
labs on an Ubuntu Server host, plus a shared management CLI. This graph records
what each lab does and why, and links to the implementation.

This is the main project documentation; start here when changing behavior.

- [[overview]] — the shared architecture, operating model and isolation stance
- [[win-lab]] — Windows VM on `dockur/windows`
- [[android-lab]] — Android app security / RE stack
- [[ios-lab]] — iOS Simulator (macOS VM or native macOS)
- [[linux-lab]] — Linux VM on `qemux/qemu`
- [[source-lab]] — local multi-platform source/package analysis
- [[source-tests]] — retained engine contracts and distribution regressions
- [[cleanup-lab]] — disk cleanup: readiness, catalog, scan jobs, guarded cleaning
- [[labctl]] — the cross-lab management CLI
- [[setup]] — one-command installers for Linux, macOS and Windows
- [[dashboard]] — the browser console: host overview, every lab, Android workbench
- [[ux-readiness]] — readiness actions, compact advanced details, and public/local navigation
- [[content]] — signed content packs: data and hooks that update between releases
- [[legal]] — terms, acceptable use, privacy and third-party notices
- [[tooling]] — CI, tests and community process
- [[brand]] — the QS-Lab identity: marks, app icon and where they appear
