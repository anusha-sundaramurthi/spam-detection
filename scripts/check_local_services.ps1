<#
Purpose: Verifies MongoDB, Ollama, both text models, and the separate vision
model used whenever a vendor supplies service images.
#>
$ErrorActionPreference = 'Stop'

# MongoDB is mandatory because the API persists every submission and assessment there.
try {
    $mongo = Test-NetConnection -ComputerName localhost -Port 27017 -WarningAction SilentlyContinue
    Write-Host "MongoDB (mandatory):" $(if ($mongo.TcpTestSucceeded) { 'READY' } else { 'NOT READY' })
} catch { Write-Host 'MongoDB (mandatory): NOT READY' }

# Ollama uses lightweight Qwen for primary text scoring and Gemma as fallback.
try {
    $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 5
    $installed = @($tags.models.name) -contains 'qwen3:1.7b'
    $backupInstalled = @($tags.models.name) -contains 'gemma3:1b'
    $visionInstalled = @($tags.models.name) -contains 'moondream:1.8b'
    Write-Host "Ollama runtime (mandatory): READY"
    Write-Host "qwen3:1.7b model (mandatory):" $(if ($installed) { 'READY' } else { 'NOT INSTALLED' })
    Write-Host "gemma3:1b backup model (mandatory):" $(if ($backupInstalled) { 'READY' } else { 'NOT INSTALLED' })
    Write-Host "moondream:1.8b image model (mandatory with images):" $(if ($visionInstalled) { 'READY' } else { 'NOT INSTALLED' })
} catch {
    Write-Host 'Ollama runtime (mandatory): NOT READY'
    Write-Host 'qwen3:1.7b model (mandatory): NOT VERIFIED'
    Write-Host 'gemma3:1b backup model (mandatory): NOT VERIFIED'
    Write-Host 'moondream:1.8b image model (mandatory with images): NOT VERIFIED'
}
