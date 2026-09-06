# 실습 환경 설치 스크립트
#   1) requirements.txt 의 파이썬 라이브러리 설치
#   2) Ollama 설치
#   3) 실습용 모델(qwen3-vl:4b-instruct, embeddinggemma) 다운로드
# 더블 클릭 실행: 같은 폴더의 "설치스크립트.bat" 을 더블 클릭하세요.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$MODELS = @('qwen3-vl:4b-instruct', 'embeddinggemma')
$REQUIREMENTS = Join-Path $PSScriptRoot 'requirements.txt'

function Update-PathFromRegistry {
    # 설치 직후에는 현재 세션 PATH 에 ollama 가 없으므로 레지스트리에서 다시 읽어온다
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Test-OllamaServer {
    try {
        Invoke-WebRequest -Uri 'http://127.0.0.1:11434' -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-PythonCommand {
    # py 런처 -> python 순으로 탐색. @(실행파일, 기본인자...) 형태로 반환
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            & $py.Source -3 --version | Out-Null
            if ($LASTEXITCODE -eq 0) { return @($py.Source, '-3') }
        } catch { }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        try {
            $ver = & $python.Source --version
            # Microsoft Store 안내용 더미 python.exe 걸러내기
            if ($LASTEXITCODE -eq 0 -and "$ver" -match 'Python 3') { return @($python.Source) }
        } catch { }
    }

    return $null
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  실습 환경 설치 (파이썬 라이브러리 + Ollama)" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------
# 1단계: 파이썬 라이브러리 설치
# ---------------------------------------------------------------
Write-Host "[1/4] 파이썬 라이브러리를 설치합니다." -ForegroundColor Green

$pythonInstalled = $false

if (-not (Test-Path $REQUIREMENTS)) {
    Write-Host "[경고] requirements.txt 를 찾을 수 없습니다: $REQUIREMENTS" -ForegroundColor Yellow
    Write-Host "       파이썬 라이브러리 설치를 건너뜁니다." -ForegroundColor Yellow
}
else {
    $pythonCmd = Get-PythonCommand

    if (-not $pythonCmd) {
        Write-Host "[경고] 파이썬을 찾을 수 없습니다." -ForegroundColor Yellow
        Write-Host "       https://www.python.org/downloads/ 에서 파이썬을 설치할 때" -ForegroundColor Yellow
        Write-Host "       'Add python.exe to PATH' 를 체크한 뒤 이 스크립트를 다시 실행하세요." -ForegroundColor Yellow
        Write-Host "       (Ollama 설치는 계속 진행합니다)" -ForegroundColor Yellow
    }
    else {
        $exe     = $pythonCmd[0]
        $baseArg = @($pythonCmd | Select-Object -Skip 1)

        Write-Host "      사용할 파이썬: $exe $baseArg" -ForegroundColor DarkGray
        try { & $exe @baseArg --version } catch { }

        try {
            Write-Host "      pip 를 최신 버전으로 갱신하는 중..." -ForegroundColor DarkGray
            & $exe @baseArg -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { throw "pip 업그레이드가 오류 코드 $LASTEXITCODE 로 종료되었습니다." }

            Write-Host "      requirements.txt 의 패키지를 설치하는 중... (몇 분 걸릴 수 있습니다)" -ForegroundColor DarkGray
            & $exe @baseArg -m pip install -r $REQUIREMENTS
            if ($LASTEXITCODE -ne 0) { throw "pip install 이 오류 코드 $LASTEXITCODE 로 종료되었습니다." }

            Write-Host "파이썬 라이브러리 설치가 완료되었습니다." -ForegroundColor Green
            $pythonInstalled = $true
        }
        catch {
            Write-Host ""
            Write-Host "[경고] 파이썬 라이브러리 설치에 실패했습니다." -ForegroundColor Yellow
            Write-Host $_.Exception.Message -ForegroundColor Yellow
            Write-Host "       새 터미널에서 아래 명령을 직접 실행해 보세요:" -ForegroundColor Yellow
            Write-Host "           pip install -r `"$REQUIREMENTS`"" -ForegroundColor Yellow
            Write-Host "       (Ollama 설치는 계속 진행합니다)" -ForegroundColor Yellow
        }
    }
}

Write-Host ""

# ---------------------------------------------------------------
# 2단계: Ollama 설치
# ---------------------------------------------------------------
Write-Host "[2/4] Ollama 를 설치합니다." -ForegroundColor Green

$doInstall = $true
$existing = Get-Command ollama -ErrorAction SilentlyContinue

if ($existing) {
    Write-Host "[알림] Ollama 가 이미 설치되어 있습니다: $($existing.Source)" -ForegroundColor Yellow
    try { ollama --version } catch { }
    Write-Host ""
    $answer = Read-Host "다시 설치(업데이트) 하시겠습니까? (Y/N)"
    if ($answer -notmatch '^[Yy]') {
        Write-Host "설치를 건너뛰고 모델 다운로드로 넘어갑니다." -ForegroundColor Yellow
        $doInstall = $false
    }
}

if ($doInstall) {
    try {
        Write-Host "      설치 스크립트를 내려받는 중..." -ForegroundColor DarkGray
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $script = Invoke-RestMethod -Uri 'https://ollama.com/install.ps1'

        Write-Host "      Ollama 를 설치하는 중... (몇 분 걸릴 수 있습니다)" -ForegroundColor DarkGray
        Invoke-Expression $script

        Write-Host "Ollama 설치가 완료되었습니다." -ForegroundColor Green
    }
    catch {
        Write-Host ""
        Write-Host "[오류] Ollama 설치에 실패했습니다." -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        Write-Host ""
        Write-Host "수동 설치: https://ollama.com/download 에서 설치 파일을 받은 뒤" -ForegroundColor Yellow
        Write-Host "           이 스크립트를 다시 실행하세요." -ForegroundColor Yellow
        return
    }
}

Write-Host ""

# ---------------------------------------------------------------
# 3단계: PATH 갱신 및 서버 기동 확인
# ---------------------------------------------------------------
Write-Host "[3/4] Ollama 서버 상태를 확인합니다." -ForegroundColor Green

Update-PathFromRegistry

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "[오류] ollama 명령을 찾을 수 없습니다." -ForegroundColor Red
    Write-Host "PC 를 재부팅하거나 새 터미널을 연 뒤 아래 명령을 직접 실행하세요:" -ForegroundColor Yellow
    foreach ($m in $MODELS) {
        Write-Host "    ollama pull $m" -ForegroundColor Yellow
    }
    return
}

if (-not (Test-OllamaServer)) {
    Write-Host "      Ollama 서버를 시작하는 중..." -ForegroundColor DarkGray
    Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-OllamaServer) { $ready = $true; break }
    }

    if (-not $ready) {
        Write-Host ""
        Write-Host "[오류] Ollama 서버가 시작되지 않았습니다." -ForegroundColor Red
        Write-Host "새 터미널에서 'ollama serve' 실행 후 아래 명령을 시도하세요:" -ForegroundColor Yellow
        foreach ($m in $MODELS) {
            Write-Host "    ollama pull $m" -ForegroundColor Yellow
        }
        return
    }
}

Write-Host "Ollama 서버가 실행 중입니다." -ForegroundColor Green
Write-Host ""

# ---------------------------------------------------------------
# 4단계: 모델 다운로드
# ---------------------------------------------------------------
Write-Host "[4/4] 실습용 모델을 내려받습니다: $($MODELS -join ', ')" -ForegroundColor Green
Write-Host "      용량이 크므로 네트워크 속도에 따라 오래 걸릴 수 있습니다." -ForegroundColor DarkGray
Write-Host ""

$failed = @()

foreach ($model in $MODELS) {
    Write-Host "  - $model 다운로드 중..." -ForegroundColor Green
    try {
        ollama pull $model
        if ($LASTEXITCODE -ne 0) { throw "ollama pull 이 오류 코드 $LASTEXITCODE 로 종료되었습니다." }
        Write-Host "  - $model 완료" -ForegroundColor Green
    }
    catch {
        Write-Host "  - [오류] $model 다운로드에 실패했습니다." -ForegroundColor Red
        Write-Host "    $($_.Exception.Message)" -ForegroundColor Red
        $failed += $model
    }
    Write-Host ""
}

if ($failed.Count -gt 0) {
    Write-Host "[경고] 아래 모델은 받지 못했습니다. 새 터미널에서 다시 시도하세요:" -ForegroundColor Yellow
    foreach ($m in $failed) {
        Write-Host "    ollama pull $m" -ForegroundColor Yellow
    }
    Write-Host ""
}

# ---------------------------------------------------------------
# 완료
# ---------------------------------------------------------------
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  준비 완료" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

if ($pythonInstalled) {
    Write-Host "파이썬 라이브러리: 설치 완료" -ForegroundColor Green
} else {
    Write-Host "파이썬 라이브러리: 설치되지 않음 (위 메시지를 확인하세요)" -ForegroundColor Yellow
}

Write-Host "설치된 모델 목록:" -ForegroundColor Green
try { ollama list } catch { }
Write-Host ""
Write-Host "테스트: 새 터미널에서  ollama run $($MODELS[0])" -ForegroundColor Green
