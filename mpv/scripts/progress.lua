-- Avanzamento per chi avvia mpv senza IPC (StreamingCommunity tramite il server MCP di aw-cli).
-- MPV_PROGRESS_FILE: dove scrivere {pos, duration, percent, eof} ogni 15 s e alla chiusura.
-- MPV_START_AT: secondi da cui ripartire all'apertura.
local mp = require 'mp'
local utils = require 'mp.utils'

local out = os.getenv("MPV_PROGRESS_FILE")
local start_at = tonumber(os.getenv("MPV_START_AT") or "")
if not out or out == "" then return end

local eof = false

local function save()
    local pos = mp.get_property_number("time-pos")
    local dur = mp.get_property_number("duration")
    if not pos or not dur or dur <= 0 then return end
    local f = io.open(out .. ".tmp", "w")
    if not f then return end
    f:write(utils.format_json({ pos = pos, duration = dur, percent = pos / dur * 100, eof = eof }))
    f:close()
    os.rename(out .. ".tmp", out)
end

mp.register_event("file-loaded", function()
    if start_at and start_at > 0 then
        mp.commandv("seek", tostring(start_at), "absolute+exact")
        start_at = nil
    end
end)

mp.observe_property("eof-reached", "bool", function(_, v)
    -- torna false se dalla fine si riavvolge
    eof = v or false
    if eof then save() end
end)
mp.add_periodic_timer(15, save)
-- alla chiusura la posizione è ancora leggibile solo prima che il file venga scaricato
mp.add_hook("on_unload", 50, save)
