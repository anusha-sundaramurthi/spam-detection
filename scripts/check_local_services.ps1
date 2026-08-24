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

# Ollama needs at least one configured model; Qwen is the automatic backup for Llama.
try {
    $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 5
    $installed = @($tags.models.name) -contains 'llama3.2:3b'
    $backupInstalled = @($tags.models.name) -contains 'qwen2.5:3b'
    $visionInstalled = @($tags.models.name) -contains 'llama3.2-vision:11b'
    Write-Host "Ollama runtime (mandatory): READY"
    Write-Host "llama3.2:3b model (mandatory):" $(if ($installed) { 'READY' } else { 'NOT INSTALLED' })
    Write-Host "qwen2.5:3b backup model (mandatory):" $(if ($backupInstalled) { 'READY' } else { 'NOT INSTALLED' })
    Write-Host "llama3.2-vision:11b image model (mandatory with images):" $(if ($visionInstalled) { 'READY' } else { 'NOT INSTALLED' })
} catch {
    Write-Host 'Ollama runtime (mandatory): NOT READY'
    Write-Host 'llama3.2:3b model (mandatory): NOT VERIFIED'
    Write-Host 'qwen2.5:3b backup model (mandatory): NOT VERIFIED'
    Write-Host 'llama3.2-vision:11b image model (mandatory with images): NOT VERIFIED'
}
