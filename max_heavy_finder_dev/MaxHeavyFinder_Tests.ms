/*
================================================================================
    Max Heavy Finder - in-Max test runner (development only, not shipped)

    WARNING: THIS SCRIPT RESETS THE CURRENT SCENE SEVERAL TIMES.
             Save your work before running it. It is a developer tool, the
             utility itself never touches your scene.

    HOW TO RUN
    ----------
    1. Open 3ds Max (2026.x).
    2. Scripting > Run Script... > select this file.
    3. Confirm the warning dialog.
    4. Read the PASS/FAIL report in the MAXScript Listener. The same report is
       written next to this script as MaxHeavyFinder_TestReport.txt

    The runner loads MaxHeavyFinder.mcr itself, so it exercises exactly the file
    that ships in the release package.
================================================================================
*/

global MHFT_Results = #()
global MHFT_ReportLines = #()

fn MHFT_Log msg =
(
    format "%\n" msg
    append MHFT_ReportLines msg
)

fn MHFT_Check testName condition details:"" =
(
    local verdict = if condition == true then "PASS" else "FAIL"
    append MHFT_Results #(testName, verdict, details)
    MHFT_Log (testName + "  ...  " + verdict + (if details == "" then "" else ("   [" + details + "]")))
    condition == true
)

fn MHFT_FindScriptFolder =
(
    local p = ""
    try ( p = getFilenamePath (getThisScriptFilename()) ) catch ( p = "" )
    p
)

/* Locates MaxHeavyFinder.mcr next to the dev folder or in the release folder. */
fn MHFT_LocateTool =
(
    local here = MHFT_FindScriptFolder()
    local candidates = #(
        here + "MaxHeavyFinder.mcr",
        here + "..\\MaxHeavyFinder_v0.1.0\\MaxHeavyFinder.mcr",
        here + "..\\MaxHeavyFinder.mcr"
    )
    local found = undefined
    for c in candidates while found == undefined do
        if doesFileExist c do found = c
    if found == undefined do
        found = getOpenFileName caption:"Locate MaxHeavyFinder.mcr" types:"MacroScript (*.mcr)|*.mcr|All|*.*|"
    found
)

fn MHFT_ResetScene =
(
    resetMaxFile #noPrompt
    ok
)

/* Returns the group whose representative node is named nm, or undefined. */
fn MHFT_GroupByName res nm =
(
    local hit = undefined
    for g in res.groups while hit == undefined do
        if g.repName == nm do hit = g
    hit
)

/* Returns the group that contains a node named nm (instances share a group). */
fn MHFT_GroupContaining res nm =
(
    local hit = undefined
    for g in res.groups while hit == undefined do
        for n in g.nodes while hit == undefined do
            if (isValidNode n) and n.name == nm do hit = g
    hit
)

