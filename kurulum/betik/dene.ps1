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

# ---------------------------------------------------------------- 1) öğretmen bilgisayarı (varsayılan klasör C:\afikod)
# 1.1 sürümünün kayıt yeri: yeni sürüm bunları C:\afikod\kayitlar\sunucu içine taşımalı
$eski = Join-Path $env:LOCALAPPDATA "afi-sinif\sunucu-veri"
python -c "import sys; sys.path.insert(0, '.'); from afi_sinif import sunucu; a = sunucu.Sunucu(sys.argv[1], port=0, sessiz=True); a.kullanici_ekle('eski', 'Eski Hoca', 'gizli123', 'admin', [])" $eski
Kontrol (Test-Path "$eski\afi-sinif.db") "eski sürüm kayıtları hazırlandı"
Kur @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/ALLUSERS", "/ROL=sunucu", "/PORT=8125", "/AD=Deneme-Sınıfı", "/ORTAK=0")
$hedef = "C:\afikod"
$veri = "C:\afikod\kayitlar\sunucu"
Kontrol (Test-Path "$hedef\afi-sunucu.exe") "sunucu programı C:\afikod içine kuruldu"
Kontrol (-not (Test-Path "$hedef\afi-istemci.exe")) "istemci programı yok"
$k = Json "$hedef\kurulum.json"
Kontrol ($k.rol -eq "sunucu" -and $k.port -eq 8125 -and $k.veri -eq $veri) "kurulum.json: $($k | ConvertTo-Json -Compress)"
Kontrol (Kural) "güvenlik duvarı kuralı eklendi"
Kontrol (Test-Path "$env:PUBLIC\Desktop\afi sınıf sunucusu.lnk") "masaüstü kısayolu"
$p = Start-Process -FilePath "$hedef\afi-sunucu.exe" -ArgumentList @("--tarayici-acma") -PassThru
$b = $null
for ($i = 0; $i -lt 30 -and -not $b; $i++) { Start-Sleep -Milliseconds 500; $b = Istek "http://127.0.0.1:8125/api/v1/bilgi" }
Kontrol ($b -and $b.rol -eq "sunucu") "kurulu sunucu penceresiz, kurulumdaki portta (8125) çalıştı"
Kontrol ($b -and $b.ad -eq "Deneme-Sınıfı") "sunucu adı kurulumdan geldi: $($b.ad)"
Kontrol (Test-Path "$veri\afi-sinif.db") "veritabanı C:\afikod\kayitlar\sunucu içinde"
Kontrol ($b -and $b.kurulum_gerekli -eq $false) "eski kayıtlar (öğretmen hesabı) yeni yere taşındı"
Kontrol (Test-Path "$eski-tasindi") "eski klasör '-tasindi' adıyla yedek kaldı"
$ses = $null
try { $g = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8125/api/v1/giris" -Body (@{ kullanici = "eski"; sifre = "gizli123" } | ConvertTo-Json) -ContentType "application/json; charset=utf-8" -SessionVariable ses } catch { Hata "giriş: $_" }
$d = $null; try { $d = Invoke-RestMethod -Uri "http://127.0.0.1:8125/api/v1/sunucu" -WebSession $ses } catch { Hata "sunucu bilgisi: $_" }
Kontrol ($d -and $d.veri_klasoru -eq $veri -and $d.kapatilabilir) "panelde sunucu bilgisi: $($d.veri_klasoru)"
try { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8125/api/v1/sunucu/kapat" -Body "{}" -ContentType "application/json" -WebSession $ses | Out-Null } catch { Hata "kapat: $_" }
$kapandi = $p.WaitForExit(15000)
Kontrol $kapandi "panelden 'Sunucuyu kapat' programı kapattı"
Get-Process afi-sunucu -ErrorAction SilentlyContinue | Stop-Process -Force
$g = Get-Content "$veri\gunluk.txt" -Raw -Encoding UTF8
Kontrol ($g -and -not ($g -match "simgesi açılamadı")) "görev çubuğu simgesi açıldı (günlükte hata yok)"
Kontrol ($g -match "port 8125 \(simge\)") "sunucu penceresiz (simge) modda başladı"

# ---------------------------------------------------------------- 2) aynı bilgisayarı öğrenciye çevir (rol değiştirme)
Kur @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/ALLUSERS", "/ROL=istemci", "/SUNUCU=127.0.0.1:8125", "/BASLANGIC=1")
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
Kontrol (Test-Path "C:\afikod\kayitlar\istemci\$env:USERNAME\ayarlar.json") "istemci kayıtları C:\afikod\kayitlar\istemci\$env:USERNAME içinde"
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
