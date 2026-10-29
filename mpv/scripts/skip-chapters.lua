-- Salta opening/ending/recap segnalati come capitoli (generati da AniSkip o presenti nel file).
-- TAB salta il segmento corrente; con auto=yes in script-opts/skip-chapters.conf salta da solo.
local mp = require 'mp'
local options = require 'mp.options'

local opts = { auto = "no", delay = 3 }
options.read_options(opts, "skip-chapters")

local patterns = { "^op", "opening", "^ed", "ending", "recap", "intro", "outro", "preview" }

local function is_skippable(title)
    if not title then return false end
    title = title:lower()
    for _, p in ipairs(patterns) do
        if title:match(p) then return true end
    end
    return false
end

local function current_chapter()
    local idx = mp.get_property_number("chapter")
    local list = mp.get_property_native("chapter-list")
    if idx == nil or idx < 0 or not list then return nil end
    return idx, list[idx + 1], #list
end

local function skip()
    local idx, ch, total = current_chapter()
    if not ch or not is_skippable(ch.title) then
        mp.osd_message("Nessun segmento da saltare")
        return
    end
    if idx + 1 < total then
        mp.set_property_number("chapter", idx + 1)
    else
        mp.commandv("seek", "100", "absolute-percent")
    end
    mp.osd_message("Saltato: " .. ch.title)
end

local timer
local function on_chapter()
    if timer then timer:kill(); timer = nil end
    local _, ch = current_chapter()
    if not ch or not is_skippable(ch.title) then return end
    if opts.auto == "yes" then
        mp.osd_message(ch.title .. " tra " .. opts.delay .. "s (TAB per saltare ora)", opts.delay)
        timer = mp.add_timeout(opts.delay, skip)
    else
        mp.osd_message("TAB per saltare: " .. ch.title, 6)
    end
end

mp.observe_property("chapter", "number", on_chapter)
mp.add_forced_key_binding("TAB", "skip-chapter", skip)
