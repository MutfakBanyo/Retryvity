-- Corona Doctor MAXScript bridge.
--
-- This file must stay small and auditable. Every helper documents why
-- pymxs alone was insufficient, which Max versions it targets, what it
-- returns, and whether it mutates scene state. Do not add helpers here
-- unless there is a demonstrated pymxs limitation; see
-- docs/ARCHITECTURE.md, "MAXScript bridge".

-- launchCoronaDoctor()
--   Why pymxs was insufficient: none — this helper exists only as a
--   convenience entry point for a MAXScript macroScript button, which
--   cannot call into Python directly without a small MAXScript shim.
--   Targets: 3ds Max 2026.2+ (Python 3.11 bundled runtime).
--   Returns: nothing.
--   Mutates scene state: no.
function launchCoronaDoctor = (
    python.Execute "from corona_doctor.bootstrap import show_corona_doctor; show_corona_doctor()"
)

-- launchCoronaDoctorAbout()
--   Same rationale as launchCoronaDoctor(): a MAXScript shim for the
--   "About Corona Doctor" menu command.
--   Targets: 3ds Max 2026.2+.
--   Returns: nothing.
--   Mutates scene state: no.
function launchCoronaDoctorAbout = (
    python.Execute "from corona_doctor.bootstrap import show_corona_doctor_about; show_corona_doctor_about()"
)

macroScript CoronaDoctor_Launch
category:"Corona Doctor"
buttonText:"Open Corona Doctor"
tooltip:"Open Corona Doctor"
(
    on execute do launchCoronaDoctor()
)

macroScript CoronaDoctor_About
category:"Corona Doctor"
buttonText:"About Corona Doctor"
tooltip:"About Corona Doctor"
(
    on execute do launchCoronaDoctorAbout()
)

-- registerCoronaDoctorMenu()
--   Why: 3ds Max 2025 removed the legacy MAXScript Menu Manager
--   (`menuMan`/`menuMan.getMainMenuBar()`) entirely — see
--   https://help.autodesk.com/cloudhelp/2025/ENU/MAXScript-Help/files/MAXScript-Tools-and-Interaction/Interacting-with-the-3ds-Max/GUID-FF48D0EC-6669-4EC7-AB43-E9998A14A198.html
--   ("The old menu system is gone, and the Maxscript Menu Manager
--   interface (MenuMan) is gone.") and
--   https://www.scriptspot.com/forums/3ds-max/general-scripting/menuman-in-3ds-max-2025 .
--   Calling `menuMan.getMainMenuBar()` on 3ds Max 2026.2 raises
--   "Unknown property: getMainMenuBar in undefined" because `menuMan`'s
--   main-menu-bar concept no longer resolves under the replacement
--   Workspace/CUI-driven menu system — that call can never succeed on
--   this host, so this repair does not retry it.
--
--   The replacement is callback-driven, not a function you call
--   directly: register a handler for the `#cuiRegisterMenus` event; 3ds
--   Max invokes it with a `CuiMenuManager` (via
--   `callbacks.notificationParam()`) whenever it (re)builds the menu
--   bar. `CuiMenuManager.mainMenuBar` is a `CuiMenu`, which exposes
--   `CreateSubMenu`/`CreateAction`/`CreateSeparator` for building menu
--   content. There is no documented way to force an immediate rebuild
--   mid-session, so a menu registered THIS session will not become
--   visible until the next 3ds Max startup — that is expected, not a
--   bug (see the callback-registration call below, which runs every
--   session so the menu appears from the following restart onward).
--
--   Targets: 3ds Max 2025+ (the `#cuiRegisterMenus` callback this relies
--   on does not exist on older hosts).
--   Idempotent: `callbacks.removeScripts id:#coronaDoctorMenu` clears
--   any prior registration under our id before re-adding it, so calling
--   this every startup/every install-script run never stacks duplicate
--   callback registrations (which would otherwise build the menu twice
--   the next time #cuiRegisterMenus fires).
--   Mutates scene state: no (UI-only).
--   Failure handling: every failure here is caught and logged via
--   `format ... \n` (prints to the MAXScript listener only — never a
--   messageBox, never blocks Corona Doctor opening) so an unsupported
--   host gets one quiet log line instead of a startup exception. See
--   docs/ARCHITECTURE.md, "Menu registration failure is non-fatal".
function registerCoronaDoctorMenu = (
    -- Fixed, never-regenerated ids: CreateSubMenu/CreateAction identify
    -- menu content by these ids, so they must stay stable across
    -- sessions/versions to avoid the menu system treating a re-run as a
    -- different, additional menu.
    local menuId = "8F3E2A10-4B7C-4D2E-9A1F-6C5D8E9B0A1D"
    local openActionId = "8F3E2A11-4B7C-4D2E-9A1F-6C5D8E9B0A1D"
    local aboutActionId = "8F3E2A12-4B7C-4D2E-9A1F-6C5D8E9B0A1D"

    fn coronaDoctorMenuCallback = (
        try (
            local menuMgr = callbacks.notificationParam()
            local mainMenuBar = menuMgr.mainMenuBar
            local cdMenu = mainMenuBar.CreateSubMenu menuId "Corona Doctor"
            -- 647394 is the macroScript action-table id; "Name`Category"
            -- addresses one macroScript's action within it — see the
            -- ScriptSpot thread linked above for this exact pattern.
            cdMenu.CreateAction openActionId 647394 "CoronaDoctor_Launch`Corona Doctor"
            cdMenu.CreateAction aboutActionId 647394 "CoronaDoctor_About`Corona Doctor"
        ) catch (
            format "Corona Doctor: menu registration skipped (%)\n" (getCurrentException())
        )
    )

    try (
        callbacks.removeScripts id:#coronaDoctorMenu
        callbacks.addScript #cuiRegisterMenus coronaDoctorMenuCallback id:#coronaDoctorMenu
    ) catch (
        format "Corona Doctor: menu callback registration unsupported on this host (%)\n" (getCurrentException())
    )
)

-- coronaDoctorSafeRegisterMenu()
--   Thin try/catch wrapper around registerCoronaDoctorMenu() with a
--   single-line, no-argument body — this exact shape (no embedded `%`
--   placeholders) is what lets install_corona_doctor.ms write a call to
--   it into the auto-generated startup script via a plain `format
--   "...\n" to:f` with no substitution arguments, without needing to
--   escape a nested format-with-arguments call inside generated text.
function coronaDoctorSafeRegisterMenu = (
    try ( registerCoronaDoctorMenu() ) catch ( format "Corona Doctor: menu registration skipped\n" )
)
