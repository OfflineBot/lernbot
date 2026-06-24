#!/usr/bin/env python3
"""Focus Lern-Daemon — Gerüst. Inhalt (Lernsystem) kommt per Update nach."""
import time

VERSION = "0.1.0"

def main():
    print(f"Focus-Daemon v{VERSION} gestartet")
    while True:
        # Platzhalter — hier kommt später das Lernsystem rein.
        time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Focus-Daemon beendet")
