[CmdletBinding()]
param(
  [Parameter(Mandatory=$false)]
  [string]$ProjectRoot = (Get-Location).Path,
  [long]$MaxIncludedFileBytes = 10MB
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd('\')
Set-Location -LiteralPath $root
$output = Join-Path $root 'amba_gov_complete_project_audit.txt'
$outputName = [IO.Path]::GetFileName($output)

$includedExtensions = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@(
  '.py','.pyi','.json','.jsonl','.yaml','.yml','.md','.rst','.toml','.ini','.cfg','.conf',
  '.sql','.ps1','.cmd','.bat','.sh','.js','.mjs','.cjs','.ts','.tsx','.jsx','.html','.htm',
  '.css','.qss','.scss','.xml','.xsd','.csv','.tsv','.properties','.lock','.graphql','.proto',
  '.dockerfile'
) | ForEach-Object { [void]$includedExtensions.Add($_) }

$includedNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@('Dockerfile','Makefile','Procfile','LICENSE','NOTICE','README','pytest.ini','tox.ini') |
  ForEach-Object { [void]$includedNames.Add($_) }

$allowedTxtNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@('requirements_lock.txt','requirements-lock.txt','reqirment_lock.txt') |
  ForEach-Object { [void]$allowedTxtNames.Add($_) }

$prunedDirectories = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@(
  '.git','.venv','venv','env','.env','.idea','.vscode','__pycache__','node_modules',
  'agent_input','migration_backups','dist','build','coverage','htmlcov','site-packages',
  'egg-info','.pytest_cache','.mypy_cache','.ruff_cache','bin','obj','target',
  '.amba_gov_backups'
) | ForEach-Object { [void]$prunedDirectories.Add($_) }

$excludedExtensions = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@(
  '.pyc','.pyo','.pyd','.so','.dll','.exe','.obj','.o','.class','.jar','.war','.whl',
  '.zip','.7z','.rar','.tar','.gz','.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx',
  '.png','.jpg','.jpeg','.gif','.webp','.ico','.db','.sqlite','.sqlite3','.bin','.pickle',
  '.pkl','.npy','.npz','.onnx','.pt','.pth','.pem','.key','.pfx','.p12','.cer','.crt'
) | ForEach-Object { [void]$excludedExtensions.Add($_) }

$sensitivePatterns = @(
  '*.env','*.env.*','*secret*','*credential*','*password*','*token*',
  'id_rsa*','id_ed25519*','*.private','*.secrets'
)

function Get-RelativePath([string]$FullPath) {
  $full = [IO.Path]::GetFullPath($FullPath)
  if ($full -eq $root) { return '.' }
  if (-not $full.StartsWith($root + '\',[StringComparison]::OrdinalIgnoreCase)) {
    throw "Path escapes project root: $full"
  }
  return $full.Substring($root.Length + 1).Replace('\','/')
}

function Test-ReparsePoint([IO.FileSystemInfo]$Item) {
  return (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Test-ExcludedFileName([string]$Name,[string]$Extension) {
  if ($Name -ieq $outputName) { return $true }
  if ($Name -like 'amba_gov_*_audit*.txt') { return $true }
  if ($excludedExtensions.Contains($Extension)) { return $true }
  foreach ($pattern in $sensitivePatterns) {
    if ($Name -like $pattern) { return $true }
  }
  return $false
}

function Test-IncludedFile([IO.FileInfo]$File) {
  if ($File.Name.StartsWith('.')) { return $false }
  if (Test-ExcludedFileName $File.Name $File.Extension) { return $false }
  if ($File.Extension -ieq '.txt') { return $allowedTxtNames.Contains($File.Name) }
  if ($includedExtensions.Contains($File.Extension)) { return $true }
  return $includedNames.Contains($File.Name)
}

function Invoke-Git([string[]]$Arguments,[switch]$AllowFailure) {
  $outputLines = @(& git.exe -C $root @Arguments 2>&1)
  $exit = $LASTEXITCODE
  if ($exit -ne 0 -and -not $AllowFailure) {
    throw "git $($Arguments -join ' ') failed with exit code ${exit}: $($outputLines -join ' ')"
  }
  return [pscustomobject]@{ ExitCode=$exit; Lines=$outputLines; Text=($outputLines -join "`n") }
}

$gitAvailable = $null -ne (Get-Command git.exe -ErrorAction SilentlyContinue)
$insideGit = $false
$branch = 'unavailable'
$head = 'unavailable'
$statusLines = @()
$gitStateByPath = @{}
$trackedPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

if ($gitAvailable) {
  $probe = Invoke-Git -Arguments @('rev-parse','--is-inside-work-tree') -AllowFailure
  $insideGit = $probe.ExitCode -eq 0 -and $probe.Text.Trim() -eq 'true'
}

if ($insideGit) {
  $branchResult = Invoke-Git -Arguments @('branch','--show-current')
  $headResult = Invoke-Git -Arguments @('rev-parse','HEAD')
  $statusResult = Invoke-Git -Arguments @('status','--porcelain=v1','--untracked-files=all')
  $branch = $branchResult.Text.Trim()
  $head = $headResult.Text.Trim()
  $statusLines = @($statusResult.Lines | Where-Object { $_ -ne '' })

  $trackedResult = Invoke-Git -Arguments @('ls-files','-z')
  foreach ($path in (($trackedResult.Text -split "`0") | Where-Object { $_ })) {
    [void]$trackedPaths.Add($path.Replace('\','/'))
  }

  foreach ($line in $statusLines) {
    if ($line.Length -lt 4) { continue }
    $xy = $line.Substring(0,2)
    $pathPart = $line.Substring(3)
    if ($pathPart -match ' -> ') { $pathPart = ($pathPart -split ' -> ')[-1] }
    $pathPart = $pathPart.Trim('"').Replace('\','/')
    $gitStateByPath[$pathPart] = $xy
  }
}

Write-Host "Scanning current filesystem state, including tracked, staged, unstaged, and untracked eligible files..." -ForegroundColor Cyan
$files = [Collections.Generic.List[IO.FileInfo]]::new()
$queue = [Collections.Generic.Queue[IO.DirectoryInfo]]::new()
$queue.Enqueue([IO.DirectoryInfo]::new($root))
$skippedDirectories = [Collections.Generic.List[string]]::new()
$readErrors = [Collections.Generic.List[string]]::new()

while ($queue.Count -gt 0) {
  $directory = $queue.Dequeue()
  try {
    foreach ($sub in $directory.GetDirectories()) {
      if ($sub.Name.StartsWith('.') -or $prunedDirectories.Contains($sub.Name) -or (Test-ReparsePoint $sub)) {
        $skippedDirectories.Add((Get-RelativePath $sub.FullName))
        continue
      }
      $queue.Enqueue($sub)
    }
  } catch { $readErrors.Add("DIR: $(Get-RelativePath $directory.FullName): $($_.Exception.Message)") }

  try {
    foreach ($file in $directory.GetFiles()) {
      if ((Test-ReparsePoint $file) -or -not (Test-IncludedFile $file)) { continue }
      $files.Add($file)
    }
  } catch { $readErrors.Add("FILES: $(Get-RelativePath $directory.FullName): $($_.Exception.Message)") }
}

$sortedFiles = @($files | Sort-Object { Get-RelativePath $_.FullName })

function Read-FileSafely([string]$FilePath) {
  $stream = $null
  $reader = $null
  try {
    $stream = [IO.FileStream]::new($FilePath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
    $reader = [IO.StreamReader]::new($stream,[Text.Encoding]::UTF8,$true)
    return $reader.ReadToEnd()
  } finally {
    if ($reader) { $reader.Dispose() }
    elseif ($stream) { $stream.Dispose() }
  }
}

function Get-FileHashShared([string]$FilePath) {
  $stream = $null
  $sha = $null
  try {
    $stream = [IO.FileStream]::new($FilePath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
    $sha = [Security.Cryptography.SHA256]::Create()
    return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant()
  } finally {
    if ($sha) { $sha.Dispose() }
    if ($stream) { $stream.Dispose() }
  }
}

$trackedCount=0; $untrackedCount=0; $stagedCount=0; $unstagedCount=0; $cleanTrackedCount=0
$fileRecords = foreach ($file in $sortedFiles) {
  $relative = Get-RelativePath $file.FullName
  $tracked = $trackedPaths.Contains($relative)
  $xy = if ($gitStateByPath.ContainsKey($relative)) { [string]$gitStateByPath[$relative] } elseif ($tracked) { '  ' } else { '??' }
  $indexState = $xy.Substring(0,1)
  $worktreeState = $xy.Substring(1,1)
  if ($tracked) { $trackedCount++ } else { $untrackedCount++ }
  if ($indexState -notin @(' ','?')) { $stagedCount++ }
  if ($worktreeState -notin @(' ','?')) { $unstagedCount++ }
  if ($tracked -and $xy -eq '  ') { $cleanTrackedCount++ }
  [pscustomobject]@{ File=$file; Path=$relative; Tracked=$tracked; XY=$xy; Index=$indexState; Worktree=$worktreeState }
}

$utf8NoBom = [Text.UTF8Encoding]::new($false)
$writer = [IO.StreamWriter]::new($output,$false,$utf8NoBom)
try {
  $writer.WriteLine('AMBA-GOV COMPLETE CURRENT FILESYSTEM TEXT-SOURCE AUDIT')
  $writer.WriteLine('FORMAT_VERSION: 2.0')
  $writer.WriteLine('CAPTURE_SCOPE: eligible files currently present on disk, regardless of Git tracked/staged/unstaged/untracked state')
  $writer.WriteLine('ROOT_NAME: ' + (Split-Path $root -Leaf))
  $writer.WriteLine('GENERATED_LOCAL: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'))
  $writer.WriteLine('INCLUDED_FILE_COUNT: ' + $fileRecords.Count)
  $writer.WriteLine('TRACKED_INCLUDED_COUNT: ' + $trackedCount)
  $writer.WriteLine('UNTRACKED_INCLUDED_COUNT: ' + $untrackedCount)
  $writer.WriteLine('STAGED_INCLUDED_COUNT: ' + $stagedCount)
  $writer.WriteLine('UNSTAGED_INCLUDED_COUNT: ' + $unstagedCount)
  $writer.WriteLine('CLEAN_TRACKED_INCLUDED_COUNT: ' + $cleanTrackedCount)
  $writer.WriteLine('')
  $writer.WriteLine('================ REPOSITORY STATE ================')
  $writer.WriteLine('GIT_AVAILABLE: ' + $gitAvailable)
  $writer.WriteLine('GIT_WORKTREE: ' + $insideGit)
  $writer.WriteLine('GIT_BRANCH: ' + $branch)
  $writer.WriteLine('GIT_HEAD: ' + $head)
  if (-not $insideGit) { $writer.WriteLine('GIT_STATUS: unavailable') }
  elseif ($statusLines.Count -eq 0) { $writer.WriteLine('GIT_STATUS: clean') }
  else { $writer.WriteLine('GIT_STATUS:'); foreach ($line in $statusLines) { $writer.WriteLine($line) } }
  $writer.WriteLine('')
  $writer.WriteLine('GIT_XY_LEGEND: first column=index/staged; second column=worktree/unstaged; ??=untracked; blank=clean tracked')
  $writer.WriteLine('')
  $writer.WriteLine('================ EXCLUSION RULES ================')
  $writer.WriteLine('Pruned directories: ' + ($prunedDirectories -join ', '))
  $writer.WriteLine('Reparse-point directories/files: excluded')
  $writer.WriteLine('TXT inclusion: only ' + ($allowedTxtNames -join ', '))
  $writer.WriteLine('Excluded binary/unsafe extensions: ' + ($excludedExtensions -join ', '))
  $writer.WriteLine('Excluded sensitive-name patterns: ' + ($sensitivePatterns -join ', '))
  $writer.WriteLine('Maximum full-content size per file: ' + $MaxIncludedFileBytes + ' bytes')
  $writer.WriteLine('')
  $writer.WriteLine('================ INCLUDED FILE INVENTORY ================')
  foreach ($record in $fileRecords) {
    $writer.WriteLine(('{0} | TRACKED={1} | GIT_XY=[{2}] | SIZE={3}' -f $record.Path,$record.Tracked,$record.XY,$record.File.Length))
  }
  $writer.WriteLine('')
  $writer.WriteLine('================ SKIPPED DIRECTORIES ================')
  foreach ($path in ($skippedDirectories | Sort-Object -Unique)) { $writer.WriteLine($path) }
  $writer.WriteLine('')
  $writer.WriteLine('================ SCAN ERRORS ================')
  if ($readErrors.Count -eq 0) { $writer.WriteLine('none') } else { foreach ($errorLine in $readErrors) { $writer.WriteLine($errorLine) } }
  $writer.WriteLine('')
  $writer.WriteLine('================ COMPLETE FILE CONTENTS ================')

  foreach ($record in $fileRecords) {
    $file=$record.File; $path=$record.Path
    $hash = try { Get-FileHashShared $file.FullName } catch { 'ERROR_CALCULATING_HASH: ' + $_.Exception.Message }
    $writer.WriteLine('')
    $writer.WriteLine('>>>>>>>>>>>>>>>> BEGIN FILE: ' + $path + ' <<<<<<<<<<<<<<<<')
    $writer.WriteLine('RELATIVE_PATH: ' + $path)
    $writer.WriteLine('TRACKED_BY_GIT: ' + $record.Tracked)
    $writer.WriteLine('GIT_XY_STATUS: [' + $record.XY + ']')
    $writer.WriteLine('SIZE_BYTES: ' + $file.Length)
    $writer.WriteLine('SHA256: ' + $hash)
    $writer.WriteLine('---------------- FILE CONTENT START ----------------')
    if ($file.Length -gt $MaxIncludedFileBytes) {
      $writer.WriteLine('[CONTENT OMITTED: file exceeds configured per-file limit]')
    } else {
      try {
        $content = Read-FileSafely $file.FullName
        if ($content.Length -gt 0) { $writer.Write($content) }
        if ($content.Length -gt 0 -and -not $content.EndsWith("`n")) { $writer.WriteLine() }
      } catch {
        $writer.WriteLine('[UNABLE TO READ FILE: ' + $_.Exception.Message + ']')
      }
    }
    $writer.WriteLine('----------------- FILE CONTENT END -----------------')
    $writer.WriteLine('>>>>>>>>>>>>>>>> END FILE: ' + $path + ' <<<<<<<<<<<<<<<<<<')
  }
  $writer.WriteLine('')
  $writer.WriteLine('================ AUDIT END ================')
} finally { $writer.Dispose() }

$outputHash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
$outputItem = Get-Item -LiteralPath $output
Write-Host ''
Write-Host "Created: $output" -ForegroundColor Green
Write-Host "Included files: $($fileRecords.Count)" -ForegroundColor Green
Write-Host "Tracked: $trackedCount; untracked: $untrackedCount; staged: $stagedCount; unstaged: $unstagedCount" -ForegroundColor Green
Write-Host "Output size: $($outputItem.Length) bytes" -ForegroundColor Green
Write-Host "Output SHA256: $outputHash" -ForegroundColor Green
