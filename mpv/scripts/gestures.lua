-- Gesti e velocità.
-- Tastiera: s rallenta e d accelera di 0,1, r torna a 1x (anche [ ] - + \ e Backspace), tenere premuto → va a 2x finché lo tieni.
-- Mouse sul video: clic rapido = pausa, doppio clic = popup, tenere premuto = 2x (solo a schermo intero), premere e trascinare = sposta il popup.
-- Opzioni in script-opts/gestures.conf.
local mp = require 'mp'
local options = require 'mp.options'
local utils = require 'mp.utils'

local opts = { boost = 2, hold_ms = 350, drag_px = 8, hints = 3, wheel_gap = 0.3, speed_step = 0.1, wheel_rate = 0.12, click_max = 0.25 }
options.read_options(opts, "gestures")

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

-- Passi di 0,1 tra 0,1x e 4x, arrotondati per non accumulare errori (1,2999…)
local function step_speed(dir)
    local s = mp.get_property_number("speed", 1)
    local target = math.floor((s + dir * opts.speed_step) * 10 + 0.5) / 10
    target = math.max(0.1, math.min(4, target))
    mp.set_property_number("speed", target)
    show_speed()
end

mp.add_key_binding(nil, "speed-up", function() step_speed(1) end, { repeatable = true })
mp.add_key_binding(nil, "speed-down", function() step_speed(-1) end, { repeatable = true })
-- Rotella e touchpad: un gesto produce decine di eventi, quindi vale solo il primo.
-- Il gesto finisce quando gli eventi si fermano per wheel_gap secondi.
local function per_gesture(fn)
    local last = 0
    return function()
        local now = mp.get_time()
        if now - last > opts.wheel_gap then fn() end
        last = now
    end
end

-- Sulla velocità invece si continua a salire o scendere finché scorri, ma al massimo uno scatto ogni wheel_rate secondi
local function throttled(fn)
    local last = 0
    return function()
        local now = mp.get_time()
        if now - last >= opts.wheel_rate then
            last = now
            fn()
        end
    end
end

mp.add_key_binding(nil, "speed-wheel-up", throttled(function() step_speed(1) end))
mp.add_key_binding(nil, "speed-wheel-down", throttled(function() step_speed(-1) end))
local function seek_by(sec)
    mp.commandv("seek", tostring(sec), "exact")
    mp.commandv("script-binding", "uosc/flash-timeline")
end
mp.add_key_binding(nil, "seek-wheel-back", per_gesture(function() seek_by(-5) end))
mp.add_key_binding(nil, "seek-wheel-forward", per_gesture(function() seek_by(5) end))

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

local down_time, windowed, down_win = 0, false, nil

-- Posizione della finestra di questo mpv secondo Hyprland (nil se non disponibile)
local function window_pos()
    local r = mp.command_native({
        name = "subprocess", args = { "hyprctl", "clients", "-j" },
        capture_stdout = true, playback_only = false,
    })
    if not r or r.status ~= 0 then return nil end
    local clients = utils.parse_json(r.stdout or "")
    local pid = mp.get_property_number("pid")
    for _, c in ipairs(clients or {}) do
        if c.pid == pid and c.at then return c.at[1] .. "," .. c.at[2] end
    end
    return nil
end

-- Su Wayland, quando inizia lo spostamento della finestra mpv riceve subito un rilascio finto:
-- prima di mettere in pausa controlliamo che la finestra non si sia mossa e che il cursore sia sul video
local function was_real_click()
    if not windowed then return true end
    local hover = (mp.get_property_native("mouse-pos") or {}).hover
    if hover == false then return false end
    local now = window_pos()
    return not (down_win and now and now ~= down_win)
end

mp.add_key_binding(nil, "click", function(e)
    if e.event == "down" then
        down_pos = mp.get_property_native("mouse-pos")
        down_time = mp.get_time()
        mouse_held, mouse_drag = false, false
        mp.observe_property("mouse-pos", "native", on_mouse_move)
        -- Nel popup premere a lungo serve a spostarlo: il 2x tenendo premuto vale solo a schermo intero
        windowed = not mp.get_property_bool("fullscreen")
        down_win = windowed and window_pos() or nil
        if not windowed then
            hold_timer = mp.add_timeout(opts.hold_ms / 1000 + 0.1, function()
                hold_timer = nil
                mouse_held = true
                boost_on()
            end)
        end
    elseif e.event == "up" then
        release_mouse()
        -- Nel popup è il compositor a spostare la finestra e il cursore resta fermo rispetto al video:
        -- una pressione più lunga di un clic rapido è uno spostamento, non una pausa
        if windowed and mp.get_time() - down_time > opts.click_max then mouse_drag = true end
        if mouse_held then
            boost_off()
        elseif skip_up then
            skip_up = false
        elseif not mouse_drag then
            -- aspetta il tempo del doppio clic prima di mettere in pausa
            local wait = mp.get_property_number("input-doubleclick-time", 300) / 1000
            click_timer = mp.add_timeout(wait, function()
                click_timer = nil
                if was_real_click() then toggle_pause() end
            end)
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
        mp.osd_message("Tieni premuto → o il clic per 2×  ·  s d velocità, r = 1×  ·  tasto destro menu  ·  ? scorciatoie", 6)
    end)
end)
