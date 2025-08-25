param(
    [Parameter(Mandatory=$true)][string]$ProcessName,
    [Parameter(Mandatory=$true)][string]$DllPath,
    [switch]$Unload
)

# BA-Cheeto Style Injection Script
# Uses the new C++ injector for better reliability

Write-Host "=== BAUnpin Injection Script v2.0 ===" -ForegroundColor Cyan
Write-Host "Based on BA-Cheeto architecture" -ForegroundColor Gray

# Find the injector executable
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$injectorPath = Join-Path $scriptDir "build\bin\Release\BAUnpinInjector.exe"

if (-not (Test-Path $injectorPath)) {
    $injectorPath = Join-Path $scriptDir "build\bin\BAUnpinInjector.exe"
    if (-not (Test-Path $injectorPath)) {
        $injectorPath = Join-Path $scriptDir "BAUnpinInjector.exe"
        if (-not (Test-Path $injectorPath)) {
            Write-Host "ERROR: BAUnpinInjector.exe not found!" -ForegroundColor Red
            Write-Host "Searched locations:" -ForegroundColor Yellow
            Write-Host "  - build\bin\Release\BAUnpinInjector.exe" -ForegroundColor Gray
            Write-Host "  - build\bin\BAUnpinInjector.exe" -ForegroundColor Gray
            Write-Host "  - BAUnpinInjector.exe" -ForegroundColor Gray
            Write-Host "Please build the project first: .\build.ps1" -ForegroundColor Yellow
            exit 1
        }
    }
}

# Check if DLL exists (unless unloading)
if (-not $Unload) {
    if (-not (Test-Path $DllPath)) {
        Write-Host "ERROR: DLL not found: $DllPath" -ForegroundColor Red
        exit 1
    }
    
    # Convert to absolute path
    $DllPath = (Resolve-Path $DllPath).Path
}

# Check if running as administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "WARNING: Not running as administrator. Injection may fail." -ForegroundColor Yellow
}

# Build command arguments
$arguments = @($ProcessName, $DllPath)
if ($Unload) {
    $arguments += "unload"
}

Write-Host "Injector: $injectorPath" -ForegroundColor Gray
Write-Host "Arguments: $($arguments -join ' ')" -ForegroundColor Gray

try {
    # Run the injector
    $process = Start-Process -FilePath $injectorPath -ArgumentList $arguments -NoNewWindow -Wait -PassThru
    
    if ($process.ExitCode -eq 0) {
        if ($Unload) {
            Write-Host "SUCCESS: DLL unloaded successfully!" -ForegroundColor Green
        } else {
            Write-Host "SUCCESS: DLL injected successfully!" -ForegroundColor Green
            Write-Host "Check the console output and logs for details." -ForegroundColor Gray
        }
    } else {
        Write-Host "ERROR: Injection failed with exit code $($process.ExitCode)" -ForegroundColor Red
    }
    
    exit $process.ExitCode
    
} catch {
    Write-Host "ERROR: Failed to run injector: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
