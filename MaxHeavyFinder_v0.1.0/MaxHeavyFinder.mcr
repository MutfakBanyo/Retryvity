/*
================================================================================
    Max Heavy Finder
    Find the geometry objects responsible for the highest polygon load
    in the current 3ds Max scene.

    Version : 0.1.0
    Author  : Murat Yuksel
    License : MIT (see LICENSE.txt)

    SCOPE
    -----
    This tool is strictly READ-ONLY. The only scene interaction it performs is:
        - inspecting objects (evaluating their mesh representation)
        - selecting objects (only when the user presses Select / Zoom)
        - framing the selection in the active viewport (Zoom)
    It never modifies geometry, modifiers, materials, transforms, visibility,
    layers, names, hierarchy or any render setting.

    IMPLEMENTATION NOTES
    --------------------
    - Pure MAXScript. No Python, no third-party DLLs, no renderer APIs,
      no internet access. The only .NET types used ship with 3ds Max
      (System.Windows.Forms.ListView for the results table).
    - Triangle counts come from getTriMeshFaceCount, which evaluates the
      complete modifier stack without creating any scene node.
    - Nodes that share the exact same evaluated object pipeline (same base
      object AND same modifier objects) are grouped into one instance group
      and evaluated only once.

    This file is a normal MAXScript file: evaluating it defines the tool and
    registers the macroScript at the bottom.
================================================================================
*/

-- ---------------------------------------------------------------------------
-- CONSTANTS (the only place the version and the homepage URL are defined)
-- ---------------------------------------------------------------------------
global MAX_HEAVY_FINDER_VERSION      = "0.1.0"
global MAX_HEAVY_FINDER_HOMEPAGE_URL = "https://yukselmurat.com/tools/max-heavy-finder"

-- ---------------------------------------------------------------------------
-- FORWARD GLOBAL DECLARATIONS
-- ---------------------------------------------------------------------------
global MHF_RolloutMain          -- the single rollout, defined further below
global MHF_Floater              -- the floater holding the rollout (single instance)
global MHF_LastScan             -- MHF_ScanResult of the most recent scan
global MHF_Filtered = #()       -- groups currently visible in the table
global MHF_UiUpdating = false   -- guard against re-entrant list events
global MHF_SortKey = #impact    -- #name | #tris | #impact | #inst | #faces
global MHF_SortDesc = true
global MaxHeavyFinder_Open      -- public entry point


-- ===========================================================================
-- DATA MODEL
-- ===========================================================================

/* One logical result row: a single object, or a family of instanced nodes
   that share the exact same evaluated geometry. */
struct MHF_GeometryGroup
(
    repNode    = undefined,  -- representative scene node
    repName    = "",         -- name captured at scan time (survives deletion)
    nodes      = #(),        -- every scene node belonging to this group
    tris       = 0,          -- triangles of ONE node (the shared geometry)
    faces      = 0,          -- polygons/faces of ONE node
    evalFailed = false,      -- true when the geometry could not be evaluated
    instCount  = 0,          -- number of nodes sharing the geometry
    impact     = 0           -- tris * instCount ("Instance Scene Impact")
)

struct MHF_ScanResult
(
    groups       = #(),
    totalTris    = 0,        -- sum of every group's scene impact
    totalObjects = 0,        -- number of geometry nodes represented
    failedNodes  = 0,        -- nodes whose geometry could not be evaluated
    seconds      = 0.0,
    aborted      = false
)


-- ===========================================================================
-- NUMBER FORMATTING
-- ===========================================================================

/* Integer64 keeps totals exact far beyond the 32-bit integer range, which
   matters because instance impact multiplies quickly. If a host build has no
   Integer64 the value degrades to a plain 32-bit integer instead of failing. */
fn MHF_ToInt64 v =
(
    local r = try ( v as Integer64 ) catch ( undefined )
    if r != undefined then r else ( try ( v as integer ) catch ( 0 ) )
)

fn MHF_Mul a b =
(
    try ( (MHF_ToInt64 a) * (MHF_ToInt64 b) ) catch ( 0 )
)

