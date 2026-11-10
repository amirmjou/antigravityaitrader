$p = Start-Process -FilePath "python" -ArgumentList "run_live_metamask_terminal.py" -WorkingDirectory "c:\Users\AmirM\Documents\Agentic trading" -NoNewWindow -PassThru
Start-Sleep -Seconds 3
Write-Output "PID=$($p.Id)"
Get-Process -Id $p.Id -ErrorAction SilentlyContinue | Format-Table Id, ProcessName, Responding, StartTime
Get-NetTCPConnection -LocalPort 8899 -ErrorAction SilentlyContinue | Format-Table LocalAddress, LocalPort, State, OwningProcess
