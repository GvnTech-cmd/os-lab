; Hooks for the os-lab NSIS installer, wired in through
; bundle.windows.nsis.installerHooks in tauri.conf.json.
;
; The installer records its directory as the default value of
; HKCU\Software\<publisher>\<product>, and Tauri's WiX package reads that value to reuse a previous
; NSIS install directory. Left behind after an uninstall, it points at a per-user folder that no
; longer exists, so a later all-users MSI install would land in the user's profile instead of
; Program Files. Clearing the value keeps the two installers independent.

!macro NSIS_HOOK_POSTUNINSTALL
  DeleteRegValue SHCTX "Software\${MANUFACTURER}\${PRODUCTNAME}" ""
!macroend
