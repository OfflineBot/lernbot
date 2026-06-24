#!/bin/bash
set -e

# Service auffindbar machen (wird vom Timer getriggert, nicht selbst "enabled")
systemctl --user link ~/.local/share/focus/focus_updater.service

# Timer aktivieren + sofort starten (legt den Timer-Symlink selbst an)
systemctl --user enable --now ~/.local/share/focus/focus_updater.timer

systemctl --user daemon-reload
systemctl --user status focus_updater.timer --no-pager
