param([string]$HostUrl="http://127.0.0.1:5055",[string]$OllamaUrl="http://127.0.0.1:11434",[switch]$QuickTests)
$ErrorActionPreference="SilentlyContinue"
$here=Split-Path -Parent $MyInvocation.MyCommand.Path; $root=Split-Path $here -Parent
$stamp=(Get-Date).ToString("yyyyMMdd_HHmmss"); $outDir=Join-Path $root "dist\debug_$stamp"; New-Item -ItemType Directory -Path $outDir -Force | Out-Null
function Run($l,[scriptblock]$sb){$o=[ordered]@{ok=$false;label=$l;output=$null;error=$null};try{$r=& $sb 2>&1;$o.ok=$true;$o.output=$r}catch{$o.error=$_.ToString()};$o}
$sys=[ordered]@{}; $sys.OS=(Get-CimInstance Win32_OperatingSystem|Select-Object -First 1 Caption,Version,OSArchitecture,BuildNumber);
$sys.CPU=(Get-CimInstance Win32_Processor|Select-Object -First 1 Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed);
$sys.RAM_GB=[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1);
$envs=@{ROTATE_180=$env:ROTATE_180;CAPTION_TIMEOUT=$env:CAPTION_TIMEOUT;DIARY_TIMEOUT=$env:DIARY_TIMEOUT}
$py=Run "python --version" { python --version }
$pip=Run "pip list (top)" { pip list | Select-Object -First 40 }
$ollver=Run "ollama --version" { ollama --version }
$tags=Run "GET /api/tags" { Invoke-RestMethod -TimeoutSec 5 -Uri "$OllamaUrl/api/tags" }
$quick=@{}; if($QuickTests){ $quick.pong=Run "20B pong" { $b=@{model="gpt-oss:20b";prompt="Say 'pong' once";stream=$false}|ConvertTo-Json; Invoke-RestMethod -Method Post -Uri "$OllamaUrl/api/generate" -ContentType "application/json" -Body $b } }
$ports=Run "Listen 5055/11434" { Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -in 5055,11434} | Select-Object LocalAddress,LocalPort,OwningProcess }
$state=[ordered]@{meta=@{generated=$stamp;hostUrl=$HostUrl;ollamaUrl=$OllamaUrl};system=$sys;env=$envs;python=$py;pip=$pip;ollama=@{ver=$ollver;tags=$tags};network=$ports;quick=$quick}
$statePath=Join-Path $outDir "system_state.json"; ($state|ConvertTo-Json -Depth 8)|Set-Content -Encoding utf8 $statePath
$jsonText=[IO.File]::ReadAllText($statePath)
$promptLines=@("You are my LOCAL TEST QA COPILOT.","- Robot Diary portal on 127.0.0.1:5055 (offline).","- Ollama on 127.0.0.1:11434 (llava:7b, gpt-oss:20b).","- Return: top hypotheses, exact PowerShell fixes (with expected outputs), and a minimal health-check sequence.","","JSON snapshot:","```json",$jsonText,"```")
Set-Content -Path (Join-Path $outDir "chatgpt_prompt.md") -Value $promptLines -Encoding utf8
$zip=Join-Path (Split-Path $outDir -Parent) ("debug_{0}.zip" -f $stamp); if(Test-Path $zip){Remove-Item $zip -Force}; Compress-Archive -Path (Join-Path $outDir "*") -DestinationPath $zip -Force
Write-Host "`n✅ Debug bundle:" $outDir; Write-Host "Paste into ChatGPT: $((Join-Path $outDir "chatgpt_prompt.md"))" -ForegroundColor Cyan
