# P0 验收演示启动脚本
# 启动 workbench + StockAnal_Sys 并运行端到端测试

$ErrorActionPreference = "Continue"

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "P0 验收演示启动脚本" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# 设置环境变量（允许外部覆盖端口/host）
$repoRoot = (Resolve-Path .).Path
$env:PYTHONPATH = $repoRoot
$env:WORKBENCH_ROOT = $repoRoot
if (![string]::IsNullOrWhiteSpace($env:WORKBENCH_HOST)) {
    $workbenchHost = $env:WORKBENCH_HOST
} else {
    $workbenchHost = "127.0.0.1"
    $env:WORKBENCH_HOST = $workbenchHost
}
if (![string]::IsNullOrWhiteSpace($env:WORKBENCH_PORT)) {
    $workbenchPort = [int]$env:WORKBENCH_PORT
} else {
    $workbenchPort = 8000
    $env:WORKBENCH_PORT = "$workbenchPort"
}
$env:WORKBENCH_DATA_DIR = Join-Path $repoRoot "data"
$env:WORKBENCH_DB_PATH = Join-Path $env:WORKBENCH_DATA_DIR "workbench.db"
$env:WORKBENCH_API_BASE = ("http://{0}:{1}/api/v1" -f $workbenchHost, $workbenchPort)

function Ensure-VenvPython {
    $venvPy = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
    if (Test-Path $venvPy) { return $venvPy }

    Write-Host "   未检测到 .venv，正在创建虚拟环境..." -ForegroundColor Gray
    try {
        & python -m venv .venv 2>&1 | Out-Null
    } catch {
        Write-Host "   ❌ 创建 .venv 失败：请先确保 python 可用 (建议 conda/base 或系统 Python)。" -ForegroundColor Red
        exit 1
    }
    if (!(Test-Path $venvPy)) {
        Write-Host "   ❌ 创建 .venv 后仍未找到 $venvPy" -ForegroundColor Red
        exit 1
    }
    return $venvPy
}

$pythonExe = Ensure-VenvPython
$condaEnv = $env:CONDA_DEFAULT_ENV
if ([string]::IsNullOrWhiteSpace($condaEnv)) { $condaEnv = "(not conda)" }
Write-Host ("Conda env: {0}" -f $condaEnv) -ForegroundColor DarkGray
Write-Host ("Python exe: {0}" -f $pythonExe) -ForegroundColor DarkGray

function Get-ListenerPid([int]$Port) {
    try {
        $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $c) { return [int]$c.OwningProcess }
    } catch {
        # Some environments deny access to Get-NetTCPConnection; fall back to netstat.
    }
    try {
        $hit = netstat -ano -p tcp 2>$null | Select-String -Pattern (":$Port\\s+.*LISTENING\\s+(\\d+)\\s*$") | Select-Object -First 1
        if ($hit -and ($hit.Line -match "LISTENING\\s+(\\d+)\\s*$")) {
            return [int]$Matches[1]
        }
    } catch {
        return $null
    }
    return $null
}

