; afi sınıf kurulum sihirbazı (Inno Setup 6.3 veya yenisi)
; Tek kurulum dosyası: öğretmen bilgisayarına SUNUCU, öğrenci bilgisayarına İSTEMCİ kurar.
;
; Derlemek (GitHub bunu kendisi yapar):  ISCC.exe kurulum\afi-sinif.iss
;   Önce dist\afi-sunucu.exe ve dist\afi-istemci.exe hazır olmalı (PyInstaller).
;
; Sessiz kurulum (her bilgisayara tek komut; yönetici Komut İstemi):
;   afi-sinif-kurulum.exe /VERYSILENT /ALLUSERS /ROL=istemci /SUNUCU=192.168.1.20:8000
;   afi-sinif-kurulum.exe /VERYSILENT /ALLUSERS /ROL=sunucu /PORT=8000 /AD="Bilgi Evi 1"
; Diğer parametreler: /VERI=klasör  /BASLANGIC=0|1  /MASAUSTU=0|1  /DUVAR=0|1  /ORTAK=0|1  /DIR=kurulum klasörü

#define Surum GetEnv("AFI_SURUM")
#if Surum == ""
  #define Surum "1.1.0"
#endif
#define UygAd "afi sınıf"

[Setup]
AppId={{5B7C2E1A-AF15-4C1A-9E5B-AF1514AF1000}
AppName={#UygAd}
AppVersion={#Surum}
AppVerName={#UygAd} {#Surum}
AppPublisher=Aydın İncekara
AppPublisherURL=https://aydinincekara.github.io/isikcirobot_offline/
AppSupportURL=https://aydinincekara.github.io/isikcirobot_offline/
AppCopyright=© 2026 Aydın İncekara
VersionInfoVersion={#Surum}
VersionInfoDescription=afi sınıf kurulumu
DefaultDirName={autopf}\afi sinif
DisableDirPage=no
UsePreviousAppDir=yes
DefaultGroupName={#UygAd}
DisableProgramGroupPage=yes
DisableWelcomePage=no
LicenseFile=LISANS.txt
OutputDir=..\dist
OutputBaseFilename=afi-sinif-kurulum
SetupIconFile=..\tools\ikon\afi-istemci.ico
UninstallDisplayIcon={app}\afi.ico
UninstallDisplayName={#UygAd}
WizardStyle=modern
WizardSizePercent=120
WizardImageFile=gorsel\buyuk-100.bmp,gorsel\buyuk-150.bmp,gorsel\buyuk-200.bmp
WizardSmallImageFile=gorsel\kucuk-100.bmp,gorsel\kucuk-150.bmp,gorsel\kucuk-200.bmp
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
MinVersion=6.3
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
CloseApplications=no
ShowLanguageDialog=no
SetupLogging=yes

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Messages]
tr.WelcomeLabel1=afi sınıf kurulumuna hoş geldiniz
tr.WelcomeLabel2=Bu sihirbaz afi sınıf {#Surum} sürümünü kuracak.%n%nAynı kurulum dosyası öğretmen bilgisayarına sunucu, öğrenci bilgisayarlarına istemci olarak kurulur. Türünü birazdan seçeceksiniz.%n%nAFİ KOD ile çocuklar blok kodlamayı öğrenir; öğretmen de sınıfı tek ekrandan izler.
tr.FinishedHeadingLabel=afi hazır!
tr.ClickFinish=Kurulumu kapatmak için Bitir düğmesine basın.
tr.SelectDirLabel3=afi sınıf şu klasöre kurulacak.
tr.SelectDirBrowseLabel=Devam etmek için Sonraki düğmesine basın. Başka bir klasör seçmek için Gözat'a basın.
tr.ReadyLabel1=afi sınıf kurulmaya hazır.
tr.ReadyLabel2a=Seçimlerinizi aşağıda kontrol edin. Değiştirmek için Geri, kurmak için Kur düğmesine basın.
tr.InstallingLabel=afi sınıf bilgisayarınıza kuruluyor, lütfen bekleyin.

[Files]
Source: "..\dist\afi-sunucu.exe"; DestDir: "{app}"; Flags: ignoreversion; Check: RolSunucu
Source: "..\dist\afi-istemci.exe"; DestDir: "{app}"; Flags: ignoreversion; Check: RolIstemci
Source: "..\tools\ikon\afi-sunucu.ico"; DestDir: "{app}"; DestName: "afi.ico"; Flags: ignoreversion; Check: RolSunucu
Source: "..\tools\ikon\afi-istemci.ico"; DestDir: "{app}"; DestName: "afi.ico"; Flags: ignoreversion; Check: RolIstemci
Source: "LISANS.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "gorsel\robot-1.bmp"; Flags: dontcopy
Source: "gorsel\robot-2.bmp"; Flags: dontcopy
Source: "gorsel\robot-3.bmp"; Flags: dontcopy
Source: "gorsel\robot-4.bmp"; Flags: dontcopy

[Dirs]
Name: "{code:VeriKlasoru}"; Permissions: users-modify; Flags: uninsneveruninstall; Check: RolSunucu and IsAdminInstallMode
Name: "{code:VeriKlasoru}"; Flags: uninsneveruninstall; Check: RolSunucu and not IsAdminInstallMode

[InstallDelete]
; rol değiştiyse öbür rolün dosyaları ve kısayolları kalkar
Type: files; Name: "{app}\afi-sunucu.exe"; Check: RolIstemci
Type: files; Name: "{app}\afi-istemci.exe"; Check: RolSunucu
Type: files; Name: "{autodesktop}\afi sınıf sunucusu.lnk"
Type: files; Name: "{autostartup}\afi sınıf sunucusu.lnk"
Type: files; Name: "{autodesktop}\AFİ KOD.lnk"
Type: files; Name: "{autostartup}\afi istemci.lnk"
Type: filesandordirs; Name: "{autoprograms}\afi sınıf"
; 1.0.0'daki kendi kendine kurulan istemcinin kalıntıları
Type: files; Name: "{userstartup}\afi istemci.lnk"
Type: files; Name: "{userdesktop}\AFİ KOD.lnk"
Type: files; Name: "{localappdata}\afi-sinif\afi-istemci.exe"

[Icons]
Name: "{autodesktop}\afi sınıf sunucusu"; Filename: "{app}\afi-sunucu.exe"; WorkingDir: "{app}"; IconFilename: "{app}\afi.ico"; Comment: "Öğretmen paneli ve sınıf sunucusu"; Check: RolSunucu and SecMasaustu
Name: "{autoprograms}\afi sınıf\afi sınıf sunucusu"; Filename: "{app}\afi-sunucu.exe"; WorkingDir: "{app}"; IconFilename: "{app}\afi.ico"; Check: RolSunucu
Name: "{autostartup}\afi sınıf sunucusu"; Filename: "{app}\afi-sunucu.exe"; Parameters: "--tarayici-acma"; WorkingDir: "{app}"; IconFilename: "{app}\afi.ico"; Flags: runminimized; Check: RolSunucu and SecBaslangic
Name: "{autodesktop}\AFİ KOD"; Filename: "{app}\afi-istemci.exe"; WorkingDir: "{app}"; IconFilename: "{app}\afi.ico"; Comment: "AFİ KOD blok kodlama"; Check: RolIstemci and SecMasaustu
Name: "{autoprograms}\afi sınıf\AFİ KOD"; Filename: "{app}\afi-istemci.exe"; WorkingDir: "{app}"; IconFilename: "{app}\afi.ico"; Check: RolIstemci
Name: "{autostartup}\afi istemci"; Filename: "{app}\afi-istemci.exe"; Parameters: "--arka-plan"; WorkingDir: "{app}"; Check: RolIstemci and SecBaslangic
Name: "{autoprograms}\afi sınıf\afi sınıf'ı kaldır"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\afi-sunucu.exe"; Description: "afi sınıf sunucusunu şimdi başlat (öğretmen paneli açılır)"; Flags: postinstall nowait skipifsilent runasoriginaluser; Check: RolSunucu and not Onizleme
Filename: "{app}\afi-istemci.exe"; Description: "AFİ KOD'u şimdi aç"; Flags: postinstall nowait skipifsilent runasoriginaluser; Check: RolIstemci and not Onizleme
Filename: "{app}\afi-istemci.exe"; Parameters: "--arka-plan"; Flags: nowait runasoriginaluser; Check: RolIstemci and WizardSilent and SecBaslangic

[UninstallDelete]
Type: files; Name: "{app}\kurulum.json"
Type: files; Name: "{app}\kurulum.ini"
Type: dirifempty; Name: "{app}"

[Code]
const
  KALDIR_ANAHTAR = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{5B7C2E1A-AF15-4C1A-9E5B-AF1514AF1000}_is1';
  DUVAR_KURAL = 'afi sinif sunucusu';

var
  BakimSayfa: TInputOptionWizardPage;
  RolSayfa, SunucuSayfa, IstemciSayfa: TWizardPage;
  RbSunucu, RbIstemci: TNewRadioButton;
  EdAd, EdPort, EdVeri, EdAdres: TNewEdit;
  CbDuvar, CbOrtak, CbSMasa, CbSBas, CbIBas, CbIMasa: TNewCheckBox;
  RobotResim: TBitmapImage;
  DurumYazi: TNewStaticText;
  OncekiSurum, OncekiRol, KaldirKomutu, KaldirVeri, KaldirRol: String;
  KaldirildiKapat: Boolean;
  SonKare: Integer;

{ ---------------------------------------------------------------- küçük yardımcılar }
function Param(Ad, Varsayilan: String): String;
begin
  Result := ExpandConstant('{param:' + Ad + '|' + Varsayilan + '}');
end;

function ParamAcik(Ad: String; Varsayilan: Boolean): Boolean;
var V: String;
begin
  if Varsayilan then V := Param(Ad, '1') else V := Param(Ad, '0');
  Result := (V = '1') or (CompareText(V, 'evet') = 0) or (CompareText(V, 'true') = 0);
end;

function Onizleme: Boolean;
begin
  Result := Param('ONIZLEME', '0') = '1';
end;

function RolSunucu: Boolean;
begin
  Result := RbSunucu.Checked;
end;

function RolIstemci: Boolean;
begin
  Result := not RbSunucu.Checked;
end;

function SecMasaustu: Boolean;
begin
  if RolSunucu then Result := CbSMasa.Checked else Result := CbIMasa.Checked;
end;

function SecBaslangic: Boolean;
begin
  if RolSunucu then Result := CbSBas.Checked else Result := CbIBas.Checked;
end;

function VeriKlasoru(Bos: String): String;
begin
  Result := Trim(EdVeri.Text);
end;

function JsonMetin(S: String): String;
begin
  StringChangeEx(S, '\', '\\', True);
  StringChangeEx(S, '"', '\"', True);
  Result := '"' + S + '"';
end;

function Yazi(Sayfa: TWizardPage; Metin: String; Sol, Ust: Integer; Kalin: Boolean): TNewStaticText;
begin
  Result := TNewStaticText.Create(Sayfa);
  Result.Parent := Sayfa.Surface;
  Result.Left := Sol;
  Result.Top := Ust;
  Result.Width := Sayfa.SurfaceWidth - Sol;
  Result.AutoSize := False;
  Result.WordWrap := True;
  Result.Caption := Metin;
  Result.AutoSize := True;
  if Kalin then Result.Font.Style := [fsBold];
end;

function Kutu(Sayfa: TWizardPage; Metin: String; Ust: Integer; Isaretli: Boolean): TNewCheckBox;
begin
  Result := TNewCheckBox.Create(Sayfa);
  Result.Parent := Sayfa.Surface;
  Result.Left := 0;
  Result.Top := Ust;
  Result.Width := Sayfa.SurfaceWidth;
  Result.Height := ScaleY(18);
  Result.Caption := Metin;
  Result.Checked := Isaretli;
end;

function Kutucuk(Sayfa: TWizardPage; Ust, Genislik: Integer; Metin: String): TNewEdit;
begin
  Result := TNewEdit.Create(Sayfa);
  Result.Parent := Sayfa.Surface;
  Result.Left := 0;
  Result.Top := Ust;
  Result.Width := Genislik;
  Result.Text := Metin;
end;

function KayitOku(Ad: String; var Deger: String): Boolean;
begin
  Result := RegQueryStringValue(HKLM64, KALDIR_ANAHTAR, Ad, Deger)
    or RegQueryStringValue(HKLM32, KALDIR_ANAHTAR, Ad, Deger)
    or RegQueryStringValue(HKCU, KALDIR_ANAHTAR, Ad, Deger);
end;

procedure Durum(Metin: String; Kare: Integer);
begin
  if DurumYazi <> nil then
  begin
    DurumYazi.Caption := Metin;
    DurumYazi.Left := (WizardForm.InstallingPage.Width - DurumYazi.Width) div 2;
  end;
  if (Kare > 0) and (Kare <> SonKare) and (RobotResim <> nil) then
  begin
    RobotResim.Bitmap.LoadFromFile(ExpandConstant('{tmp}\robot-' + IntToStr(Kare) + '.bmp'));
    SonKare := Kare;
  end;
  WizardForm.Refresh;
end;

procedure UygulamalariKapat;
var R: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM afi-istemci.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM afi-sunucu.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
end;

procedure GozatTikla(Sender: TObject);
var K: String;
begin
  K := EdVeri.Text;
  if BrowseForFolder('Öğrenci verilerinin tutulacağı klasörü seçin:', K, True) then
    EdVeri.Text := K;
end;

function RolAdi(R: String): String;
begin
  if R = 'sunucu' then Result := 'öğretmen bilgisayarı (sunucu)'
  else if R = 'istemci' then Result := 'öğrenci bilgisayarı (istemci)'
  else Result := 'bilinmiyor';
end;

{ ---------------------------------------------------------------- sayfalar }
procedure RolSayfasiniYap;
var Y: Integer; T: TNewStaticText;
begin
  RolSayfa := CreateCustomPage(wpLicense, 'Kurulum türü', 'Bu bilgisayar sınıfta ne olacak?');

  RbSunucu := TNewRadioButton.Create(RolSayfa);
  RbSunucu.Parent := RolSayfa.Surface;
  RbSunucu.Left := 0; RbSunucu.Top := 0;
  RbSunucu.Width := RolSayfa.SurfaceWidth; RbSunucu.Height := ScaleY(20);
  RbSunucu.Caption := 'Öğretmen bilgisayarı  (sunucu)';
  RbSunucu.Font.Style := [fsBold];
  T := Yazi(RolSayfa, 'Sınıfın merkezi. Öğretmen paneli burada açılır: öğrencileri canlı izler, mesaj gönderir, AFİ KOD güncellemelerini yapar. Sınıfta bir tane yeter.', ScaleX(18), ScaleY(22), False);
  Y := T.Top + T.Height + ScaleY(16);

  RbIstemci := TNewRadioButton.Create(RolSayfa);
  RbIstemci.Parent := RolSayfa.Surface;
  RbIstemci.Left := 0; RbIstemci.Top := Y;
  RbIstemci.Width := RolSayfa.SurfaceWidth; RbIstemci.Height := ScaleY(20);
  RbIstemci.Caption := 'Öğrenci bilgisayarı  (istemci)';
  RbIstemci.Font.Style := [fsBold];
  T := Yazi(RolSayfa, 'Öğrenci AFİ KOD''u bu bilgisayarda açar. Ağ olmasa da çalışır, kayıtları saklar; öğretmen sunucusunu ağda kendisi bulur. Her öğrenci bilgisayarına kurulur.', ScaleX(18), Y + ScaleY(22), False);
  Y := T.Top + T.Height + ScaleY(18);

  if IsAdminInstallMode then
    T := Yazi(RolSayfa, 'Bu bilgisayardaki tüm kullanıcılar için kuruluyor (yönetici).', 0, Y, False)
  else
    T := Yazi(RolSayfa, 'Yalnızca sizin için kuruluyor. Öğretmen bilgisayarında "Tüm kullanıcılar için" (yönetici) kurulum önerilir; böylece güvenlik duvarı izni kurulumda verilir.', 0, Y, False);
  T.Font.Color := $707070;

  if (CompareText(Param('ROL', ''), 'sunucu') = 0) or ((Param('ROL', '') = '') and (OncekiRol = 'sunucu')) then
    RbSunucu.Checked := True
  else
    RbIstemci.Checked := True;
end;

procedure SunucuSayfasiniYap;
var Y: Integer; T: TNewStaticText; B: TNewButton; Varsayilan: String;
begin
  SunucuSayfa := CreateCustomPage(RolSayfa.ID, 'Öğretmen bilgisayarı ayarları', 'Bunları sonra öğretmen panelinden ya da kurulumu yeniden çalıştırarak değiştirebilirsiniz.');
  T := Yazi(SunucuSayfa, 'Sunucunun adı (öğrencilerin ekranında görünür)', 0, 0, False);
  EdAd := Kutucuk(SunucuSayfa, T.Top + T.Height + ScaleY(3), SunucuSayfa.SurfaceWidth, Param('AD', GetPreviousData('Ad', 'afi sınıf - ' + GetComputerNameString)));
  Y := EdAd.Top + EdAd.Height + ScaleY(8);

  T := Yazi(SunucuSayfa, 'Port (değiştirmeniz gerekmez)', 0, Y, False);
  EdPort := Kutucuk(SunucuSayfa, T.Top + T.Height + ScaleY(3), ScaleX(80), Param('PORT', GetPreviousData('Port', '8000')));
  Y := EdPort.Top + EdPort.Height + ScaleY(8);

  if IsAdminInstallMode then
    Varsayilan := ExpandConstant('{commonappdata}\afi-sinif\sunucu-veri')
  else
    Varsayilan := ExpandConstant('{localappdata}\afi-sinif\sunucu-veri');
  T := Yazi(SunucuSayfa, 'Öğrenci kayıtlarının tutulacağı klasör (yedek için bu klasörü kopyalamanız yeter)', 0, Y, False);
  EdVeri := Kutucuk(SunucuSayfa, T.Top + T.Height + ScaleY(3), SunucuSayfa.SurfaceWidth - ScaleX(90), Param('VERI', GetPreviousData('Veri', Varsayilan)));
  B := TNewButton.Create(SunucuSayfa);
  B.Parent := SunucuSayfa.Surface;
  B.Caption := 'Gözat...';
  B.Left := SunucuSayfa.SurfaceWidth - ScaleX(82);
  B.Top := EdVeri.Top - ScaleY(1);
  B.Width := ScaleX(82);
  B.Height := EdVeri.Height + ScaleY(2);
  B.OnClick := @GozatTikla;
  Y := EdVeri.Top + EdVeri.Height + ScaleY(12);

  CbDuvar := Kutu(SunucuSayfa, 'Güvenlik duvarında izin ver (öğrenciler bağlanabilsin)', Y, ParamAcik('DUVAR', True));
  CbOrtak := Kutu(SunucuSayfa, 'Okul ağı "Ortak ağ" görünse de izin ver', Y + ScaleY(20), ParamAcik('ORTAK', GetPreviousData('Ortak', '1') = '1'));
  if not IsAdminInstallMode then
  begin
    CbDuvar.Checked := False; CbDuvar.Enabled := False; CbOrtak.Checked := False; CbOrtak.Enabled := False;
    CbDuvar.Caption := 'Güvenlik duvarı izni (yönetici kurulumu gerekir; Windows ilk açılışta soracak)';
  end;
  CbSMasa := Kutu(SunucuSayfa, 'Masaüstüne "afi sınıf sunucusu" kısayolu koy', Y + ScaleY(40), ParamAcik('MASAUSTU', GetPreviousData('SMasaustu', '1') = '1'));
  CbSBas := Kutu(SunucuSayfa, 'Windows açılınca sunucuyu kendiliğinden başlat', Y + ScaleY(60), ParamAcik('BASLANGIC', GetPreviousData('SBaslangic', '0') = '1'));
end;

procedure IstemciSayfasiniYap;
var T: TNewStaticText; Y: Integer;
begin
  IstemciSayfa := CreateCustomPage(SunucuSayfa.ID, 'Öğrenci bilgisayarı ayarları', 'AFİ KOD ağ olsa da olmasa da çalışır.');
  T := Yazi(IstemciSayfa, 'Öğretmen sunucusunun adresi (isteğe bağlı)', 0, 0, False);
  EdAdres := Kutucuk(IstemciSayfa, T.Top + T.Height + ScaleY(3), IstemciSayfa.SurfaceWidth, Param('SUNUCU', GetPreviousData('Sunucu', '')));
  T := Yazi(IstemciSayfa, 'Boş bırakırsanız sunucuyu ağda kendisi bulur. Örnek: 192.168.1.20:8000 ya da OGRETMEN-PC', 0, EdAdres.Top + EdAdres.Height + ScaleY(4), False);
  T.Font.Color := $707070;
  Y := T.Top + T.Height + ScaleY(14);
  CbIBas := Kutu(IstemciSayfa, 'Windows açılınca arka planda başlat (önerilir)', Y, ParamAcik('BASLANGIC', GetPreviousData('IBaslangic', '1') = '1'));
  CbIMasa := Kutu(IstemciSayfa, 'Masaüstüne "AFİ KOD" kısayolu koy', Y + ScaleY(20), ParamAcik('MASAUSTU', GetPreviousData('IMasaustu', '1') = '1'));
  T := Yazi(IstemciSayfa, 'Öğrenci kayıtları her Windows kullanıcısının kendi klasöründe tutulur (%LOCALAPPDATA%\afi-sinif). Bağlantı yokken biriken kayıtlar, sunucu bulununca gönderilir.', 0, Y + ScaleY(52), False);
  T.Font.Color := $707070;
end;

procedure IlerlemeGorseliniYap;
begin
  ExtractTemporaryFile('robot-1.bmp');
  ExtractTemporaryFile('robot-2.bmp');
  ExtractTemporaryFile('robot-3.bmp');
  ExtractTemporaryFile('robot-4.bmp');
  RobotResim := TBitmapImage.Create(WizardForm);
  RobotResim.Parent := WizardForm.InstallingPage;
  RobotResim.Stretch := True;
  RobotResim.Width := ScaleX(256);
  RobotResim.Height := ScaleY(144);
  RobotResim.Left := (WizardForm.InstallingPage.Width - RobotResim.Width) div 2;
  RobotResim.Top := WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(18);
  RobotResim.Bitmap.LoadFromFile(ExpandConstant('{tmp}\robot-1.bmp'));
  SonKare := 1;
  DurumYazi := TNewStaticText.Create(WizardForm);
  DurumYazi.Parent := WizardForm.InstallingPage;
  DurumYazi.Top := RobotResim.Top + RobotResim.Height + ScaleY(8);
  DurumYazi.Font.Style := [fsBold];
  DurumYazi.Font.Color := $C96325;      { afi mavisi (BGR) }
  DurumYazi.Caption := 'afi hazırlanıyor...';
  DurumYazi.Left := (WizardForm.InstallingPage.Width - DurumYazi.Width) div 2;
end;

{ ---------------------------------------------------------------- olaylar }
procedure InitializeWizard;
begin
  KayitOku('DisplayVersion', OncekiSurum);
  KayitOku('Inno Setup CodeFile: Rol', OncekiRol);
  KayitOku('UninstallString', KaldirKomutu);
  if OncekiSurum <> '' then
  begin
    BakimSayfa := CreateInputOptionPage(wpWelcome, 'afi sınıf bu bilgisayarda kurulu',
      'Kurulu sürüm: ' + OncekiSurum + '   ·   Tür: ' + RolAdi(OncekiRol),
      'Ne yapmak istersiniz? Öğrenci kayıtları her iki durumda da korunur (kaldırırken ayrıca sorulur).', True, False);
    BakimSayfa.Add('Güncelle ya da ayarları / kurulum türünü değiştir  (yeni sürüm: {#Surum})');
    BakimSayfa.Add('afi sınıf''ı bu bilgisayardan kaldır');
    BakimSayfa.SelectedValueIndex := 0;
  end;
  RolSayfasiniYap;
  SunucuSayfasiniYap;
  IstemciSayfasiniYap;
  IlerlemeGorseliniYap;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PageID = wpLicense) and (OncekiSurum <> '') then Result := True;
  if PageID = SunucuSayfa.ID then Result := not RolSunucu;
  if PageID = IstemciSayfa.ID then Result := not RolIstemci;
end;

procedure CurPageChanged(CurPageID: Integer);
var Port: String;
begin
  if (CurPageID = wpLicense) and Onizleme then
    WizardForm.LicenseAcceptedRadio.Checked := True;
  if CurPageID = wpFinished then
  begin
    Port := Trim(EdPort.Text);
    if RolSunucu then
      WizardForm.FinishedLabel.Caption :=
        'afi sınıf sunucusu kuruldu.' + #13#10#13#10 +
        'Öğrenciler tarayıcıda  http://' + GetComputerNameString + ':' + Port + '  adresini açar ya da afi istemciyle kendiliğinden bağlanır.' + #13#10#13#10 +
        'Öğretmen paneli:  http://localhost:' + Port + '/panel/' + #13#10 +
        'İlk açılışta admin hesabınızı oluşturun.'
    else
      WizardForm.FinishedLabel.Caption :=
        'AFİ KOD bu bilgisayara kuruldu.' + #13#10#13#10 +
        'Masaüstündeki "AFİ KOD" simgesiyle açılır. Öğretmen sunucusu ağdaysa kendiliğinden bağlanır; değilse kayıtlar bu bilgisayarda saklanır.' + #13#10#13#10 +
        'Bağlantı ayarları: AFİ KOD''da üstteki "Sınıf" etiketine tıklayın.';
    WizardForm.AdjustLabelHeight(WizardForm.FinishedLabel);
    WizardForm.RunList.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(14);
  end;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if KaldirildiKapat then Confirm := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var R, P: Integer;
begin
  Result := True;
  if (BakimSayfa <> nil) and (CurPageID = BakimSayfa.ID) and (BakimSayfa.SelectedValueIndex = 1) then
  begin
    Result := False;
    if Exec(RemoveQuotes(KaldirKomutu), '', '', SW_SHOW, ewWaitUntilTerminated, R) then
    begin
      KaldirildiKapat := True;
      WizardForm.Close;
    end
    else
      MsgBox('Kaldırma programı açılamadı. Denetim Masası > Programlar bölümünden kaldırabilirsiniz.', mbError, MB_OK);
  end;
  if CurPageID = SunucuSayfa.ID then
  begin
    P := StrToIntDef(Trim(EdPort.Text), 0);
    if (P < 1) or (P > 65535) then
    begin
      MsgBox('Port 1 ile 65535 arasında bir sayı olmalı (önerilen: 8000).', mbError, MB_OK);
      Result := False;
    end
    else if Trim(EdAd.Text) = '' then
    begin
      MsgBox('Sunucuya bir ad verin.', mbError, MB_OK);
      Result := False;
    end
    else if Trim(EdVeri.Text) = '' then
    begin
      MsgBox('Verilerin tutulacağı klasörü seçin.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var S: String;
begin
  if RolSunucu then
  begin
    S := 'Kurulum türü:' + NewLine + Space + 'Öğretmen bilgisayarı (sunucu)' + NewLine + NewLine;
    S := S + 'Sunucu:' + NewLine + Space + Trim(EdAd.Text) + '  ·  port ' + Trim(EdPort.Text) + NewLine + NewLine;
    S := S + 'Öğrenci kayıtları:' + NewLine + Space + Trim(EdVeri.Text) + NewLine + NewLine;
    if CbDuvar.Checked then
    begin
      if CbOrtak.Checked then S := S + 'Güvenlik duvarı:' + NewLine + Space + 'izin verilecek (özel, etki alanı ve ortak ağlar)' + NewLine + NewLine
      else S := S + 'Güvenlik duvarı:' + NewLine + Space + 'izin verilecek (özel ve etki alanı ağları)' + NewLine + NewLine;
    end;
  end
  else
  begin
    S := 'Kurulum türü:' + NewLine + Space + 'Öğrenci bilgisayarı (istemci)' + NewLine + NewLine;
    if Trim(EdAdres.Text) = '' then
      S := S + 'Öğretmen sunucusu:' + NewLine + Space + 'ağda kendiliğinden bulunacak' + NewLine + NewLine
    else
      S := S + 'Öğretmen sunucusu:' + NewLine + Space + Trim(EdAdres.Text) + NewLine + NewLine;
  end;
  S := S + MemoDirInfo + NewLine + NewLine;
  S := S + 'Kısayollar:' + NewLine;
  if SecMasaustu then S := S + Space + 'masaüstü' + NewLine;
  if SecBaslangic then S := S + Space + 'Windows açılışında başlat' + NewLine;
  S := S + Space + 'Başlat menüsü > afi sınıf' + NewLine;
  Result := S;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  if RolSunucu then SetPreviousData(PreviousDataKey, 'Rol', 'sunucu') else SetPreviousData(PreviousDataKey, 'Rol', 'istemci');
  SetPreviousData(PreviousDataKey, 'Ad', Trim(EdAd.Text));
  SetPreviousData(PreviousDataKey, 'Port', Trim(EdPort.Text));
  SetPreviousData(PreviousDataKey, 'Veri', Trim(EdVeri.Text));
  SetPreviousData(PreviousDataKey, 'Sunucu', Trim(EdAdres.Text));
  if CbOrtak.Checked then SetPreviousData(PreviousDataKey, 'Ortak', '1') else SetPreviousData(PreviousDataKey, 'Ortak', '0');
  if CbSMasa.Checked then SetPreviousData(PreviousDataKey, 'SMasaustu', '1') else SetPreviousData(PreviousDataKey, 'SMasaustu', '0');
  if CbSBas.Checked then SetPreviousData(PreviousDataKey, 'SBaslangic', '1') else SetPreviousData(PreviousDataKey, 'SBaslangic', '0');
  if CbIMasa.Checked then SetPreviousData(PreviousDataKey, 'IMasaustu', '1') else SetPreviousData(PreviousDataKey, 'IMasaustu', '0');
  if CbIBas.Checked then SetPreviousData(PreviousDataKey, 'IBaslangic', '1') else SetPreviousData(PreviousDataKey, 'IBaslangic', '0');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Durum('Açık afi programları kapatılıyor...', 1);
  UygulamalariKapat;
  Result := '';
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
var K: Integer;
begin
  if MaxProgress <= 0 then Exit;
  K := 1 + (CurProgress * 2) div MaxProgress;
  if K = 1 then Durum('afi dosyaları yerleştiriyor...', 1)
  else if K = 2 then Durum('AFİ KOD hazırlanıyor...', 2)
  else Durum('Dosyalar yerleşti.', 3);
end;

procedure AyarlariYaz;
var J: TArrayOfString; Dosya, Ozel: String;
begin
  Dosya := ExpandConstant('{app}\kurulum.json');
  SetArrayLength(J, 1);
  if RolSunucu then
    J[0] := '{"rol": "sunucu", "surum": "{#Surum}", "ad": ' + JsonMetin(Trim(EdAd.Text)) +
            ', "port": ' + IntToStr(StrToIntDef(Trim(EdPort.Text), 8000)) + ', "veri": ' + JsonMetin(Trim(EdVeri.Text)) + '}'
  else
    J[0] := '{"rol": "istemci", "surum": "{#Surum}", "sunucu": ' + JsonMetin(Trim(EdAdres.Text)) + '}';
  SaveStringsToUTF8File(Dosya, J, False);
  Ozel := ExpandConstant('{app}\kurulum.ini');
  if RolSunucu then SetIniString('kurulum', 'rol', 'sunucu', Ozel) else SetIniString('kurulum', 'rol', 'istemci', Ozel);
  SetIniString('kurulum', 'veri', Trim(EdVeri.Text), Ozel);
end;

procedure DuvarAyarla;
var R: Integer; Profil: String;
begin
  if not IsAdminInstallMode then Exit;
  Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="' + DUVAR_KURAL + '"', '', SW_HIDE, ewWaitUntilTerminated, R);
  if RolSunucu and CbDuvar.Checked then
  begin
    if CbOrtak.Checked then Profil := 'any' else Profil := 'private,domain';
    Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall add rule name="' + DUVAR_KURAL + '" dir=in action=allow enable=yes profile=' + Profil +
      ' program="' + ExpandConstant('{app}\afi-sunucu.exe') + '"', '', SW_HIDE, ewWaitUntilTerminated, R);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Bekle: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    Bekle := 250;
    if Onizleme then Bekle := 1500;
    Durum('Ayarlar yazılıyor...', 3);
    AyarlariYaz;
    Sleep(Bekle);
    if RolSunucu then
    begin
      Durum('Güvenlik duvarı ayarlanıyor...', 3);
      DuvarAyarla;
    end
    else
    begin
      Durum('Kısayollar hazırlanıyor...', 3);
      DuvarAyarla;
    end;
    Sleep(Bekle);
    Durum('afi hazır!', 4);
    Sleep(Bekle);
  end;
end;

{ ---------------------------------------------------------------- kaldırma }
function InitializeUninstall: Boolean;
begin
  UygulamalariKapat;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var R: Integer; Ozel: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    Ozel := ExpandConstant('{app}\kurulum.ini');
    KaldirRol := GetIniString('kurulum', 'rol', '', Ozel);
    KaldirVeri := GetIniString('kurulum', 'veri', '', Ozel);
    if IsAdminInstallMode then
      Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="' + DUVAR_KURAL + '"', '', SW_HIDE, ewWaitUntilTerminated, R);
  end;
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    if (KaldirRol = 'sunucu') and (KaldirVeri <> '') and DirExists(KaldirVeri) then
    begin
      if MsgBox('Öğrenci kayıtları da silinsin mi?' + #13#10#13#10 + KaldirVeri + #13#10#13#10 +
                'Hayır derseniz kayıtlar kalır; afi sınıf yeniden kurulunca kaldığı yerden devam eder.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(KaldirVeri, True, True, True);
    end
    else if (KaldirRol = 'istemci') and DirExists(ExpandConstant('{localappdata}\afi-sinif')) then
    begin
      if MsgBox('Bu kullanıcının bu bilgisayardaki AFİ KOD kayıtları da silinsin mi?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(ExpandConstant('{localappdata}\afi-sinif'), True, True, True);
    end;
  end;
end;
