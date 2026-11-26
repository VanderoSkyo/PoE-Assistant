"""
pob_engine.py - silnik Path of Building uruchamiany "bez okna" przez biblioteke lupa.
Ten plik jest zaczatkiem docelowego modulu programu.
"""
import json
import os

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:  # starsza wersja lupa
    from lupa import LuaRuntime

try:
    from lupa import LuaError
except ImportError:  # pragma: no cover
    LuaError = Exception


class PoBError(Exception):
    pass


# Czesc 1: atrapy funkcji okna PoB, tlumaczenie "+=" i zastepczy lua-utf8 (sprawdzone testem).
LUA_BASE = r"""
print("   Lua engine: " .. (jit and jit.version or "no jit (plain Lua, PoB may not work)"))
package.path = POB_PATH .. "lua/?.lua;" .. POB_PATH .. "lua/?/init.lua;" .. POB_PATH .. "?.lua;" .. package.path


-- === Tlumaczenie zapisu "a += b" na "a = a + (b)" (zwykly LuaJIT go nie rozumie) ===
local OPS = { { "%+", "+" }, { "%-", "-" }, { "%*", "*" }, { "/", "/" }, { "%.%.", ".." } }
local KEYWORDS = { ["else"] = 1, ["then"] = 1, ["do"] = 1, ["end"] = 1, ["if"] = 1, ["elseif"] = 1,
                   ["while"] = 1, ["for"] = 1, ["repeat"] = 1, ["return"] = 1, ["local"] = 1,
                   ["and"] = 1, ["or"] = 1, ["not"] = 1, ["function"] = 1 }
local function fixLine(line)
    if not line:find("=", 1, true) then return line end
    for _, op in ipairs(OPS) do
        local indent, lhs, rhs = line:match("^(%s*)([%a_][%w_%.%[%]\"' %+%-%*/%(%)]-)%s*" .. op[1] .. "=%s*(.-)%s*$")
        if lhs then
            local first = lhs:match("^(%a+)%s")
            if not (first and KEYWORDS[first]) then
                local tail = ""
                local body, ending = rhs:match("^(.-)(%s+end)$")
                if body then rhs, tail = body, ending end
                local code, comment = rhs:match("^(.-)%s*(%-%-.*)$")
                if code and not code:find("[\"']") then rhs = code; tail = tail .. " " .. comment end
                rhs = rhs:gsub(";$", "")
                return indent .. lhs .. " = " .. lhs .. " " .. op[2] .. " (" .. rhs .. ")" .. tail
            end
        end
    end
    return line
end
function PreprocessSource(src)
    if not (src:find("[%+%-%*/]=") or src:find("%.%.=")) then return src end
    local out, n = {}, 0
    for line in (src .. "\n"):gmatch("(.-)\n") do
        n = n + 1
        out[n] = fixLine(line)
    end
    return table.concat(out, "\n")
end
local rawLoadstring = loadstring
function loadfile(path)
    local f = io.open(path, "rb")
    if not f then return nil, "cannot open " .. tostring(path) end
    local src = f:read("*a")
    f:close()
    if src:sub(1, 3) == "\239\187\191" then src = src:sub(4) end
    return rawLoadstring(PreprocessSource(src), "@" .. path)
end
function dofile(path)
    local fn, err = loadfile(path)
    if not fn then error(err, 0) end
    return fn()
end

-- require() tez musi tlumaczyc "+=" (PoB laduje tak klasy, np. Classes.CompareBuySimilar)
local function pobSearcher(name)
    local rel = name:gsub("%.", "/")
    for pattern in package.path:gmatch("[^;]+") do
        local path = pattern:gsub("%?", rel)
        local f = io.open(path, "rb")
        if f then
            f:close()
            local fn, err = loadfile(path)
            if not fn then
                error("error loading module '" .. name .. "' from file '" .. path .. "':\n\t" .. tostring(err), 0)
            end
            return fn
        end
    end
    return "\n\tbrak pliku dla modulu " .. name
end
table.insert(package.loaders, 2, pobSearcher)

-- === Zastepczy modul lua-utf8 (wystarczy dla tekstow ASCII) ===
package.preload["lua-utf8"] = function()
    local u = {}
    local function enc(cp)
        if cp < 0x80 then return string.char(cp)
        elseif cp < 0x800 then return string.char(0xC0 + math.floor(cp / 0x40), 0x80 + cp % 0x40)
        elseif cp < 0x10000 then
            return string.char(0xE0 + math.floor(cp / 0x1000), 0x80 + math.floor(cp / 0x40) % 0x40, 0x80 + cp % 0x40)
        else
            return string.char(0xF0 + math.floor(cp / 0x40000), 0x80 + math.floor(cp / 0x1000) % 0x40,
                               0x80 + math.floor(cp / 0x40) % 0x40, 0x80 + cp % 0x40)
        end
    end
    function u.char(...)
        local t = {}
        for i, cp in ipairs({ ... }) do t[i] = enc(cp) end
        return table.concat(t)
    end
    function u.len(s) local _, c = s:gsub("[^\128-\191]", "") return c end
    function u.codepoint(s, i, j) return s:byte(i, j) end
    return setmetatable(u, { __index = string })
end

function PCall(func, ...)
    local ret = { pcall(func, ...) }
    if ret[1] then table.remove(ret, 1) return nil, unpack(ret) else return ret[2] end
end
function LoadModule(fileName, ...)
    if not fileName:match("%.lua") then fileName = fileName .. ".lua" end
    local fullPath = fileName
    local f = io.open(fullPath, "r")
    if not f then fullPath = POB_PATH .. fileName else f:close() end
    local func, err = loadfile(fullPath)
    if func then return func(...) else error("LoadModule: " .. tostring(err)) end
end
function PLoadModule(fileName, ...)
    if not fileName:match("%.lua") then fileName = fileName .. ".lua" end
    local fullPath = fileName
    local f = io.open(fullPath, "r")
    if not f then fullPath = POB_PATH .. fileName else f:close() end
    local func, err = loadfile(fullPath)
    if func then return PCall(func, ...) else error("PLoadModule: " .. tostring(err)) end
end

function RenderInit() end
function GetScreenSize() return 1920, 1080 end
function GetVirtualScreenSize() return 1920, 1080 end
function SetClearColor(...) end
function SetDrawLayer(...) end
function SetViewport(...) end
function SetDrawColor(...) end
function DrawImage(...) end
function DrawImageQuad(...) end
function DrawString(...) end
function DrawStringWidth(...) return 1 end
function DrawStringCursorIndex(...) return 0 end
function StripEscapes(text)
    return text and text:gsub("%^%d", ""):gsub("%^x%x%x%x%x%x%x", "") or ""
end
function GetAsyncCount() return 0 end
function NewFileSearch() end
function NewImageHandle()
    return { Load = function(s) s.valid = true end, Unload = function(s) s.valid = false end,
             IsValid = function(s) return s.valid end, SetLoadingPriority = function() end,
             ImageSize = function() return 1, 1 end }
end
function SetWindowTitle(...) end
function GetCursorPos() return 0, 0 end
function SetCursorPos(...) end
function ShowCursor(...) end
function IsKeyDown(...) return false end
function Copy(...) end
function Paste() return "" end
function Deflate(s) return s end
function Inflate(s) return s end
function GetTime() return os.clock() * 1000 end
function MakeDir(...) end
function RemoveDir(...) end
function SetWorkDir(...) end
function GetWorkDir() return POB_PATH end
function LaunchSubScript(...) end
function DownloadPage(...) end
function ConPrintf(...) end
function ConPrintTable(...) end
function ConExecute(...) end
function ConClear(...) end
function SpawnProcess(...) end
function OpenURL(...) end
function SetProfiling(...) end
function Restart(...) end
function Exit(...) end
function SetForeground(...) end
function GetScriptPath() return POB_PATH end
function GetRuntimePath() return POB_PATH end
function GetUserPath() return POB_PATH end

callbackTable = {}
mainObject = nil
function runCallback(name, ...)
    if callbackTable[name] then return callbackTable[name](...)
    elseif mainObject and mainObject[name] then return mainObject[name](mainObject, ...) end
end
function SetCallback(name, func) callbackTable[name] = func end
function GetCallback(name) return callbackTable[name] end
function SetMainObject(obj) mainObject = obj end

local l_require = require
function require(name)
    if name == "lcurl.safe" or name == "lcurl" then return nil end
    return l_require(name)
end

function Step(label, f)
    local ok, err = pcall(f)
    if ok then print("[OK]   " .. label) else print("[ERROR] " .. label .. "\n       " .. tostring(err)) end
    return ok
end
"""