/* 14284337 -> "14,284,337" (no scientific notation, no decimals). */
fn MHF_FormatInt v =
(
    local s = try ( (MHF_ToInt64 v) as string ) catch ( "0" )
    if s == undefined or s.count == 0 do s = "0"
    local neg = false
    if s[1] == "-" do
    (
        neg = true
        s = substring s 2 (s.count - 1)
    )
    local out = ""
    local c = 0
    for i = s.count to 1 by -1 do
    (
        out = s[i] + out
        c += 1
        if (mod c 3) == 0 and i > 1 do out = "," + out
    )
    if neg then ("-" + out) else out
)

/* Scene percentage with a single decimal, safe on empty scenes. */
fn MHF_FormatPct part total =
(
    local t = (try ( total as float ) catch ( 0.0 ))
    if t == undefined or t <= 0.0 then "0.0%"
    else
    (
        local p = ((try ( part as float ) catch ( 0.0 )) / t) * 100.0
        (formattedPrint p format:".1f") + "%"
    )
)


-- ===========================================================================
-- TRIANGLE EVALUATION
-- ===========================================================================

/* getTriMeshFaceCount / getPolygonCount return a Point2 in current versions of
   3ds Max, but accept an array form as well so a signature change cannot break
   the scan. Returns #(faces, verts) or undefined. */
fn MHF_ReadCountPair v =
(
    local f = undefined
    local n = undefined
    case of
    (
        (classOf v == Point2):
        (
            f = v.x
            n = v.y
        )
        (classOf v == Point3):
        (
            f = v.x
            n = v.y
        )
        ((classOf v == Array) and v.count >= 2):
        (
            f = v[1]
            n = v[2]
        )
    )
    if f == undefined then undefined else #((f as integer), (n as integer))
)

/*
    Evaluates one node and returns #(triangles, faces), or undefined when the
    geometry cannot be evaluated (unsupported plugin objects, proxies that do
    not expose a mesh, broken references...).

    Primary method: getTriMeshFaceCount, which reports the triangle count of the
    node's evaluated mesh - the whole modifier stack included (TurboSmooth,
    Edit Poly, ...) - without creating a scene node and without touching the
    object itself.

    Fallback: snapshotAsMesh, which returns a temporary TriMesh *value* (again,
    no scene node). It is released immediately with delete to avoid leaks.
*/
fn MHF_EvaluateNode n =
(
    local tris  = undefined
    local faces = 0

    try
    (
        local pair = MHF_ReadCountPair (getTriMeshFaceCount n)
        if pair != undefined do tris = pair[1]
    )
    catch ()

    try
    (
        local pair2 = MHF_ReadCountPair (getPolygonCount n)
        if pair2 != undefined do faces = pair2[1]
    )
    catch ()

    -- A zero result also goes through the fallback: some plugin/proxy objects
    -- report nothing through getTriMeshFaceCount but do produce a mesh here.
    -- A genuinely empty object simply snapshots to zero faces as well.
    if tris == undefined or tris == 0 do
    (
        try
        (
            local m = snapshotAsMesh n
            if m != undefined and (classOf m == TriMesh) do
            (
                local snapTris = getNumFaces m
                delete m   -- free the temporary mesh value right away
                if snapTris > 0 or tris == undefined do tris = snapTris
            )
        )
        catch ()
    )

    if tris == undefined then undefined else #(tris, faces)
)


-- ===========================================================================
-- INSTANCE DETECTION / GROUPING
-- ===========================================================================

/*
    Builds a key that is identical for two nodes only when they evaluate to the
    exact same geometry:

        base object handle + the handles of every modifier on the node

    - True instances share the base object AND the modifier objects  -> same key.
    - A copy owns a private base object (even with identical topology and
      parameters) -> different key, so copies are never merged into an
      instance group.
    - A reference shares the base object but owns its own extra modifiers, so it
      only joins the group while its evaluated geometry really is identical.

    Falling back to the node handle keeps an object that cannot be inspected as
    its own single-node group instead of aborting the scan.
*/
fn MHF_GetGeometryKey n =
(
    local k = undefined
    try
    (
        k = "o" + ((getHandleByAnim n.baseObject) as string)
        for m in n.modifiers do k += "_m" + ((getHandleByAnim m) as string)
    )
    catch ( k = undefined )
    if k == undefined do k = "n" + ((try ((getHandleByAnim n) as string) catch ("?" + n as string)))
    k
)


-- ===========================================================================
-- SCANNING
-- ===========================================================================

