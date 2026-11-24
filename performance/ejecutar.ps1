<#
.SYNOPSIS
  Ejecuta las pruebas de rendimiento con k6 y registra el consumo de recursos.

.EXAMPLE
  .\performance\ejecutar.ps1                              # todas: humo, carga, estres, pico, bot, login
  .\performance\ejecutar.ps1 -Pruebas humo,carga          # solo algunas
  .\performance\ejecutar.ps1 -Pruebas bot -Reposo 30
  .\performance\ejecutar.ps1 -Python .venv\Scripts\python.exe   # un Python que tenga psutil

  Necesita k6, Python con psutil (pip install psutil) y el stack levantado con la CA de mkcert instalada.
  Resultados en performance/resultados: <prueba>-resumen.json (resumen de k6), <prueba>.csv.gz (cada
  petición), recursos.csv (CPU y memoria) y ventanas.json (inicio y fin de cada prueba).
#>
param(
  [string[]]$Pruebas = @('humo', 'carga', 'estres', 'pico', 'bot', 'login'),
  [int]$Reposo = 60,
  [string]$Python = 'python'
)
# 'Continue': k6 escribe su progreso por stderr y en Windows PowerShell 5.1 eso no debe cortar el script
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot -Parent)
$res = 'performance/resultados'
New-Item -ItemType Directory -Force $res | Out-Null
$k6 = (Get-Command k6).Source
$py = (Get-Command $Python).Source

$archivoVentanas = "$res/ventanas.json"
$ventanas = @()
if (Test-Path $archivoVentanas) { $ventanas = @(Get-Content $archivoVentanas -Raw | ConvertFrom-Json) }

# La sonda del monitor valida el certificado con la CA de mkcert (si está instalada)
if (Get-Command mkcert -ErrorAction SilentlyContinue) { $env:SONDA_CA = Join-Path (mkcert -CAROOT) 'rootCA.pem' }
$parada = "$res/.detener-monitor"
Remove-Item $parada -ErrorAction SilentlyContinue
$monitor = Start-Process $py -ArgumentList @('performance/monitor.py', "$res/recursos.csv", $parada) -PassThru -WindowStyle Hidden

try {
  foreach ($p in $Pruebas) {
    # Los tokens duran 1 h: se renuevan antes de cada prueba (va despacio por el límite de login)
    & $k6 run --quiet performance/k6/preparar.js
    switch ($p) {
      'bot'   { $script = 'performance/k6/bot-ws.js';       $extra = @() }
      'login' { $script = 'performance/k6/login-limite.js'; $extra = @() }
      default { $script = 'performance/k6/flujos.js';       $extra = @('-e', "PERFIL=$p") }
    }
    Write-Host "`n=== $p ($script) ==="
    $inicio = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    & $k6 run @extra --out "csv=$res/$p.csv.gz" $script
    $codigo = $LASTEXITCODE   # 99 = algún umbral no se cumplió (esperable en estrés y pico)
    $fin = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $ventanas = @($ventanas | Where-Object { $_.prueba -ne $p }) + [pscustomobject]@{ prueba = $p; inicio = $inicio; fin = $fin; codigo = $codigo }
    $ventanas | ConvertTo-Json | Set-Content $archivoVentanas -Encoding utf8
    if ($p -ne $Pruebas[-1]) { Start-Sleep -Seconds $Reposo }  # que el sistema vuelva a reposo
  }
} finally {
  New-Item -ItemType File $parada -Force | Out-Null
  $monitor | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue
  Remove-Item $parada -ErrorAction SilentlyContinue
}