$listenerPid = Get-ListenerPid -Port $workbenchPort
if ($listenerPid) {
    $proc = Get-Process -Id $listenerPid -ErrorAction SilentlyContinue
    $pname = if ($proc) { $proc.ProcessName } else { "unknown" }
    Write-Host "⚠️  端口 $workbenchPort 已被占用 (PID=$listenerPid, $pname)。" -ForegroundColor Yellow
    $ans = Read-Host "是否停止该进程以继续启动 Workbench? (y/N)"
    if ($ans -match '^[Yy]') {
        try {
            Stop-Process -Id $listenerPid -Force -ErrorAction Stop
            Start-Sleep -Seconds 1
        } catch {
            Write-Host "   ❌ 无法停止占用端口的进程，请手动释放端口后重试。" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "   退出：请释放端口或设置 `$env:WORKBENCH_PORT 后重试。" -ForegroundColor Yellow
        exit 1
    }
}

# 创建数据目录
if (!(Test-Path "data")) {
    New-Item -ItemType Directory -Path "data" | Out-Null
}

Write-Host "1. 检查 Python 环境..." -ForegroundColor Yellow
try {
    $pythonVersion = & $pythonExe --version 2>&1
    Write-Host "   $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Python 未安装或未添加到 PATH" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "2. 安装依赖..." -ForegroundColor Yellow

Write-Host "   安装 workbench 依赖..." -ForegroundColor Gray
if (!(Test-Path "workbench\requirements.txt")) {
    Write-Host "   ❌ 未找到 workbench\requirements.txt" -ForegroundColor Red
    exit 1
}
& $pythonExe -m pip install -q -r workbench\requirements.txt

$uiReq = $env:STOCKANAL_REQUIREMENTS
if ([string]::IsNullOrWhiteSpace($uiReq)) {
    if ($env:STOCKANAL_FULL -and $env:STOCKANAL_FULL.ToLower() -in @("1", "true", "yes")) {
        $uiReq = "StockAnal_Sys\requirements.txt"
    } else {
        $uiReq = "StockAnal_Sys\requirements_ui.txt"
    }
}

Write-Host "   安装 StockAnal_Sys 依赖 ($uiReq)..." -ForegroundColor Gray
if (!(Test-Path $uiReq)) {
    Write-Host "   ❌ 未找到 $uiReq" -ForegroundColor Red
    exit 1
}
& $pythonExe -m pip install -q -r $uiReq

Write-Host ""
Write-Host "3. 启动 Workbench API 服务 (端口 $workbenchPort)..." -ForegroundColor Yellow

# 在后台启动 workbench
$workbenchJob = Start-Job -ScriptBlock {
    param($root, $host, $port, $pyExe)
    Set-Location $root
    $env:PYTHONPATH = $root
    $env:WORKBENCH_ROOT = $root
    $env:WORKBENCH_HOST = $host
    $env:WORKBENCH_PORT = "$port"
    $env:WORKBENCH_DATA_DIR = Join-Path $root "data"
    $env:WORKBENCH_DB_PATH = Join-Path $env:WORKBENCH_DATA_DIR "workbench.db"
    # Merge stderr into stdout so Receive-Job can show startup failures.
    & $pyExe -m workbench 2>&1
} -ArgumentList $repoRoot, $workbenchHost, $workbenchPort, $pythonExe

Write-Host "   ⏳ 等待 API 服务启动..." -ForegroundColor Gray
Start-Sleep -Seconds 5

# 检查 API 是否启动
$maxRetries = 30
$apiReady = $false
for ($i = 0; $i -lt $maxRetries; $i++) {
    try {
        $response = Invoke-RestMethod -Uri ("http://{0}:{1}/api/v1/health" -f $workbenchHost, $workbenchPort) -TimeoutSec 5
        if ($response.ok) {
            $apiReady = $true
            Write-Host "   ✅ API 服务已启动" -ForegroundColor Green
            break
        }
    } catch {
        # 忽略错误
    }

    # If the background job crashed (e.g. port bind failure), surface logs early.
    if ($workbenchJob.State -ne "Running") {
        Write-Host "   ❌ API 进程已退出 (state=$($workbenchJob.State))" -ForegroundColor Red
        $jobErr = $null
        $jobOut = Receive-Job $workbenchJob -Keep -ErrorVariable jobErr -ErrorAction SilentlyContinue
        if ($jobOut) {
            Write-Host "---- Workbench 输出 ----" -ForegroundColor DarkGray
            $jobOut | ForEach-Object { Write-Host $_ }
            Write-Host "------------------------" -ForegroundColor DarkGray
        }
        if ($jobErr) {
            Write-Host "---- Workbench 错误 ----" -ForegroundColor DarkGray
            $jobErr | ForEach-Object { Write-Host $_ }
            Write-Host "------------------------" -ForegroundColor DarkGray
        } else {
            Write-Host "   (无可用输出；可能是启动即崩溃或输出被缓冲)" -ForegroundColor DarkGray
        }
        break
    }
    Start-Sleep -Seconds 2
    Write-Host "   ⏳ 等待中... ($($i+1)/$maxRetries)" -ForegroundColor Gray
}

if (!$apiReady) {
    Write-Host "   ❌ API 服务启动超时" -ForegroundColor Red
    $jobErr = $null
    $jobOut = Receive-Job $workbenchJob -Keep -ErrorVariable jobErr -ErrorAction SilentlyContinue
    if ($jobOut) {
        Write-Host "---- Workbench 输出 ----" -ForegroundColor DarkGray
        $jobOut | ForEach-Object { Write-Host $_ }
        Write-Host "------------------------" -ForegroundColor DarkGray
    }
    if ($jobErr) {
        Write-Host "---- Workbench 错误 ----" -ForegroundColor DarkGray
        $jobErr | ForEach-Object { Write-Host $_ }
        Write-Host "------------------------" -ForegroundColor DarkGray
    }
    Stop-Job $workbenchJob -ErrorAction SilentlyContinue
    exit 1
}

Write-Host ""
Write-Host "4. 运行端到端验收测试..." -ForegroundColor Yellow

# 运行测试
$testResult = & $pythonExe tests\end_to_end_test.py
Write-Host $testResult

Write-Host ""
Write-Host "5. 启动 StockAnal_Sys UI (端口 8888)..." -ForegroundColor Yellow

# 在后台启动 UI
$uiJob = Start-Job -ScriptBlock {
    param($root, $apiBase, $pyExe)
    Set-Location $root
    $env:PYTHONPATH = $root
    $env:PORT = "8888"
    $env:HOST = "0.0.0.0"
    $env:WORKBENCH_API_BASE = $apiBase
    # Default to preview mode unless explicitly asked to boot the full analytics server.
    if (-not ($env:STOCKANAL_FULL -and $env:STOCKANAL_FULL.ToLower() -in @("1", "true", "yes"))) {
        $env:UI_PREVIEW = "1"
    }
    & $pyExe StockAnal_Sys\run.py
} -ArgumentList $repoRoot, $env:WORKBENCH_API_BASE, $pythonExe

Write-Host "   ⏳ 等待 UI 服务启动..." -ForegroundColor Gray
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "✅ 系统已启动" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "🌐 访问地址:" -ForegroundColor Yellow
Write-Host "   - Workbench API: http://$workbenchHost`:$workbenchPort" -ForegroundColor White
Write-Host "   - API 文档: http://$workbenchHost`:$workbenchPort/docs" -ForegroundColor White
Write-Host "   - UI 界面: http://127.0.0.1:8888" -ForegroundColor White
Write-Host ""
Write-Host "📝 操作建议:" -ForegroundColor Yellow
Write-Host "   1. 访问 UI 界面体验完整功能" -ForegroundColor White
Write-Host "   2. 使用搜索功能 (输入 600519 查看贵州茅台)" -ForegroundColor White
Write-Host "   3. 在选股工作台中查看 K 线和指标" -ForegroundColor White
Write-Host "   4. 在组合管理中创建投资组合" -ForegroundColor White
Write-Host ""
Write-Host "⚠️  按 Ctrl+C 停止所有服务" -ForegroundColor Yellow
Write-Host ""

# 等待用户中断
try {
    while ($true) {
        Start-Sleep -Seconds 10
    }
} finally {
    Write-Host ""
    Write-Host "🛑 正在停止服务..." -ForegroundColor Yellow

    # 停止后台任务（只清理本脚本启动的 jobs，避免误伤用户其它 job）
    if ($workbenchJob) {
        Stop-Job $workbenchJob -ErrorAction SilentlyContinue
        Remove-Job $workbenchJob -Force -ErrorAction SilentlyContinue
    }
    if ($uiJob) {
        Stop-Job $uiJob -ErrorAction SilentlyContinue
        Remove-Job $uiJob -Force -ErrorAction SilentlyContinue
    }

    Write-Host "✅ 所有服务已停止" -ForegroundColor Green
}

