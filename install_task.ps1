# A股双体系行情推送 - Windows定时任务安装脚本
# 每日16:00自动运行

$taskName = "A股双体系行情推送"
$scriptPath = "C:\Users\22730\.claude\skills\market-push\run_daily.bat"

# 删除旧任务
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "已删除旧任务"
}

# 创建操作
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$scriptPath`""

# 每日16:00触发
$trigger = New-ScheduledTaskTrigger -Daily -At "16:00"

# 高级设置
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -WakeToRun `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5)

# 注册
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "每日16:00自动获取A股行情并双体系分析推送到企业微信" `
    -RunLevel Limited `
    -Force

Write-Host ""
Write-Host "任务计划创建成功!"
Write-Host "  名称: $taskName"
Write-Host "  时间: 每日 16:00"
Write-Host "  脚本: $scriptPath"
Write-Host ""
Write-Host "验证: 运行 taskschd.msc 打开任务计划程序"
