/* afi sınıf - öğretmen paneli */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var S = { ben: null, sekme: 'sinif', uyg: 'afi-kod', ogr: [], secili: null, uygYuklu: {}, ws: null, bilgi: null };
  var DURUM = { calisiyor: 'Çalıştırıyor', basarili: 'Başardı', hata: 'Hata aldı', duraklatildi: 'Duraklattı', hazir: 'Düşünüyor' };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function api(yol, veri, yontem, ham) {
    var o = { method: yontem || (veri || ham ? 'POST' : 'GET'), headers: {}, credentials: 'same-origin' };
    if (ham) { o.body = ham; o.headers['Content-Type'] = 'application/zip'; }
    else if (veri) { o.body = JSON.stringify(veri); o.headers['Content-Type'] = 'application/json'; }
    return fetch('/api/v1/' + yol, o).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) { var e = new Error(j && j.hata || ('Hata ' + r.status)); e.kod = r.status; throw e; } return j; });
    });
  }
  function toast(m) { var t = $('toast'); t.textContent = m; t.hidden = false; clearTimeout(toast.z); toast.z = setTimeout(function () { t.hidden = true; }, 2600); }
  function once(t) {
    var s = Math.max(0, Math.round(Date.now() / 1000 - t));
    if (s < 60) return s + ' sn önce'; if (s < 3600) return Math.round(s / 60) + ' dk önce'; if (s < 86400) return Math.round(s / 3600) + ' sa önce';
    return new Date(t * 1000).toLocaleDateString('tr-TR');
  }
  function formHata(form, e) { var p = form.querySelector('.hata'); p.textContent = e ? e.message : ''; p.hidden = !e; }
  function formVeri(form) { var o = {}; new FormData(form).forEach(function (v, k) { o[k] = v; }); return o; }

  /* ---------- açılış ---------- */
  function ac() {
    api('bilgi').then(function (b) {
      S.bilgi = b; $('sunucuAd').textContent = b.ad; $('altBilgi').textContent = 'platform ' + b.platform;
      if (b.kurulum_gerekli) {
        api('kurulum').then(function (k) { $('kurulumKutu').hidden = false; $('kurulumUzak').hidden = k.yerel; $('kurulumForm').hidden = !k.yerel; });
        return;
      }
      return api('ben').then(function (k) { if (k.giris) girdi(k); else $('girisKutu').hidden = false; });
    }).catch(function (e) { toast('Sunucuya ulaşılamadı: ' + e.message); });
  }
  function girdi(k) {
    S.ben = k;
    $('kurulumKutu').hidden = true; $('girisKutu').hidden = true;
    $('sekmeler').hidden = false; $('kullaniciKutu').hidden = false;
    $('kullaniciAd').textContent = k.ad + (k.rol === 'admin' ? ' (admin)' : '');
    document.querySelectorAll('[data-admin]').forEach(function (e) { e.hidden = k.rol !== 'admin'; });
    sekme(/^#ayarlar$/.test(location.hash) ? 'ayarlar' : 'sinif');
    yenile(); setInterval(function () { if (S.sekme === 'sinif' && !document.hidden) yenile(); }, 3000);
    uygulamaYukle(S.uyg).then(function () { ciz(); }).catch(function () {});
  }
  $('kurulumForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this;
    api('kurulum', formVeri(f)).then(function (k) { girdi(k); }).catch(function (er) { formHata(f, er); });
  });
  $('girisForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this;
    api('giris', formVeri(f)).then(function (k) { girdi(k); }).catch(function (er) { formHata(f, er); });
  });
  $('cikisBtn').onclick = function () { api('cikis', {}).then(function () { location.reload(); }); };

  /* ---------- sekmeler ---------- */
  function sekme(ad) {
    S.sekme = ad;
    document.querySelectorAll('#sekmeler button').forEach(function (b) { b.setAttribute('aria-current', String(b.getAttribute('data-sekme') === ad)); });
    document.querySelectorAll('.sekme').forEach(function (s) { s.hidden = s.id !== 'sekme-' + ad; });
    if (ad === 'ogretmenler') kullanicilar();
    if (ad === 'guncelleme') guncelleme();
    if (ad === 'ayarlar') ayarlar();
    if (ad === 'sinif') yenile();
  }
  $('sekmeler').addEventListener('click', function (e) { var b = e.target.closest('[data-sekme]'); if (b) sekme(b.getAttribute('data-sekme')); });

  /* ---------- uygulamanın kendi dosyaları: robot resimleri, bölüm listesi, blok çizimi ---------- */
  function uygulamaYukle(uyg) {
    if (S.uygYuklu[uyg]) return S.uygYuklu[uyg];
    S.uygYuklu[uyg] = fetch('/' + uyg + '/index.html').then(function (r) { return r.text(); }).then(function (html) {
      var re = /<script(?:\s+src="([^"]+)")?\s*>([\s\S]*?)<\/script>/g, m, liste = [];
      while ((m = re.exec(html))) {
        if (m[1]) { if (!/js\/(app|sinif|sensor-ui)\.js/.test(m[1])) liste.push({ src: '/' + uyg + '/' + m[1] }); }
        else if (m[2].trim()) liste.push({ kod: m[2] });
      }
      return liste.reduce(function (p, it) {
        return p.then(function () {
          return new Promise(function (res) {
            var s = document.createElement('script');
            if (it.src) { s.src = it.src; s.onload = res; s.onerror = res; } else { s.textContent = it.kod; }
            document.head.appendChild(s); if (!it.src) res();
          });
        });
      }, Promise.resolve());
    }).then(function () {
      if (window.RobotBlocks) window.RobotBlocks.setLang('tr');
      return true;
    });
    return S.uygYuklu[uyg];
  }
  function avatar(robot) { return window.ROBOTS ? '<img src="' + window.ROBOTS.avatar(robot || 'afi', 104) + '" alt="">' : '<span class="av"></span>'; }
  function adimlar() {
    var C = window.COURSE; if (!C) return null;
    var out = []; C.chapters.forEach(function (ch) { var ids = []; ch.lessons.forEach(function (l) { l.steps.forEach(function (s) { ids.push(s); }); }); out.push({ ch: ch, adimlar: ids }); });
    return out;
  }

  /* ---------- sınıf ---------- */
  function yenile() {
    if (!S.ben) return;
    api('sinif?uygulama=' + encodeURIComponent(S.uyg)).then(function (c) {
      S.ogr = c.ogrenciler; S.simdi = c.simdi;
      var u = c.uygulamalar || [], sec = $('uygSec');
      sec.hidden = u.length < 2;
      if (u.length && !u.some(function (x) { return x.uygulama === S.uyg; })) S.uyg = u[0].uygulama;
      $('uygAcBtn').href = '/' + S.uyg + '/';
      sec.innerHTML = u.map(function (x) { return '<option value="' + esc(x.uygulama) + '"' + (x.uygulama === S.uyg ? ' selected' : '') + '>' + esc(x.ad) + ' ' + esc(x.surum) + '</option>'; }).join('');
      ciz();
      if (S.secili) ayrinti(S.secili, true);
    }).catch(function (e) { if (e.kod === 401) location.reload(); });
  }
  $('uygSec').onchange = function () { S.uyg = this.value; uygulamaYukle(S.uyg); yenile(); };
  $('ara').oninput = ciz; $('sadeceCevrimici').onchange = ciz;
  $('csvBtn').onclick = function (e) { e.preventDefault(); location.href = '/api/v1/disa-aktar.csv?uygulama=' + encodeURIComponent(S.uyg); };
  function ciz() {
    var q = $('ara').value.trim().toLocaleLowerCase('tr'), sadece = $('sadeceCevrimici').checked;
    var liste = S.ogr.filter(function (o) { return (!sadece || o.cevrimici) && (!q || (o.ad + ' ' + o.cihaz + ' ' + o.ip + ' ' + (o.oturum || '')).toLocaleLowerCase('tr').indexOf(q) >= 0); });
    var acik = S.ogr.filter(function (o) { return o.cevrimici; }), hata = acik.filter(function (o) { return o.durum === 'hata'; }).length;
    var ort = acik.length ? Math.round(acik.reduce(function (a, o) { return a + (o.biten || 0); }, 0) / acik.length) : 0;
    $('ozet').innerHTML = '<div><b>' + acik.length + '</b><span>şu an bağlı</span></div><div><b>' + S.ogr.length + '</b><span>kayıtlı öğrenci</span></div>' +
      '<div><b>' + ort + '</b><span>ortalama biten adım (bağlı olanlar)</span></div><div><b>' + hata + '</b><span>şu an hata almış</span></div>';
    $('ogrenciler').innerHTML = liste.map(function (o) {
      return '<button class="ogr' + (o.cevrimici ? '' : ' kapali') + '" data-anahtar="' + esc(o.anahtar) + '">' + avatar(o.robot) +
        '<b>' + esc(o.ad) + '</b><small title="Bilgisayar · IP adresi">' + esc([o.cihaz, o.ip].filter(Boolean).join(' · ')) + '</small>' +
        '<span class="oturum" title="Windows kullanıcısı">' + (o.oturum ? '👤 ' + esc(o.oturum) : (o.istemci ? '' : 'tarayıcıdan bağlı')) + '</span>' +
        '<span class="adim">' + esc(o.adim_ad || o.adim || '—') + '</span>' +
        '<span class="alt"><span class="hap ' + esc(o.durum || '') + '">' + esc(DURUM[o.durum] || '—') + '</span><span>★ ' + (o.yildiz || 0) + ' · ' + (o.biten || 0) + ' adım</span><small>' + once(o.son) + '</small></span>' +
        '<i class="nokta-d' + (o.cevrimici ? ' acik' : '') + '"></i></button>';
    }).join('');
    $('bosMesaj').hidden = !!liste.length;
    $('bosMesaj').innerHTML = S.ogr.length ? 'Filtreye uyan öğrenci yok.' : 'Henüz öğrenci bağlanmadı. Öğrenciler <b>Ayarlar</b> sekmesindeki adresi açınca burada görünür.';
  }
  $('ogrenciler').addEventListener('click', function (e) { var b = e.target.closest('[data-anahtar]'); if (b) ayrinti(b.getAttribute('data-anahtar')); });

  /* ---------- öğrenci ayrıntısı ---------- */
  function ayrinti(anahtar, sessizYenile) {
    S.secili = anahtar;
    api('ogrenci?uygulama=' + encodeURIComponent(S.uyg) + '&anahtar=' + encodeURIComponent(anahtar)).then(function (d) {
      var o = d.ogrenci; $('cekmece').hidden = false;
      $('dAd').innerHTML = avatar(o.robot).replace('<img', '<img style="width:40px;height:40px;vertical-align:middle;margin-right:8px"') + esc(o.ad);
      $('dBilgi').innerHTML = esc([o.cihaz, o.ip, o.oturum ? 'Windows kullanıcısı: ' + o.oturum : (o.istemci ? '' : 'tarayıcıdan bağlı')].filter(Boolean).join(' · ')) + ' · ' + (o.cevrimici ? '<b style="color:var(--ok)">bağlı</b>' : 'son görülme ' + once(o.son)) +
        ' · ★ ' + (o.yildiz || 0) + ' · ' + (o.biten || 0) + ' adım<br>Şu an: ' + esc(o.adim_ad || o.adim || '—') + ' — ' + esc(DURUM[o.durum] || '');
      var b = adimlar();
      $('dBolumler').innerHTML = b ? b.map(function (x) {
        var n = x.adimlar.length, k = x.adimlar.filter(function (s) { return d.yildizlar[s.id]; }).length;
        return '<div class="bolum"><span>' + x.ch.num + '. ' + esc(x.ch.name.tr) + '</span><span class="cubuk"><i style="width:' + Math.round(100 * k / n) + '%"></i></span><span>' + k + ' / ' + n + '</span></div>';
      }).join('') : '<p class="not">Bölüm listesi yükleniyor...</p>';
      var an = d.anlik;
      $('dAnlikZaman').textContent = an && an.guncelleme ? '(' + (an.adim || '') + ', ' + once(an.guncelleme) + ')' : '';
      $('dKod').textContent = an && an.kod ? an.kod : 'Henüz kod gelmedi.';
      if (!sessizYenile || !S.wsAnahtar || S.wsAnahtar !== anahtar + (an && an.guncelleme)) { S.wsAnahtar = anahtar + (an && an.guncelleme); bloklariCiz(an); }
      $('dOlaylar').innerHTML = d.olaylar.map(function (x) {
        var ay = {}; try { ay = JSON.parse(x.ayrinti) || {}; } catch (e) {}
        return '<li><span>' + new Date(x.zaman * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) + '</span><b style="color:' + (x.tur === 'basari' ? 'var(--ok)' : 'var(--bad)') + '">' +
          (x.tur === 'basari' ? '✓ ' + (ay.yildiz || '') + '★' : '✗') + '</b><span>' + esc(x.adim) + (ay.mesaj ? ' — ' + esc(ay.mesaj) : '') + '</span></li>';
      }).join('') || '<li>Henüz olay yok.</li>';
    }).catch(function (e) { toast(e.message); });
  }
  function bloklariCiz(an) {
    var kutu = $('dBloklar');
    if (S.ws) { try { S.ws.dispose(); } catch (e) {} S.ws = null; }
    kutu.innerHTML = '';
    if (!an || !an.ws || !window.Blockly) return;
    uygulamaYukle(S.uyg).then(function () {
      var st = null; (window.COURSE.chapters || []).forEach(function (ch) { ch.lessons.forEach(function (l) { l.steps.forEach(function (s) { if (s.id === an.adim) st = s; }); }); });
      if (st && st.kind === 'home' && window.HomeBlocks) window.HomeBlocks.ctx = st;
      if (st && st.kind === 'ai' && window.KINDS && window.KINDS.ai) window.KINDS.ai.ctx.ctx = st;
      try {
        S.ws = Blockly.inject(kutu, { readOnly: true, renderer: 'zelos', media: '/' + S.uyg + '/lib/media/', zoom: { controls: true, startScale: 0.7 }, move: { scrollbars: true, drag: true } });
        Blockly.serialization.workspaces.load(an.ws, S.ws);
        S.ws.cleanUp(); S.ws.scrollCenter();
      } catch (e) { kutu.textContent = 'Bloklar çizilemedi: ' + e.message; }
    });
  }
  $('dKapat').onclick = function () { $('cekmece').hidden = true; S.secili = null; if (S.ws) { S.ws.dispose(); S.ws = null; } };
  $('dMesajBtn').onclick = function () {
    var m = $('dMesaj').value.trim(); if (!m || !S.secili) return;
    api('mesaj', { hedef: S.secili, metin: m }).then(function () { $('dMesaj').value = ''; toast('Mesaj gönderildi.'); }).catch(function (e) { toast(e.message); });
  };
  $('herkeseMesajBtn').onclick = function () { $('mesajModal').hidden = false; $('mesajForm').metin.focus(); };
  $('mesajModal').addEventListener('click', function (e) { if (e.target === this || e.target.hasAttribute('data-kapat')) this.hidden = true; });
  $('mesajForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this;
    api('mesaj', { hedef: '*', metin: f.metin.value }).then(function () { f.reset(); $('mesajModal').hidden = true; toast('Mesaj gönderildi.'); }).catch(function (er) { toast(er.message); });
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { $('mesajModal').hidden = true; if (!$('cekmece').hidden) $('dKapat').click(); } });

  /* ---------- öğretmenler ---------- */
  function kullanicilar() {
    $('buIp').textContent = S.bilgi ? S.bilgi.ip : '';
    api('kullanicilar').then(function (l) {
      $('kullaniciTablo').querySelector('tbody').innerHTML = l.map(function (k) {
        return '<tr><td>' + esc(k.kullanici) + '</td><td>' + esc(k.ad) + '</td><td>' + (k.rol === 'admin' ? 'Admin' : 'Öğretmen') + '</td><td>' + (k.araliklar.map(esc).join('<br>') || '<span class="not">hepsi</span>') +
          '</td><td><button class="ince" data-duzenle=\'' + esc(JSON.stringify(k)) + '\'>Düzenle</button>' + (k.kullanici !== S.ben.kullanici ? ' <button class="ince" data-sil="' + k.id + '">Sil</button>' : '') + '</td></tr>';
      }).join('');
    }).catch(function (e) { toast(e.message); });
  }
  function kFormTemizle() { var f = $('kullaniciForm'); f.reset(); f.id.value = ''; f.kullanici.disabled = false; $('kFormBaslik').textContent = 'Yeni öğretmen'; $('kFormIptal').hidden = true; $('parolaNot').textContent = '(en az 6 karakter)'; formHata(f); }
  $('kullaniciTablo').addEventListener('click', function (e) {
    var d = e.target.closest('[data-duzenle]'), s = e.target.closest('[data-sil]'), f = $('kullaniciForm');
    if (d) {
      var k = JSON.parse(d.getAttribute('data-duzenle'));
      f.id.value = k.id; f.kullanici.value = k.kullanici; f.kullanici.disabled = true; f.ad.value = k.ad; f.rol.value = k.rol; f.araliklar.value = k.araliklar.join('\n'); f.sifre.value = '';
      $('kFormBaslik').textContent = 'Düzenle: ' + k.kullanici; $('kFormIptal').hidden = false; $('parolaNot').textContent = '(değiştirmeyecekseniz boş bırakın)';
    }
    if (s && confirm('Bu öğretmen hesabı silinsin mi?')) api('kullanicilar?id=' + s.getAttribute('data-sil'), null, 'DELETE').then(kullanicilar).catch(function (er) { toast(er.message); });
  });
  $('kFormIptal').onclick = kFormTemizle;
  $('kullaniciForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this, v = formVeri(f);
    v.araliklar = (v.araliklar || '').split(/[\n,]/).map(function (x) { return x.trim(); }).filter(Boolean);
    if (f.id.value) v.id = +f.id.value; else delete v.id;
    if (f.id.value) v.kullanici = f.kullanici.value;
    if (!v.sifre) delete v.sifre;
    api('kullanicilar', v).then(function () { kFormTemizle(); kullanicilar(); toast('Kaydedildi.'); }).catch(function (er) { formHata(f, er); });
  });

  /* ---------- güncelleme ---------- */
  function guncelleme() {
    api('guncelleme').then(function (g) {
      $('gAdres').textContent = g.adres;
      $('yerelSurumler').innerHTML = g.yerel.map(function (u) {
        return '<div class="surum"><div><b>' + esc(u.ad) + '</b> — kullanılan sürüm <b>' + esc(u.surum) + '</b><br><span class="not">Kurulu sürümler: ' + u.surumler.map(esc).join(', ') + '</span></div>' +
          '<span>' + u.surumler.filter(function (s) { return s !== u.surum; }).map(function (s) { return '<button class="ince" data-sec="' + esc(u.uygulama) + '|' + esc(s) + '">' + esc(s) + ' sürümüne dön</button>'; }).join(' ') + '</span></div>';
      }).join('') || '<p class="not">Kurulu uygulama yok.</p>';
      if (g.son_denetim) uzakCiz(g.son_denetim);
    }).catch(function (e) { toast(e.message); });
  }
  function uzakCiz(d) {
    $('uzakSurumler').innerHTML = d.uygulamalar.map(function (u) {
      return '<div class="surum"><div><b>' + esc(u.ad) + '</b>: bu sunucuda ' + esc(u.yerel || '—') + ', yayında <b>' + esc(u.uzak) + '</b>' + (u.notlar && u.notlar.tr ? '<br><span class="not">' + esc(u.notlar.tr) + '</span>' : '') + '</div>' +
        (u.yeni ? '<button class="ana" data-kur="' + esc(u.uygulama) + '">İndir ve kur</button>' : '<span class="hap basarili">güncel</span>') + '</div>';
    }).join('');
    $('gDurum').textContent = 'Son denetim: ' + new Date(d.zaman * 1000).toLocaleTimeString('tr-TR');
  }
  $('denetleBtn').onclick = function () {
    var b = this; b.disabled = true; $('gDurum').textContent = 'Denetleniyor...';
    api('guncelleme/denetle', {}).then(uzakCiz).catch(function (e) { $('gDurum').textContent = e.message; }).then(function () { b.disabled = false; });
  };
  $('uzakSurumler').addEventListener('click', function (e) {
    var k = e.target.closest('[data-kur]'); if (!k) return;
    k.disabled = true; $('gDurum').textContent = 'İndiriliyor ve doğrulanıyor...';
    api('guncelleme/kur', { uygulama: k.getAttribute('data-kur') }).then(function (c) {
      $('gDurum').textContent = c.manifest.ad + ' ' + c.manifest.surum + ' kuruldu. Öğrencilere bildirim gitti.'; S.uygYuklu = {}; guncelleme();
    }).catch(function (er) { $('gDurum').textContent = er.message; k.disabled = false; });
  });
  $('yerelSurumler').addEventListener('click', function (e) {
    var s = e.target.closest('[data-sec]'); if (!s) return;
    var p = s.getAttribute('data-sec').split('|');
    if (!confirm(p[1] + ' sürümüne dönülsün mü?')) return;
    api('guncelleme/sec', { uygulama: p[0], surum: p[1] }).then(function () { toast('Sürüm değişti.'); S.uygYuklu = {}; guncelleme(); }).catch(function (er) { toast(er.message); });
  });
  $('paketYukleBtn').onclick = function () {
    var f = $('paketDosya').files[0]; if (!f) { toast('Önce bir .zip paketi seçin.'); return; }
    $('yukleDurum').textContent = 'Yükleniyor...';
    f.arrayBuffer().then(function (buf) { return api('guncelleme/yukle', null, 'POST', buf); }).then(function (c) {
      $('yukleDurum').textContent = c.manifest.ad + ' ' + c.manifest.surum + ' kuruldu.'; S.uygYuklu = {}; guncelleme();
    }).catch(function (er) { $('yukleDurum').textContent = er.message; });
  };

  /* ---------- ayarlar ---------- */
  function sure(sn) { sn = Math.max(0, Math.round(sn)); var s = Math.floor(sn / 3600), d = Math.floor(sn % 3600 / 60); return (s ? s + ' saat ' : '') + d + ' dakika'; }
  function sunucuDurum() {
    api('sunucu').then(function (b) {
      var satir = [['Durum', '<b style="color:var(--ok)">çalışıyor</b> · ' + sure(b.simdi - b.baslangic)], ['Sunucu', esc(b.ad)], ['Bilgisayar', esc(b.bilgisayar) + ' · port ' + b.port],
        ['Öğrenci adresleri', b.adresler.concat([b.ad_adresi]).map(esc).join('<br>')], ['Uygulamalar', b.uygulamalar.map(function (u) { return esc(u.ad + ' ' + u.surum); }).join(', ')],
        ['Platform', esc(b.platform)], ['Program klasörü', esc(b.program)]];
      if (b.veri_klasoru) satir.push(['Kayıtlar', esc(b.veri_klasoru)]);
      $('sunucuDurum').innerHTML = '<dl class="bilgi-tablo">' + satir.map(function (x) { return '<dt>' + x[0] + '</dt><dd>' + x[1] + '</dd>'; }).join('') + '</dl>';
      if (b.gunluk) $('gunluk').textContent = b.gunluk.join('');
      $('kapatBtn').hidden = !b.kapatilabilir || S.ben.rol !== 'admin';
    }).catch(function (e) { $('sunucuDurum').textContent = e.message; });
  }
  $('kapatBtn').onclick = function () {
    if (!confirm('Sunucu kapatılsın mı? Öğrenciler bağlanamaz (istemcisi olanlar çalışmaya devam eder). Yeniden açmak için masaüstündeki "afi sınıf sunucusu" simgesi.')) return;
    api('sunucu/kapat', {}).then(function () { document.body.innerHTML = '<main><div class="kart dar"><h1>Sunucu kapatıldı</h1><p>Yeniden açmak için masaüstündeki <b>afi sınıf sunucusu</b> simgesine çift tıklayın.</p></div></main>'; }).catch(function (e) { toast(e.message); });
  };
  function ayarlar() {
    sunucuDurum();
    var adm = S.ben.rol === 'admin';
    (adm ? api('ayarlar') : Promise.resolve(null)).then(function (a) {
      var adresler = a ? a.adresler.concat([a.ad_adresi]) : [location.origin + '/'];
      $('adresListe').innerHTML = adresler.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('');
      if (a) { var f = $('ayarForm'); f.sunucu_adi.value = a.sunucu_adi; f.guncelleme_adresi.value = a.guncelleme_adresi; $('veriKlasor').textContent = a.veri_klasoru; }
    }).catch(function (e) { toast(e.message); });
  }
  $('ayarForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this;
    api('ayarlar', formVeri(f)).then(function (a) { $('sunucuAd').textContent = a.sunucu_adi; toast('Kaydedildi.'); formHata(f); }).catch(function (er) { formHata(f, er); });
  });
  $('sifreForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this;
    api('sifre', formVeri(f)).then(function () { f.reset(); formHata(f); toast('Parola değişti.'); }).catch(function (er) { formHata(f, er); });
  });
  $('temizleBtn').onclick = function () {
    var o = prompt('Bütün öğrenci verileri silinecek. Onaylamak için büyük harflerle SİL yazın:');
    if (o === null) return;
    api('temizle', { onay: o.trim() }).then(function () { toast('Öğrenci verileri silindi.'); }).catch(function (er) { toast(er.message); });
  };

  ac();
})();
