# QTT OS - Remote help: set up this company computer (Windows). Run in PowerShell as Administrator:
#   irm "<the link from QTT OS > Remote help > Add computer>" | iex
# What it does: installs RustDesk if needed, points it at QTT's own server, applies the company policy (no direct IP
# connections, no LAN discovery, no remote settings changes, no tunnels, idle sessions end), sets a long random
# permanent password made by QTT (never shown), and adds a small agent (a scheduled task, every 15 minutes) that
# changes the password when QTT asks - e.g. when someone's access is revoked. Remove the computer in QTT OS to lock it.
$ErrorActionPreference = "Stop"
$Base = "__QTT_BASE__"
$Code = "__QTT_CODE__"
$Config = "__QTT_CONFIG__"
$Policy = "__QTT_POLICY__"
$Dir = Join-Path $env:ProgramData "QTT\RemoteHelp"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "Please run PowerShell as Administrator (right-click > Run as administrator), then paste the command again." -ForegroundColor Yellow
  return
}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Find-RustDesk {
  foreach ($p in @("$env:ProgramFiles\RustDesk\rustdesk.exe", "${env:ProgramFiles(x86)}\RustDesk\rustdesk.exe")) { if (Test-Path $p) { return $p } }
  return $null
}

$exe = Find-RustDesk
if (-not $exe) {
  Write-Host "Installing RustDesk..."
  $rel = Invoke-RestMethod "https://api.github.com/repos/rustdesk/rustdesk/releases/latest" -Headers @{ "User-Agent" = "qtt-os" }
  $asset = $rel.assets | Where-Object { $_.name -match "x86_64\.exe$" -and $_.name -notmatch "sciter" } | Select-Object -First 1
  $tmp = Join-Path $env:TEMP "rustdesk-setup.exe"
  Invoke-WebRequest $asset.browser_download_url -OutFile $tmp -UseBasicParsing
  Start-Process $tmp -ArgumentList "--silent-install" -Wait
  for ($i = 0; $i -lt 30 -and -not (Find-RustDesk); $i++) { Start-Sleep 2 }
  $exe = Find-RustDesk
  if (-not $exe) { throw "RustDesk didn't install - install it from rustdesk.com, then run this again." }
  Start-Sleep 10
}

function Set-Policy([string]$exe, [string]$config, [string]$policy) {
  & $exe --config $config | Out-Null
  foreach ($kv in $policy.Split(";")) {
    $k, $v = $kv.Split("=", 2)
    try { & $exe --option $k $v | Out-Null } catch { }
  }
}
Set-Policy $exe $Config $Policy

$id = ""
for ($i = 0; $i -lt 15 -and -not $id; $i++) { $id = ((& $exe --get-id | Out-String).Trim() -replace "\s", ""); if (-not $id) { Start-Sleep 2 } }
if (-not $id) { throw "RustDesk didn't give an ID yet - open RustDesk once, then run this again." }

$r = Invoke-RestMethod -Method Post "$Base/api/method/qtt_platform.api.workplace_agent.enroll" -Body @{ code = $Code; rustdesk_id = $id; os = "windows"; host = $env:COMPUTERNAME }
$m = $r.message
& $exe --password $m.password | Out-Null

# The agent: its key readable only by SYSTEM and Administrators.
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
foreach ($who in @("SYSTEM", "Administrators")) {
  $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($who, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")))
}
Set-Acl -Path $Dir -AclObject $acl
@{ base = $Base; key = $m.agent_key } | ConvertTo-Json | Set-Content (Join-Path $Dir "agent.json") -Encoding UTF8

$agent = @'
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Dir = Join-Path $env:ProgramData "QTT\RemoteHelp"
$cfg = Get-Content (Join-Path $Dir "agent.json") -Raw | ConvertFrom-Json
$exe = @("$env:ProgramFiles\RustDesk\rustdesk.exe", "${env:ProgramFiles(x86)}\RustDesk\rustdesk.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $exe) { exit 0 }
$id = ((& $exe --get-id | Out-String).Trim() -replace "\s", "")
$m = (Invoke-RestMethod -Method Post "$($cfg.base)/api/method/qtt_platform.api.workplace_agent.sync" -Body @{ agent_key = $cfg.key; rustdesk_id = $id; version = "__QTT_VERSION__" }).message
if ($m.config) { & $exe --config $m.config | Out-Null }
if ($m.policy) { foreach ($p in $m.policy.PSObject.Properties) { try { & $exe --option $p.Name $p.Value | Out-Null } catch { } } }
if ($m.password) {
  & $exe --password $m.password | Out-Null
  Invoke-RestMethod -Method Post "$($cfg.base)/api/method/qtt_platform.api.workplace_agent.confirm" -Body @{ agent_key = $cfg.key; nonce = $m.nonce } | Out-Null
  if ($m.lock) {
    Unregister-ScheduledTask -TaskName "QTT Remote Help" -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item $Dir -Recurse -Force -ErrorAction SilentlyContinue
  }
}
'@
Set-Content (Join-Path $Dir "agent.ps1") $agent -Encoding UTF8

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Dir\agent.ps1`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$boot = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "QTT Remote Help" -Action $action -Trigger @($trigger, $boot) -User "SYSTEM" -RunLevel Highest -Force | Out-Null

Write-Host ""
Write-Host "Done - this computer is in QTT OS > Remote help as $env:COMPUTERNAME (RustDesk ID $id)." -ForegroundColor Green
Write-Host "Its RustDesk password is managed by QTT and changes by itself when access is revoked."
