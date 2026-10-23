# Kurulum dosyasını sessiz kurulumla dener (GitHub Actions'ta, yönetici olarak çalışır).
$kur = (Resolve-Path "dist\afi-sinif-kurulum.exe").Path
$hedef = "C:\afi-test"
$veri = "C:\afi-test-veri"
$script:hata = $false
function Not($m) { Write-Host "::notice::$m" }
function Hata($m) { Write-Host "::error::$m"; $script:hata = $true }
function Kontrol($kosul, $m) { if ($kosul) { Write-Host "TAMAM: $m" } else { Hata "BAŞARISIZ: $m" } }

function Kur([string[]]$argv) {
  $log = Join-Path $env:RUNNER_TEMP ("kurulum-" + [guid]::NewGuid().ToString("N").Substring(0, 6) + ".log")
  $p = Start-Process -FilePath $kur -ArgumentList ($argv + @("/LOG=$log")) -PassThru
  $null = $p.Handle
  if (-not $p.WaitForExit(180000)) { $p.Kill(); Hata "Kurulum 3 dakikada bitmedi: $argv"; return }
  $son = (Get-Content $log -Tail 12 -ErrorAction SilentlyContinue) -join " / "
  if ($p.ExitCode -ne 0) { Hata "Kurulum çıkış kodu $($p.ExitCode): $argv / $son" } else { Write-Host "Kurulum tamam: $argv" }
}

function Json($yol) { Get-Content $yol -Raw -Encoding UTF8 | ConvertFrom-Json }
function Kural { & netsh advfirewall firewall show rule name="afi sinif sunucusu" | Out-Null; return ($LASTEXITCODE -eq 0) }
function Istek($url) { try { return Invoke-RestMethod -Uri $url -TimeoutSec 3 } catch { return $null } }

# ---------------------------------------------------------------- 1) öğretmen bilgisayarı
Kur @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/ALLUSERS", "/DIR=$hedef", "/ROL=sunucu", "/PORT=8125", "/AD=Deneme-Sınıfı", "/VERI=$veri", "/ORTAK=0")
Kontrol (Test-Path "$hedef\afi-sunucu.exe") "sunucu programı kuruldu"
Kontrol (-not (Test-Path "$hedef\afi-istemci.exe")) "istemci programı yok"
$k = Json "$hedef\kurulum.json"
Kontrol ($k.rol -eq "sunucu" -and $k.port -eq 8125 -and $k.veri -eq $veri) "kurulum.json: $($k | ConvertTo-Json -Compress)"
Kontrol (Kural) "güvenlik duvarı kuralı eklendi"
Kontrol (Test-Path "$env:PUBLIC\Desktop\afi sınıf sunucusu.lnk") "masaüstü kısayolu"
Kontrol (Test-Path "$veri") "veri klasörü oluştu"
$p = Start-Process -FilePath "$hedef\afi-sunucu.exe" -ArgumentList @("--tarayici-acma") -PassThru -WindowStyle Hidden
$b = $null
for ($i = 0; $i -lt 20 -and -not $b; $i++) { Start-Sleep -Milliseconds 500; $b = Istek "http://127.0.0.1:8125/api/v1/bilgi" }
Kontrol ($b -and $b.rol -eq "sunucu") "kurulu sunucu kurulumdaki portta (8125) çalıştı"
Kontrol ($b -and $b.ad -eq "Deneme-Sınıfı") "sunucu adı kurulumdan geldi: $($b.ad)"
Kontrol (Test-Path "$veri\afi-sinif.db") "veritabanı seçilen klasörde"
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Get-Process afi-sunucu -ErrorAction SilentlyContinue | Stop-Process -Force

# ---------------------------------------------------------------- 2) aynı bilgisayarı öğrenciye çevir (rol değiştirme)
Kur @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/ALLUSERS", "/DIR=$hedef", "/ROL=istemci", "/SUNUCU=127.0.0.1:8125", "/BASLANGIC=1")
Kontrol (Test-Path "$hedef\afi-istemci.exe") "istemci programı kuruldu"
Kontrol (-not (Test-Path "$hedef\afi-sunucu.exe")) "sunucu programı kaldırıldı"
Kontrol (-not (Kural)) "güvenlik duvarı kuralı kaldırıldı"
Kontrol (Test-Path "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\afi istemci.lnk") "Windows açılış kısayolu"
Kontrol (Test-Path "$env:PUBLIC\Desktop\AFİ KOD.lnk") "AFİ KOD masaüstü kısayolu"
Kontrol (-not (Test-Path "$env:PUBLIC\Desktop\afi sınıf sunucusu.lnk")) "sunucu kısayolu kaldırıldı"
$b = $null
for ($i = 0; $i -lt 30 -and -not $b; $i++) { Start-Sleep -Milliseconds 500; $b = Istek "http://127.0.0.1:8100/api/v1/durum" }
Kontrol ($b -and $b.rol -eq "istemci") "istemci kurulumdan sonra arka planda başladı"
Kontrol ($b -and $b.ayar.sunucu -eq "http://127.0.0.1:8125") "istemcinin sunucu adresi kurulumdan geldi: $($b.ayar.sunucu)"
$sayfa = $null; try { $sayfa = (Invoke-WebRequest -Uri "http://127.0.0.1:8100/afi-kod/" -UseBasicParsing -TimeoutSec 5).Content } catch {}
Kontrol ($sayfa -and $sayfa.Contains("sinif.js")) "AFİ KOD istemciden açılıyor"

# ---------------------------------------------------------------- 3) kaldırma
$p = Start-Process -FilePath "$hedef\unins000.exe" -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -PassThru
$null = $p.WaitForExit(120000)
for ($i = 0; $i -lt 60 -and (Test-Path "$hedef\afi-istemci.exe"); $i++) { Start-Sleep -Milliseconds 500 }
Kontrol (-not (Test-Path "$hedef\afi-istemci.exe")) "kaldırınca program silindi"
Kontrol (-not (Test-Path "$env:PUBLIC\Desktop\AFİ KOD.lnk")) "kaldırınca kısayol silindi"
Kontrol (-not (Get-Process afi-istemci -ErrorAction SilentlyContinue)) "kaldırınca istemci kapandı"
Kontrol (Test-Path "$veri\afi-sinif.db") "sessiz kaldırmada öğrenci kayıtları korundu"

if ($script:hata) { exit 1 } else { Not "Sessiz kurulum, rol değiştirme ve kaldırma denemeleri geçti."; exit 0 }
