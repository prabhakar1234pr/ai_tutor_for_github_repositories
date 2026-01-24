#!/usr/bin/env python3
"""
Fix .env file for docker-compose compatibility.
Quotes values that contain special characters.
"""

import re
import shutil
from pathlib import Path

ENV_FILE = Path(".env")
BACKUP_FILE = Path(".env.backup")


def fix_env_file():
    if not ENV_FILE.exists():
        print("ERROR: .env file not found!")
        return False

    # Backup
    shutil.copy(ENV_FILE, BACKUP_FILE)
    print("OK: Backed up .env to .env.backup")

    # Read file
    with open(ENV_FILE, encoding="utf-8") as f:
        lines = f.readlines()

    fixed_lines = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            fixed_lines.append(line)
            continue

        # Check if line has = (is a variable assignment)
        if "=" in stripped:
            # Split on first = only
            parts = stripped.split("=", 1)
            var_name = parts[0].strip()
            var_value = parts[1].strip()

            # Check if value needs quoting
            needs_quoting = False

            # Values with special characters need quoting
            if re.search(r"[/\\=\s#]", var_value):
                needs_quoting = True

            # Values that aren't already quoted
            if not (var_value.startswith('"') and var_value.endswith('"')):
                if needs_quoting:
                    # Remove any existing quotes and re-quote
                    var_value = var_value.strip('"').strip("'")
                    var_value = f'"{var_value}"'
                    fixed_lines.append(f"{var_name}={var_value}\n")
                    print(f"  Line {i}: Quoted value for {var_name}")
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)
        else:
            # Line without = - might be malformed, keep as-is but warn
            if stripped and not stripped.startswith("#"):
                print(f"  WARNING: Line {i}: No '=' found, keeping as-is: {stripped[:50]}...")
            fixed_lines.append(line)

    # Write fixed content
    with open(ENV_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(fixed_lines)

    print("OK: Fixed .env file")
    return True


if __name__ == "__main__":
    print("Fixing .env file for docker-compose compatibility...")
    print("")

    if fix_env_file():
        print("")
        print("Testing docker-compose config...")
        import subprocess

        result = subprocess.run(["docker-compose", "config"], capture_output=True, text=True)

        if result.returncode == 0:
            print("OK: docker-compose config is valid!")
        else:
            print("WARNING: docker-compose config still has issues:")
            print(result.stderr)
            print("")
            print("TIP: You may need to manually fix remaining issues.")
            print(f"TIP: Restore backup: Copy-Item {BACKUP_FILE} {ENV_FILE} -Force")
    else:
        print("ERROR: Failed to fix .env file")
