param([string]$ImgFolder = (Join-Path $PSScriptRoot "..\sample_data\img"))
$img = Get-ChildItem $ImgFolder -File | Where-Object {$_.Extension -match "^\.(jpg|jpeg|png)$"} | Select-Object -First 1
if (-not $img){ Write-Error "No images in $ImgFolder"; exit 1 }
curl.exe -F "title=manual" -F "text=hello" -F "image=@$($img.FullName)" http://127.0.0.1:5055/api/post
