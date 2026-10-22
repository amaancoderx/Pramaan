# Push the backend to a Hugging Face Docker Space.
# Usage: .\deploy\push-backend-to-hf.ps1 -User <hf-username> -Token <hf-write-token> [-Space pramaan-api]
param(
    [Parameter(Mandatory = $true)][string]$User,
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Space = "pramaan-api"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Tmp = Join-Path $env:TEMP "pramaan-hf-space"
if (Test-Path $Tmp) { Remove-Item -Recurse -Force $Tmp }
New-Item -ItemType Directory $Tmp | Out-Null

foreach ($item in "app", "tests", "Dockerfile", "requirements.txt", "pytest.ini", ".dockerignore") {
    Copy-Item -Recurse (Join-Path "$Root\backend" $item) $Tmp
}
Get-ChildItem -Recurse -Directory -Filter "__pycache__" $Tmp | Remove-Item -Recurse -Force
@"
---
title: Pramaan API
sdk: docker
app_port: 8000
pinned: false
---

Backend for Pramaan (UPI payment screenshot verification). Docs at /docs.
"@ | Set-Content -Encoding utf8 (Join-Path $Tmp "README.md")
"*.ttf filter=lfs diff=lfs merge=lfs -text" | Set-Content -Encoding utf8 (Join-Path $Tmp ".gitattributes")

Set-Location $Tmp
git init -q -b main
git config user.name "amaancoderx"
git config user.email "amaan.coderx@gmail.com"
git lfs install --local | Out-Null
git add -A
git commit -q -m "Deploy Pramaan API"
git push --force "https://${User}:${Token}@huggingface.co/spaces/${User}/${Space}" main
Write-Host ""
Write-Host "Pushed. Build logs: https://huggingface.co/spaces/$User/$Space"
Write-Host "API URL:          https://$User-$Space.hf.space"
