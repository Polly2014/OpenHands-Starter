<#
.SYNOPSIS
    OpenHands Windows Deployment Script
.DESCRIPTION
    Automates the deployment of OpenHands on Windows platform
.NOTES
    Version: 1.0
    Author: Polly (Baoli Wang)
    Last Updated: 2025-03-17
#>

# Run as administrator
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Warning "Please run this script as Administrator!"
    Start-Process powershell.exe "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    Exit
}

# Set error action preference to stop on any error
$ErrorActionPreference = "Stop"

# Variables
$dockerDesktopUrl = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
$dockerInstallerPath = "$env:TEMP\DockerDesktopInstaller.exe"
$workspaceDir = "Q:\Src"
$stateDirPath = "$env:USERPROFILE\.openhands-state"
$dockerComposeFile = if ($PSScriptRoot) {
    # 正常 PowerShell 脚本环境
    Join-Path $PSScriptRoot "docker-compose.yaml"
} elseif ($MyInvocation.MyCommand.Path) {
    # 可能是打包为 EXE 的环境，但还能获取到命令路径
    Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "docker-compose.yaml"
} else {
    # 在 EXE 环境中两者都为 null 的情况
    Join-Path (Get-Location) "docker-compose.yaml"
}
$webPort = "80"

# Track completion status of each step
$stepStatus = @{
    "WSLInstalled" = $false
    "DockerInstalled" = $false
    "DockerRunning" = $false
    "WorkspaceSetup" = $false
    "ComposeCreated" = $false
    "ImagesPulled" = $false
    "OpenHandsDeployed" = $false
}

# Function to display status
function Write-Status {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Message,
        
        [Parameter(Mandatory = $false)]
        [string]$Type = "Info" # Info, Success, Warning, Error
    )

    switch ($Type) {
        "Info" {
            Write-Host "[INFO] $Message" -ForegroundColor Cyan
        }
        "Success" {
            Write-Host "[SUCCESS] $Message" -ForegroundColor Green
        }
        "Warning" {
            Write-Host "[WARNING] $Message" -ForegroundColor Yellow
        }
        "Error" {
            Write-Host "[ERROR] $Message" -ForegroundColor Red
        }
    }
}

# Function to verify required steps are completed
function Test-Prerequisites {
    param (
        [Parameter(Mandatory = $true)]
        [string[]]$RequiredSteps
    )

    $allPrerequisitesMet = $true
    
    foreach ($step in $RequiredSteps) {
        if (-not $stepStatus[$step]) {
            Write-Status "Prerequisite step '$step' not completed successfully. Cannot continue." -Type "Error"
            $allPrerequisitesMet = $false
        }
    }
    
    return $allPrerequisitesMet
}

# Function to check if WSL is installed
function Test-WSL {
    try {
        $wslStatus = wsl --status
        return $true
    }
    catch {
        return $false
    }
}

# Function to install WSL
function Install-WSL {
    Write-Status "Installing WSL..."
    
    try {
        # Enable WSL feature
        dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
        
        # Enable Virtual Machine Platform
        dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
        
        # Set WSL 2 as default
        wsl --set-default-version 2
        
        Write-Status "WSL installation completed. You might need to restart your computer." -Type "Warning"
        $restartChoice = Read-Host "Do you want to restart now? (y/n)"
        
        if ($restartChoice -eq 'y') {
            Restart-Computer
            exit
        }
        
        # Verify WSL installation was successful
        if (Test-WSL) {
            return $true
        } else {
            Write-Status "WSL installation appears to have failed." -Type "Error"
            return $false
        }
    }
    catch {
        Write-Status "Failed to install WSL: $_" -Type "Error"
        return $false
    }
}

# Function to check if Docker Desktop is installed
function Test-DockerDesktop {
    try {
        $dockerVersion = docker --version
        return $true
    }
    catch {
        return $false
    }
}

# Function to check if Docker service is running
function Test-DockerRunning {
    try {
        # First check using a simple command with a short timeout
        $process = Start-Process -FilePath "docker" -ArgumentList "version" -NoNewWindow -PassThru -Wait -ErrorAction SilentlyContinue
        if ($process.ExitCode -eq 0) {
            return $true
        }
        
        # Try a second approach
        $info = docker info --format '{{.ServerVersion}}' 2>$null
        if ($info) {
            return $true
        }
        
        return $false
    }
    catch {
        return $false
    }
}

