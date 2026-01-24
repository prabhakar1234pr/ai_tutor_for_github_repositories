#!/bin/bash
# Fix .env file for docker-compose compatibility
# Docker Compose requires values with special characters to be quoted

ENV_FILE=".env"
BACKUP_FILE=".env.backup"

echo "🔧 Fixing .env file for docker-compose compatibility..."

# Backup original file
if [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" "$BACKUP_FILE"
    echo "✅ Backed up .env to .env.backup"
else
    echo "❌ .env file not found!"
    exit 1
fi

# Use Python to fix the file (more reliable for complex cases)
python3 << 'PYTHON_SCRIPT'
import re
import sys

env_file = ".env"
backup_file = ".env.backup"

try:
    with open(env_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fixed_lines = []

    for line in lines:
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith('#'):
            fixed_lines.append(line)
            continue

        # Check if line has = (is a variable assignment)
        if '=' in stripped:
            parts = stripped.split('=', 1)
            var_name = parts[0].strip()
            var_value = parts[1].strip()

            # If value contains special characters and isn't already quoted, quote it
            if re.search(r'[/\\=\s]', var_value) and not (var_value.startswith('"') and var_value.endswith('"')):
                # Remove existing quotes if any and re-quote properly
                var_value = var_value.strip('"').strip("'")
                var_value = f'"{var_value}"'
                fixed_lines.append(f"{var_name}={var_value}\n")
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)

    # Write fixed content
    with open(env_file, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)

    print("✅ Fixed .env file")
    print("")
    print("📋 Changes made:")
    print("  - Quoted values containing special characters (/, \\, =, spaces)")
    print("  - Normalized line endings")
    print("")
    print("💡 Original backed up to: .env.backup")

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
PYTHON_SCRIPT

if [ $? -eq 0 ]; then
    echo ""
    echo "🧪 Testing docker-compose config..."
    if docker-compose config > /dev/null 2>&1; then
        echo "✅ docker-compose config is valid!"
    else
        echo "⚠️  docker-compose config still has issues:"
        docker-compose config
        echo ""
        echo "💡 You may need to manually fix remaining issues."
        echo "💡 Restore backup: cp .env.backup .env"
    fi
fi
