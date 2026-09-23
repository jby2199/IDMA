<#
V&V 단계 게이트 실행기.

  powershell -ExecutionPolicy Bypass -File tools/gate.ps1 docs

해당 단계의 검사를 실제로 실행하고, 그 결과로 tools/gates/<단계>.GATE.md 를 다시 쓴다.
GATE.md 는 사람도 모델도 손으로 고치지 않는다. 판정은 이 스크립트만 한다.
통과하면 exit 0, 실패하면 exit 1.

단계는 3개다:
  docs  요건+설계 (PRD/SRS/SDD/SAD/adr)   — 최상류
  impl  구현 (src/, tests/)
  vv    사용자 실테스트 + 이슈 등록/조치 (issue/0.issue, 1.open, 2.todo, 3.done, 4.archive)

검사 대상은 '실작업 파일'이다. 파일명에 '(template)' 또는 '.example.' 이 들어간 것은
템플릿/예시로 간주해 제외한다. 같은 종류 파일이 여러 개면 전부 검사한다.
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('docs', 'impl', 'vv')]
    [string]$Stage
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent

$evidence = New-Object System.Collections.ArrayList
$blocking = New-Object System.Collections.ArrayList
function Note($msg) { [void]$evidence.Add($msg) }
function Fail($msg) { [void]$blocking.Add($msg) }

# 스킬 디렉토리 탐색. 프로젝트 로컬 '.claude\skills' 를 먼저 보고, 없으면 상위 폴더로
# 거슬러 올라가며 워크스페이스 공용 '.claude\skills' 를 찾는다. 프로젝트마다 갖고 있던
# .claude 를 워크스페이스 루트 한 곳으로 합치면서, 프로젝트 로컬 경로만 보던 기존
# 방식이 validate.py 를 못 찾아 docs 게이트가 '검증 스크립트 없음' 으로 FAIL 났다.
# 판정 기준은 by-prd-writer 의 validate.py 존재 여부다 — 폴더만 있고 내용이 빈
# .claude/skills 를 잘못 집는 것을 막는다.
function Resolve-SkillsDir($startDir) {
    $dir = $startDir
    while ($dir) {
        $cand = Join-Path $dir '.claude\skills'
        if (Test-Path (Join-Path $cand 'by-prd-writer\scripts\validate.py')) { return $cand }
        $parent = Split-Path $dir -Parent
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    return (Join-Path $startDir '.claude\skills')
}

# 실작업 파일만: (template) / .example. 제외
# 산출 문서는 <단계>/docs/ 에 둔다. 하위 폴더(adr/ 등)까지 재귀 검색한다.
# $prefix 는 문서 접두(예: 'SDD','SAD','PRD') — 파일명 어디에 있어도 잡는다
# (예: '2.SAD.md' 도 SAD 로 잡힘). 대문자 접두만 인정한다 — 소문자 'sad.md' 는
# 검사 대상에서 제외된다(의도적 미검사 표시로 오해할 여지를 없앤다).
function Get-WorkFiles($stageDir, $prefix) {
    $docs = Join-Path $stageDir 'docs'
    $searchRoot = if (Test-Path $docs) { $docs } else { $stageDir }
    if (-not (Test-Path $searchRoot)) { return @() }
    return @(Get-ChildItem -LiteralPath $searchRoot -Filter '*.md' -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -notmatch '\(template\)' -and $_.Name -notmatch '\.example\.' -and
            ($_.Name -cmatch [regex]::Escape($prefix))
        })
}

function Read-All($files) {
    if (-not $files -or $files.Count -eq 0) { return '' }
    return (($files | ForEach-Object { [System.IO.File]::ReadAllText($_.FullName) }) -join "`n")
}

