-- Popup video di mpv: fluttuante, fissato su tutti i desktop, sopra le altre finestre.
-- App-id dedicato (senza "mpv" nel nome) per restare fuori dalle regole centrate di Omarchy.
-- Si sposta con SUPER + trascina (tasto sinistro) e si ridimensiona con SUPER + tasto destro;
-- keep_aspect_ratio mantiene il 16:9.
o.window("^AnimePip$", {
  tag = "-default-opacity",
  float = true,
  pin = true,
  keep_aspect_ratio = true,
  no_initial_focus = true,
  no_dim = true,
  border_size = 0,
  rounding = 8,
  opacity = "1 1",
  size = { "(monitor_w*0.32)", "(monitor_w*0.32*9/16)" },
  move = { "(monitor_w-monitor_w*0.32-40)", "(monitor_h-monitor_w*0.32*9/16-40)" },
})

-- SUPER + CTRL + P: porta la finestra attiva dal desktop al popup (e viceversa).
-- Lo script ignora tutto ciò che non è mpv, quindi premerlo su un'altra finestra non fa nulla.
o.bind("SUPER + CTRL + P", "Popup video (float, pin, basso a destra)", "~/.local/bin/mpv-pip-toggle")
