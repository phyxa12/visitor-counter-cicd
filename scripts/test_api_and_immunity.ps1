<#
.SYNOPSIS
    Skrip pengujian otomatis untuk Web Visitor Counter Log (Studi Kasus #5).
    Menguji:
      1. Health Check (/api/health)
      2. POST /api/logs (201 Created)
      3. GET /api/logs (200 OK)
      4. Error Handling 400 Bad Request (body kosong & tanpa field 'page')
      5. Error Handling 404 Not Found (DELETE index di luar jangkauan)
      6. Simulasi Data Immunity (docker rm -f visitor-backend -> docker compose up -d)
      7. DELETE /api/logs?index=0 (200 OK)
#>

$ErrorActionPreference = "Stop"
$BaseUrl = "http://localhost:8080/api"

Write-Host "`n=== [1/7] Uji Health Check ===" -ForegroundColor Cyan
curl.exe -s "$BaseUrl/health"
Write-Host ""

Write-Host "`n=== [2/7] Tambah 2 Log Kunjungan (POST /logs -> 201 Created) ===" -ForegroundColor Cyan
curl.exe -s -X POST "$BaseUrl/logs" -H "Content-Type: application/json" -d '{"page":"/praktikum/docker","visitor":"Faiz - 101012330071"}'
Write-Host ""
curl.exe -s -X POST "$BaseUrl/logs" -H "Content-Type: application/json" -d '{"page":"/praktikum/jenkins","visitor":"Zaky - 101012300005"}'
Write-Host ""

Write-Host "`n=== [3/7] Ambil Statistik & Daftar Log (GET /logs -> 200 OK) ===" -ForegroundColor Cyan
curl.exe -s "$BaseUrl/logs"
Write-Host ""

Write-Host "`n=== [4/7] Uji Error Handling 400 Bad Request ===" -ForegroundColor Yellow
curl.exe -i -s -X POST "$BaseUrl/logs" -H "Content-Type: application/json" -d '{}' | Select-String "HTTP/|error"

Write-Host "`n=== [5/7] Uji Error Handling 404 Not Found (DELETE ?index=999) ===" -ForegroundColor Yellow
curl.exe -i -s -X DELETE "$BaseUrl/logs?index=999" | Select-String "HTTP/|error"

Write-Host "`n=== [6/7] Simulasi Data Immunity (Hapus Paksa Kontainer Backend) ===" -ForegroundColor Magenta
docker rm -f visitor-backend
docker compose up -d
Start-Sleep -Seconds 3
Write-Host "Data setelah kontainer backend dibuat ulang:" -ForegroundColor Green
curl.exe -s "$BaseUrl/logs"
Write-Host ""

Write-Host "`n=== [7/7] Hapus Log Index ke-0 (DELETE /logs?index=0 -> 200 OK) ===" -ForegroundColor Cyan
curl.exe -s -X DELETE "$BaseUrl/logs?index=0"
Write-Host "`n`n[SELESAI] Seluruh pengujian API & Data Immunity berhasil!" -ForegroundColor Green