# Czesc 2: uruchomienie PoB (to samo, co zrobil test_pob.py).
LUA_INIT = r"""
arg = arg or {}
dofile(POB_PATH .. "Launch.lua")
runCallback("OnInit")
runCallback("OnFrame")
local startMsg = mainObject and mainObject.promptMsg
if startMsg then
    error("PoB reported an error during startup:\n" .. tostring(startMsg), 0)
end
"""

# Czesc 3: import postaci tymi samymi funkcjami, ktore PoB wywoluje przyciskiem "Import".
LUA_IMPORT = r"""
function CheckLaunchError(where)
    local m = mainObject and mainObject.promptMsg
    if m then
        error("PoB reported an error (" .. where .. "):\n" .. tostring(m), 0)
    end
end

function ReadStats(build)
    local o = build.calcsTab.mainOutput or {}
    return {
        DPS = o.CombinedDPS or o.TotalDPS or 0,
        EHP = o.TotalEHP or 0,
        LIFE = o.Life or 0,
        ES = o.EnergyShield or 0,
        MANA = o.Mana or 0,
        FIRE = o.FireResist or 0,
        COLD = o.ColdResist or 0,
        LIGHT = o.LightningResist or 0,
        CHAOS = o.ChaosResist or 0,
        FIRE_T = o.FireResistTotal or ((o.FireResist or 0) + (o.FireResistOverCap or 0)),
        COLD_T = o.ColdResistTotal or ((o.ColdResist or 0) + (o.ColdResistOverCap or 0)),
        LIGHT_T = o.LightningResistTotal or ((o.LightningResist or 0) + (o.LightningResistOverCap or 0)),
        CHAOS_T = o.ChaosResistTotal or ((o.ChaosResist or 0) + (o.ChaosResistOverCap or 0)),
    }
end

function PickBestSkill(build)
    local sk = build.skillsTab.socketGroupList
    local origGroup = build.mainSocketGroup
    local origIdx = sk[origGroup] and sk[origGroup].mainActiveSkill
    local best = { dps = 0 }
    SKILL_LIST = {}
    for g, group in ipairs(sk) do
        if group.enabled ~= false then
            local n = #(group.displaySkillList or {})
            for i = 1, n do
                local ok, err = pcall(function()
                    build.mainSocketGroup = g
                    group.mainActiveSkill = i
                    build.calcsTab:BuildOutput()
                    local o = build.calcsTab.mainOutput or {}
                    local dps = o.CombinedDPS or o.TotalDPS or 0
                    local entry = group.displaySkillList and group.displaySkillList[i]
                    local ge = entry and entry.activeEffect and entry.activeEffect.grantedEffect
                    print(string.format("  umiejetnosc %d.%d %s: DPS %.0f", g, i, tostring(ge and ge.name or "?"), dps))
                    SKILL_LIST[#SKILL_LIST + 1] = { g = g, i = i, name = tostring(ge and ge.name or "?"), dps = dps }
                    if dps > best.dps then best = { dps = dps, g = g, i = i } end
                end)
                if not ok then print("  blad przy umiejetnosci " .. g .. "." .. i .. ": " .. tostring(err)) end
            end
        end
    end
    if best.g then
        build.mainSocketGroup = best.g
        sk[best.g].mainActiveSkill = best.i
        CURRENT_SKILL = { g = best.g, i = best.i }
    else
        build.mainSocketGroup = origGroup
        CURRENT_SKILL = { g = origGroup, i = origIdx or 1 }
        if sk[origGroup] and origIdx then sk[origGroup].mainActiveSkill = origIdx end
    end
    build.calcsTab:BuildOutput()
end

function ListSkills(build)
    local list = {}
    for g, group in ipairs(build.skillsTab.socketGroupList) do
        if group.enabled ~= false then
            for i, entry in ipairs(group.displaySkillList or {}) do
                local ge = entry.activeEffect and entry.activeEffect.grantedEffect
                list[#list + 1] = { g = g, i = i, name = tostring(ge and ge.name or "?") }
            end
        end
    end
    return list
end

local function evalSkill(build, g, i)
    build.mainSocketGroup = g
    build.skillsTab.socketGroupList[g].mainActiveSkill = i
    build.calcsTab:BuildOutput()
    local o = build.calcsTab.mainOutput or {}
    return o.CombinedDPS or o.TotalDPS or 0
end

-- Wybor glownej umiejetnosci BEZ przeszukiwania calego buildu:
-- 1) przypieta przez uzytkownika (po nazwie), 2) najlepsza w grupie, ktora PoB uznal za glowna,
-- 3) dopiero gdy tam nic nie zadaje obrazen - przeglad wszystkich.
function ChooseSkill(build, pinned)
    SKILL_LIST = ListSkills(build)
    local origGroup = build.mainSocketGroup
    local chosen
    if pinned and pinned ~= "" then
        for _, s in ipairs(SKILL_LIST) do
            if s.name == pinned and s.g == origGroup then chosen = s break end
        end
        if not chosen then
            for _, s in ipairs(SKILL_LIST) do
                if s.name == pinned then chosen = s break end
            end
        end
    end
    if not chosen then
        local bestDps = 0
        for pass = 1, 2 do
            for _, s in ipairs(SKILL_LIST) do
                if pass == 2 or s.g == origGroup then
                    s.dps = evalSkill(build, s.g, s.i)
                    if s.dps > bestDps then chosen, bestDps = s, s.dps end
                end
            end
            if chosen then break end
        end
    end
    if chosen then
        chosen.dps = evalSkill(build, chosen.g, chosen.i)
        CURRENT_SKILL = { g = chosen.g, i = chosen.i }
    else
        build.mainSocketGroup = origGroup
        build.calcsTab:BuildOutput()
        CURRENT_SKILL = { g = origGroup, i = 1 }
    end
end

-- Pelny przeglad wszystkich umiejetnosci (na zadanie): uzupelnia DPS na liscie i wybiera najlepsza.
function ScanSkills()
    local build = mainObject.main.modes["BUILD"]
    SKILL_LIST = ListSkills(build)
    local best, bestDps = nil, 0
    for _, s in ipairs(SKILL_LIST) do
        s.dps = evalSkill(build, s.g, s.i)
        if s.dps > bestDps then best, bestDps = s, s.dps end
    end
    if best then
        evalSkill(build, best.g, best.i)
        CURRENT_SKILL = { g = best.g, i = best.i }
    end
    return ReadStats(build)
end

function ScanSkillsSafe()
    local ok, res = xpcall(ScanSkills, debug.traceback)
    if not ok then error(res, 0) end
    return res
end

function ImportCharacter(charJson, itemsJson, passivesJson, pinned)
    local dkjson = require("dkjson")
    local charInfo = dkjson.decode(charJson)
    local items = dkjson.decode(itemsJson)
    local passives = dkjson.decode(passivesJson)

    mainObject.main:SetMode("BUILD", false, "PoE Assistant")
    runCallback("OnFrame")
    CheckLaunchError("tworzenie buildu")
    local build = mainObject.main.modes["BUILD"]
    if not build or not build.configTab then
        error("Build was not initialised (main.mode=" .. tostring(mainObject.main.mode) ..
              ", newMode=" .. tostring(mainObject.main.newMode) .. ")", 0)
    end
    local tab = build.importTab

    passives.bandit_choice = passives.bandit_choice or build.configTab.input.bandit
    passives.pantheon_major = passives.pantheon_major or build.configTab.input.pantheonMajorGod
    passives.pantheon_minor = passives.pantheon_minor or build.configTab.input.pantheonMinorGod

    local treeData = copyTable(charInfo)
    treeData.passives = passives
    treeData.jewels = passives.items
    tab:ImportPassiveTreeAndJewels(treeData, true)

    local itemData = copyTable(charInfo)
    itemData.equipment = items.items
    itemData.guardian = items.guardian
    tab:ImportItemsAndSkills(itemData, true, true, true)

    runCallback("OnFrame")
    CheckLaunchError("po imporcie")
    build.calcsTab:BuildOutput()
    pcall(function()
        local nItems = 0
        for _ in pairs(build.itemsTab.items) do nItems = nItems + 1 end
        print("zaimportowane przedmioty: " .. nItems)
        local sk = build.skillsTab.socketGroupList
        print("grupy umiejetnosci: " .. #sk .. ", glowna: " .. tostring(build.mainSocketGroup))
        for i, g in ipairs(sk) do
            local names = {}
            for _, gem in ipairs(g.gemList or {}) do names[#names + 1] = tostring(gem.nameSpec or "?") end
            print(string.format("  grupa %d%s: %s", i, (i == build.mainSocketGroup) and " (GLOWNA)" or "", table.concat(names, ", ")))
        end
        local env = build.calcsTab.mainEnv
        local ms = env and env.player and env.player.mainSkill
        local ge = ms and ms.activeEffect and ms.activeEffect.grantedEffect
        print("aktywna umiejetnosc: " .. tostring(ge and ge.name))
    end)
    local okPick, errPick = pcall(ChooseSkill, build, pinned)
    if not okPick then print("skill selection error: " .. tostring(errPick)) end
    pcall(function()
        local ms = build.calcsTab.mainEnv.player.mainSkill
        print("WYBRANA umiejetnosc: " .. tostring(ms.activeEffect.grantedEffect.name))
    end)
    return ReadStats(build)
end

function ImportCharacterSafe(charJson, itemsJson, passivesJson, pinned)
    local ok, res = xpcall(function() return ImportCharacter(charJson, itemsJson, passivesJson, pinned) end, debug.traceback)
    if not ok then error(res, 0) end
    return res
end

function GetSkillsJson()
    local dkjson = require("dkjson")
    return dkjson.encode({ skills = SKILL_LIST or {}, current = CURRENT_SKILL or {} })
end

function SelectSkill(g, i)
    local build = mainObject.main.modes["BUILD"]
    local sk = build.skillsTab.socketGroupList
    build.mainSocketGroup = g
    sk[g].mainActiveSkill = i
    build.calcsTab:BuildOutput()
    CURRENT_SKILL = { g = g, i = i }
    local o = build.calcsTab.mainOutput or {}
    for _, s in ipairs(SKILL_LIST or {}) do
        if s.g == g and s.i == i then s.dps = o.CombinedDPS or o.TotalDPS or 0 end
    end
    return ReadStats(build)
end

local EXTRA_KEYS = { "Armour", "Evasion", "BlockChance", "SpellBlockChance", "SpellSuppressionChance",
                     "Str", "Dex", "Int", "CritChance" }
function Summ(o)
    local s = {
        dps = o.CombinedDPS or o.TotalDPS or 0,
        ehp = o.TotalEHP or 0,
        life = o.Life or 0,
        es = o.EnergyShield or 0,
        mana = o.Mana or 0,
        fire = o.FireResist or 0,
        cold = o.ColdResist or 0,
        light = o.LightningResist or 0,
        chaos = o.ChaosResist or 0,
        fire_total = o.FireResistTotal or ((o.FireResist or 0) + (o.FireResistOverCap or 0)),
        cold_total = o.ColdResistTotal or ((o.ColdResist or 0) + (o.ColdResistOverCap or 0)),
        light_total = o.LightningResistTotal or ((o.LightningResist or 0) + (o.LightningResistOverCap or 0)),
        chaos_total = o.ChaosResistTotal or ((o.ChaosResist or 0) + (o.ChaosResistOverCap or 0)),
        fire_max = o.FireResistMax or 75,
        cold_max = o.ColdResistMax or 75,
        light_max = o.LightningResistMax or 75,
    }
    for _, k in ipairs(EXTRA_KEYS) do s[k] = tonumber(o[k]) or 0 end
    return s
end

function MakeItem(raw)
    -- W tej wersji PoB przedmiot tworzy sie przez new("Item"):Item(tekst)
    local item
    pcall(function() item = new("Item"):Item(raw) end)
    if not (item and item.base) then
        local alt = new("Item"):Item()
        if pcall(function() alt:ParseRaw(raw) end) then item = alt end
    end
    if not item then error("PoB could not create the item", 0) end
    if not item.base then
        error("PoB did not recognise the item: " .. tostring(item.baseName or item.name or "?"), 0)
    end
    if item.NormaliseQuality then item:NormaliseQuality() end
    return item
end

-- usuwa z tekstu przedmiotu pierwsza linie zawierajaca dany modyfikator
function RemoveLine(raw, needle)
    local lines, out, removed = {}, {}, false
    for l in (raw .. "\n"):gmatch("(.-)\n") do lines[#lines + 1] = l end
    for idx, l in ipairs(lines) do
        if not removed and idx > 3 and l:find(needle, 1, true) then
            removed = true
        else
            out[#out + 1] = l
        end
    end
    return table.concat(out, "\n"), removed
end

function AnalyzeMods(raw, slotName)
    local dkjson = require("dkjson")
    local build = mainObject and mainObject.main and mainObject.main.modes["BUILD"]
    if not (build and build.calcsTab and build.calcsTab.mainOutput) then error("No character loaded", 0) end
    raw = raw:gsub("\r", "")
    local item = MakeItem(raw)
    local calcFunc = build.calcsTab:GetMiscCalculator()
    local full = Summ(calcFunc({ repSlotName = slotName, repItem = item }))
    local mods = {}
    local function scan(list, kind)
        for _, ml in ipairs(list or {}) do
            local line = ml.line
            if line and #line > 0 then
                local newRaw, removed = RemoveLine(raw, line)
                if removed then
                    local ok, res = pcall(function()
                        local it = MakeItem(newRaw)
                        return Summ(calcFunc({ repSlotName = slotName, repItem = it }))
                    end)
                    if ok and res then mods[#mods + 1] = { line = line, kind = kind, without = res } end
                end
            end
        end
    end
    scan(item.explicitModLines, "explicit")
    scan(item.implicitModLines, "implicit")
    return dkjson.encode({ rarity = item.rarity, full = full, mods = mods })
end

function AnalyzeModsSafe(raw, slotName)
    local ok, res = xpcall(function() return AnalyzeMods(raw, slotName) end, debug.traceback)
    if not ok then error(res, 0) end
    return res
end


function S2(o)
    return {
        dps = o.CombinedDPS or o.TotalDPS or 0, ehp = o.TotalEHP or 0, life = o.Life or 0,
        fire = o.FireResist or 0, cold = o.ColdResist or 0, light = o.LightningResist or 0, chaos = o.ChaosResist or 0,
    }
end

-- Podpowiedzi ulepszen: enchanty (helm/rekawice/buty), pomazanie (amulet), dodanie modyfikatora (craft).
function SuggestUpgrades(raw, slotName)
    local dkjson = require("dkjson")
    local build = mainObject and mainObject.main and mainObject.main.modes["BUILD"]
    if not (build and build.calcsTab and build.calcsTab.mainOutput) then error("No character loaded", 0) end
    raw = raw:gsub("\r", "")
    local item = MakeItem(raw)
    local calcFunc = build.calcsTab:GetMiscCalculator()
    local baseOut = calcFunc({ repSlotName = slotName, repItem = item })
    local t0 = os.clock()
    local BUDGET = 30 -- sekundy na calosc
    local function timeLeft() return (os.clock() - t0) < BUDGET end

    local res = {
        base = S2(baseOut), rarity = item.rarity, item_level = item.itemLevel,
        base_type = item.base and item.base.type or "",
        enchants = {}, anoints = {}, prefixes = {}, suffixes = {},
        craftable = item.crafted and true or false, open_prefix = 0, open_suffix = 0,
        partial = false,
    }

    -- 1) Enchanty
    local okE, errE = pcall(function()
        if not item.enchantments then return end
        local sources = data.enchantmentSource or {}
        local function bestSource(tbl)
            local chosen
            for _, src in ipairs(sources) do if tbl[src.name] then chosen = src.name end end
            return chosen
        end
        local function tryLine(line, label)
            if not timeLeft() then res.partial = true return end
            local it = new("Item"):Item(item:BuildRaw())
            local first, second = line:match("([^/]+)/([^/]+)")
            if first then
                it.enchantModLines = { { crafted = true, line = first }, { crafted = true, line = second } }
            else
                it.enchantModLines = { { crafted = true, line = line } }
            end
            it:BuildAndParseRaw()
            local out = calcFunc({ repSlotName = slotName, repItem = it })
            res.enchants[#res.enchants + 1] = { label = label or line, new = S2(out) }
        end
        local haveSkills = true
        for _, src in ipairs(sources) do
            if item.enchantments[src.name] then haveSkills = false break end
        end
        if haveSkills then
            local used = {}
            for _, g in ipairs(build.skillsTab.socketGroupList) do
                for _, gem in ipairs(g.gemList or {}) do
                    if gem.gemData then
                        for _, ge in ipairs(gem.gemData.grantedEffectList or {}) do
                            if not ge.support then used[ge.name] = true end
                        end
                    end
                end
            end
            for skillName, tbl in pairs(item.enchantments) do
                if used[skillName] then
                    local src = bestSource(tbl)
                    for _, line in ipairs(src and tbl[src] or {}) do tryLine(line, skillName .. ": " .. line) end
                end
            end
        else
            local src = bestSource(item.enchantments)
            for _, line in ipairs(src and item.enchantments[src] or {}) do tryLine(line) end
        end
    end)
    if not okE then res.enchant_error = tostring(errE) end

    -- 2) Pomazanie amuletu
    local okA, errA = pcall(function()
        local b = item.base
        if not (b and not b.cannotBeAnointed and b.subType ~= "Talisman" and (item.canBeAnointed or b.type == "Amulet")) then return end
        local nodes, anyRecipe = {}, false
        for id, node in pairs(build.spec.tree.nodes) do
            if node.type == "Notable" and not node.ascendancyName and not build.spec.allocNodes[id] then
                nodes[#nodes + 1] = node
                if node.recipe then anyRecipe = true end
            end
        end
        for _, node in ipairs(nodes) do
            if (not anyRecipe) or node.recipe then
                if not timeLeft() then res.partial = true break end
                local out = calcFunc({ addNodes = { [node] = true } })
                res.anoints[#res.anoints + 1] = { label = node.dn, new = S2(out) }
            end
        end
    end)
    if not okA then res.anoint_error = tostring(errA) end

    -- 3) Craft: pojedyncze modyfikatory, najlepsze pary oraz zamiana najslabszego modyfikatora
    local okC, errC = pcall(function()
        if not (item.crafted and item.rarity == "RARE" and item.affixes) then return end
        res.combos = {}
        res.replace = {}
        local quality = (main and main.defaultItemAffixQuality) or 0.5
        local ilvl = item.itemLevel or 100
        local lists = { Prefix = "prefixes", Suffix = "suffixes" }

        local function limitOf(listName) return item[listName].limit or ((item.affixLimit or 6) / 2) end
        local function openSlots(listName)
            local open = {}
            for i = 1, limitOf(listName) do
                local e = item[listName][i]
                if not e or e.modId == "None" then open[#open + 1] = i end
            end
            return open
        end
        local function groupsAndTags(skip)
            local excl, tags = {}, {}
            for _, listName in pairs(lists) do
                for i = 1, limitOf(listName) do
                    if not (skip and skip[listName] == i) then
                        local e = item[listName][i]
                        local mod = e and item.affixes[e.modId]
                        if mod then
                            if mod.group then excl[mod.group] = true end
                            for _, tag in ipairs(mod.tags or {}) do tags[tag] = true end
                        end
                    end
                end
            end
            return excl, tags
        end
        local function pool(modType, excl, tags)
            local bestByGroup = {}
            for modId, mod in pairs(item.affixes) do
                if mod.type == modType and not excl[mod.group] and not item:CheckIfModIsDelve(mod)
                   and mod.level <= ilvl and item:CanHaveMod(mod, tags) then
                    local key = mod.group or modId
                    local cur = bestByGroup[key]
                    if not cur or mod.level > item.affixes[cur].level then bestByGroup[key] = modId end
                end
            end
            local list = {}
            for _, modId in pairs(bestByGroup) do list[#list + 1] = modId end
            return list
        end
        local function modLabel(modId) return table.concat(item.affixes[modId], " / ") end
        local function evalEdits(edits)
            local it = new("Item"):Item(item:BuildRaw())
            for _, ed in ipairs(edits) do it[ed[1]][ed[2]] = { modId = ed[3], range = quality } end
            it:Craft()
            return S2(calcFunc({ repSlotName = slotName, repItem = it }))
        end
        local function score(o)
            local function pc(n, b) if b and b ~= 0 then return (n - b) / b * 100 end return 0 end
            return pc(o.dps, res.base.dps) + pc(o.ehp, res.base.ehp)
        end

        local open = { Prefix = openSlots("prefixes"), Suffix = openSlots("suffixes") }
        res.open_prefix, res.open_suffix = #open.Prefix, #open.Suffix

        -- 3a) pojedyncze modyfikatory na wolne miejsca
        local singles = { Prefix = {}, Suffix = {} }
        local excl0, tags0 = groupsAndTags(nil)
        for modType, listName in pairs(lists) do
            if #open[modType] > 0 then
                for _, modId in ipairs(pool(modType, excl0, tags0)) do
                    if not timeLeft() then res.partial = true break end
                    local ok, out = pcall(evalEdits, { { listName, open[modType][1], modId } })
                    if ok and out then
                        local e = { label = modLabel(modId), tier_level = item.affixes[modId].level, new = out }
                        local target = (modType == "Prefix") and res.prefixes or res.suffixes
                        target[#target + 1] = e
                        singles[modType][#singles[modType] + 1] = { modId = modId, score = score(out) }
                    end
                end
                table.sort(singles[modType], function(x, y) return x.score > y.score end)
            end
        end

        -- 3b) najlepsze pary (maks. 30 sprawdzen)
        local nPairs = 0
        local function tryPair(edits, idA, idB)
            if nPairs >= 30 or not timeLeft() then return end
            nPairs = nPairs + 1
            local ok, out = pcall(evalEdits, edits)
            if ok and out then
                res.combos[#res.combos + 1] = { label = modLabel(idA) .. "  +  " .. modLabel(idB), new = out }
            end
        end
        local TOP = 4
        if #open.Prefix >= 1 and #open.Suffix >= 1 then
            for i = 1, math.min(TOP, #singles.Prefix) do
                for j = 1, math.min(TOP, #singles.Suffix) do
                    local a, b = singles.Prefix[i].modId, singles.Suffix[j].modId
                    tryPair({ { "prefixes", open.Prefix[1], a }, { "suffixes", open.Suffix[1], b } }, a, b)
                end
            end
        end
        for modType, listName in pairs(lists) do
            if #open[modType] >= 2 then
                local sg = singles[modType]
                for i = 1, math.min(TOP, #sg) do
                    for j = i + 1, math.min(TOP, #sg) do
                        local a, b = sg[i].modId, sg[j].modId
                        if item.affixes[a].group ~= item.affixes[b].group then
                            tryPair({ { listName, open[modType][1], a }, { listName, open[modType][2], b } }, a, b)
                        end
                    end
                end
            end
        end

        -- 3c) brak wolnych miejsc: usun najslabszy modyfikator danego typu i wstaw najlepszy zamiennik
        for modType, listName in pairs(lists) do
            if #open[modType] == 0 and timeLeft() then
                local weakest
                for i = 1, limitOf(listName) do
                    local e = item[listName][i]
                    if e and e.modId ~= "None" and item.affixes[e.modId] then
                        local ok, out = pcall(evalEdits, { { listName, i, "None" } })
                        if ok and out then
                            local sc = score(out)
                            if not weakest or sc > weakest.score then weakest = { idx = i, modId = e.modId, score = sc } end
                        end
                    end
                end
                if weakest then
                    local excl, tags = groupsAndTags({ [listName] = weakest.idx })
                    local entries = {}
                    for _, modId in ipairs(pool(modType, excl, tags)) do
                        if not timeLeft() then res.partial = true break end
                        if modId ~= weakest.modId then
                            local ok, out = pcall(evalEdits, { { listName, weakest.idx, modId } })
                            if ok and out then
                                entries[#entries + 1] = { label = modLabel(modId), tier_level = item.affixes[modId].level, new = out }
                            end
                        end
                    end
                    res.replace[#res.replace + 1] = { type = modType, removed = modLabel(weakest.modId), entries = entries }
                end
            end
        end
    end)
    if not okC then res.craft_error = tostring(errC) end

    return dkjson.encode(res)
end

function SuggestUpgradesSafe(raw, slotName)
    local ok, r = xpcall(function() return SuggestUpgrades(raw, slotName) end, debug.traceback)
    if not ok then error(r, 0) end
    return r
end


local function stripCodes(str)
    str = str:gsub("%^x%x%x%x%x%x%x", "")
    str = str:gsub("%^%d", "")
    return str
end

-- Lista statystyk dokladnie taka, jak w bocznym panelu Path of Building.
function GetSidebar()
    local dkjson = require("dkjson")
    local build = mainObject and mainObject.main and mainObject.main.modes["BUILD"]
    if not (build and build.calcsTab and build.calcsTab.mainEnv) then error("No character loaded", 0) end
    build:RefreshStatList()
    local list = build.controls and build.controls.statBox and build.controls.statBox.list or {}
    local out = {}
    for _, e in ipairs(list) do
        local a, b = e[1], e[2]
        if type(a) == "string" and a ~= "" then
            a = stripCodes(a)
            local label, value
            if type(b) == "string" then
                label, value = a, stripCodes(b)
            else
                label, value = a:match("^(.-):%s*(.*)$")
                if not label then label, value = a, "" end
            end
            label = label:gsub(":%s*$", "")
            out[#out + 1] = { label = label, value = value }
        elseif #out > 0 and not out[#out].sep then
            out[#out + 1] = { sep = true }
        end
    end
    return dkjson.encode({ lines = out })
end

function GetSidebarSafe()
    local ok, r = xpcall(GetSidebar, debug.traceback)
    if not ok then error(r, 0) end
    return r
end

function AnalyzeEquipped(slotName)
    local dkjson = require("dkjson")
    local build = mainObject and mainObject.main and mainObject.main.modes["BUILD"]
    if not (build and build.calcsTab and build.calcsTab.mainOutput) then error("No character loaded", 0) end
    local slot = build.itemsTab.slots[slotName]
    local cur = slot and build.itemsTab.items[slot.selItemId]
    if not cur then return dkjson.encode({ empty = true }) end
    local raw = cur.raw or cur:BuildRaw()
    local analysis = dkjson.decode(AnalyzeMods(raw, slotName))
    return dkjson.encode({ name = cur.name, analysis = analysis })
end

function AnalyzeEquippedSafe(slotName)
    local ok, r = xpcall(function() return AnalyzeEquipped(slotName) end, debug.traceback)
    if not ok then error(r, 0) end
    return r
end

function CompareItem(raw, slotList)
    local dkjson = require("dkjson")
    local build = mainObject and mainObject.main and mainObject.main.modes["BUILD"]
    if not (build and build.calcsTab and build.calcsTab.mainOutput) then
        error("No character loaded", 0)
    end
    raw = raw:gsub("\r", "")
    local item = MakeItem(raw)
    local calcFunc = build.calcsTab:GetMiscCalculator()
    local base = build.calcsTab.mainOutput
    local results = {}
    for slotName in slotList:gmatch("[^,]+") do
        local out = calcFunc({ repSlotName = slotName, repItem = item })
        local slot = build.itemsTab.slots[slotName]
        local cur = slot and build.itemsTab.items[slot.selItemId]
        results[#results + 1] = {
            slot = slotName, equipped = cur and cur.name or nil, item = item.name,
            base = Summ(base), new = Summ(out),
        }
    end
    return dkjson.encode(results)
end

function CompareItemSafe(raw, slotList)
    local ok, res = xpcall(function() return CompareItem(raw, slotList) end, debug.traceback)
    if not ok then error(res, 0) end
    return res
end
"""