function Get-Ids($text, $pattern) {
    if (-not $text) { return @() }
    return @([regex]::Matches($text, $pattern) | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
}

# 정의 줄('[SRS-F001]'이 그 줄 어디에든 있으면 정의로 인정, 위치 제약 없음) 뒤 6줄 안에
# 링크 줄(상위요건:/구현요건:)이 있는지.
# 위치 제약을 없애면서 본문 서술 중의 '[ID]' 인용(아직 <ID> 로 전환 안 된 옛 참조 등)도
# defPattern 에 걸려 정의 후보로 잡힐 수 있다. 그런 인용 occurrence 근처에서 스캔이
# 조기 종료되면 그 뒤에 있는 진짜 정의+링크를 가려 오탐(false orphan)이 난다.
# 그래서 판정을 줄 단위가 아니라 ID 단위로 바꾼다 - 같은 ID 의 모든 occurrence 를 모아
# 그중 하나라도 6줄 이내에 링크가 있으면 그 ID 는 고아가 아니다.
function Find-OrphanDefs($text, $defPattern, $linkKeyword) {
    if (-not $text) { return @() }
    $lines = $text -split "`r?`n"
    $occurrencesById = @{}
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $defPattern) {
            $id = $Matches[1]
            if (-not $occurrencesById.ContainsKey($id)) { $occurrencesById[$id] = @() }
            $occurrencesById[$id] += $i
        }
    }
    $orphans = @()
    foreach ($id in $occurrencesById.Keys) {
        $linked = $false
        foreach ($i in $occurrencesById[$id]) {
            $stop = [Math]::Min($i + 6, $lines.Count - 1)
            for ($j = $i + 1; $j -le $stop; $j++) {
                if ($lines[$j] -match [regex]::Escape($linkKeyword)) { $linked = $true; break }
                if ($lines[$j] -match $defPattern) { break }
            }
            if ($linked) { break }
        }
        if (-not $linked) { $orphans += $id }
    }
    return @($orphans | Sort-Object -Unique)
}

# ISSUE 파일 프론트매터(YAML, --- 사이)에서 라인 단위로 필드를 뽑는다.
# 중첩 없는 flat 파서다 - 정식 YAML 파서가 아니라 이 문서의 고정 스키마 전용.
#   원인단계: <stage>
#   상태: 발견|조치중|파생대기|사람확인대기|완료
#   조치:
#     - 단계: <stage>
#       파생: <stage 또는 빈값>
# 반환: @{ 원인단계=...; 상태=...; 조치단계목록=@(...); 마지막파생=... }
function Get-IssueFrontmatter($filePath) {
    $text = [System.IO.File]::ReadAllText($filePath)
    $fm = [regex]::Match($text, '(?s)^---\s*\r?\n(.*?)\r?\n---')
    if (-not $fm.Success) {
        # 구형식(프론트매터 없음) 하위호환: 본문의 '원인 추정 단계: `stage`' 줄만 인식.
        # 조치/파생 추적은 못 하므로 원인단계만 채우고 나머지는 미확정으로 둔다.
        $bt = [char]96
        $legacy = [regex]::Match($text, "원인 추정 단계\s*:\s*$bt+([\w-]+)$bt+")
        if ($legacy.Success) {
            return @{ 원인단계 = $legacy.Groups[1].Value; 상태 = $null; 조치단계목록 = @(); 마지막파생 = $null }
        }
        return $null
    }
    $body = $fm.Groups[1].Value
    $lines = $body -split "`r?`n"

    $result = @{ 원인단계 = $null; 상태 = $null; 조치단계목록 = @(); 마지막파생 = $null }
    $curStage = $null
    $curDerive = $null
    foreach ($line in $lines) {
        if ($line -match '^\s*원인단계\s*:\s*(\S+)') { $result.원인단계 = $Matches[1]; continue }
        if ($line -match '^\s*상태\s*:\s*(\S+)') { $result.상태 = $Matches[1]; continue }
        if ($line -match '^\s*-\s*단계\s*:\s*(\S+)') {
            if ($curStage) { $result.조치단계목록 += $curStage }
            $curStage = $Matches[1]
            $curDerive = $null
            continue
        }
        if ($line -match '^\s*파생\s*:\s*(\S*)') {
            $curDerive = $Matches[1]
            continue
        }
    }
    if ($curStage) { $result.조치단계목록 += $curStage }
    $result.마지막파생 = $curDerive
    $result.마지막조치단계 = $curStage
    return $result
}