# Function to install Docker Desktop
function Install-DockerDesktop {
    Write-Status "Downloading Docker Desktop..."
    
    try {
        Invoke-WebRequest -Uri $dockerDesktopUrl -OutFile $dockerInstallerPath
        
        Write-Status "Installing Docker Desktop..." -Type "Info"
        Write-Status "This may take several minutes. Please be patient." -Type "Info"
        
        # Run the Docker Desktop installer with silent options
        Start-Process -FilePath $dockerInstallerPath -ArgumentList "install", "--quiet" -Wait -NoNewWindow
        
        # Clean up
        if (Test-Path $dockerInstallerPath) {
            Remove-Item $dockerInstallerPath -Force
        }
        
        # Verify installation succeeded
        if (Test-DockerDesktop) {
            Write-Status "Docker Desktop installed successfully" -Type "Success"
            return $true
        } else {
            Write-Status "Docker Desktop installation verification failed" -Type "Error"
            return $false
        }
    }
    catch {
        Write-Status "Failed to install Docker Desktop: $_" -Type "Error"
        return $false
    }
}

# Function to start Docker Desktop
function Start-DockerDesktop {
    Write-Status "Starting Docker Desktop..." -Type "Info"
    
    # Check if Docker Desktop GUI is already running
    $dockerDesktopProcess = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
    
    if (-not $dockerDesktopProcess) {
        # Try to start Docker Desktop
        try {
            # Check both possible paths for Docker Desktop
            $dockerPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
            if (-not (Test-Path $dockerPath)) {
                $dockerPath = "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe"
                if (-not (Test-Path $dockerPath)) {
                    Write-Status "Docker Desktop executable not found at expected locations" -Type "Error"
                    return $false
                }
            }
            
            Start-Process $dockerPath
            Write-Status "Started Docker Desktop application" -Type "Info"
        }
        catch {
            Write-Status "Could not start Docker Desktop automatically: $_" -Type "Error"
            Write-Status "Please start Docker Desktop manually from the Start menu" -Type "Warning"
            return $false
        }
    } else {
        Write-Status "Docker Desktop application is already running" -Type "Info"
    }
    
    # Wait for Docker service
    Write-Status "Waiting for Docker service to be ready..." -Type "Info"
    Write-Status "This may take a minute or two" -Type "Info"
    
    # Try a different approach to waiting for Docker
    $maxRetries = 60  # 5 minutes total with 5-second intervals
    $retryCount = 0
    $dockerRunning = $false
    
    while (-not $dockerRunning -and $retryCount -lt $maxRetries) {
        Start-Sleep -Seconds 5
        $retryCount++
        
        # Show progress every 6 attempts (30 seconds)
        if ($retryCount % 6 -eq 0 -or $retryCount -eq 1) {
            Write-Status "Still waiting for Docker... ($(($retryCount * 5) / 60) minutes elapsed)" -Type "Info"
        }
        
        # First try a simple test command
        try {
            $process = Start-Process -FilePath "docker" -ArgumentList "version" -NoNewWindow -PassThru -Wait -ErrorAction SilentlyContinue
            if ($process.ExitCode -eq 0) {
                $dockerRunning = $true
                break
            }
        }
        catch {
            # Continue with the next check
        }
        
        # Try another approach
        try {
            $info = docker info --format '{{.ServerVersion}}' 2>$null
            if ($info) {
                $dockerRunning = $true
                break
            }
        }
        catch {
            $dockerRunning = $false
        }
    }
    
    if ($dockerRunning) {
        Write-Status "Docker service is now ready!" -Type "Success"
        return $true
    }
    else {
        Write-Status "Docker Desktop is taking longer than expected to initialize" -Type "Warning"
        
        $manualCheck = Read-Host "Is the Docker Desktop icon in your system tray showing as running? (y/n)"
        if ($manualCheck -eq 'y') {
            Write-Status "Continuing with deployment since Docker appears to be running" -Type "Info"
            return $true
        } else {
            Write-Status "Please ensure Docker Desktop is fully started before running this script again" -Type "Warning"
            Write-Status "You can verify Docker is running by opening a new PowerShell window and typing 'docker version'" -Type "Info"
            return $false
        }
    }
}

