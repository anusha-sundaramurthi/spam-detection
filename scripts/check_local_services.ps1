<#
Purpose: Verifies mandatory local MongoDB, Ollama runtime, and llama3.2:3b
model readiness before the demo is started.
#>
$ErrorActionPreference = 'Stop'

# MongoDB is mandatory because the API persists every submission and assessment there.
try {
    $mongo = Test-NetConnection -ComputerName localhost -Port 27017 -WarningAction SilentlyContinue
    Write-Host "MongoDB (mandatory):" $(if ($mongo.TcpTestSucceeded) { 'READY' } else { 'NOT READY' })
} catch { Write-Host 'MongoDB (mandatory): NOT READY' }

# Ollama and the configured model are mandatory for full AI scoring; rules remain a safety fallback.
try {
    $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 5
    $installed = @($tags.models.name) -contains 'llama3.2:3b'
    Write-Host "Ollama runtime (mandatory): READY"
    Write-Host "llama3.2:3b model (mandatory):" $(if ($installed) { 'READY' } else { 'NOT INSTALLED' })
} catch {
    Write-Host 'Ollama runtime (mandatory): NOT READY'
    Write-Host 'llama3.2:3b model (mandatory): NOT VERIFIED'
}
