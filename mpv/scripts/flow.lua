-- Flusso dell'episodio: avviso di ripresa, fine episodio con chiusura automatica annullabile.
-- Opzioni in script-opts/flow.conf.
local mp = require 'mp'
local options = require 'mp.options'

local opts = { auto_close = "yes", close_delay = 8 }
options.read_options(opts, "flow")

local function fmt(sec)
    sec = math.floor(sec)
    local h, m, s = math.floor(sec / 3600), math.floor(sec % 3600 / 60), sec % 60
    if h > 0 then return string.format("%d:%02d:%02d", h, m, s) end
    return string.format("%d:%02d", m, s)
end

-- Ripresa: dopo il primo posizionamento, se non si parte dall'inizio lo diciamo
local announced = false
mp.register_event("start-file", function() announced = false end)
mp.register_event("playback-restart", function()
    if announced then return end
    announced = true
    local pos = mp.get_property_number("time-pos", 0)
    if pos > 10 then
        mp.osd_message("Ripreso da " .. fmt(pos), 4)
    end
end)

-- Fine episodio: conto alla rovescia, ESC o qualsiasi riposizionamento lo annullano
local countdown, ticker
local function stop_countdown()
    if ticker then ticker:kill(); ticker = nil end
    if countdown then
        mp.remove_key_binding("flow-stay")
        countdown = nil
    end
end

local function start_countdown()
    stop_countdown()
    if opts.auto_close ~= "yes" then return end
    -- con altri file in coda mpv passa da solo al successivo
    local count, pos = mp.get_property_number("playlist-count", 1), mp.get_property_number("playlist-pos", 0)
    if pos + 1 < count then return end
    countdown = tonumber(opts.close_delay) or 8
    mp.add_forced_key_binding("ESC", "flow-stay", stop_countdown)
    local function tick()
        if not countdown then return end
        if countdown <= 0 then
            stop_countdown()
            mp.command("quit")
            return
        end
        mp.osd_message(string.format("Episodio finito. Chiusura tra %ds (ESC per restare)", countdown), 1.1)
        countdown = countdown - 1
    end
    tick()
    ticker = mp.add_periodic_timer(1, tick)
end

mp.observe_property("eof-reached", "bool", function(_, reached)
    if reached then start_countdown() else stop_countdown() end
end)
mp.register_event("end-file", stop_countdown)
