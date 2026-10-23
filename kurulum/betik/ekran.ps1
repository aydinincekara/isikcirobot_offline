# Kurulum sihirbazının ekran görüntülerini alır (GitHub Actions'ta). Görüntüler 'ekranlar' klasörüne yazılır.
Add-Type -AssemblyName System.Windows.Forms, System.Drawing, Microsoft.VisualBasic
$kur = (Resolve-Path "dist\afi-sinif-kurulum.exe").Path
$out = Join-Path (Get-Location) "ekranlar"
New-Item -ItemType Directory -Force $out | Out-Null

function Cek($ad) {
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
  $bmp.Save((Join-Path $out "$ad.png"), [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Write-Host "ekran: $ad"
}
function Odak {
  $p = Get-Process | Where-Object { $_.MainWindowTitle -like "*afi*" } | Select-Object -First 1
  if ($p) { try { [Microsoft.VisualBasic.Interaction]::AppActivate($p.Id) } catch {} }
}
function Tus($k, $bekle = 1500) { Odak; Start-Sleep -Milliseconds 300; [System.Windows.Forms.SendKeys]::SendWait($k); Start-Sleep -Milliseconds $bekle }
function Kapat { Get-Process | Where-Object { $_.Path -like "*afi-sinif-kurulum*" -or $_.MainWindowTitle -like "*afi*" } | Stop-Process -Force -ErrorAction SilentlyContinue }

# 1) ilk kurulum: öğretmen bilgisayarı
Start-Process -FilePath $kur -ArgumentList @("/ALLUSERS", "/ROL=sunucu", "/ONIZLEME=1", "/DIR=C:\afi-ekran")
Start-Sleep -Seconds 6; Odak; Start-Sleep -Milliseconds 800
Cek "01-hosgeldiniz"; Tus "{ENTER}"
Cek "02-lisans"; Tus "{ENTER}"
Cek "03-kurulum-turu"; Tus "{ENTER}"
Cek "04-ogretmen-ayarlari"; Tus "{ENTER}"
Cek "05-klasor"; Tus "{ENTER}"
Cek "06-hazir"; Tus "{ENTER}" 1800
Cek "07-kuruluyor"; Start-Sleep -Milliseconds 1700
Cek "07b-kuruluyor"; Start-Sleep -Seconds 5
Cek "08-bitti"; Tus "{ENTER}" 2000
Kapat

# 2) ikinci kez açılınca: bakım sayfası, öğrenci türü
Start-Process -FilePath $kur -ArgumentList @("/ALLUSERS", "/ROL=istemci", "/ONIZLEME=1")
Start-Sleep -Seconds 6; Odak; Start-Sleep -Milliseconds 800
Cek "09-yeniden-hosgeldiniz"; Tus "{ENTER}"
Cek "10-bakim"; Tus "{ENTER}"
Cek "11-kurulum-turu-ogrenci"; Tus "{ENTER}"
Cek "12-ogrenci-ayarlari"; Tus "{ENTER}"
Cek "13-klasor"; Tus "{ENTER}"
Cek "14-hazir-ogrenci"
Kapat
Start-Sleep -Seconds 2
if (Test-Path "C:\afi-ekran\unins000.exe") { Start-Process "C:\afi-ekran\unins000.exe" -ArgumentList "/VERYSILENT" -Wait }
Get-ChildItem $out