# 이 단계 앞으로 지목된 ISSUE(원인단계 or 파생 대상)가 아직 처리 안 됐는지 확인.
# ISSUE 파일은 항상 issue/2.todo 에 있다(이동하지 않는다) - 각 단계는
# 자기 앞으로 온 것만 걸러서 GATE 를 FAIL 로 되돌린다.
#   1) 원인단계 == 나 인데, 내 이름으로 된 조치 블록이 아직 없음 -> 원인 조치 필요
#   2) 마지막 조치의 파생 == 나 인데, 그 마지막 조치가 내 것이 아님 -> 파생 조치 필요
# 사람 확인 대기는 issue/3.done 에 두고 vv 게이트가 차단한다.
function Test-ReturnedIssues($stageName) {
    $todoDir = Join-Path (Join-Path $root 'issue') '2.todo'
    if (-not (Test-Path $todoDir)) { return }
    $files = @(Get-ChildItem $todoDir -Filter '*.md' -File -ErrorAction SilentlyContinue |
               Where-Object { $_.Name -notmatch '\(template\)' })

    $causeMine = @()
    $deriveMine = @()
    foreach ($f in $files) {
        $fm = Get-IssueFrontmatter $f.FullName
        if (-not $fm) { continue }
        if ($fm.상태 -eq '완료') { continue }
        $acted = $fm.조치단계목록 -contains $stageName
        if ($fm.원인단계 -eq $stageName -and -not $acted) { $causeMine += $f }
        elseif ($fm.마지막파생 -eq $stageName -and $fm.마지막조치단계 -ne $stageName) { $deriveMine += $f }
    }

    if ($causeMine.Count -gt 0) {
        $refs = ($causeMine | ForEach-Object { "issue/2.todo/$($_.Name)" }) -join ', '
        Fail "반송된 ISSUE $($causeMine.Count) 건 처리 필요: $refs"
    }
    if ($deriveMine.Count -gt 0) {
        $refs = ($deriveMine | ForEach-Object { "issue/2.todo/$($_.Name)" }) -join ', '
        Fail "파생 조치 필요 ISSUE $($deriveMine.Count) 건: $refs"
    }
}

# 체인 전파: 상류 전 단계가 PASS 인지 확인한다. 자기 검사가 전부 통과해도 상류가 막혀
# 있으면 이 단계도 FAIL 로 쓴다 — SessionStart 훅(gate-check.ps1)이 경고만 하고 강제하지
# 않으므로, 실행 시점에 게이트 스스로 FAIL 을 물려받게 해서 체인이 끊기지 않게 한다.
# 게이트 판정 파일 경로. 구현이 저장소 루트로 올라오면서 단계별 폴더가 사라졌으므로
# 세 판정 파일을 tools/gates/ 한곳에 모은다. 사람이 손대는 파일이 아니다.
function Get-GatePath($stageName) {
    return (Join-Path (Join-Path $root 'tools') (Join-Path 'gates' "$stageName.GATE.md"))
}

function Test-UpstreamChain($upstreamStages) {
    foreach ($stage in $upstreamStages) {
        $gate = Get-GatePath $stage
        $rel = "tools/gates/$stage.GATE.md"
        if (-not (Test-Path $gate)) { Fail "상류 GATE 없음: $rel"; continue }
        $first = (Get-Content -LiteralPath $gate -TotalCount 1 -Encoding UTF8)
        if ($first -notmatch '^\s*STATUS:\s*PASS\s*$') {
            Fail "상류 미통과: $stage ($first) — $rel 확인"
        }
    }
}

