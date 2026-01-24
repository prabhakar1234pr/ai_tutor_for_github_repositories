# Fix .env file for docker-compose compatibility
# Docker Compose requires values with special characters to be quoted

$envFile = ".env"
$backupFile = ".env.backup"

Write-Host "🔧 Fixing .env file for docker-compose compatibility..." -ForegroundColor Cyan

# Backup original file
if (Test-Path $envFile) {
    Copy-Item $envFile $backupFile -Force
    Write-Host "✅ Backed up .env to .env.backup" -ForegroundColor Green
} else {
    Write-Host "❌ .env file not found!" -ForegroundColor Red
    exit 1
}

# Read all lines
$lines = Get-Content $envFile -Raw

# Fix common issues:
# 1. Values with /, \, =, or spaces that aren't quoted
# 2. Windows line endings (\r\n)
# 3. Trailing whitespace

$fixedLines = @()
$allLines = $lines -split "`r?`n"

foreach ($line in $allLines) {
    $trimmedLine = $line.Trim()

    # Skip empty lines and comments
    if ([string]::IsNullOrWhiteSpace($trimmedLine) -or $trimmedLine.StartsWith("#")) {
        $fixedLines += $trimmedLine
        continue
    }

    # Check if line has = (is a variable assignment)
    if ($trimmedLine -match '^([^=]+)=(.*)$') {
        $varName = $matches[1].Trim()
        $varValue = $matches[2].Trim()

        # If value contains special characters and isn't already quoted, quote it
        if ($varValue -match '[/\\=\s]' -and -not ($varValue.StartsWith('"') -and $varValue.EndsWith('"'))) {
            # Remove existing quotes if any and re-quote properly
            $varValue = $varValue.Trim('"').Trim("'")
            $varValue = "`"$varValue`""
            $fixedLines += "$varName=$varValue"
        } else {
            $fixedLines += $trimmedLine
        }
    } else {
        $fixedLines += $trimmedLine
    }
}

# Write fixed content
$fixedContent = $fixedLines -join "`n"
$fixedContent | Set-Content $envFile -NoNewline

Write-Host "✅ Fixed .env file" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Changes made:" -ForegroundColor Cyan
Write-Host "  - Quoted values containing special characters (/, \, =, spaces)" -ForegroundColor Gray
Write-Host "  - Normalized line endings" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 Original backed up to: .env.backup" -ForegroundColor Yellow
Write-Host ""
Write-Host "🧪 Testing docker-compose config..." -ForegroundColor Cyan

# Test docker-compose config
$testResult = docker-compose config 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ docker-compose config is valid!" -ForegroundColor Green
} else {
    Write-Host "⚠️  docker-compose config still has issues:" -ForegroundColor Yellow
    Write-Host $testResult -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 You may need to manually fix remaining issues." -ForegroundColor Yellow
    Write-Host "💡 Restore backup: Copy-Item .env.backup .env -Force" -ForegroundColor Yellow
}
