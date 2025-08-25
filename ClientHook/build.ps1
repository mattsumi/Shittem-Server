param(
  [string]$Config = "Release",
  [string]$Generator = "Visual Studio 17 2022",
  [string]$Arch = "x64",
  [string]$VcpkgRoot = $env:VCPKG_ROOT
)

Write-Host "=== BAUnpin Build Script v2.0 ===" -ForegroundColor Cyan
Write-Host "Based on BA-Cheeto Architecture" -ForegroundColor Gray

# Resolve VCPKG root
if (-not $VcpkgRoot -or -not (Test-Path $VcpkgRoot)) {
  if (Test-Path "C:\vcpkg") {
    $VcpkgRoot = "C:\vcpkg"
  } else {
    Write-Error "VCPKG_ROOT not set and C:\vcpkg not found. Install vcpkg and set $env:VCPKG_ROOT or pass -VcpkgRoot."
    exit 1
  }
}

$toolchain = Join-Path $VcpkgRoot "scripts\buildsystems\vcpkg.cmake"
if (-not (Test-Path $toolchain)) {
  Write-Error "Toolchain file not found at $toolchain"
  exit 1
}

$src = "$PSScriptRoot"
$bld = Join-Path $src "build"

if (-not (Test-Path $bld)) { New-Item -ItemType Directory -Path $bld | Out-Null }

Write-Host "Building BAUnpin DLL and Injector..." -ForegroundColor Yellow
Write-Host "Configuration: $Config" -ForegroundColor Gray
Write-Host "Architecture: $Arch" -ForegroundColor Gray
Write-Host "VCPKG Root: $VcpkgRoot" -ForegroundColor Gray

Write-Host "Configuring with CMake..." -ForegroundColor Yellow
$cfgCmd = @(
  "-S", $src,
  "-B", $bld,
  "-G", $Generator,
  "-A", $Arch,
  "-DCMAKE_TOOLCHAIN_FILE=$toolchain"
)

& cmake @cfgCmd
if ($LASTEXITCODE -ne 0) { 
    Write-Host "CMake configuration failed!" -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "Building $Config..." -ForegroundColor Yellow
& cmake --build $bld --config $Config
if ($LASTEXITCODE -ne 0) { 
    Write-Host "Build failed!" -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "Build completed successfully!" -ForegroundColor Green
Write-Host "Output files:" -ForegroundColor Gray
$binDir = Join-Path $bld "bin\$Config"
if (Test-Path $binDir) {
    Get-ChildItem $binDir -File | ForEach-Object { Write-Host "  - $($_.Name)" -ForegroundColor Gray }
} else {
    $binDir = Join-Path $bld "bin"
    if (Test-Path $binDir) {
        Get-ChildItem $binDir -File | ForEach-Object { Write-Host "  - $($_.Name)" -ForegroundColor Gray }
    }
}

Write-Host ""
Write-Host "Usage examples:" -ForegroundColor Cyan
Write-Host "  .\inject.bat BlueArchive.exe" -ForegroundColor White
Write-Host "  .\inject_v2.ps1 -ProcessName BlueArchive.exe -DllPath .\build\bin\$Config\BAUnpin.dll" -ForegroundColor White

exit 0