class PoBEngine:
    def __init__(self, core_dir, log=print):
        self.core = os.path.abspath(core_dir)
        os.chdir(self.core)   # PoB reads its files relative to this folder
        self.lua = LuaRuntime(unpack_returned_tuples=True, encoding="utf-8")
        g = self.lua.globals()
        g.POB_PATH = self._lua_path(self.core)
        g.print = lambda *a: log(" ".join(str(x) for x in a))
        try:
            self.lua.execute(LUA_BASE)
            self.lua.execute(LUA_INIT)
            self.lua.execute(LUA_IMPORT)
        except LuaError as e:
            raise PoBError(f"Could not start PoB: {e}")

    @staticmethod
    def _lua_path(path):
        """Path used inside Lua. Lua's io.open cannot open non-ASCII paths on Windows (e.g. a user name with
        letters like 'ł'), so in that case relative paths are used - the working directory is the core folder."""
        try:
            path.encode("ascii")
        except UnicodeEncodeError:
            return "./"
        return path.replace("\\", "/") + "/"

    def import_character(self, char_info, items_json, passives_json, pinned_skill=""):
        """char_info: wpis z listy postaci (slownik). items_json / passives_json: surowy tekst odpowiedzi serwera.
        pinned_skill: nazwa umiejetnosci wybranej przez uzytkownika (puste = domyslny wybor w glownej grupie)."""
        try:
            out = self.lua.globals().ImportCharacterSafe(json.dumps(char_info), items_json, passives_json,
                                                          pinned_skill or "")
        except LuaError as e:
            raise PoBError(f"Character import failed:\n{e}")
        return {str(k): float(v) for k, v in out.items()}

    def skills(self):
        """Lista umiejetnosci z DPS oraz aktualnie wybrana: {'skills': [...], 'current': {...}}."""
        data = json.loads(self.lua.globals().GetSkillsJson())
        if not isinstance(data.get("current"), dict):
            data["current"] = {}
        if not isinstance(data.get("skills"), list):
            data["skills"] = []
        return data

    def select_skill(self, group, index):
        try:
            out = self.lua.globals().SelectSkill(int(group), int(index))
        except LuaError as e:
            raise PoBError(f"Changing skill failed:\n{e}")
        return {str(k): float(v) for k, v in out.items()}

    def compare_item(self, raw_item_text, slot_names):
        """Porownuje przedmiot (tekst skopiowany z gry) z zalozonym w podanych slotach PoB."""
        try:
            text = self.lua.globals().CompareItemSafe(raw_item_text, ",".join(slot_names))
        except LuaError as e:
            raise PoBError(str(e))
        return json.loads(text)

    def analyze_mods(self, raw_item_text, slot_name):
        """Dla kazdego modyfikatora przedmiotu liczy build bez niego (do oceny, ile on daje)."""
        try:
            text = self.lua.globals().AnalyzeModsSafe(raw_item_text, slot_name)
        except LuaError as e:
            raise PoBError(str(e))
        data = json.loads(text)
        if not isinstance(data.get("mods"), list):
            data["mods"] = []
        return data

    def suggest_upgrades(self, raw_item_text, slot_name):
        """Enchanty, pomazania i mozliwe dodatkowe modyfikatory dla przedmiotu (ranking wg wplywu na build)."""
        try:
            text = self.lua.globals().SuggestUpgradesSafe(raw_item_text, slot_name)
        except LuaError as e:
            raise PoBError(str(e))
        return json.loads(text)

    def sidebar(self):
        """Statystyki w tej samej kolejnosci i formacie, co w bocznym panelu Path of Building."""
        try:
            text = self.lua.globals().GetSidebarSafe()
        except LuaError as e:
            raise PoBError(str(e))
        lines = json.loads(text).get("lines")
        return lines if isinstance(lines, list) else []

    def scan_skills(self):
        """Przeglad wszystkich umiejetnosci (liczy DPS kazdej) - tylko na zadanie."""
        try:
            out = self.lua.globals().ScanSkillsSafe()
        except LuaError as e:
            raise PoBError(f"Skill scan failed:\n{e}")
        return {str(k): float(v) for k, v in out.items()}

    def analyze_equipped(self, slot_name):
        """Modyfikatory aktualnie zalozonego przedmiotu w slocie (z wartoscia kazdego z nich)."""
        try:
            text = self.lua.globals().AnalyzeEquippedSafe(slot_name)
        except LuaError as e:
            raise PoBError(str(e))
        return json.loads(text)