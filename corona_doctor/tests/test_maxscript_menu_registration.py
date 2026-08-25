"""Static regression checks over the MAXScript menu-registration source.

MAXScript itself cannot run in this test suite (no 3ds Max host), so
these assert the *idempotency/safety guards themselves are present in the
source* — the same class of static check as
test_adapter_contract.py's AST-based contract tests. Real-host behavior
still needs manual verification (see docs/ARCHITECTURE.md, "3ds Max 2025+
menu system" and the milestone report's exact retest commands).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HELPERS_MS = _REPO_ROOT / "corona_doctor" / "maxscript" / "helpers.ms"
_INSTALLER_MS = _REPO_ROOT / "install_corona_doctor.ms"


def _helpers_source() -> str:
    return _HELPERS_MS.read_text(encoding="utf-8")


def _installer_source() -> str:
    return _INSTALLER_MS.read_text(encoding="utf-8")


def _code_only(source: str) -> str:
    """Strip MAXScript `-- ...` line comments so a check for "does the
    CODE call X" isn't fooled by prose that merely *mentions* X (e.g. a
    docstring explaining why a removed API is no longer called)."""

    lines = []
    for line in source.splitlines():
        idx = line.find("--")
        lines.append(line[:idx] if idx != -1 else line)
    return "\n".join(lines)


def test_helpers_ms_exists():
    assert _HELPERS_MS.is_file()


def test_installer_ms_exists():
    assert _INSTALLER_MS.is_file()


def test_menu_registration_does_not_call_the_removed_menuman_api():
    """The real-host bug: menuMan.getMainMenuBar() was removed in 3ds Max
    2025 and always raises on 2026.2 - it must not be called anywhere."""

    for source in (_helpers_source(), _installer_source()):
        code = _code_only(source).lower()
        assert "getmainmenubar" not in code
        assert "menuman" not in code


def test_menu_registration_uses_the_documented_2025plus_callback():
    source = _helpers_source()
    assert "#cuiRegisterMenus" in source
    assert "callbacks.notificationParam()" in source
    assert "mainMenuBar" in source


def test_menu_callback_registration_removes_prior_registration_before_readding():
    """Idempotency guard: calling registerCoronaDoctorMenu() twice (every
    startup, every install-script re-run) must never stack duplicate
    #cuiRegisterMenus callback registrations under our id, which would
    otherwise build the menu twice the next time it fires."""

    source = _helpers_source()
    remove_index = source.find("callbacks.removeScripts id:#coronaDoctorMenu")
    add_index = source.find("callbacks.addScript #cuiRegisterMenus")
    assert remove_index != -1, "missing callbacks.removeScripts guard"
    assert add_index != -1, "missing callbacks.addScript registration"
    assert remove_index < add_index, "removeScripts must run before addScript on every call"


def test_menu_and_action_ids_are_fixed_literals_not_regenerated():
    """CreateSubMenu/CreateAction identify content by id - a freshly
    generated id on every call would make each run add a NEW menu/action
    instead of updating the existing one, silently duplicating over time.
    Guard: the ids are hardcoded GUID-shaped string literals, not the
    output of a generator call."""

    source = _helpers_source()
    for name in ("menuId", "openActionId", "aboutActionId"):
        line = next(line for line in source.splitlines() if line.strip().startswith(f"local {name}"))
        assert '"' in line, f"{name} must be a literal string"
        # A hardcoded literal has no function-call parens on the right-hand side.
        rhs = line.split("=", 1)[1]
        assert "(" not in rhs, f"{name} looks generated, not a fixed literal: {line!r}"


def test_menu_registration_failures_are_caught_not_raised():
    """Every menuMgr/CreateSubMenu/CreateAction call and the callback
    registration itself must be wrapped in try/catch - a menu-system
    failure must never surface as an uncaught exception during startup."""

    source = _helpers_source()
    assert source.count("try (") >= 2
    assert source.count("catch (") >= 2


def test_menu_failures_are_logged_not_shown_as_messagebox():
    code = _code_only(_helpers_source())
    assert "messageBox" not in code


def test_installer_registers_menu_for_current_session_and_persists_it_for_future_startups():
    installer = _installer_source()
    assert "coronaDoctorSafeRegisterMenu()" in installer
    assert "coronaDoctorSafeRegisterMenu" in installer  # also referenced in the generated startup file text


def test_installer_still_opens_the_panel_even_if_menu_registration_is_skipped():
    """show_corona_doctor() must be called unconditionally, never gated
    behind the menu-registration try block's success."""

    installer = _installer_source()
    open_call_index = installer.find("show_corona_doctor()")
    assert open_call_index != -1
    # It must not be nested inside the same `if helpersLoadOk` guard that
    # protects the menu-registration call.
    menu_call_index = installer.find("coronaDoctorSafeRegisterMenu()")
    assert menu_call_index < open_call_index


