#!/bin/bash

systemctl --user enable --now ~/.local/share/focus/focus_updater.timer

systemctl --user daemon-reload
systemctl --user status focus_updater.timer --no-pager