fn MHF_SetStatus msg =
(
    try ( MHF_RolloutMain.lbl_status.text = msg ) catch ()
)

/*
    Walks every geometry node in the scene (hidden and frozen nodes included -
    they still belong to the scene and their state is never touched), evaluates
    each distinct geometry pipeline exactly once and returns an MHF_ScanResult.

    Cameras, lights, helpers, shapes and bones are not part of the "geometry"
    system collection, so they are skipped by construction.
*/
fn MHF_ScanScene =
(
    local t0     = timeStamp()
    local result = MHF_ScanResult groups:#()
    local nodes  = for o in geometry collect o
    local total  = nodes.count
    local groups = #()
    local dict   = Dictionary #string
    local aborted = false

    for i = 1 to total do
    (
        if (mod i 50) == 0 do
        (
            MHF_SetStatus ("Scanning " + (MHF_FormatInt i) + " / " + (MHF_FormatInt total) + "...")
            try ( windows.processPostedMessages() ) catch ()
            if keyboard.escPressed do
            (
                aborted = true
                exit
            )
        )

        local n = nodes[i]
        if not (isValidNode n) do continue

        local key = MHF_GetGeometryKey n
        local g = try ( dict[key] ) catch ( undefined )   -- undefined when the key is new

        if g == undefined then
        (
            -- first node of this pipeline: evaluate the shared geometry once
            local ev = MHF_EvaluateNode n
            if ev == undefined then
                g = MHF_GeometryGroup repNode:n repName:n.name nodes:#(n) tris:0 faces:0 evalFailed:true
            else
                g = MHF_GeometryGroup repNode:n repName:n.name nodes:#(n) tris:ev[1] faces:ev[2] evalFailed:false
            dict[key] = g
            append groups g
        )
        else
        (
            append g.nodes n
        )
    )

    try ( freeDict dict ) catch ()

    local totalTris    = MHF_ToInt64 0
    local totalObjects = 0
    local failedNodes  = 0

    for g in groups do
    (
        g.instCount = g.nodes.count
        totalObjects += g.instCount
        if g.evalFailed then
        (
            g.impact = MHF_ToInt64 0
            failedNodes += g.instCount
        )
        else
        (
            g.impact = MHF_Mul g.tris g.instCount
            totalTris += g.impact
        )
    )

    result.groups       = groups
    result.totalTris    = totalTris
    result.totalObjects = totalObjects
    result.failedNodes  = failedNodes
    result.aborted      = aborted
    result.seconds      = (((timeStamp()) - t0) as float) / 1000.0
    result
)


-- ===========================================================================
-- SORTING
-- ===========================================================================

fn MHF_CompareGroups a b =
(
    local r = 0
    if MHF_SortKey == #name then
    (
        local sa = toLower (a.repName as string)
        local sb = toLower (b.repName as string)
        r = if sa < sb then -1 else if sa > sb then 1 else 0
    )
    else
    (
        local va = 0
        local vb = 0
        case MHF_SortKey of
        (
            #tris:  ( va = a.tris;      vb = b.tris )
            #inst:  ( va = a.instCount; vb = b.instCount )
            #faces: ( va = a.faces;     vb = b.faces )
            default:( va = a.impact;    vb = b.impact )   -- #impact / "Scene %"
        )
        r = if va < vb then -1 else if va > vb then 1 else 0
    )
    if MHF_SortDesc then -r else r
)

fn MHF_SortGroups =
(
    if MHF_LastScan != undefined and MHF_LastScan.groups.count > 1 do
        qsort MHF_LastScan.groups MHF_CompareGroups
)


-- ===========================================================================
-- UI HELPERS (table, header, details panel, filters)
-- ===========================================================================

fn MHF_UpdateDetails g =
(
    try
    (
        if g == undefined then
        (
            MHF_RolloutMain.lbl_sel_name.text   = "-"
            MHF_RolloutMain.lbl_sel_tris.text   = "-"
            MHF_RolloutMain.lbl_sel_inst.text   = "-"
            MHF_RolloutMain.lbl_sel_impact.text = "-"
        )
        else
        (
            MHF_RolloutMain.lbl_sel_name.text   = g.repName
            MHF_RolloutMain.lbl_sel_tris.text   = if g.evalFailed then "not available" else ((MHF_FormatInt g.tris) + " tris")
            MHF_RolloutMain.lbl_sel_inst.text   = MHF_FormatInt g.instCount
            MHF_RolloutMain.lbl_sel_impact.text = if g.evalFailed then "not available" else ((MHF_FormatInt g.impact) + " tris")
        )
    )
    catch ()
)