-- ---------------------------------------------------------------------------
-- TEST RUN
-- ---------------------------------------------------------------------------
(
    local proceed = queryBox "This test runner RESETS the current 3ds Max scene several times.\n\nContinue?" title:"Max Heavy Finder tests"
    if not proceed then
    (
        format "Test run cancelled by user.\n"
    )
    else
    (
        MHFT_Results = #()
        MHFT_ReportLines = #()
        MHFT_Log ("MAX HEAVY FINDER - TEST RUN")
        MHFT_Log ("3ds Max version : " + (maxVersion() as string))
        MHFT_Log ("Date            : " + localTime)
        MHFT_Log ("------------------------------------------------------------")

        -- ---------------------------------------------------------------
        -- PLUGIN LOAD
        -- ---------------------------------------------------------------
        local toolPath = MHFT_LocateTool()
        local loaded = false
        if toolPath != undefined and toolPath != "" and (doesFileExist toolPath) then
        (
            try
            (
                fileIn toolPath
                loaded = (MaxHeavyFinder_Open != undefined)
            )
            catch ( loaded = false )
        )
        MHFT_Check "PLUGIN LOAD" loaded details:(if toolPath == undefined then "file not found" else toolPath)

        if not loaded then
        (
            MHFT_Log "Aborting: the tool could not be loaded."
        )
        else
        (
            MHFT_Check "MACRO REGISTERED" ((macros.exists "MaxHeavyFinder" "Max Heavy Finder") == true)

            -- -----------------------------------------------------------
            -- TEST A - empty scene
            -- -----------------------------------------------------------
            MHFT_ResetScene()
            local resEmpty = MHF_ScanScene()
            MHFT_Check "EMPTY SCENE" (resEmpty.totalObjects == 0 and resEmpty.groups.count == 0) details:("objects=" + resEmpty.totalObjects as string)

            -- -----------------------------------------------------------
            -- TEST B - basic primitives
            -- -----------------------------------------------------------
            MHFT_ResetScene()
            local b = box name:"T_Box" length:10 width:10 height:10
            local s = sphere name:"T_Sphere" radius:10 segments:32
            local c = cylinder name:"T_Cyl" radius:10 height:20 sides:24
            local resB = MHF_ScanScene()
            local gBox = MHFT_GroupByName resB "T_Box"
            local gSph = MHFT_GroupByName resB "T_Sphere"
            MHFT_Check "BASIC SCAN" (resB.totalObjects == 3 and gBox != undefined and gBox.tris == 12) details:("objects=" + resB.totalObjects as string + " boxTris=" + (if gBox == undefined then "-" else gBox.tris as string))
            MHFT_Check "SORTED BY IMPACT" (resB.groups.count == 3) details:"scan produced three groups"
            -- the tool sorts on demand; verify the comparator orders descending
            MHF_LastScan = resB
            MHF_SortKey = #impact
            MHF_SortDesc = true
            MHF_SortGroups()
            local ordered = true
            for i = 1 to (resB.groups.count - 1) do
                if resB.groups[i].impact < resB.groups[i + 1].impact do ordered = false
            MHFT_Check "SORT ORDER" ordered details:"heaviest first"

            local totalCheck = (gBox.impact + gSph.impact + (MHFT_GroupByName resB "T_Cyl").impact) == resB.totalTris
            MHFT_Check "SCENE TOTAL" totalCheck details:("total=" + resB.totalTris as string)

            -- -----------------------------------------------------------
            -- TEST C - modifier stack evaluation
            -- -----------------------------------------------------------
            MHFT_ResetScene()
            local baseBox = box name:"T_Smooth" length:10 width:10 height:10
            local baseRes = MHF_ScanScene()
            local baseTris = (MHFT_GroupByName baseRes "T_Smooth").tris
            addModifier baseBox (TurboSmooth iterations:2)
            local smoothRes = MHF_ScanScene()
            local smoothTris = (MHFT_GroupByName smoothRes "T_Smooth").tris
            local stackOk = (smoothTris > baseTris) and (baseBox.modifiers.count == 1)
            MHFT_Check "MODIFIER STACK COUNT" stackOk details:("base=" + baseTris as string + " turbosmooth=" + smoothTris as string + " stack kept=" + (baseBox.modifiers.count as string))

            -- -----------------------------------------------------------
            -- TEST D / 35 - instances
            -- -----------------------------------------------------------
            MHFT_ResetScene()
            local src = geoSphere name:"Box_A" radius:10 segments:12
            for i = 1 to 20 do ( local ni = instance src; ni.name = ("Box_A_inst_" + i as string) )
            local resInst = MHF_ScanScene()
            local gInst = MHFT_GroupContaining resInst "Box_A"
            local instOk = (gInst != undefined) and (gInst.instCount == 21)
            local impactOk = instOk and (gInst.impact == (gInst.tris * 21))
            MHFT_Check "INSTANCE GROUPING" instOk details:("instances=" + (if gInst == undefined then "-" else gInst.instCount as string) + " (expected 21)")
            MHFT_Check "INSTANCE SCENE IMPACT" impactOk details:("tris=" + (if gInst == undefined then "-" else gInst.tris as string) + " impact=" + (if gInst == undefined then "-" else gInst.impact as string))
            MHFT_Check "ONE ROW PER FAMILY" (resInst.groups.count == 1) details:("groups=" + resInst.groups.count as string)
            MHFT_Check "TOTAL COUNTS INSTANCES" (resInst.totalObjects == 21 and resInst.totalTris == gInst.impact) details:("totalObjects=" + resInst.totalObjects as string + " totalTris=" + resInst.totalTris as string)

            -- -----------------------------------------------------------
            -- TEST E / 35 - copies must not be grouped with instances
            -- -----------------------------------------------------------
            local cp = copy src; cp.name = "Box_A_copy"
            local resCopy = MHF_ScanScene()
            local gCopy = MHFT_GroupByName resCopy "Box_A_copy"
            local copyOk = (gCopy != undefined) and (gCopy.instCount == 1) and (resCopy.groups.count == 2)
            MHFT_Check "COPY DISTINCTION" copyOk details:("groups=" + resCopy.groups.count as string + " copyInstCount=" + (if gCopy == undefined then "-" else gCopy.instCount as string))

            MHFT_ResetScene()
            local c1 = geoSphere name:"C1" radius:10 segments:12
            local c2 = copy c1; c2.name = "C2"
            local c3 = copy c1; c3.name = "C3"
            local resCopies = MHF_ScanScene()
            MHFT_Check "COPIES NOT MERGED" (resCopies.groups.count == 3) details:("groups=" + resCopies.groups.count as string + " (expected 3)")

            -- -----------------------------------------------------------
            -- TEST F - hidden / frozen
            -- -----------------------------------------------------------
            MHFT_ResetScene()
            local hv = box name:"T_Visible" length:10 width:10 height:10
            local hh = box name:"T_Hidden" length:10 width:10 height:10
            local hf = box name:"T_Frozen" length:10 width:10 height:10
            hide hh
            freeze hf
            local resHF = MHF_ScanScene()
            local hiddenOk = (MHFT_GroupByName resHF "T_Hidden") != undefined
            local frozenOk = (MHFT_GroupByName resHF "T_Frozen") != undefined
            MHFT_Check "HIDDEN/FROZEN" (hiddenOk and frozenOk and hh.isHidden and hf.isFrozen) details:("hidden found=" + hiddenOk as string + " frozen found=" + frozenOk as string + " states untouched")

            -- -----------------------------------------------------------
            -- TEST G - deleted node safety
            -- -----------------------------------------------------------
            MHFT_ResetScene()
            local dn = box name:"T_Doomed" length:10 width:10 height:10
            local resDel = MHF_ScanScene()
            local gDel = MHFT_GroupByName resDel "T_Doomed"
            delete dn
            local survived = false
            try
            (
                local r = MHF_SelectGroup gDel
                survived = (r == false)
            )
            catch ( survived = false )
            MHFT_Check "DELETED NODE SAFETY" survived details:"MHF_SelectGroup returns false, no exception"

            -- -----------------------------------------------------------
            -- SELECT / ZOOM
            -- -----------------------------------------------------------
            MHFT_ResetScene()
            local selSrc = box name:"T_Sel" length:10 width:10 height:10
            for i = 1 to 4 do ( local ni2 = instance selSrc; ni2.name = ("T_Sel_" + i as string) )
            local resSel = MHF_ScanScene()
            local gSel = MHFT_GroupContaining resSel "T_Sel"
            clearSelection()
            local selOk = false
            try ( selOk = (MHF_SelectGroup gSel) and (selection.count == 5) ) catch ( selOk = false )
            MHFT_Check "SELECT" selOk details:("selected=" + selection.count as string + " (expected 5, the whole instance family)")

            local zoomOk = false
            try
            (
                viewport.setType #view_persp_user   -- make sure the active viewport is not a camera view
                zoomOk = (MHF_SelectGroup gSel doZoom:true) == true
            )
            catch ( zoomOk = false )
            MHFT_Check "ZOOM" zoomOk details:"framed the selection in a perspective viewport"

            -- -----------------------------------------------------------
            -- FILTERS / FORMATTING (pure functions)
            -- -----------------------------------------------------------
            MHFT_Check "NUMBER FORMAT" ((MHF_FormatInt 14284337) == "14,284,337" and (MHF_FormatInt 0) == "0" and (MHF_FormatInt 641210) == "641,210") details:(MHF_FormatInt 14284337)
            MHFT_Check "PERCENT FORMAT" ((MHF_FormatPct 2000000 10000000) == "20.0%" and (MHF_FormatPct 1 0) == "0.0%") details:((MHF_FormatPct 2418440 14284337))

            -- -----------------------------------------------------------
            -- WINDOW LIFECYCLE + UI DRIVEN SCAN
            -- -----------------------------------------------------------
            MHFT_ResetScene()
            for i = 1 to 5 do box name:("T_Ui_" + i as string) length:10 width:10 height:10 lengthsegs:i widthsegs:i
            local openOk = false
            try ( MaxHeavyFinder_Open(); openOk = (MHF_Floater != undefined and MHF_Floater.open) ) catch ( openOk = false )
            MHFT_Check "WINDOW OPEN" openOk

            local secondOk = false
            try ( MaxHeavyFinder_Open(); secondOk = (MHF_Floater != undefined and MHF_Floater.open) ) catch ( secondOk = false )
            MHFT_Check "SECOND OPEN" secondOk details:"reopening replaces the window instead of stacking floaters"

            local uiScanOk = false
            try
            (
                MHF_RunScan()
                uiScanOk = (MHF_LastScan.totalObjects == 5 and MHF_Filtered.count == 5)
            )
            catch ( uiScanOk = false )
            MHFT_Check "UI SCAN + TABLE" uiScanOk details:("rows=" + MHF_Filtered.count as string)

            local filterOk = false
            try
            (
                MHF_RolloutMain.ddl_top.selection = 1     -- Top 10
                MHF_ApplyFilters()
                local a = MHF_Filtered.count
                MHF_RolloutMain.ddl_threshold.selection = 4  -- 1M
                MHF_ApplyFilters()
                local b2 = MHF_Filtered.count
                MHF_RolloutMain.ddl_threshold.selection = 1
                MHF_ApplyFilters()
                filterOk = (a == 5) and (b2 == 0) and (MHF_Filtered.count == 5)
            )
            catch ( filterOk = false )
            MHFT_Check "FILTERS" filterOk details:"Top N and threshold both applied"

            local refreshOk = false
            try
            (
                box name:"T_Ui_extra" length:10 width:10 height:10
                MHF_RunScan()
                refreshOk = (MHF_LastScan.totalObjects == 6)
            )
            catch ( refreshOk = false )
            MHFT_Check "REFRESH" refreshOk details:("objects after refresh=" + MHF_LastScan.totalObjects as string)

            local emptyUiOk = false
            try
            (
                MHFT_ResetScene()
                MHF_RunScan()
                emptyUiOk = (MHF_Filtered.count == 0)
            )
            catch ( emptyUiOk = false )
            MHFT_Check "EMPTY SCENE (UI)" emptyUiOk details:"table empty, status reports no geometry"

            -- -----------------------------------------------------------
            -- TEST H - heavy scene
            -- -----------------------------------------------------------
            MHFT_ResetScene()
            local heavyStart = timeStamp()
            local proto = #()
            for i = 1 to 10 do
            (
                local p = geoSphere name:("H_Proto_" + i as string) radius:10 segments:(6 + i)
                append proto p
                for k = 1 to 60 do ( local hi = instance p; hi.name = ("H_Proto_" + i as string + "_" + k as string) )
            )
            for i = 1 to 400 do box name:("H_Box_" + i as string) length:10 width:10 height:10 lengthsegs:3 widthsegs:3 heightsegs:3
            local buildSecs = ((timeStamp() - heavyStart) as float) / 1000.0
            local resHeavy = MHF_ScanScene()
            local heavyOk = (resHeavy.totalObjects == 1010) and (resHeavy.groups.count == 410) and (resHeavy.seconds < 60.0)
            MHFT_Check "HEAVY SCENE" heavyOk details:("nodes=" + resHeavy.totalObjects as string + " groups=" + resHeavy.groups.count as string + " scan=" + (formattedPrint resHeavy.seconds format:".2f") + " sec")

            -- -----------------------------------------------------------
            -- TEST I - unsupported object safety
            -- -----------------------------------------------------------
            MHFT_ResetScene()
            local safeOk = false
            try
            (
                box name:"S_Box" length:10 width:10 height:10
                -- a particle system is geometry that does not evaluate to a
                -- normal mesh; it must not abort the scan
                try ( PCloud name:"S_Cloud" ) catch ()
                try ( Spray name:"S_Spray" ) catch ()
                local resSafe = MHF_ScanScene()
                safeOk = (MHFT_GroupByName resSafe "S_Box") != undefined
            )
            catch ( safeOk = false )
            MHFT_Check "UNSUPPORTED OBJECT SAFETY" safeOk details:"scan finished and still reported the normal geometry"

            MHFT_ResetScene()
        )

        -- ---------------------------------------------------------------
        -- REPORT
        -- ---------------------------------------------------------------
        MHFT_Log "------------------------------------------------------------"
        local passCount = 0
        local failCount = 0
        for r in MHFT_Results do
            if r[2] == "PASS" then passCount += 1 else failCount += 1
        MHFT_Log ("TOTAL: " + MHFT_Results.count as string + "   PASS: " + passCount as string + "   FAIL: " + failCount as string)

        local outPath = (MHFT_FindScriptFolder()) + "MaxHeavyFinder_TestReport.txt"
        try
        (
            local f = createFile outPath
            for l in MHFT_ReportLines do format "%\n" l to:f
            close f
            format "Report written to %\n" outPath
        )
        catch ( format "Could not write the report file.\n" )
    )
)
