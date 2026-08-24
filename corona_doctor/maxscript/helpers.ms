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
--   Targets: 3ds Max 2026.3+ (Python 3.11 bundled runtime).
--   Returns: nothing.
--   Mutates scene state: no.
function launchCoronaDoctor = (
    python.Execute "from corona_doctor.bootstrap import show_corona_doctor; show_corona_doctor()"
)

macroScript CoronaDoctor_Launch
category:"Corona Doctor"
buttonText:"Corona Doctor"
tooltip:"Open Corona Doctor"
(
    on execute do launchCoronaDoctor()
)