# 요건 무단변경 감지. 단계별 폴더가 사라지면서 없어진 하네스 차원의 쓰기 차단
# (구현 세션이 요건 파일을 못 고치게 하던 deny 규칙)을 대체한다.
# 기준선은 docs 게이트 판정 파일이 마지막으로 커밋된 시점. 그 이후 요건/설계 문서가
# 바뀌었으면 docs 게이트를 다시 통과시키라고 막는다 - 구현하다 막혔을 때 요건을
# 슬쩍 고쳐 맞추는 것을 차단한다. git 이 없으면 조용히 건너뛴다.
function Test-UpstreamDrift {
    $gateRel = 'tools/gates/docs.GATE.md'
    # 대상은 docs/ 전체를 받아와 PowerShell 쪽에서 거른다. 예전에는 파일명을
    # ('docs/1.Concept/PRD.md' 처럼) 박아뒀는데, 문서에 순번 접두가 붙으면서('0.PRD.md')
    # 그 목록에 걸리지 않아 요건을 고쳐도 감지가 안 됐다(fail-open).
    # 이제 Get-WorkFiles 와 같은 규칙으로 판정한다:
    #   - 대문자 PRD/SRS/SDD/SAD 가 파일명 어디에 있어도 대상
    #   - adr/ 아래 .md 전부 대상
    #   - (template) / .example. / notes/ 는 제외
    $targets = @('docs')

    # git 호출 주의: PowerShell 5.1 은 네이티브 명령의 stderr 를 ErrorRecord 로 감싸고,
    # 이 스크립트는 $ErrorActionPreference='Stop' 이라 git 이 경고 한 줄만 찍어도
    # (예: "CRLF will be replaced by LF") 예외로 튄다. 그걸 catch 로 삼키면 이 검사가
    # 조용히 꺼져버린다(fail-open) - 폴더 권한 차단의 대체물이 무력화되는 것이라
    # 절대 그렇게 두면 안 된다. 그래서 이 함수 안에서만 'Continue' 로 낮추고,
    # 성공 여부는 $LASTEXITCODE 로만 판단한다.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Push-Location $root
    try {
        # 'git ... | Select-Object -First 1' 로 쓰면 안 된다. -First 1 이 파이프라인을
        # 조기 종료시키면서 git 이 정상 종료(0)해도 $LASTEXITCODE 가 -1 로 남는다.
        # 그러면 아래 검사가 '기준 커밋 없음' 으로 빠져 요건변경 감지가 통째로
        # 꺼져버린다(fail-open). 전체를 배열로 받은 뒤 첫 줄만 꺼낸다.
        $anchorOut = @(& git log -n 1 --format=%H -- $gateRel 2>$null)
        $anchorRc = $LASTEXITCODE
        $anchor = if ($anchorOut.Count -gt 0) { $anchorOut[0] } else { $null }
        if ($anchorRc -ne 0 -or -not $anchor) {
            # 커밋된 기준점이 없다 - docs 게이트를 로컬에서 PASS 시켰지만 아직
            # 커밋하지 않은 경우가 여기 해당한다. 이때 무조건 건너뛰면(fail-open)
            # "방금 통과시킨 docs 를 기준으로 인정 안 해서 impl 이 못 나간다"는
            # 문제가 아니라 반대로 "요건 변경 감지가 통째로 꺼진다"는 문제가 생긴다.
            # 워킹트리의 docs.GATE.md 가 지금 PASS 라면 그 파일의 마지막 수정 시각을
            # 기준점으로 삼아 그 이후 변경분만 본다 - git 기록이 없어도 로컬 PASS 를
            # 유효한 기준으로 인정한다.
            $gatePathFull = Join-Path $root $gateRel
            if (Test-Path $gatePathFull) {
                $gateFirst = (Get-Content -LiteralPath $gatePathFull -TotalCount 1 -Encoding UTF8)
                if ($gateFirst -match '^\s*STATUS:\s*PASS\s*$') {
                    $anchorTime = (Get-Item -LiteralPath $gatePathFull).LastWriteTimeUtc
                    $changed = @(Get-ChildItem -LiteralPath (Join-Path $root 'docs') -Filter '*.md' -Recurse -File -ErrorAction SilentlyContinue |
                        Where-Object {
                            $_.Name -notmatch '\(template\)' -and $_.Name -notmatch '\.example\.' -and
                            $_.FullName -notmatch '\\notes\\' -and
                            ($_.Name -cmatch '(PRD|SRS|SDD|SAD)' -or $_.FullName -match '\\adr\\|/adr/') -and
                            $_.LastWriteTimeUtc -gt $anchorTime
                        } | ForEach-Object { "docs/" + $_.FullName.Substring((Join-Path $root 'docs').Length + 1).Replace('\', '/') })
                    if ($changed.Count -gt 0) {
                        Fail ("docs 게이트 통과(로컬) 이후 요건/설계 문서가 변경됨: " + ($changed -join ', ') +
                              " — docs 게이트를 다시 통과시킬 것 (gate.ps1 docs)")
                    } else {
                        Note '요건변경 감지: 커밋된 기준 없음, 로컬 PASS 기준(GATE.md 수정시각)으로 대체 확인 -> 무변경'
                    }
                    return
                }
            }
            Note '요건변경 감지: 기준 커밋 없음, 로컬 PASS 도 없음 -> 건너뜀'
            return
        }

        $out = @(& git diff --name-only $anchor -- $targets 2>$null)
        if ($LASTEXITCODE -ne 0) {
            Note '요건변경 감지: git diff 실패 -> 건너뜀'
            return
        }

        # git diff 는 추적되지 않는 새 파일을 못 본다. 새 요건/설계 문서를 커밋 없이
        # 추가하면 감지를 그냥 빠져나가므로, untracked 목록도 같이 받아 합친다.
        $untracked = @(& git ls-files --others --exclude-standard -- $targets 2>$null)
        if ($LASTEXITCODE -eq 0) { $out += $untracked }
        $changed = @($out | Where-Object {
            $_ -and $_.Trim() -and
            $_ -notmatch '\(template\)' -and $_ -notmatch '\.example\.' -and
            $_ -notmatch '^docs/notes/' -and
            ($_ -match '^docs/.*(PRD|SRS|SDD|SAD)[^/]*\.md$' -or $_ -match '^docs/.*/adr/.*\.md$')
        })
    } finally {
        Pop-Location
        $ErrorActionPreference = $prevEap
    }

    if ($changed.Count -gt 0) {
        Fail ("docs 게이트 통과 이후 요건/설계 문서가 변경됨: " + ($changed -join ', ') +
              " — docs 게이트를 다시 통과시킬 것 (gate.ps1 docs)")
    } else {
        Note '요건/설계 문서 무변경 확인 (docs 게이트 기준선 대비)'
    }
}

function Invoke-Validator($validator, $file, $label) {
    if (-not (Test-Path $validator)) { Fail "$label 검증 스크립트 없음: $validator"; return }
    # -X utf8: 콘솔 cp949 로는 못 찍는 문자(⚠ 등)가 출력에 섞이면 python 이 그대로
    # UnicodeEncodeError 로 죽는다. 그러면 게이트 스크립트 전체가 $ErrorActionPreference
    # 'Stop' 때문에 여기서 멈춰버려 이 뒤의 다른 검사가 전부 무시된 채 종료된다.
    # -X utf8 은 python 내부 인코딩만 UTF-8로 바꾼다. stdout 바이트를 PowerShell 이
    # 파이프(2>&1 | Out-String)로 받아 문자열로 디코딩할 때는 여전히 [Console]::OutputEncoding
    # (기본 cp949)을 쓰므로 한글이 깨진다. 호출 직전에 콘솔 출력 인코딩을 UTF-8로 맞춘다.
    $prevOutputEncoding = [Console]::OutputEncoding
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    try {
        $out = & python -X utf8 $validator $file.FullName 2>&1 | Out-String
    } finally {
        [Console]::OutputEncoding = $prevOutputEncoding
    }
    if ($LASTEXITCODE -eq 0) {
        Note "$label $($file.Name) validate.py -> 통과"
    } else {
        $head = ($out -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 4) -join ' / '
        Fail "$label $($file.Name) validate.py 실패: $head"
    }
}

# ------------------------------------------------------------------ docs
# 요건 + 설계. 기존 01-req / 02-design 을 한 게이트로 합쳤다. 최상류라 상류 검사 없음.
if ($Stage -eq 'docs') {
    $dir = Join-Path $root 'docs'
    $prdFiles = Get-WorkFiles $dir 'PRD'
    $srsFiles = Get-WorkFiles $dir 'SRS'
    $sddFiles = Get-WorkFiles $dir 'SDD'

    if ($prdFiles.Count -eq 0) { Fail '실작업 PRD 문서 없음 (*PRD*.md, 대문자만, (template) 제외)' }
    if ($srsFiles.Count -eq 0) { Fail '실작업 SRS 문서 없음 (*SRS*.md, 대문자만, (template) 제외)' }
    if ($sddFiles.Count -eq 0) { Fail '실작업 SDD 문서 없음 (*SDD*.md, 대문자만, (template) 제외)' }
    if ($prdFiles.Count -gt 0) { Note "PRD 대상 $($prdFiles.Count) 건: $(($prdFiles | ForEach-Object Name) -join ', ')" }
    if ($srsFiles.Count -gt 0) { Note "SRS 대상 $($srsFiles.Count) 건: $(($srsFiles | ForEach-Object Name) -join ', ')" }
    if ($sddFiles.Count -gt 0) { Note "SDD 대상 $($sddFiles.Count) 건: $(($sddFiles | ForEach-Object Name) -join ', ')" }

    $skills = Resolve-SkillsDir $root
    $prdVal = Join-Path $skills 'by-prd-writer\scripts\validate.py'
    $srsVal = Join-Path $skills 'by-srs-writer\scripts\validate.py'
    $sddVal = Join-Path $skills 'by-sdd-writer\scripts\validate.py'
    foreach ($f in $prdFiles) { Invoke-Validator $prdVal $f 'PRD' }
    foreach ($f in $srsFiles) { Invoke-Validator $srsVal $f 'SRS' }
    foreach ($f in $sddFiles) { Invoke-Validator $sddVal $f 'SDD' }

    $prd = Read-All $prdFiles
    $srs = Read-All $srsFiles
    $sdd = Read-All $sddFiles

    # --- 요건 (구 01-req) ---
    foreach ($pair in @(@('PRD', $prd), @('SRS', $srs))) {
        if ($pair[1] -and $pair[1] -match '\[확인 필요') {
            $n = ([regex]::Matches($pair[1], '\[확인 필요')).Count
            Fail "$($pair[0]) 에 미해결 [확인 필요] $n 건 남음"
        }
    }

    $prdReq = Get-Ids $prd '\[(PRD-[FN]\d{2,})\]'
    $srsReq = Get-Ids $srs '\[(SRS-[FN]\d{3})\]'
    if ($prd -and $prdReq.Count -eq 0) { Fail 'PRD 에 [PRD-F###]/[PRD-N###] 요구사항 ID 없음' }
    if ($srs -and $srsReq.Count -eq 0) { Fail 'SRS 에 [SRS-F###]/[SRS-N###] 요구사항 ID 없음' }

    # 고아 SRS 요구사항: 상위요건 링크 없음
    $orphan = Find-OrphanDefs $srs '\[(SRS-[FN]\d{3})\]' '상위요건'
    if ($orphan.Count -gt 0) { Fail ("상위요건 링크 없는 SRS 요구사항: " + ($orphan -join ', ')) }

    # 전개 안 된 PRD 요구사항
    if ($prd -and $srs) {
        $linked = @()
        foreach ($m in [regex]::Matches($srs, '상위요건\s*:\s*(.+)')) {
            foreach ($id in [regex]::Matches($m.Groups[1].Value, '<(PRD-[UAFN]\d{2,})>')) {
                $linked += $id.Groups[1].Value
            }
        }
        $missing = @($prdReq | Where-Object { $linked -notcontains $_ })
        if ($missing.Count -gt 0) { Fail ("SRS 로 전개되지 않은 PRD 요구사항: " + ($missing -join ', ')) }
        else { Note "추적: PRD 요구사항 $($prdReq.Count) 건 전부 SRS 전개 확인 (SRS $($srsReq.Count) 건)" }
    }

    # --- 설계 (구 02-design) ---
    if ($sdd -and $sdd -match '\[확인 필요') {
        $n = ([regex]::Matches($sdd, '\[확인 필요')).Count
        Fail "SDD 에 미해결 [확인 필요] $n 건 남음"
    }

    $sddIds = Get-Ids $sdd '\[(SDD-[MIDC]\d{2,})\]'
    if ($sdd -and $sddIds.Count -eq 0) { Fail 'SDD 에 [SDD-M###]/[SDD-I###] 형식 ID 없음' }

    $orphanSdd = Find-OrphanDefs $sdd '\[(SDD-[MIDC]\d{2,})\]' '구현요건'
    if ($orphanSdd.Count -gt 0) { Fail ("구현요건 링크 없는 SDD 항목: " + ($orphanSdd -join ', ')) }

    if ($srs -and $sdd) {
        $covered = @()
        foreach ($m in [regex]::Matches($sdd, '구현요건\s*:\s*(.+)')) {
            foreach ($id in [regex]::Matches($m.Groups[1].Value, '<(SRS-[FN]\d{3})>')) {
                $covered += $id.Groups[1].Value
            }
        }
        $missing = @($srsReq | Where-Object { $covered -notcontains $_ })
        if ($missing.Count -gt 0) { Fail ("SDD 가 커버하지 않은 SRS 요구사항: " + ($missing -join ', ')) }
        else { Note "추적: SRS 요구사항 $($srsReq.Count) 건 전부 SDD 커버 (SDD 항목 $($sddIds.Count) 건)" }
    }

    # SAD 는 선택 문서다. 있으면 검사하고, 없으면 건너뛴다.
    $sadFiles = Get-WorkFiles $dir 'SAD'
    $sad = ''
    if ($sadFiles.Count -eq 0) {
        Note 'SAD 없음 -> 구조 문서 검사 건너뜀 (선택 문서)'
    } else {
        Note "SAD 대상 $($sadFiles.Count) 건: $(($sadFiles | ForEach-Object Name) -join ', ')"
        $sadVal = Join-Path $skills 'by-sad-writer\scripts\validate.py'
        foreach ($f in $sadFiles) { Invoke-Validator $sadVal $f 'SAD' }

        $sad = Read-All $sadFiles
        if ($sad -match '\[확인 필요') {
            $n = ([regex]::Matches($sad, '\[확인 필요')).Count
            Fail "SAD 에 미해결 [확인 필요] $n 건 남음"
        }

        $sadIds = Get-Ids $sad '\[(SAD-[CIQR]\d{2,})\]'
        if ($sadIds.Count -eq 0) { Fail 'SAD 에 [SAD-C###]/[SAD-I###]/[SAD-Q###] 형식 ID 없음' }

        $orphanSad = Find-OrphanDefs $sad '\[(SAD-[CIQR]\d{2,})\]' '구현요건'
        if ($orphanSad.Count -gt 0) { Fail ("구현요건 링크 없는 SAD 항목: " + ($orphanSad -join ', ')) }

        if ($srs) {
            $coveredSad = @()
            foreach ($m in [regex]::Matches($sad, '구현요건\s*:\s*(.+)')) {
                foreach ($id in [regex]::Matches($m.Groups[1].Value, '<(SRS-[FN]\d{3})>')) {
                    $coveredSad += $id.Groups[1].Value
                }
            }
            $missingSad = @($srsReq | Where-Object { $coveredSad -notcontains $_ })
            if ($missingSad.Count -gt 0) { Fail ("SAD 가 커버하지 않은 SRS 요구사항: " + ($missingSad -join ', ')) }
            else { Note "추적: SRS 요구사항 $($srsReq.Count) 건 전부 SAD 커버 (SAD 항목 $($sadIds.Count) 건)" }
        }
    }

    # adr/ 는 docs 하위 어디에든 있을 수 있다(예: docs/3.Design/adr/) - 재귀로 찾는다.
    $adrDirs = @(Get-ChildItem $dir -Filter 'adr' -Directory -Recurse -ErrorAction SilentlyContinue)
    $adrFiles = @()
    if ($adrDirs.Count -gt 0) {
        $adrFiles = @($adrDirs | ForEach-Object {
            Get-ChildItem $_.FullName -Filter '*.md' -File -ErrorAction SilentlyContinue
        } | Where-Object { $_.Name -notmatch '\(template\)' })
    }
    $undecided = @($adrFiles | Where-Object {
        [System.IO.File]::ReadAllText($_.FullName) -match '(TBD|미정|결정 필요)' })
    if ($undecided.Count -gt 0) { Fail ("미결정 ADR: " + (($undecided | ForEach-Object Name) -join ', ')) }
    elseif ($adrFiles.Count -gt 0) { Note "ADR $($adrFiles.Count) 건 전부 결정 완료" }

    # SAD/SDD 가 참조한 ADR 번호가 실제 파일로 존재하는지 (깨진 링크만 차단)
    $refText = @($sdd, $sad) -join "`n"
    $refIds = Get-Ids $refText '\b(ADR-\d{2,})\b'
    if ($refIds.Count -gt 0) {
        $adrNames = @($adrFiles | ForEach-Object { $_.Name })
        $broken = @($refIds | Where-Object { $id = $_; -not ($adrNames | Where-Object { $_ -like "$id*" }) })
        if ($broken.Count -gt 0) { Fail ("참조된 ADR 파일 없음: " + ($broken -join ', ')) }
        else { Note "ADR 참조 $($refIds.Count) 건 전부 파일 존재 확인" }
    }

    Test-ReturnedIssues 'docs'
}

# ------------------------------------------------------------------ impl
# 구현. src/ tests/ 가 저장소 루트에 있다.
if ($Stage -eq 'impl') {
    Test-UpstreamChain @('docs')
    Test-UpstreamDrift

    Push-Location $root
    try {
        $testFiles = @(Get-ChildItem (Join-Path $root 'tests') -Filter 'test_*.py' -Recurse -File -ErrorAction SilentlyContinue |
                       Where-Object { $_.Name -notmatch '\.example\.' })
        if ($testFiles.Count -eq 0) {
            Fail '실작업 테스트 없음 (tests/test_*.py, .example. 제외). TDD 단계에서 테스트 없이 통과시킬 수 없다'
        } else {
            $out = & python -m pytest -q --basetemp=./tests/.pytest-tmp 2>&1 | Out-String
            if ($LASTEXITCODE -eq 0) {
                Note "pytest ($($testFiles.Count) 파일) -> 통과"
            } else {
                $tail = ($out -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 3) -join ' / '
                Fail "pytest 실패: $tail"
            }
        }
        $null = & python -m compileall -q src 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0) { Note 'compileall -> 통과' } else { Fail 'compileall 실패' }
    } finally { Pop-Location }

    # SDD 모듈/인터페이스가 코드에 실제로 나타나는지.
    # 스캔은 src/ tests/ 만 본다 - 루트 전체를 훑으면 docs/3.Design/SDD.md 자기 자신이 매핑
    # 소스로 잡혀 이 검사가 항상 통과해버린다(무의미해진다).
    $sdd = Read-All (Get-WorkFiles $root 'SDD')
    if ($sdd) {
        $ids = Get-Ids $sdd '\[(SDD-[MI]\d{2,})\]'
        $scanDirs = @(@('src', 'tests') | ForEach-Object { Join-Path $root $_ } | Where-Object { Test-Path $_ })
        $files = @()
        if ($scanDirs.Count -gt 0) {
            $files = @(Get-ChildItem $scanDirs -Recurse -File -Include '*.py','*.md','*.ts','*.js' -ErrorAction SilentlyContinue |
                       Where-Object { $_.FullName -notmatch '\\node_modules\\' -and $_.FullName -notmatch '__pycache__' })
        }
        $blob = ($files | ForEach-Object { [System.IO.File]::ReadAllText($_.FullName) }) -join "`n"
        $unmapped = @($ids | Where-Object { $blob -notmatch [regex]::Escape($_) })
        if ($unmapped.Count -gt 0) { Fail ("코드에 매핑되지 않은 SDD 항목: " + ($unmapped -join ', ')) }
        elseif ($ids.Count -gt 0) { Note "추적: SDD 모듈/인터페이스 $($ids.Count) 건 전부 코드 매핑 확인" }
    }

    Test-ReturnedIssues 'impl'
}

# -------------------------------------------------------------------- vv
# 사용자 실테스트 + 이슈 등록/조치. TC 강제는 없다 - 이슈 트래커만 판정한다.
# 0.issue 는 사용자가 막 적어둔 원시 입력 자리라 게이트가 보지 않는다.
# 1.open 으로 승격돼야 판정 대상이 된다.
if ($Stage -eq 'vv') {
    Test-UpstreamChain @('docs', 'impl')
    Test-UpstreamDrift

    $issueRoot = Join-Path $root 'issue'
    $openCount = 0
    foreach ($state in @('1.open', '2.todo', '3.done')) {
        $sdir = Join-Path $issueRoot $state
        $n = @(Get-ChildItem $sdir -Filter 'ISSUE-*.md' -Recurse -File -ErrorAction SilentlyContinue |
               Where-Object { $_.Name -notmatch '\(template\)' }).Count
        if ($n -gt 0) { Fail "미해결 ISSUE: issue/$state 에 $n 건"; $openCount += $n }
    }
    if ($openCount -eq 0) { Note 'issue/1.open, issue/2.todo, issue/3.done 비어 있음' }

    $raw = @(Get-ChildItem (Join-Path $issueRoot '0.issue') -Filter '*.md' -Recurse -File -ErrorAction SilentlyContinue |
             Where-Object { $_.Name -notmatch '\(template\)' }).Count
    if ($raw -gt 0) { Note "참고: issue/0.issue 에 미분류 사용자 기록 $raw 건 (게이트 판정 대상 아님)" }
}

# ----------------------------------------------------------------- 결과
$status = if ($blocking.Count -gt 0) { 'FAIL' } else { 'PASS' }

$lines = @()
$lines += "STATUS: $status"
$lines += "DATE: " + (Get-Date -Format 'yyyy-MM-dd HH:mm')
$lines += "EVIDENCE:"
if ($evidence.Count -eq 0) { $lines += "- 없음" } else { foreach ($e in $evidence) { $lines += "- $e" } }
$lines += "BLOCKING:"
if ($blocking.Count -eq 0) { $lines += "- 없음" } else { foreach ($b in $blocking) { $lines += "- $b" } }
$lines += ""
$lines += "<!-- 이 파일은 tools/gate.ps1 이 다시 쓴다. 손으로 고치지 않는다. -->"

$gatePath = Get-GatePath $Stage
$gateDir = Split-Path $gatePath -Parent
if (-not (Test-Path $gateDir)) { $null = New-Item -ItemType Directory -Path $gateDir -Force }
$lines -join "`n" | Out-File -LiteralPath $gatePath -Encoding utf8

Write-Output "[$Stage] $status"
foreach ($b in $blocking) { Write-Output "  BLOCKING: $b" }
if ($status -eq 'PASS') { exit 0 } else { exit 1 }
