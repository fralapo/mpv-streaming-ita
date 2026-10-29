-- Sottotitoli degli stream HLS (StreamingCommunity/vixsrc).
-- Il sito mette l'intero file WebVTT dell'episodio in un solo segmento HLS: mpv lo rilegge
-- e le battute si ripetono una sotto l'altra. Qui lo carichiamo direttamente come file esterno.
local mp = require 'mp'

local LANG = "^it" -- solo le tracce italiane, per non scaricare decine di playlist

local function resolve(base, uri)
    if uri:match("^https?://") then return uri end
    if uri:sub(1, 1) == "/" then return base:match("^(https?://[^/]+)") .. uri end
    return (base:gsub("[?#].*$", ""):gsub("[^/]*$", "")) .. uri
end

local function curl_args(url)
    local args = { "curl", "-sL", "--max-time", "15" }
    for _, h in ipairs(mp.get_property_native("http-header-fields") or {}) do
        table.insert(args, "-H"); table.insert(args, h)
    end
    local ua = mp.get_property("user-agent")
    if ua and ua ~= "" then table.insert(args, "-A"); table.insert(args, ua) end
    table.insert(args, url)
    return args
end

-- Scarica senza bloccare il player: la coroutine riprende quando curl finisce
local function fetch(url)
    local co = coroutine.running()
    mp.command_native_async({ name = "subprocess", args = curl_args(url), capture_stdout = true, playback_only = false },
        function(ok, r) coroutine.resume(co, ok and r and r.status == 0 and r.stdout or nil) end)
    return coroutine.yield()
end

local function attr(line, key)
    return line:match(key .. '="([^"]*)"') or line:match(key .. '=([^,]*)')
end

local function fix_subs(path)
    local master = fetch(path)
    if not master or not master:find("#EXTM3U") then return end
    local added = {}
    for line in master:gmatch("[^\r\n]+") do
        if line:find("^#EXT%-X%-MEDIA:") and attr(line, "TYPE") == "SUBTITLES" then
            local lang, name, uri = attr(line, "LANGUAGE") or "", attr(line, "NAME") or "", attr(line, "URI")
            if uri and lang:match(LANG) then
                local list_url = resolve(path, uri)
                local segments = {}
                for l in (fetch(list_url) or ""):gmatch("[^\r\n]+") do
                    if not l:find("^#") then table.insert(segments, l) end
                end
                -- Con più segmenti mpv li gestisce già bene: interveniamo solo sul segmento unico
                if #segments == 1 then
                    table.insert(added, { url = resolve(list_url, segments[1]), lang = lang, name = name })
                end
            end
        end
    end
    if #added == 0 or mp.get_property("path") ~= path then return end

    -- Ricorda la lingua della traccia scelta e seleziona il file esterno equivalente
    local current
    for _, t in ipairs(mp.get_property_native("track-list") or {}) do
        if t.type == "sub" and t.selected then current = t.lang end
    end
    for _, s in ipairs(added) do
        local flag = (current and s.lang == current) and "select" or "auto"
        mp.commandv("sub-add", s.url, flag, s.name .. " (file)", s.lang)
    end
    mp.msg.info(string.format("caricati %d sottotitoli italiani come file esterni", #added))
end

mp.register_event("file-loaded", function()
    local path = mp.get_property("path", "")
    if not path:match("^https?://") or mp.get_property("file-format") ~= "hls" then return end
    coroutine.wrap(fix_subs)(path)
end)
