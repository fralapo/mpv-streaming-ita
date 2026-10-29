-- Qualità degli stream HLS (StreamingCommunity e simili) con più versioni del video.
-- Automatica di default: non supera quello che la finestra può mostrare e scende se la connessione non regge.
-- A mano: menu Qualità (tasto destro o pulsante nella barra) oppure il tasto Q.
-- Serve hls-bitrate=no in mpv.conf, così mpv espone ogni versione come traccia video.
local mp = require 'mp'
local utils = require 'mp.utils'

local opts = {
    safety = 0.7,    -- uso al massimo il 70% della banda misurata
    low_cache = 6,   -- sotto questi secondi di buffer si scende subito
    up_cache = 25,   -- per salire servono almeno questi secondi di buffer
    cooldown = 15,   -- secondi minimi tra due cambi automatici
    up_block = 60,   -- dopo una discesa non si risale per questi secondi
}
require('mp.options').read_options(opts, "quality")

local mode = "auto" -- "auto" oppure l'altezza massima scelta a mano (1080, 720, 480...)
local variants = {} -- dalla più alta alla più bassa: {id, w, h, bitrate}
local speed = nil   -- banda stimata in bit/s
local last_switch, last_down = 0, -1e9
-- Dopo apertura, salti e cambi di qualità il buffer riparte da zero: in quei secondi non è segno di rete lenta
local refill_until = 0

local function bitrate_of(t)
    return t["hls-bitrate"] or t["demux-bitrate"] or ((t["demux-w"] or 0) * (t["demux-h"] or 0) * 2)
end

local function load_variants()
    variants = {}
    for _, t in ipairs(mp.get_property_native("track-list") or {}) do
        if t.type == "video" and not t.image and not t.albumart then
            table.insert(variants, { id = t.id, w = t["demux-w"] or 0, h = t["demux-h"] or 0, bitrate = bitrate_of(t) })
        end
    end
    table.sort(variants, function(a, b) return a.bitrate > b.bitrate end)
end

local function current_index()
    local vid = mp.get_property_number("vid")
    for i, v in ipairs(variants) do if v.id == vid then return i end end
    return nil
end

-- Nome della versione dalla larghezza (1920 → 1080p), perché molti video sono in 2:1 e l'altezza inganna
local function label(v)
    local std = { { 3840, 2160 }, { 2560, 1440 }, { 1920, 1080 }, { 1280, 720 }, { 854, 480 }, { 640, 360 } }
    for _, s in ipairs(std) do
        if v.w >= s[1] * 0.95 then return s[2] .. "p" end
    end
    return v.h .. "p"
end

local function label_height(v) return tonumber(label(v):match("%d+")) end

-- Indice della versione più bassa ancora nitida nella finestra attuale (in un popup piccolo basta meno)
local function window_cap()
    local width = mp.get_property_number("osd-width", 0)
    if width <= 0 then return 1 end
    local cap = 1
    for i, v in ipairs(variants) do
        if v.w >= width * 0.9 then cap = i end
    end
    return cap
end

local function switch_to(i, why)
    local v = variants[i]
    if not v or v.id == mp.get_property_number("vid") then return end
    local old = current_index()
    mp.set_property_number("vid", v.id)
    last_switch = mp.get_time()
    refill_until = last_switch + 20
    if old and i > old then last_down = last_switch end
    local prefix = mode == "auto" and "Qualità automatica: " or "Qualità: "
    mp.osd_message(prefix .. label(v) .. (why and ("  ·  " .. why) or ""), 2.5)
    mp.msg.info(string.format("vid=%d %s (%s), banda stimata %s", v.id, label(v), why or "scelta",
        speed and string.format("%.1f Mbit/s", speed / 1e6) or "non ancora misurata"))
end

-- Indice della versione più alta che la banda stimata regge (senza stima: nessun limite)
local function bandwidth_fit()
    if not speed then return 1 end
    local fit = #variants
    for i = #variants, 1, -1 do
        if variants[i].bitrate <= speed * opts.safety then fit = i end
    end
    return fit
end

-- Scelta automatica: la più bassa tra quella che serve alla finestra e quella che la banda regge
local function auto_target()
    return math.max(window_cap(), bandwidth_fit())
