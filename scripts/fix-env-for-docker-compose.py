#!/usr/bin/env python3
"""
Fix .env file for docker-compose - comment out VM_SSH_KEY (not needed for local dev).
"""

import shutil
from pathlib import Path

ENV_FILE = Path(".env")
BACKUP_FILE = Path(".env.backup")


def fix_env_for_docker_compose():
    if not ENV_FILE.exists():
        print("ERROR: .env file not found!")
        return False

    # Backup
    if not BACKUP_FILE.exists():
        shutil.copy(ENV_FILE, BACKUP_FILE)
        print("OK: Backed up .env to .env.backup")

    # Read file
    with open(ENV_FILE, encoding="utf-8") as f:
        lines = f.readlines()

    fixed_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this is VM_SSH_KEY line
        if stripped.startswith("VM_SSH_KEY") and "=" in stripped:
            # Comment out VM_SSH_KEY and all continuation lines
            fixed_lines.append(f"# {line.rstrip()}\n")
            i += 1

            # Comment out continuation lines until we hit next variable or END marker
            while i < len(lines):
                next_line = lines[i]
                next_stripped = next_line.strip()

                # Stop if we hit a new variable assignment
                if next_stripped and "=" in next_stripped and not next_stripped.startswith(" "):
                    break

                # Stop if we hit END marker
                if (
                    "END OPENSSH PRIVATE KEY" in next_stripped
                    or "END RSA PRIVATE KEY" in next_stripped
                ):
                    fixed_lines.append(f"# {next_line.rstrip()}\n")
                    i += 1
                    break

                # Comment out continuation line
                if next_stripped:
                    fixed_lines.append(f"# {next_line.rstrip()}\n")
                else:
                    fixed_lines.append(next_line)  # Keep empty lines as-is
                i += 1

            print("  Commented out VM_SSH_KEY (not needed for local docker-compose)")
            continue

        # Regular line
        fixed_lines.append(line)
        i += 1

    # Write fixed content
    with open(ENV_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(fixed_lines)

    print("OK: Fixed .env file for docker-compose")
    return True


if __name__ == "__main__":
    print("Fixing .env file for docker-compose compatibility...")
    print("(Commenting out VM_SSH_KEY - not needed for local development)")
    print("")

    if fix_env_for_docker_compose():
        print("")
        print("Testing docker-compose config...")
        import subprocess

        result = subprocess.run(["docker-compose", "config"], capture_output=True, text=True)

        if result.returncode == 0:
            print("SUCCESS: docker-compose config is valid!")
            print("")
            print("You can now run: docker-compose up -d")
        else:
            print("WARNING: docker-compose config still has issues:")
            print(result.stderr[:1000])  # Show first 1000 chars
            print("")
            print("TIP: Restore backup: Copy-Item .env.backup .env -Force")
    else:
        print("ERROR: Failed to fix .env file")
