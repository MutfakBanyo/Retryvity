-- RevisionGuard MAXScript bridge.
--
-- Defines the launcher function and the macroScript the main menu item
-- points at. Everything real happens in Python; this file only exists
-- because 3ds Max menus need a macroScript to bind to.

global launchRevisionGuard

fn launchRevisionGuard =
(
	python.Execute "from revision_guard.bootstrap import show_revision_guard; show_revision_guard()"
)

macroScript RevisionGuard_Launch
	category:"RevisionGuard"
	buttonText:"RevisionGuard"
	toolTip:"Snapshot the scene and compare it against the stored snapshot"
(
	on execute do launchRevisionGuard()
)

macroScript RevisionGuard_SmokeTest
	category:"RevisionGuard"
	buttonText:"RevisionGuard Smoke Test"
	toolTip:"Run the V0.1 comparison engine self-test (creates and deletes temporary objects)"
(
	on execute do python.Execute "from revision_guard.devtools.smoke_test import run_smoke_test; run_smoke_test()"
)
