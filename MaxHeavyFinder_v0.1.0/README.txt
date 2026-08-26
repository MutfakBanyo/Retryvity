================================================================================
MAX HEAVY FINDER  v0.1.0
Find high-poly objects slowing down your 3ds Max scenes.
================================================================================

Max Heavy Finder answers one question: "What is making my 3ds Max scene heavy?"

It scans the geometry in the current scene, ranks it by triangle count and by
total scene impact, groups instanced geometry into a single row, and lets you
select or zoom to the result straight from the list.

The tool is READ-ONLY. It never changes geometry, modifiers, materials,
transforms, visibility, layers, names, hierarchy or render settings. The only
scene interaction it performs is inspecting objects, selecting them when you
press Select or Zoom, and framing that selection in the viewport.


--------------------------------------------------------------------------------
FEATURES
--------------------------------------------------------------------------------
* Find the heaviest geometry objects
* Triangle count (evaluated geometry, modifier stack included)
* Scene percentage
* Instance detection
* Instance scene impact (geometry tris x instance count)
* Select objects (the whole instance family)
* Zoom to objects
* Top 10 / 25 / 50 / All filters
* 100K / 500K / 1M thresholds
* Faces (polygon) column
* Column-click sorting
* Renderer independent - no Corona, V-Ray or Arnold required
* Read-only scene analysis
* No ads, no telemetry, no account, no internet access


--------------------------------------------------------------------------------
INSTALLATION
--------------------------------------------------------------------------------
Recommended (permanent install):

1. Close 3ds Max.
2. Copy MaxHeavyFinder.mcr into your user macros folder:

       %LOCALAPPDATA%\Autodesk\3dsMax\2026 - 64bit\ENU\usermacros\

   (For another release, replace "2026" with your version. You can print the
   exact folder from the MAXScript Listener with:
       getDir #usermacros )
3. Start 3ds Max.
4. Customize > Customize User Interface (or Hotkey Editor / Toolbars in the
   newer UI). Choose the category:

       Max Heavy Finder

   and the action:

       Max Heavy Finder

   Drag it onto a toolbar, a menu or a quad menu, or assign a keyboard
   shortcut.

Quick try (current session only):

   Scripting > Run Script... and pick MaxHeavyFinder.mcr, then run this line in
   the MAXScript Listener:

       macros.run "Max Heavy Finder" "MaxHeavyFinder"

Uninstall: delete MaxHeavyFinder.mcr from the usermacros folder and remove the
button or shortcut you assigned.


--------------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------------
1. Open Max Heavy Finder.
2. Click Scan Scene.
3. Review the heaviest objects.
4. Select a result.
5. Click Select or Zoom (or double-click the row, which does both).

Use Refresh after you change the scene - the tool never watches the scene in
the background, so the list always shows the state of the last scan.

Press ESC during a long scan to stop it; the partial result is kept and the
status bar says so.


--------------------------------------------------------------------------------
READING THE RESULTS
--------------------------------------------------------------------------------
Object    Name of the representative scene object.
Tris      Triangles of ONE object, with its modifier stack evaluated.
Scene %   That row's scene impact as a share of the whole scene.
Inst.     How many scene nodes share that exact geometry.
Faces     Polygon count of one object.

The Selected panel below the list separates the three numbers that matter:

    Geometry              tris of a single object
    Instances             number of nodes sharing it
    Instance Scene Impact geometry tris x instances

100 instances of an 84,000 triangle chair are one row: 84,000 tris,
100 instances, 8,400,000 triangles of scene impact. The chair mesh itself is
still only 84,000 triangles.

Sorting and the triangle threshold both work on scene impact, because that is
what actually costs you performance. Click a column header to sort by that
column instead.

Copies are not instances: a copied object owns its own geometry, so it gets its
own row even when its topology is identical to the original.

Hidden and frozen objects are counted - they are still part of the scene - and
their state is never changed.

Objects whose geometry cannot be evaluated (some renderer proxies and unusual
plugin objects do not expose a mesh through standard MAXScript) are shown with
"n/a" instead of an invented number, and the status bar reports how many there
were.


--------------------------------------------------------------------------------
COMPATIBILITY
--------------------------------------------------------------------------------
Developed for Autodesk 3ds Max 2026.x on Windows.

Pure MAXScript. It uses only APIs that have existed in 3ds Max for many
releases, so it should also load in recent earlier versions, but it has not
been verified there.

No Python packages, no external executables, no internet access and no
renderer-specific code. Works with or without Corona, V-Ray or Arnold.


--------------------------------------------------------------------------------
KNOWN LIMITATIONS
--------------------------------------------------------------------------------
* Renderer proxy objects (V-Ray Proxy, Corona Proxy, ...) only report a
  triangle count when they expose a mesh through standard MAXScript. Otherwise
  they are marked "n/a" - no number is invented for them.
* Triangle counts are read through getTriMeshFaceCount, whose result is a
  floating point pair. Above roughly 16.7 million triangles on a single object
  the last digits can be off by a few triangles. Totals and percentages are not
  meaningfully affected.
* No live scene watching. Press Refresh after changing the scene.
* In a camera or spot-light viewport, Zoom selects the objects but does not
  frame them, because framing there would move the camera or the light. Switch
  to a perspective or orthographic viewport to frame the selection.


--------------------------------------------------------------------------------
LICENSE
--------------------------------------------------------------------------------
MIT - see LICENSE.txt.
Copyright (c) 2026 Murat Yüksel


--------------------------------------------------------------------------------
WEBSITE
--------------------------------------------------------------------------------
https://yukselmurat.com/tools/max-heavy-finder
