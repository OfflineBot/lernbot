#!/bin/bash
# Schaltet Focus komplett ab und entfernt alle systemd-Verknüpfungen.
# Die Dateien selbst bleiben — endgültig löschen mit:  rm -rf ~/.local/share/focus

systemctl --user disable --now focus_updater.timer 2>/dev/null
systemctl --user disable --now focus.service 2>/dev/null
systemctl --user stop focus_updater.service 2>/dev/null

# Symlinks im systemd-Suchpfad entfernen
rm -f ~/.config/systemd/user/focus_updater.timer
rm -f ~/.config/systemd/user/focus_updater.service
rm -f ~/.config/systemd/user/focus.service
rm -f ~/.config/systemd/user/timers.target.wants/focus_updater.timer
rm -f ~/.config/systemd/user/default.target.wants/focus.service

systemctl --user daemon-reload
echo "Focus deaktiviert — es läuft nichts mehr."
echo "Dateien endgültig entfernen:  rm -rf ~/.local/share/focus"
