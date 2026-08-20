<#
Purpose: Verifies MongoDB, Ollama, primary llama3.2:3b, and backup qwen2.5:3b
readiness before the AI-only demo is started.
#>
$ErrorActionPreference = 'Stop'

# MongoDB is mandatory because the API persists every submission and assessment there.
try {
    $mongo = Test-NetConnection -ComputerName localhost -Port 27017 -WarningAction SilentlyContinue
    Write-Host "MongoDB (mandatory):" $(if ($mongo.TcpTestSucceeded) { 'READY' } else { 'NOT READY' })
} catch { Write-Host 'MongoDB (mandatory): NOT READY' }

# Ollama needs at least one configured model; Qwen is the automatic backup for Llama.
try {
    $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 5
    $installed = @($tags.models.name) -contains 'llama3.2:3b'
    $backupInstalled = @($tags.models.name) -contains 'qwen2.5:3b'
    Write-Host "Ollama runtime (mandatory): READY"
    Write-Host "llama3.2:3b model (mandatory):" $(if ($installed) { 'READY' } else { 'NOT INSTALLED' })
    Write-Host "qwen2.5:3b backup model (mandatory):" $(if ($backupInstalled) { 'READY' } else { 'NOT INSTALLED' })
} catch {
    Write-Host 'Ollama runtime (mandatory): NOT READY'
    Write-Host 'llama3.2:3b model (mandatory): NOT VERIFIED'
    Write-Host 'qwen2.5:3b backup model (mandatory): NOT VERIFIED'
}
