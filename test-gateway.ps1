# Test script for GameGateway API
$boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
$testData = Get-Content "test-data.json" -Raw

# Create multipart body
$bodyLines = @(
    "--$boundary",
    'Content-Disposition: form-data; name="mx.dat"; filename="mx.dat"',
    'Content-Type: application/octet-stream',
    '',
    $testData,
    "--$boundary--"
)

$body = $bodyLines -join "`r`n"
$headers = @{
    'Content-Type' = "multipart/form-data; boundary=$boundary"
}

Write-Host "Testing GameGateway /api/gateway endpoint..." -ForegroundColor Green
Write-Host "Request data: $testData" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "http://localhost:7000/api/gateway" -Method POST -Body $body -Headers $headers
    Write-Host "Status Code: $($response.StatusCode)" -ForegroundColor Green
    Write-Host "Response Headers:" -ForegroundColor Cyan
    $response.Headers | Format-Table
    Write-Host "Response Body:" -ForegroundColor Cyan
    $response.Content | ConvertFrom-Json | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "Status Code: $($_.Exception.Response.StatusCode)" -ForegroundColor Red
        Write-Host "Response: $($_.Exception.Response)" -ForegroundColor Red
    }
}