end

local function evaluate()
    if mode ~= "auto" or #variants < 2 then return end
    local now = mp.get_time()
    local cur = current_index() or 1
    local cache = mp.get_property_number("demuxer-cache-duration", 0)
    local stalled = mp.get_property_bool("paused-for-cache")
    local draining = cache < opts.low_cache and not mp.get_property_bool("demuxer-cache-idle")

    -- Si blocca o il buffer si svuota a regime: scendo di un gradino subito
    if (stalled or draining) and now > refill_until and cur < #variants then
        switch_to(cur + 1, "connessione lenta")
        return
    end
    if now - last_switch < opts.cooldown then return end

    if window_cap() > cur then
        -- la finestra è diventata più piccola (es. popup): basta una versione più leggera
        switch_to(window_cap(), "adattata alla finestra")
    elseif bandwidth_fit() > cur and cache < opts.up_cache and now > refill_until then
        -- la stima di banda da sola può sbagliare per difetto: si scende solo se il buffer non è comodo
        switch_to(cur + 1, "adattata alla rete")
    elseif auto_target() < cur and cache >= opts.up_cache and now - last_down > opts.up_block then
        switch_to(cur - 1, "connessione buona")
    end
end

mp.register_event("playback-restart", function() refill_until = mp.get_time() + 20 end)

-- Banda: cache-speed vale solo mentre si scarica, quindi la media ignora i momenti a buffer pieno
local function sample_speed()
    if mp.get_property_bool("demuxer-cache-idle") then return end
    local bps = (mp.get_property_number("cache-speed", 0) or 0) * 8
    if bps < 1e5 then return end -- i primi istanti di una richiesta non dicono nulla
    speed = speed and (speed * 0.7 + bps * 0.3) or bps
end

local function set_mode(m)
    load_variants()
    if #variants < 2 then
        mp.osd_message("Questo video ha una sola qualità", 2)
        return
    end
    mode = m
    last_switch = 0
    local pick
    if m == "auto" then
        pick = auto_target()
    else
        local h = tonumber(m) or 0
        pick = #variants
        for i = #variants, 1, -1 do
            if label_height(variants[i]) <= h then pick = i end
        end
    end
    if variants[pick].id == mp.get_property_number("vid") then
        mp.osd_message((m == "auto" and "Qualità automatica: " or "Qualità: ") .. label(variants[pick]), 2)
    end
    switch_to(pick)
end

local function open_menu()
    load_variants()
    if #variants < 2 then
        mp.osd_message("Questo video ha una sola qualità", 2)
        return
    end
    local cur = variants[current_index() or 1]
    local items = { {
        title = "Automatica",
        hint = mode == "auto" and label(cur) or nil,
        active = mode == "auto",
        value = { "script-message-to", "quality", "set", "auto" },
    } }
    for _, v in ipairs(variants) do
        table.insert(items, {
            title = label(v),
            hint = string.format("%.1f Mbit/s", v.bitrate / 1e6),
            active = mode ~= "auto" and v.id == cur.id,
            value = { "script-message-to", "quality", "set", tostring(label_height(v)) },
        })
    end
    local footnote = speed and string.format("Connessione misurata: %.0f Mbit/s", speed / 1e6) or nil
    mp.commandv("script-message-to", "uosc", "open-menu", utils.format_json({
        type = "quality", title = "Qualità", footnote = footnote, items = items,
    }))
end

mp.register_script_message("set", set_mode)
mp.add_key_binding(nil, "menu", open_menu)

mp.register_event("file-loaded", function()
    mode, speed, last_switch, last_down = "auto", nil, 0, -1e9
    refill_until = mp.get_time() + 20
    load_variants()
    if #variants > 1 then
        mp.msg.info(string.format("%d qualità disponibili", #variants))
        -- prima scelta subito, in base alla finestra; poi la rete corregge
        switch_to(window_cap())
    end
end)

mp.observe_property("osd-width", "number", function() if #variants > 1 then evaluate() end end)
mp.add_periodic_timer(1, function()
    if #variants > 1 then
        sample_speed()
        evaluate()
    end
end)
