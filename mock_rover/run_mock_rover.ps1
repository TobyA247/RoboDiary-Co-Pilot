param(
  [string]$HostUrl="http://127.0.0.1:5055",
  [string]$ImagesPath=(Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "mock_images"),
  [int]$Count=3, [int]$IntervalSec=2, [switch]$Watch
)
New-Item -ItemType Directory -Path $ImagesPath -Force | Out-Null
function Get-RoverImages([string]$p){ Get-ChildItem -Path $p -File | Where-Object {$_.Extension -match "^\.(jpg|jpeg|png)$"} | Sort-Object Name }
function Post-Image([string]$path){ $ts=Get-Date -Format s; $n=[IO.Path]::GetFileName($path);
  Write-Host "[$ts] POST $n";
  curl.exe -s -F "title=update" -F "text=$ts mock rover" -F "reason=rover" -F "image=@$path" "$HostUrl/api/post" | Write-Host }
try { Invoke-WebRequest -UseBasicParsing -Uri "$HostUrl/" -TimeoutSec 2 | Out-Null } catch { }
if ($Watch) {
  Write-Host "Watching $ImagesPath for new JPG/PNG (Ctrl+C to stop)."
  $fsw=New-Object IO.FileSystemWatcher $ImagesPath,"*.*"; $fsw.EnableRaisingEvents=$true
  Register-ObjectEvent $fsw Created -Action { $p=$Event.SourceEventArgs.FullPath; if ($p -match "\.(jpg|jpeg|png)$"){ Start-Sleep -Milliseconds 500; Post-Image $p } } | Out-Null
  while($true){ Start-Sleep 1 }
} else {
  $imgs=Get-RoverImages $ImagesPath; if (-not $imgs){ Write-Error "No images in $ImagesPath (need .jpg/.jpeg/.png)"; exit 1 }
  $send = if ($Count -le 0) { $imgs } else { $imgs | Select-Object -First $Count }
  foreach($f in $send){ Post-Image $f.FullName; Start-Sleep -Seconds $IntervalSec }
}
