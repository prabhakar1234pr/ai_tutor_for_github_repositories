#!/usr/bin/env python3
"""
Fix SSH key in .env file - convert multi-line SSH key to single line for docker-compose.
"""

import shutil
from pathlib import Path

ENV_FILE = Path(".env")
BACKUP_FILE = Path(".env.backup")


def fix_ssh_key():
    if not ENV_FILE.exists():
        print("ERROR: .env file not found!")
        return False

    # Backup
    if BACKUP_FILE.exists():
        shutil.copy(BACKUP_FILE, ENV_FILE)  # Restore from previous backup
    else:
        shutil.copy(ENV_FILE, BACKUP_FILE)
    print("OK: Using .env.backup as source")

    # Read file
    with open(ENV_FILE, encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    fixed_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this is VM_SSH_KEY line
        if stripped.startswith("VM_SSH_KEY="):
            # Get the variable name and any value on same line
            parts = stripped.split("=", 1)
            var_name = parts[0]

            # Collect all SSH key lines (until we hit next variable or empty line with no continuation)
            ssh_key_parts = []
            if len(parts) > 1 and parts[1].strip():
                ssh_key_parts.append(parts[1].strip())

            i += 1
            # Continue reading lines until we hit a line that starts with a variable name or is empty
            while i < len(lines):
                next_line = lines[i].strip()
                # Stop if we hit a new variable assignment or empty line (but allow continuation)
                if next_line and "=" in next_line and not next_line.startswith(" "):
                    break
                # Stop if we hit END marker
                if "END OPENSSH PRIVATE KEY" in next_line or "END RSA PRIVATE KEY" in next_line:
                    ssh_key_parts.append(next_line)
                    i += 1
                    break
                # Continue collecting if line has content
                if next_line:
                    ssh_key_parts.append(next_line)
                i += 1

            # Join SSH key parts with escaped newlines for docker-compose
            # Docker Compose supports \n in quoted strings
            ssh_key_value = "\\n".join(ssh_key_parts)
            fixed_lines.append(f'{var_name}="{ssh_key_value}"')
            print(f"  Fixed VM_SSH_KEY: Combined {len(ssh_key_parts)} lines into single line")
            continue

        # Regular line
        fixed_lines.append(line)
        i += 1

    # Write fixed content
    with open(ENV_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(fixed_lines))

    print("OK: Fixed SSH key in .env file")
    return True


if __name__ == "__main__":
    print("Fixing SSH key in .env file for docker-compose...")
    print("")

    if fix_ssh_key():
        print("")
        print("Testing docker-compose config...")
        import subprocess

        result = subprocess.run(["docker-compose", "config"], capture_output=True, text=True)

        if result.returncode == 0:
            print("OK: docker-compose config is valid!")
        else:
            print("WARNING: docker-compose config still has issues:")
            print(result.stderr[:500])  # Show first 500 chars
            print("")
            print("TIP: You may need to manually fix remaining issues.")
    else:
        print("ERROR: Failed to fix .env file")
