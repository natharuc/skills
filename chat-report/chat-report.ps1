# PowerShell 5.1 and PowerShell 7 entry point.
# Intentionally use $args rather than named PowerShell parameters: all arguments
# belong to the bundled CLI and must arrive there unchanged.
$ForwardArgs = @($args)
$EntryPoint = Join-Path $PSScriptRoot 'scripts/chat_report.py'

if (-not (Test-Path -LiteralPath $EntryPoint -PathType Leaf)) {
    [Console]::Error.WriteLine('chat-report: missing scripts/chat_report.py. Install the complete skill folder.')
    exit 2
}

# Keep native exit codes authoritative, including when the caller enabled the
# PowerShell 7 native-command error preference. These settings are script-local.
$PSNativeCommandUseErrorActionPreference = $false
$ErrorActionPreference = 'Continue'
$RunningOnWindows = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$RuntimeCandidates = @()
if ($RunningOnWindows) {
    $RuntimeCandidates += @{ Name = 'py'; Prefix = @('-3') }
}
$RuntimeCandidates += @{ Name = 'python3'; Prefix = @() }
$RuntimeCandidates += @{ Name = 'python'; Prefix = @() }
$Runtime = $null

foreach ($RuntimeCandidate in $RuntimeCandidates) {
    $ResolvedCommand = Get-Command -Name $RuntimeCandidate.Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $ResolvedCommand) { continue }
    $CandidatePath = $ResolvedCommand.Source
    $CandidatePrefix = @($RuntimeCandidate.Prefix)
    try {
        & $CandidatePath @CandidatePrefix -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) {
            $Runtime = @{ Path = $CandidatePath; Prefix = $CandidatePrefix }
            break
        }
    } catch {
        # A stale executable or unavailable interpreter is not a usable runtime.
        continue
    }
}

if ($null -eq $Runtime) {
    [Console]::Error.WriteLine('chat-report: Python 3.10 or newer is required. Install it separately and make py -3 (Windows), python3, or python available on PATH. No dependencies are downloaded by this launcher.')
    exit 127
}

$RuntimePath = $Runtime.Path
$RuntimePrefix = @($Runtime.Prefix)
try {
    $LASTEXITCODE = $null
    & $RuntimePath @RuntimePrefix $EntryPoint @ForwardArgs
    if ($null -eq $LASTEXITCODE) {
        [Console]::Error.WriteLine('chat-report: unable to start the selected Python interpreter.')
        exit 126
    }
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine('chat-report: unable to start the selected Python interpreter: ' + $_.Exception.Message)
    exit 126
}
