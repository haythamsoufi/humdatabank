# PowerShell script to update email configuration
Write-Host "🔧 Updating Email Configuration" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""

# Read current .env file
$envContent = Get-Content .env -Raw

Write-Host "Current .env file content:" -ForegroundColor Yellow
Write-Host $envContent
Write-Host ""

Write-Host "Please provide your Gmail credentials:" -ForegroundColor Cyan

# Get Gmail address
do {
    $gmail = Read-Host "Enter your Gmail address"
    if ($gmail -notlike "*@gmail.com") {
        Write-Host "❌ Please enter a valid Gmail address (must contain @gmail.com)" -ForegroundColor Red
    }
} while ($gmail -notlike "*@gmail.com")

# Get App Password
Write-Host ""
Write-Host "🔐 App Password Setup:" -ForegroundColor Yellow
Write-Host "You need to generate an App Password from Google:"
Write-Host "1. Go to https://myaccount.google.com/security"
Write-Host "2. Enable 2-Step Verification if not already enabled"
Write-Host "3. Go to 'App passwords' under 2-Step Verification"
Write-Host "4. Select 'Mail' as app and 'Other' as device"
Write-Host "5. Click 'Generate'"
Write-Host "6. Copy the 16-character password (remove spaces)"
Write-Host ""

do {
    $appPassword = Read-Host "Enter your Gmail App Password" -AsSecureString
    $appPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($appPassword))
    if ($appPasswordPlain.Length -lt 16) {
        Write-Host "❌ App Password should be 16 characters long" -ForegroundColor Red
    }
} while ($appPasswordPlain.Length -lt 16)

# Update the .env content
$envContent = $envContent -replace "MAIL_USERNAME=your\.email@gmail\.com", "MAIL_USERNAME=$gmail"
$envContent = $envContent -replace "MAIL_PASSWORD=your-app-password-here", "MAIL_PASSWORD=$appPasswordPlain"
$envContent = $envContent -replace "MAIL_DEFAULT_SENDER=your\.email@gmail\.com", "MAIL_DEFAULT_SENDER=$gmail"
$envContent = $envContent -replace "ADMIN_EMAILS=your\.email@gmail\.com", "ADMIN_EMAILS=$gmail"

# Write updated content back to .env file
$envContent | Set-Content .env

Write-Host ""
Write-Host "✅ Email configuration updated successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Updated Configuration:" -ForegroundColor Yellow
Write-Host "   Gmail: $gmail"
Write-Host "   Admin emails: $gmail"
Write-Host ""
Write-Host "🚀 You can now test the email functionality with:" -ForegroundColor Cyan
Write-Host "   python test_email.py"
Write-Host ""
Write-Host "⚠️  Important:" -ForegroundColor Red
Write-Host "   - Keep your .env file secure and don't commit it to version control"
Write-Host "   - The App Password is sensitive - don't share it"
