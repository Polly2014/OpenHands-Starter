# OpenHands-Starter


## Script of PS2EXE
```ps
Invoke-ps2exe -InputFile "D:\git_workspace\OpenHands-Starter\install_script_windows.ps1" `
              -OutputFile "D:\git_workspace\OpenHands-Starter\OpenHands-Starter.exe" `
              -iconFile "D:\git_workspace\OpenHands-Starter\polly.ico" `
              -title "OpenHands Starter" `
              -description "OpenHands Windows Deployment Tool" `
              -company "Microsoft" `
              -product "OpenHands Starter" `
              -version "1.0.0" `
              -copyright "Copyright © 2025" `
              -requireAdmin `
              -noConsole
```