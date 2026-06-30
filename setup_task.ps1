# PowerShell script to create Windows scheduled task
# Run as Administrator
# Usage: powershell -ExecutionPolicy Bypass -File setup_task.ps1

$taskName = "A股双体系行情推送"
$scriptPath = "D:\stock-analysis\market-push\run_daily.bat"
$taskDescription = "每日16:00自动获取A股行情，双体系分析并推送到企业微信"

# Remove existing task if present
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "删除已存在的任务: $taskName"
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Create task action
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$scriptPath`""

# Create trigger: daily at 16:00
$trigger = New-ScheduledTaskTrigger -Daily -At "16:00"

# Create settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -WakeToRun

# Register task
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description $taskDescription `
    -RunLevel Limited `
    -Force

Write-Host "✅ 任务计划已创建: $taskName"
Write-Host "   每日 16:00 自动执行"
Write-Host "   脚本路径: $scriptPath"
Write-Host ""
Write-Host "验证: 打开 taskschd.msc 查看任务计划程序库"

# Create required directories
$dirs = @(
    "D:\stock-analysis\market-push\reports",
    "D:\stock-analysis\market-push\logs"
)
foreach ($d in $dirs) {
    if (!(Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Host "创建目录: $d"
    }
}