# Function to create and update docker-compose file
function Update-DockerComposeFile {
    if (-not (Test-Prerequisites -RequiredSteps @("WSLInstalled", "DockerInstalled", "DockerRunning", "WorkspaceSetup"))) {
        return $false
    }
    
    Write-Status "Setting up docker-compose.yaml..."
    
    try {
        # Create docker compose template with correct volume format
        $dockerComposeTemplate = @"
services:
  openhands-app:
    image: docker.all-hands.dev/all-hands-ai/openhands:latest
    container_name: openhands-app
    environment:
      - SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:0.30-nikolaik
      - LOG_ALL_EVENTS=true
      - SANDBOX_USER_ID=1000
      - WORKSPACE_MOUNT_PATH=$($workspaceDir.Replace('\','/'))
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - $($stateDirPath.Replace('\','/')):/.openhands-state
      - $($workspaceDir.Replace('\','/')):/opt/workspace_base
    ports:
      - "$($webPort):3000"
    extra_hosts:
      - host.docker.internal:host-gateway
    tty: true
    stdin_open: true
    restart: "no"
"@
        
        # Create docker-compose.yaml file
        $dockerComposeTemplate | Out-File -FilePath $dockerComposeFile -Encoding utf8
        
        Write-Status "docker-compose.yaml created successfully" -Type "Success"
        return $true
    }
    catch {
        Write-Status "Failed to create docker-compose.yaml: $_" -Type "Error"
        return $false
    }
}

# Function to setup workspace directories
function Setup-Workspace {
    if (-not (Test-Prerequisites -RequiredSteps @("WSLInstalled", "DockerInstalled", "DockerRunning"))) {
        return $false
    }
    
    Write-Status "Setting up workspace directories..."
    
    try {
        # Create workspace directory if it doesn't exist
        if (-not (Test-Path $workspaceDir)) {
            # Check if drive exists, if not create it
            $driveLetter = $workspaceDir.Substring(0, 1)
            if (-not (Test-Path "$($driveLetter):")) {
                Write-Status "Drive $driveLetter not found. Creating a virtual drive..." -Type "Warning"
                
                # Create a virtual drive using subst command
                $tempPath = "$env:USERPROFILE\OpenHands_Workspace"
                New-Item -ItemType Directory -Path $tempPath -Force | Out-Null
                subst "$($driveLetter):" $tempPath
                
                Write-Status "Virtual drive $driveLetter created pointing to $tempPath" -Type "Success"
            }
            
            New-Item -ItemType Directory -Path $workspaceDir -Force | Out-Null
            Write-Status "Created workspace directory at $workspaceDir" -Type "Success"
        }
        else {
            Write-Status "Workspace directory already exists at $workspaceDir" -Type "Info"
        }
        
        # Create state directory if it doesn't exist
        if (-not (Test-Path $stateDirPath)) {
            New-Item -ItemType Directory -Path $stateDirPath -Force | Out-Null
            Write-Status "Created OpenHands state directory at $stateDirPath" -Type "Success"
        }
        else {
            Write-Status "OpenHands state directory already exists at $stateDirPath" -Type "Info"
        }
        
        # Verify directories were created successfully
        if ((Test-Path $workspaceDir) -and (Test-Path $stateDirPath)) {
            return $true
        } else {
            Write-Status "Failed to verify workspace directories" -Type "Error"
            return $false
        }
    }
    catch {
        Write-Status "Failed to setup workspace directories: $_" -Type "Error"
        return $false
    }
}

# Function to pull Docker images
# function Pull-DockerImages {
#     if (-not (Test-Prerequisites -RequiredSteps @("WSLInstalled", "DockerInstalled", "DockerRunning"))) {
#         return $false
#     }
    
#     Write-Status "Pulling Docker images (this may take some time)..."
    
#     try {
#         # Try to pull OpenHands image
#         Write-Status "Pulling OpenHands application image..." -Type "Info"
#         $pullApp = docker pull docker.all-hands.dev/all-hands-ai/openhands:latest
        
#         # Try to pull runtime image
#         Write-Status "Pulling OpenHands runtime image..." -Type "Info"
#         $pullRuntime = docker pull docker.all-hands.dev/all-hands-ai/runtime:0.30-nikolaik
        
#         Write-Status "Docker images pulled successfully" -Type "Success"
#         return $true
#     }
#     catch {
#         Write-Status "Failed to pull Docker images: $_" -Type "Warning"
        
#         $continueAnyway = Read-Host "Do you want to continue with deployment despite image pull failure? (y/n)"
#         if ($continueAnyway -eq 'y') {
#             Write-Status "Continuing with deployment..." -Type "Info"
#             return $true
#         } else {
#             return $false
#         }
#     }
# }
function Pull-DockerImages {
    if (-not (Test-Prerequisites -RequiredSteps @("WSLInstalled", "DockerInstalled", "DockerRunning"))) {
        return $false
    }
    
    Write-Status "Pulling Docker images (this may take some time)..." -Type "Info"
    
    try {
        # 设置不捕获输出，以允许 Docker pull 命令的进度显示直接输出到控制台
        Write-Status "Pulling OpenHands application image... (Progress will be shown below)" -Type "Info"
        Write-Host ""
        
        # 使用 Start-Process 执行 Docker pull 命令并等待完成，确保输出显示在控制台
        $appPullProcess = Start-Process -FilePath "docker" -ArgumentList "pull", "docker.all-hands.dev/all-hands-ai/openhands:latest" -NoNewWindow -PassThru -Wait
        
        Write-Host ""
        if ($appPullProcess.ExitCode -ne 0) {
            Write-Status "Warning: The application image pull may have encountered issues." -Type "Warning"
        }
        
        # 同样的方法拉取运行时镜像
        Write-Status "Pulling OpenHands runtime image... (Progress will be shown below)" -Type "Info"
        Write-Host ""
        
        $runtimePullProcess = Start-Process -FilePath "docker" -ArgumentList "pull", "docker.all-hands.dev/all-hands-ai/runtime:0.30-nikolaik" -NoNewWindow -PassThru -Wait
        
        Write-Host ""
        if ($runtimePullProcess.ExitCode -ne 0) {
            Write-Status "Warning: The runtime image pull may have encountered issues." -Type "Warning"
        }
        
        # 验证镜像是否已拉取
        $appImage = docker images --format "{{.Repository}}:{{.Tag}}" | Where-Object { $_ -eq "docker.all-hands.dev/all-hands-ai/openhands:latest" }
        $runtimeImage = docker images --format "{{.Repository}}:{{.Tag}}" | Where-Object { $_ -eq "docker.all-hands.dev/all-hands-ai/runtime:0.30-nikolaik" }
        
        if ($appImage -and $runtimeImage) {
            Write-Status "Docker images pulled successfully" -Type "Success"
            return $true
        } elseif ($appImage) {
            Write-Status "OpenHands application image pulled successfully, but runtime image pull may have failed" -Type "Warning"
            $continueAnyway = Read-Host "Do you want to continue with deployment? (y/n)"
            return ($continueAnyway -eq 'y')
        } elseif ($runtimeImage) {
            Write-Status "OpenHands runtime image pulled successfully, but application image pull may have failed" -Type "Warning"
            $continueAnyway = Read-Host "Do you want to continue with deployment? (y/n)"
            return ($continueAnyway -eq 'y')
        } else {
            Write-Status "Failed to verify that images were pulled successfully" -Type "Warning"
            $continueAnyway = Read-Host "Do you want to continue with deployment anyway? (y/n)"
            return ($continueAnyway -eq 'y')
        }
    }
    catch {
        Write-Status "Failed to pull Docker images: $_" -Type "Warning"
        
        $continueAnyway = Read-Host "Do you want to continue with deployment despite image pull failure? (y/n)"
        if ($continueAnyway -eq 'y') {
            Write-Status "Continuing with deployment..." -Type "Info"
            return $true
        } else {
            return $false
        }
    }
}

# Function to deploy OpenHands with Docker
# 直接使用 Docker 命令部署
function Deploy-OpenHands {
    if (-not (Test-Prerequisites -RequiredSteps @("WSLInstalled", "DockerInstalled", "DockerRunning", "WorkspaceSetup"))) {
        return $false
    }
    
    Write-Status "Deploying OpenHands..."
    
    try {
        # 检查是否有正在运行的容器并停止
        Write-Status "Checking for existing OpenHands containers..." -Type "Info"
        $existingContainer = docker ps -a --filter "name=openhands-app" --format "{{.Names}}"
        
        if ($existingContainer) {
            Write-Status "Found existing OpenHands container. Stopping and removing..." -Type "Info"
            docker stop openhands-app 2>$null
            docker rm openhands-app 2>$null
        }
        
        # 使用直接的 Docker 命令部署
        Write-Status "Deploying OpenHands container using Docker..." -Type "Info"
        
        # 准备正确的路径格式 - 完全修复格式问题
        $stateDir = $stateDirPath.Replace('\', '/')
        $workspace = $workspaceDir.Replace('\', '/')
        
        # 使用批处理命令构建完整的Docker命令，避免转义问题
        $script = @"
@echo off
docker run -d --name openhands-app ^
  -p $webPort`:3000 ^
  -e SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:0.30-nikolaik ^
  -e LOG_ALL_EVENTS=true ^
  -e SANDBOX_USER_ID=1000 ^
  -e WORKSPACE_MOUNT_PATH=$workspace ^
  -v /var/run/docker.sock:/var/run/docker.sock ^
  -v "$stateDir":/.openhands-state ^
  -v "$workspace":/opt/workspace_base ^
  --add-host=host.docker.internal:host-gateway ^
  -t docker.all-hands.dev/all-hands-ai/openhands:latest
"@
        
        # 将命令写入临时批处理文件
        $batchFile = "$env:TEMP\openhands_deploy.bat"
        $script | Out-File -FilePath $batchFile -Encoding ASCII
        
        # 执行批处理文件
        Write-Status "Executing deployment command via batch file..." -Type "Info"
        cmd /c $batchFile
        
        # 验证容器是否正在运行
        Start-Sleep -Seconds 5
        $containerRunning = docker ps --filter "name=openhands-app" --format "{{.Status}}" | Select-String "Up"
        
        # 清理临时文件
        if (Test-Path $batchFile) {
            Remove-Item $batchFile -Force
        }
        
        if ($containerRunning) {
            Write-Status "OpenHands deployed successfully!" -Type "Success"
            return $true
        } else {
            # 检查容器日志以查看错误
            Write-Status "Container not running properly. Checking logs..." -Type "Warning"
            $containerLogs = docker ps -a --filter "name=openhands-app" --format "{{.Status}}"
            Write-Status "Container status: $containerLogs" -Type "Info"
            
            $containerLogs = docker logs openhands-app 2>&1
            if ($containerLogs) {
                Write-Status "Container logs show:" -Type "Info"
                $containerLogs | ForEach-Object { Write-Status $_ -Type "Info" }
            } else {
                Write-Status "No container logs available" -Type "Warning"
            }
            
            Write-Status "Deployment failed. Please check Docker for errors." -Type "Error"
            return $false
        }
    }
    catch {
        Write-Status "Failed to deploy OpenHands: $_" -Type "Error"
        
        # 输出完整错误详情
        Write-Status "Error details:" -Type "Error"
        Write-Status "$($_.Exception)" -Type "Error"
        Write-Status "$($_.ScriptStackTrace)" -Type "Error"
        
        return $false
    }
}
# 由于 Docker Desktop 在 Windows 上的行为，使用 docker-compose 是更好的选择
# 使用 docker-compose 部署
# function Deploy-OpenHands {
#     if (-not (Test-Prerequisites -RequiredSteps @("WSLInstalled", "DockerInstalled", "DockerRunning", "WorkspaceSetup", "ComposeCreated"))) {
#         return $false
#     }
    
#     Write-Status "Deploying OpenHands..."
    
#     try {
#         # 检查是否有正在运行的容器并停止
#         Write-Status "Checking for existing OpenHands containers..." -Type "Info"
#         $existingContainer = docker ps -a --filter "name=openhands-app" --format "{{.Names}}"
        
#         if ($existingContainer) {
#             Write-Status "Found existing OpenHands container. Stopping and removing..." -Type "Info"
#             docker stop openhands-app 2>$null
#             docker rm openhands-app 2>$null
#         }
        
#         # 使用 docker-compose 文件部署
#         Write-Status "Deploying OpenHands using docker-compose..." -Type "Info"
#         Write-Status "Using docker-compose file: $dockerComposeFile" -Type "Info"
        
#         # 切换到包含 docker-compose.yaml 的目录
#         $currentDir = Get-Location
#         $composeDir = Split-Path -Parent $dockerComposeFile
#         Set-Location $composeDir
        
#         # 执行 docker-compose up 命令
#         docker-compose -f $dockerComposeFile up -d
        
#         # 恢复原始目录
#         Set-Location $currentDir
        
#         # 验证容器是否正在运行
#         Start-Sleep -Seconds 5
#         $containerRunning = docker ps --filter "name=openhands-app" --format "{{.Status}}" | Select-String "Up"
        
#         if ($containerRunning) {
#             Write-Status "OpenHands deployed successfully!" -Type "Success"
#             return $true
#         } else {
#             # 检查容器日志以查看错误
#             Write-Status "Container not running properly. Checking logs..." -Type "Warning"
#             $containerLogs = docker ps -a --filter "name=openhands-app" --format "{{.Status}}"
#             Write-Status "Container status: $containerLogs" -Type "Info"
            
#             $containerLogs = docker logs openhands-app 2>&1
#             if ($containerLogs) {
#                 Write-Status "Container logs show:" -Type "Info"
#                 $containerLogs | ForEach-Object { Write-Status $_ -Type "Info" }
#             } else {
#                 Write-Status "No container logs available" -Type "Warning"
#             }
            
#             Write-Status "Deployment failed. Please check Docker for errors." -Type "Error"
#             return $false
#         }
#     }
#     catch {
#         Write-Status "Failed to deploy OpenHands: $_" -Type "Error"
        
#         # 输出完整错误详情
#         Write-Status "Error details:" -Type "Error"
#         Write-Status "$($_.Exception)" -Type "Error"
#         Write-Status "$($_.ScriptStackTrace)" -Type "Error"
        
#         return $false
#     }
# }

# Function to open OpenHands in browser
function Open-OpenHandsInBrowser {
    if (-not (Test-Prerequisites -RequiredSteps @("OpenHandsDeployed"))) {
        return $false
    }
    
    Write-Status "Opening OpenHands in browser..."
    
    try {
        Start-Process "http://localhost:$webPort"
        Write-Status "OpenHands should now be accessible at http://localhost:$webPort" -Type "Success"
        return $true
    }
    catch {
        Write-Status "Failed to open browser: $_" -Type "Warning"
        Write-Status "Please manually navigate to http://localhost:$webPort in your browser" -Type "Info"
        return $false
    }
}

# Main execution
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  OpenHands Windows Deployment Script  " -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check and install WSL
Write-Status "Step 1: Checking WSL installation..."
if (-not (Test-WSL)) {
    Write-Status "WSL is not installed" -Type "Warning"
    $installWSL = Read-Host "Do you want to install WSL? (y/n)"
    
    if ($installWSL -eq 'y') {
        $stepStatus["WSLInstalled"] = Install-WSL
        if (-not $stepStatus["WSLInstalled"]) {
            Write-Status "WSL installation failed. Cannot continue." -Type "Error"
            exit 1
        }
    }
    else {
        Write-Status "WSL installation skipped. OpenHands requires WSL to function properly." -Type "Warning"
        $continueAnyway = Read-Host "Do you want to continue anyway? (y/n)"
        if ($continueAnyway -eq 'y') {
            $stepStatus["WSLInstalled"] = $true # User chose to continue without WSL
        } else {
            Write-Status "Deployment canceled." -Type "Error"
            exit 1
        }
    }
}
else {
    Write-Status "WSL is already installed" -Type "Success"
    $stepStatus["WSLInstalled"] = $true
}

# Step 2: Check and install Docker Desktop
Write-Status "Step 2: Checking Docker Desktop installation..."
if (-not (Test-DockerDesktop)) {
    Write-Status "Docker Desktop is not installed" -Type "Warning"
    $installDocker = Read-Host "Do you want to install Docker Desktop? (y/n)"
    
    if ($installDocker -eq 'y') {
        $stepStatus["DockerInstalled"] = Install-DockerDesktop
        if (-not $stepStatus["DockerInstalled"]) {
            Write-Status "Docker Desktop installation failed. Cannot continue." -Type "Error"
            exit 1
        }
    }
    else {
        Write-Status "Docker Desktop installation skipped. OpenHands requires Docker Desktop to function." -Type "Error"
        exit 1
    }
}
else {
    Write-Status "Docker Desktop is already installed" -Type "Success"
    $stepStatus["DockerInstalled"] = $true
}

# Step 3: Check Docker service status
Write-Status "Step 3: Checking Docker service status..."
if (-not (Test-DockerRunning)) {
    Write-Status "Docker service is not responding" -Type "Warning"
    
    $dockerDesktopProcess = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
    if ($dockerDesktopProcess) {
        Write-Status "Docker Desktop application is running, but the Docker service is not responding" -Type "Warning"
        Write-Status "This could mean Docker is still initializing" -Type "Info"
        
        $waitForDocker = Read-Host "Do you want to wait for Docker to initialize? (y/n)"
        if ($waitForDocker -eq 'y') {
            $stepStatus["DockerRunning"] = Start-DockerDesktop
            if (-not $stepStatus["DockerRunning"]) {
                Write-Status "Docker service still not responding after waiting" -Type "Error"
                Write-Status "Please make sure Docker Desktop is properly configured and running" -Type "Info"
                exit 1
            }
        }
        else {
            Write-Status "Docker must be running to deploy OpenHands" -Type "Error"
            exit 1
        }
    }
    else {
        $startDocker = Read-Host "Do you want to start Docker Desktop? (y/N, default=y)"
        if ($startDocker -eq 'y' -or $startDocker -eq '' -or $startDocker -eq 'Y') {
            $stepStatus["DockerRunning"] = Start-DockerDesktop
            
            if (-not $stepStatus["DockerRunning"]) {
                Write-Status "Docker startup failed. Please:" -Type "Error"
                Write-Status "1. Start Docker Desktop manually from the Start menu" -Type "Info"
                Write-Status "2. Wait for the Docker icon to show 'Docker is running' in the system tray" -Type "Info"
                Write-Status "3. Run this script again" -Type "Info"
                exit 1
            }
        }
        else {
            Write-Status "Docker must be running to deploy OpenHands" -Type "Error"
            exit 1
        }
    }
}
else {
    Write-Status "Docker service is running" -Type "Success"
    $stepStatus["DockerRunning"] = $true
}

# Step 4: Setup workspace directories
Write-Status "Step 4: Setting up workspace directories..."
$stepStatus["WorkspaceSetup"] = Setup-Workspace
if (-not $stepStatus["WorkspaceSetup"]) {
    Write-Status "Failed to set up workspace directories. Cannot continue." -Type "Error"
    exit 1
}

# Step 5: Create/update docker-compose.yaml
Write-Status "Step 5: Preparing OpenHands configuration..."
$stepStatus["ComposeCreated"] = Update-DockerComposeFile
if (-not $stepStatus["ComposeCreated"]) {
    Write-Status "Failed to create docker-compose configuration. Cannot continue." -Type "Error"
    exit 1
}

# Step 6: Pull Docker images
Write-Status "Step 6: Pulling required Docker images..."
$stepStatus["ImagesPulled"] = Pull-DockerImages
# Continue even if image pull fails, as they might be pulled during deployment

# Step 7: Deploy OpenHands
Write-Status "Step 7: Deploying OpenHands..."
$stepStatus["OpenHandsDeployed"] = Deploy-OpenHands
if (-not $stepStatus["OpenHandsDeployed"]) {
    Write-Status "Failed to deploy OpenHands. Cannot continue." -Type "Error"
    exit 1
}

# 添加额外的等待时间，确保服务完全启动
Write-Status "Waiting for OpenHands service to initialize (10 seconds)..." -Type "Info"
Start-Sleep -Seconds 10

# Step 8: Open in browser
Write-Status "Step 8: Opening OpenHands in browser..."
Open-OpenHandsInBrowser

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  OpenHands deployment completed!      " -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host ""
Write-Host "If you encounter any issues, please check the Docker Desktop logs"
Write-Host "or run 'docker logs openhands-app' to view container logs."
Write-Host ""
Write-Host "Access OpenHands at http://localhost:$webPort"