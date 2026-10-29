-- Gesti e velocità.
-- Tastiera: [ ] scorrono una scala di velocità, \ o Backspace tornano a 1x, tenere premuto → va a 2x finché lo tieni.
-- Mouse sul video: clic = pausa, doppio clic = popup, tenere premuto = 2x, premere e trascinare = sposta la finestra.
-- Opzioni in script-opts/gestures.conf.
local mp = require 'mp'
local options = require 'mp.options'

local opts = { boost = 2, hold_ms = 350, drag_px = 8, hints = 3 }
options.read_options(opts, "gestures")

local LADDER = { 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4 }
local ACCENT = "&HF7A6CB&" -- cba6f7 in BGR, lo stesso viola di uosc

local function fmt_speed(s)
    local txt = string.format("%.2f", s):gsub("0+$", ""):gsub("%.$", "")
    return txt:gsub("%.", ",") .. "×"
end

-- Indicatore fisso in alto a destra quando la velocità non è 1x
local badge = mp.create_osd_overlay("ass-events")
badge.res_x, badge.res_y = 1920, 1080
local boosting = false

local function update_badge()
    local s = mp.get_property_number("speed", 1)
    if math.abs(s - 1) < 0.001 then
        badge:remove()
        return
    end
    local label = boosting and ("▶▶ " .. fmt_speed(s)) or fmt_speed(s)
    badge.data = string.format("{\\an9\\pos(1885,95)\\fs38\\bord2.5\\shad0\\1c%s\\3c&H11111B&}%s", ACCENT, label)
    badge:update()
end
mp.observe_property("speed", "number", update_badge)

local function show_speed()
    mp.osd_message("Velocità " .. fmt_speed(mp.get_property_number("speed", 1)))
    mp.commandv("script-binding", "uosc/flash-speed")
end

local function step_speed(dir)
    local s = mp.get_property_number("speed", 1)
    local target = s
    if dir > 0 then
        for _, v in ipairs(LADDER) do if v > s + 0.001 then target = v; break end end
    else
        for i = #LADDER, 1, -1 do if LADDER[i] < s - 0.001 then target = LADDER[i]; break end end
    end
    mp.set_property_number("speed", target)
    show_speed()
end

mp.add_key_binding(nil, "speed-up", function() step_speed(1) end, { repeatable = true })
mp.add_key_binding(nil, "speed-down", function() step_speed(-1) end, { repeatable = true })
mp.add_key_binding(nil, "speed-reset", function()
    mp.set_property_number("speed", 1)
    show_speed()
end)

-- Accelerazione temporanea: parte anche da pausa e al rilascio ripristina tutto com'era
local saved_speed, saved_pause
local function boost_on()
    if boosting then return end
    saved_speed = mp.get_property_number("speed", 1)
    saved_pause = mp.get_property_bool("pause")
    boosting = true
    mp.set_property_number("speed", saved_speed >= opts.boost and saved_speed * 2 or opts.boost)
    mp.set_property_bool("pause", false)
    update_badge()
end

local function boost_off()
    if not boosting then return end
    boosting = false
    mp.set_property_number("speed", saved_speed or 1)
    if saved_pause then mp.set_property_bool("pause", true) end
    update_badge()
end

-- → : tocco = avanti 5s, tenuto = accelerato finché lo tieni
local right_timer, right_held = nil, false
local function seek_forward()
    mp.commandv("seek", "5", "exact")
    mp.commandv("script-binding", "uosc/flash-timeline")
end
mp.add_key_binding(nil, "right", function(e)
    if e.event == "down" then
        right_held = false
        right_timer = mp.add_timeout(opts.hold_ms / 1000, function()
            right_timer = nil
            right_held = true
            boost_on()
        end)
    elseif e.event == "up" then
        if right_timer then right_timer:kill(); right_timer = nil end
        if right_held then boost_off() else seek_forward() end
        right_held = false
    elseif e.event == "press" then
        seek_forward()
    end
end, { complex = true })

-- Mouse sul video
local click_timer, hold_timer, down_pos
local mouse_held, mouse_drag, skip_up = false, false, false

local function toggle_pause()
    mp.command("cycle pause")
end

local function on_mouse_move(_, pos)
    if not down_pos or not pos or mouse_held or mouse_drag then return end
    if math.abs(pos.x - down_pos.x) + math.abs(pos.y - down_pos.y) > opts.drag_px then
        mouse_drag = true
        if hold_timer then hold_timer:kill(); hold_timer = nil end
        -- trascinando si sposta la finestra (utile nel popup; a schermo intero non fa nulla)
        mp.commandv("begin-vo-dragging")
    end
end

local function release_mouse()
    mp.unobserve_property(on_mouse_move)
    if hold_timer then hold_timer:kill(); hold_timer = nil end
    down_pos = nil
end

mp.add_key_binding(nil, "click", function(e)
    if e.event == "down" then
        down_pos = mp.get_property_native("mouse-pos")
        mouse_held, mouse_drag = false, false
        mp.observe_property("mouse-pos", "native", on_mouse_move)
        hold_timer = mp.add_timeout(opts.hold_ms / 1000 + 0.1, function()
            hold_timer = nil
            mouse_held = true
            boost_on()
        end)
    elseif e.event == "up" then
        release_mouse()
        if mouse_held then
            boost_off()
        elseif skip_up then
            skip_up = false
        elseif not mouse_drag then
            -- aspetta il tempo del doppio clic prima di mettere in pausa
            local wait = mp.get_property_number("input-doubleclick-time", 300) / 1000
            click_timer = mp.add_timeout(wait, function() click_timer = nil; toggle_pause() end)
        end
        mouse_held, mouse_drag = false, false
    elseif e.event == "press" then
        toggle_pause()
    end
end, { complex = true })

mp.add_key_binding(nil, "double-click", function()
    if click_timer then click_timer:kill(); click_timer = nil end
    skip_up = true
    mp.commandv("run", "/home/lapo/.local/bin/mpv-pip-toggle")
end)

-- Suggerimento sui gesti nelle prime aperture
mp.register_event("file-loaded", function()
    local n = tonumber(opts.hints) or 0
    if n <= 0 then return end
    local path = mp.command_native({ "expand-path", "~~state/gestures-hints" })
    local f = io.open(path, "r")
    local seen = f and tonumber(f:read("*l")) or 0
    if f then f:close() end
    if seen >= n then return end
    f = io.open(path, "w")
    if f then f:write(tostring(seen + 1)); f:close() end
    mp.add_timeout(5, function()
        mp.osd_message("Tieni premuto → o il clic per 2×  ·  [ ] velocità  ·  tasto destro menu  ·  ? scorciatoie", 6)
    end)
end)
