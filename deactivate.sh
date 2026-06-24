#!/bin/bash

systemctl --user disable --now focus_updater.timer 2>/dev/null
systemctl --user disable --now focus.service 2>/dev/null
systemctl --user stop focus_updater.service 2>/dev/null

rm -f ~/.config/systemd/user/focus_updater.timer
rm -f ~/.config/systemd/user/focus_updater.service
rm -f ~/.config/systemd/user/focus.service
rm -f ~/.config/systemd/user/timers.target.wants/focus_updater.timer
rm -f ~/.config/systemd/user/default.target.wants/focus.service

systemctl --user daemon-reload
systemctl --user reset-failed focus_updater.timer focus_updater.service focus.service 2>/dev/null
