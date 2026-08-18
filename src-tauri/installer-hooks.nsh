!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /F /IM short-maker-backend.exe /T'
  Pop $0
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::Exec 'taskkill /F /IM short-maker-backend.exe /T'
  Pop $0
!macroend
