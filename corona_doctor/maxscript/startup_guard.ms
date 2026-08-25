-- Corona Doctor startup guard.
--
-- Loaded by the auto-generated CoronaDoctor_Startup.ms, AFTER helpers.ms
-- has been fileIn'd. Kept as its own real, directly-authored .ms file
-- rather than assembled character-by-character from escaped string
-- literals inside install_corona_doctor.ms's generated-file writer — a
-- real host hit "Type error: Call needs function or class, got:
-- undefined" from the generated file, and hand-verifying nested
-- escaped try/catch text inside a MAXScript string literal (itself
-- inside another MAXScript string literal) is exactly the kind of thing
-- that is easy to get subtly wrong and hard to catch without a real
-- host to test against. A single-line `if doesFileExist ... then (try
-- (fileIn ...) catch ())` per file (see install_corona_doctor.ms) is the
-- only string-generated MAXScript left; everything else lives in this
-- normal, directly-reviewable file.
--
-- Safe to call every startup: coronaDoctorSafeRegisterMenu() (defined in
-- helpers.ms) is itself idempotent — see its docstring.
if isGlobal #coronaDoctorSafeRegisterMenu then (
    coronaDoctorSafeRegisterMenu()
)
