<#
SessionStart 훅. 직속 상위뿐 아니라 그 위 전체 체인을 재귀 확인해 PASS 가 아닌 단계가
있으면 세션 첫 문맥에 차단 경고를 주입한다. 루트 .claude/settings.json 에서 호출한다.

    $env:GATE_STAGE = 'impl'; powershell -NoProfile -ExecutionPolicy Bypass -File tools/gate-check.ps1
    $env:GATE_STAGE = 'vv'; powershell -NoProfile -ExecutionPolicy Bypass -File tools/gate-check.ps1

체인이 끊긴 이유: 각 세션은 자기 직속 상위 GATE 만 봐 왔다. docs 가 FAIL 이어도
impl 이 이미 PASS 스냅샷을 들고 있으면(재실행 안 함) vv 는 그 사실을 전혀
모른 채 진행할 수 있었다. 이제 -Upstream 이 가리키는 단계부터 docs 까지 전체를 훑는다.

판정 파일은 tools/gates/<단계>.GATE.md 에 모여 있다 - 구현이 저장소 루트로 올라오면서
단계별 폴더가 사라졌기 때문이다.
#>
param(
    [string]$Upstream = $env:GATE_STAGE
)

if ([string]::IsNullOrWhiteSpace($Upstream)) { $Upstream = 'docs' }

# 파이프라인 순서. $Upstream 은 지금 시작하려는 단계다 - 그 앞부분(자기 자신 제외)이
# 확인 대상이다. docs 는 최상류라 확인할 상류가 없다(자기 자신을 넣으면 docs 를 처음
# 작성하는 세션에서마다 "docs 가 PASS 아님" 이라는 자기참조 경고가 항상 뜬다).
$chain = @('docs', 'impl', 'vv')
$idx = $chain.IndexOf($Upstream)
if ($idx -lt 0) {
    Write-Output "UNKNOWN STAGE - '$Upstream' 은 알려진 단계가 아니다: $($chain -join ', ')"
    exit 0
}
if ($idx -eq 0) {
    Write-Output "UPSTREAM CHAIN OK - docs 는 최상류라 확인할 상류가 없다. 이 단계를 진행해도 된다."
    exit 0
}
$toCheck = $chain[0..($idx - 1)]

$root = Split-Path $PSScriptRoot -Parent
$failed = @()

foreach ($stage in $toCheck) {
    $gate = Join-Path (Join-Path $root 'tools') (Join-Path 'gates' "$stage.GATE.md")
    if (-not (Test-Path $gate)) {
        $failed += [PSCustomObject]@{ Stage = $stage; Reason = "tools/gates/$stage.GATE.md 가 없다"; Blocking = @() }
        continue
    }
    $first = (Get-Content -LiteralPath $gate -TotalCount 1 -Encoding UTF8)
    if ($first -match '^\s*STATUS:\s*PASS\s*$') { continue }

    $blocking = @()
    $lines = Get-Content -LiteralPath $gate -Encoding UTF8
    $inBlock = $false
    foreach ($l in $lines) {
        if ($l -match '^BLOCKING:') { $inBlock = $true; continue }
        if ($inBlock) {
            if ($l.Trim() -eq '' -or $l -match '^<!--') { break }
            $blocking += $l.Trim()
        }
    }
    $failed += [PSCustomObject]@{ Stage = $stage; Reason = $first; Blocking = $blocking }
}

if ($failed.Count -eq 0) {
    Write-Output "UPSTREAM CHAIN OK - $($toCheck -join ' -> ') 전부 PASS. 이 단계를 진행해도 된다."
    exit 0
}

Write-Output "UPSTREAM CHAIN NOT PASSED - 체인 중 $($failed.Count)개 단계가 막혀 있다."
Write-Output "이 단계의 작업을 시작하지 않는다. 사용자에게 아래 단계 미완료를 알리고 중단한다."
foreach ($f in $failed) {
    Write-Output "  [$($f.Stage)] $($f.Reason)"
    foreach ($b in $f.Blocking) { Write-Output "    - $b" }
    Write-Output "    해소: 'tools/gate.ps1 $($f.Stage)' 를 통과시킨다."
}
exit 0