def test_bootstrap_exposes_about_entry_point_for_the_about_macroscript():
    helpers = _helpers_source()
    assert "show_corona_doctor_about" in helpers
    assert "CoronaDoctor_About" in helpers


def test_startup_guard_ms_exists_and_calls_the_safe_wrapper():
    guard_path = _REPO_ROOT / "corona_doctor" / "maxscript" / "startup_guard.ms"
    assert guard_path.is_file()
    guard_source = guard_path.read_text(encoding="utf-8")
    assert "isGlobal #coronaDoctorSafeRegisterMenu" in guard_source
    assert "coronaDoctorSafeRegisterMenu()" in guard_source


def _render_maxscript_format(template: str, *args: str) -> str:
    """Reproduce MAXScript ``format``'s escape/substitution rules for
    exactly the escapes install_corona_doctor.ms's generator uses
    (``\\"``, ``%``, ``\\n``) — enough to render the ACTUAL text that
    gets written to the auto-generated CoronaDoctor_Startup.ms, so this
    test catches a real escaping bug instead of just pattern-matching the
    template source. See the real-host regression this guards: "Type
    error: Call needs function or class, got: undefined" from an earlier
    multi-line version of the generated file."""

    out: list[str] = []
    arg_iter = iter(args)
    i = 0
    while i < len(template):
        ch = template[i]
        if ch == "\\" and i + 1 < len(template):
            nxt = template[i + 1]
            if nxt == "n":
                out.append("\n")
            elif nxt == "t":
                out.append("\t")
            elif nxt in ('"', "\\"):
                out.append(nxt)
            else:
                out.append(nxt)
            i += 2
            continue
        if ch == "%":
            out.append(str(next(arg_iter)))
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def test_generated_startup_guard_line_is_a_single_self_contained_statement():
    """Simulates exactly what install_corona_doctor.ms's format calls
    write for one file path, and asserts the result is one physical
    line with balanced parens/quotes and no nested escaped try/catch
    text — the real-host failure mode this was rewritten to avoid."""

    template = r'if doesFileExist @\"%\" then ( try ( fileIn @\"%\" ) catch () )\n'
    path = r"D:\proj\corona_doctor\maxscript\helpers.ms"
    rendered = _render_maxscript_format(template, path, path)

    assert rendered.count("\n") == 1
    assert rendered.endswith("\n")
    body = rendered.rstrip("\n")
    assert body.count("(") == body.count(")")
    assert body.count('"') % 2 == 0
    assert body == f'if doesFileExist @"{path}" then ( try ( fileIn @"{path}" ) catch () )'


def test_installer_generates_one_guarded_line_per_file_no_multiline_compound_block():
    installer = _installer_source()
    assert 'format "if doesFileExist @\\"%\\" then ( try ( fileIn @\\"%\\" ) catch () )\\n" helpersPath helpersPath to:f' in installer
    assert (
        'format "if doesFileExist @\\"%\\" then ( try ( fileIn @\\"%\\" ) catch () )\\n" startupGuardPath startupGuardPath to:f'
        in installer
    )
    # The old, real-host-broken shape: a "then (" opening a block that
    # spans multiple separate format calls. Must not reappear.
    assert 'then (\\n"' not in installer