fn MHF_UpdateHeader =
(
    try
    (
        if MHF_LastScan == undefined or MHF_LastScan.totalObjects == 0 then
            MHF_RolloutMain.lbl_scene.text = "Scene Geometry:   -"
        else
            MHF_RolloutMain.lbl_scene.text = "Scene Geometry:   " + (MHF_FormatInt MHF_LastScan.totalTris) + " tris      " + (MHF_FormatInt MHF_LastScan.totalObjects) + " objects"
    )
    catch ()
)

fn MHF_RebuildList =
(
    local lv = undefined
    try ( lv = MHF_RolloutMain.lv_results ) catch ()
    if lv == undefined do return false

    MHF_UiUpdating = true
    try
    (
        lv.BeginUpdate()
        lv.Items.Clear()
        for i = 1 to MHF_Filtered.count do
        (
            local g  = MHF_Filtered[i]
            local li = dotNetObject "System.Windows.Forms.ListViewItem" g.repName
            li.SubItems.Add (if g.evalFailed then "n/a" else (MHF_FormatInt g.tris))
            li.SubItems.Add (if g.evalFailed then "-"   else (MHF_FormatPct g.impact MHF_LastScan.totalTris))
            li.SubItems.Add (MHF_FormatInt g.instCount)
            li.SubItems.Add (if g.evalFailed then "-"   else (MHF_FormatInt g.faces))
            lv.Items.Add li
        )
        lv.EndUpdate()
    )
    catch ( try ( lv.EndUpdate() ) catch () )
    MHF_UiUpdating = false
    MHF_UpdateDetails undefined
    true
)

/*
    The triangle threshold filters on SCENE IMPACT (tris x instances) rather
    than on the geometry count of a single node: scene impact is what actually
    makes a scene heavy - 500 instances of a 20k object cost far more than one
    600k object, and the user is looking for the cost, not the mesh size.
*/
fn MHF_ApplyFilters =
(
    local src = if MHF_LastScan == undefined then #() else MHF_LastScan.groups
    local thrIdx = 1
    local topIdx = 2
    try ( thrIdx = MHF_RolloutMain.ddl_threshold.selection ) catch ()
    try ( topIdx = MHF_RolloutMain.ddl_top.selection ) catch ()

    local minImpact = case thrIdx of
    (
        2: 100000
        3: 500000
        4: 1000000
        default: 0
    )

    local filtered = for g in src where ((not g.evalFailed) and g.impact >= minImpact) collect g

    -- objects that could not be evaluated have no honest triangle count, so
    -- they are listed (clearly marked) only when no threshold is active
    if minImpact == 0 do for g in src where g.evalFailed do append filtered g

    local topN = case topIdx of
    (
        1: 10
        2: 25
        3: 50
        default: 0
    )
    if topN > 0 and filtered.count > topN do filtered = for i = 1 to topN collect filtered[i]

    MHF_Filtered = filtered
    MHF_RebuildList()
    true
)

