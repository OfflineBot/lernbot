#!/bin/bash
set -e

systemctl --user link ~/.local/share/focus/focus_updater.service
systemctl --user enable --now ~/.local/share/focus/focus_updater.timer
systemctl --user enable --now ~/.local/share/focus/focus.service
systemctl --user daemon-reload
