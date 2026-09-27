!include "nsDialogs.nsh"

!macro customInit
  StrCpy $SkillTreeDesktopSelection ${BST_CHECKED}
!macroend

!macro customPageAfterChangeDir
  Var SkillTreeDesktopCheckbox
  Var SkillTreeDesktopSelection
  Page custom SkillTreeShortcutPageCreate SkillTreeShortcutPageLeave

  Function SkillTreeShortcutPageCreate
    ${If} ${isUpdated}
      Abort
    ${EndIf}

    nsDialogs::Create 1018
    Pop $0
    ${If} $0 == error
      Abort
    ${EndIf}

    !insertmacro MUI_HEADER_TEXT "Shortcuts" "Choose where Skill Tree is easy to open."
    ${NSD_CreateLabel} 0u 0u 100% 20u "Skill Tree will be added to the Start menu."
    Pop $0
    ${NSD_CreateCheckbox} 0u 32u 100% 12u "Add a desktop shortcut"
    Pop $SkillTreeDesktopCheckbox
    ${NSD_SetState} $SkillTreeDesktopCheckbox ${BST_CHECKED}
    nsDialogs::Show
  FunctionEnd

  Function SkillTreeShortcutPageLeave
    ${NSD_GetState} $SkillTreeDesktopCheckbox $SkillTreeDesktopSelection
  FunctionEnd
!macroend

!macro customInstall
  ; electron-builder creates the shortcut during installation. If the user
  ; opted out, remove it before the Finish page and let its normal uninstaller
  ; continue to own shortcut cleanup on later installs.
  ${IfNot} ${isUpdated}
  ${AndIfNot} ${Silent}
  ${AndIf} $SkillTreeDesktopSelection == ${BST_UNCHECKED}
    WinShell::UninstShortcut "$newDesktopLink"
    Delete "$newDesktopLink"
    System::Call 'Shell32::SHChangeNotify(i 0x8000000, i 0, i 0, i 0)'
  ${EndIf}
!macroend

!macro customFinishPage
  !ifndef HIDE_RUN_AFTER_FINISH
    Function StartApp
      ${If} ${isUpdated}
        StrCpy $1 "--updated"
      ${Else}
        StrCpy $1 ""
      ${EndIf}
      ; Launch the installed executable directly. The default electron-builder
      ; finish action launches its Start menu .lnk, which failed on Windows even
      ; though the shortcut and executable were present.
      ${StdUtils.ExecShellAsUser} $0 "$appExe" "open" "$1"
    FunctionEnd

    !define MUI_FINISHPAGE_RUN
    !define MUI_FINISHPAGE_RUN_FUNCTION "StartApp"
  !endif
  !insertmacro MUI_PAGE_FINISH
!macroend