fn MHF_SetSortKey k =
(
    if MHF_SortKey == k then MHF_SortDesc = not MHF_SortDesc
    else
    (
        MHF_SortKey  = k
        MHF_SortDesc = (k != #name)   -- numbers descend, names ascend
    )
    MHF_SortGroups()
    MHF_ApplyFilters()
)

fn MHF_GetSelectedGroup =
(
    local g = undefined
    try
    (
        local lv = MHF_RolloutMain.lv_results
        if lv.SelectedIndices.Count > 0 do
        (
            local idx = (lv.SelectedIndices.Item[0]) + 1   -- .NET is 0-based
            if idx >= 1 and idx <= MHF_Filtered.count do g = MHF_Filtered[idx]
        )
    )
    catch ()
    g
)


-- ===========================================================================
-- SELECT / ZOOM
-- ===========================================================================

/*
    Frames the current selection in the active viewport.
    In a camera or light viewport "zoom extents selected" would move the camera
    or the light, which is a scene modification - so framing is skipped there
    and the caller reports it. Returns true when the viewport was framed.
*/
fn MHF_FrameSelection =
(
    local vt = undefined
    try ( vt = viewport.getType() ) catch ()
    if vt == #view_camera or vt == #view_spot do return false
    local ok = true
    try ( max zoomext sel ) catch ( ok = false )
    ok
)

fn MHF_SelectGroup g doZoom:false =
(
    if g == undefined do
    (
        MHF_SetStatus "Select a row in the list first."
        return false
    )

    local valid = for n in g.nodes where (isValidNode n) collect n
    if valid.count == 0 do
    (
        MHF_SetStatus "Object no longer exists. Refresh the scan."
        return false
    )

    select valid

    local msg = "Selected: " + g.repName
    if valid.count > 1 do msg += "  (" + (MHF_FormatInt valid.count) + " nodes)"
    if valid.count < g.nodes.count do msg += "  Some nodes no longer exist - refresh the scan."

    if doZoom do
    (
        if MHF_FrameSelection() then msg += "  Framed in viewport."
        else msg += "  Camera/light viewport: framing skipped to protect the camera."
    )

    MHF_SetStatus msg
    true
)

fn MHF_OpenHomepage =
(
    try ( shellLaunch MAX_HEAVY_FINDER_HOMEPAGE_URL "" )
    catch ( MHF_SetStatus ("Could not open " + MAX_HEAVY_FINDER_HOMEPAGE_URL) )
)


-- ===========================================================================
-- SCAN ENTRY POINT (shared by "Scan Scene" and "Refresh")
-- ===========================================================================

fn MHF_RunScan =
(
    MHF_SetStatus "Scanning scene..."
    try ( windows.processPostedMessages() ) catch ()

    local res = MHF_ScanScene()
    MHF_LastScan = res
    MHF_SortGroups()
    MHF_UpdateHeader()
    MHF_ApplyFilters()

    if res.totalObjects == 0 then
        MHF_SetStatus "No geometry found in the current scene."
    else
    (
        local msg = "Scan completed: " + (MHF_FormatInt res.totalObjects) + " objects in " + (formattedPrint res.seconds format:".1f") + " sec."
        if res.failedNodes > 0 do
            msg += "  " + (MHF_FormatInt res.failedNodes) + " object(s) could not be evaluated."
        if res.aborted do msg = "Scan cancelled (ESC). Partial result. " + msg
        MHF_SetStatus msg
    )
    res
)


-- ===========================================================================
-- UI
-- ===========================================================================

fn MHF_SetupListView lv =
(
    try
    (
        local viewCls = dotNetClass "System.Windows.Forms.View"
        local alignCls = dotNetClass "System.Windows.Forms.HorizontalAlignment"

        lv.View          = viewCls.Details
        lv.FullRowSelect = true
        lv.GridLines     = true
        lv.HideSelection = false
        lv.MultiSelect   = false
        lv.LabelEdit     = false
        lv.HeaderStyle   = (dotNetClass "System.Windows.Forms.ColumnHeaderStyle").Clickable

        lv.Columns.Clear()
        lv.Columns.Add "Object"  208
        lv.Columns.Add "Tris"     92
        lv.Columns.Add "Scene %"  70
        lv.Columns.Add "Inst."    50
        lv.Columns.Add "Faces"    82

        for i = 1 to 4 do lv.Columns.Item[i].TextAlign = alignCls.Right

        -- follow the 3ds Max UI colours so the table looks native
        local colorCls = dotNetClass "System.Drawing.Color"
        local bg = colorMan.getColor #window
        local fg = colorMan.getColor #windowText
        lv.BackColor = colorCls.FromArgb ((bg.x * 255.0) as integer) ((bg.y * 255.0) as integer) ((bg.z * 255.0) as integer)
        lv.ForeColor = colorCls.FromArgb ((fg.x * 255.0) as integer) ((fg.y * 255.0) as integer) ((fg.z * 255.0) as integer)
    )
    catch ()
)

rollout MHF_RolloutMain "Max Heavy Finder" width:540 height:516
(
    label lbl_brand "MAX HEAVY FINDER" pos:[12,8] width:220 height:16
    label lbl_ver   "" pos:[180,8] width:348 height:16

    label lbl_scene "Scene Geometry:   -" pos:[12,28] width:516 height:16

    button btn_scan    "Scan Scene" pos:[12,48]  width:110 height:26
    button btn_refresh "Refresh"    pos:[128,48] width:86  height:26

    label lbl_show "Show:" pos:[232,55] width:34 height:16
    dropdownlist ddl_top "" pos:[268,51] width:86 items:#("Top 10", "Top 25", "Top 50", "All") selection:2
    label lbl_thr "Threshold:" pos:[362,55] width:64 height:16
    dropdownlist ddl_threshold "" pos:[428,51] width:100 items:#("All", "100K", "500K", "1M") selection:1

    dotNetControl lv_results "System.Windows.Forms.ListView" pos:[12,84] width:516 height:236

    groupBox grp_sel "Selected" pos:[12,328] width:516 height:136

    label lbl_cap_name   "Object:"                pos:[24,348] width:142 height:16
    label lbl_sel_name   "-"                      pos:[172,348] width:346 height:16
    label lbl_cap_tris   "Geometry:"              pos:[24,368] width:142 height:16
    label lbl_sel_tris   "-"                      pos:[172,368] width:346 height:16
    label lbl_cap_inst   "Instances:"             pos:[24,388] width:142 height:16
    label lbl_sel_inst   "-"                      pos:[172,388] width:346 height:16
    label lbl_cap_impact "Instance Scene Impact:" pos:[24,408] width:142 height:16
    label lbl_sel_impact "-"                      pos:[172,408] width:346 height:16

    button btn_select "Select" pos:[24,430] width:100 height:26
    button btn_zoom   "Zoom"   pos:[130,430] width:100 height:26

    label lbl_status "Ready." pos:[12,474] width:430 height:18
    button btn_web "Website" pos:[452,472] width:76 height:22 tooltip:"Open the Max Heavy Finder homepage in your browser"

    on MHF_RolloutMain open do
    (
        lbl_ver.text = "Free 3ds Max Utility   -   v" + MAX_HEAVY_FINDER_VERSION
        MHF_SetupListView lv_results
        MHF_LastScan = undefined
        MHF_Filtered = #()
        MHF_SortKey  = #impact
        MHF_SortDesc = true
        MHF_UpdateHeader()
        MHF_UpdateDetails undefined
        MHF_SetStatus "Ready. Press Scan Scene."
    )

    on btn_scan    pressed do MHF_RunScan()
    on btn_refresh pressed do MHF_RunScan()

    on ddl_top       selected i do MHF_ApplyFilters()
    on ddl_threshold selected i do MHF_ApplyFilters()

    on btn_select pressed do MHF_SelectGroup (MHF_GetSelectedGroup())
    on btn_zoom   pressed do MHF_SelectGroup (MHF_GetSelectedGroup()) doZoom:true
    on btn_web    pressed do MHF_OpenHomepage()

    on lv_results SelectedIndexChanged arg do
    (
        if not MHF_UiUpdating do MHF_UpdateDetails (MHF_GetSelectedGroup())
    )

    on lv_results DoubleClick arg do
    (
        if not MHF_UiUpdating do MHF_SelectGroup (MHF_GetSelectedGroup()) doZoom:true
    )

    on lv_results ColumnClick arg do
    (
        if not MHF_UiUpdating do
        (
            local keys = #(#name, #tris, #impact, #inst, #faces)
            local i = (arg.Column) + 1
            if i >= 1 and i <= keys.count do MHF_SetSortKey keys[i]
        )
    )
)

/* Opens the tool. Any window already open is closed first, so repeated calls
   can never stack up duplicate floaters or duplicate control handlers. */
fn MaxHeavyFinder_Open =
(
    if MHF_Floater != undefined do ( try ( closeRolloutFloater MHF_Floater ) catch () )
    MHF_Floater = newRolloutFloater ("Max Heavy Finder v" + MAX_HEAVY_FINDER_VERSION) 556 552
    addRollout MHF_RolloutMain MHF_Floater
    MHF_Floater
)


-- ===========================================================================
-- MACROSCRIPT REGISTRATION
--   Customize > Customize User Interface > Category: "Max Heavy Finder"
-- ===========================================================================
macroScript MaxHeavyFinder
    category:"Max Heavy Finder"
    buttonText:"Max Heavy Finder"
    toolTip:"Max Heavy Finder - find the heaviest geometry in the scene"
(
    on execute do MaxHeavyFinder_Open()
)
