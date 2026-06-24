
import subprocess
from pathlib import Path

REPO = Path.home() / ".local/share/focus"

def git(*args):
    return subprocess.run(
        ["git", "-C", str(REPO), *args], 
        check=True, capture_output=True, text=True
    ).stdout.strip()

def main():
    before = git("rev-parse", "HEAD")
    git("pull", "--quiet")
    after = git("rev-parse", "HEAD")

    if before == after:
        print("no change")
        return

    print(f"Update: {before[:7]} -> {after[:7]}")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "restart", "focus.service"], check=True)
    print("Restarted daemon")

if __name__ == "__main__":
    main()


