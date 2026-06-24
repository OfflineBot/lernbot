#!/bin/bash
set -e

# Service auffindbar machen (wird vom Timer getriggert, nicht selbst "enabled")
systemctl --user link ~/.local/share/focus/focus_updater.service

# Timer aktivieren + sofort starten (legt den Timer-Symlink selbst an)
systemctl --user enable --now ~/.local/share/focus/focus_updater.timer

# Lern-Daemon aktivieren + starten
systemctl --user enable --now ~/.local/share/focus/focus.service

systemctl --user daemon-reload
echo "Fertig. Updater + Lern-Daemon laufen."
echo "Deaktivieren jederzeit mit:  bash ~/.local/share/focus/deactivate.sh"
