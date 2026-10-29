-- Salta opening/ending/recap segnalati come capitoli (generati da AniSkip o presenti nel file).
-- TAB salta il segmento corrente, A attiva il salto automatico. Nella barra dei controlli di uosc
-- compare un pulsante "Salta" solo mentre si è dentro un segmento saltabile.
local mp = require 'mp'
local options = require 'mp.options'
local utils = require 'mp.utils'

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

-- Pulsante gestito da uosc: nascosto finché non serve
local function set_button(ch)
    local data = {
        icon = "fast_forward",
        hide = ch == nil,
        badge = "TAB",
        tooltip = ch and ("Salta: " .. ch.title) or "Salta",
        command = "script-binding skip_chapters/skip-chapter",
    }
    mp.commandv("script-message-to", "uosc", "set-button", "skip", utils.format_json(data))
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
    if not ch or not is_skippable(ch.title) then
        set_button(nil)
        return
    end
    set_button(ch)
    if opts.auto == "yes" then
        mp.osd_message(ch.title .. " tra " .. opts.delay .. "s (TAB per saltare ora)", opts.delay)
        timer = mp.add_timeout(opts.delay, skip)
    else
        mp.osd_message("TAB per saltare: " .. ch.title, 6)
    end
end

local function toggle_auto()
    opts.auto = opts.auto == "yes" and "no" or "yes"
    local _, ch = current_chapter()
    if ch and is_skippable(ch.title) then
        on_chapter()
    else
        mp.osd_message("Salto automatico di opening e ending: " .. (opts.auto == "yes" and "attivo" or "disattivato"))
    end
end

mp.observe_property("chapter", "number", on_chapter)
-- uosc potrebbe non essere ancora pronto al primo invio: lo ripetiamo a caricamento finito
mp.register_event("file-loaded", on_chapter)
mp.add_forced_key_binding("TAB", "skip-chapter", skip)
mp.add_key_binding(nil, "toggle-auto", toggle_auto)
