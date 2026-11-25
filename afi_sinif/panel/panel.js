/* afi sınıf - öğretmen paneli */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var S = { ben: null, sekme: 'sinif', uyg: 'afi-kod', ogr: [], secili: null, seciliO: null, uygYuklu: {}, ws: null, bilgi: null,
    sinif: '*', goster: 'hepsi', siniflar: [], kip: 'serbest', kartlar: {}, rapor: null, raporSira: { a: 'ad', yon: 1 }, simdi: Date.now() / 1000 };
  var DURUM = { calisiyor: 'Çalıştırıyor', basarili: 'Başardı', hata: 'Hata aldı', duraklatildi: 'Duraklattı', hazir: 'Düşünüyor' };
  (function () { var t = {}; try { t = JSON.parse(localStorage.getItem('afi-panel') || '{}'); } catch (e) {} if (t.sinif) S.sinif = t.sinif; if (t.goster) S.goster = t.goster; })();

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
  /* Zaman farkı sunucu saatine göre hesaplanır (bu bilgisayarın saati yanlış olsa da doğru çıkar) */
  function once(t) {
    var s = Math.max(0, Math.round((S.simdi || Date.now() / 1000) - t));
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
    sekme(/^#ayarlar$/.test(location.hash) ? 'ayarlar' : /^#ogrenciler$/.test(location.hash) ? 'ogrenciler' : /^#rapor$/.test(location.hash) ? 'rapor' : 'sinif');
    setInterval(function () { if ((S.sekme === 'sinif' || S.sekme === 'ogrenciler' || S.secili) && !document.hidden) yenile(); }, 3000);
    setInterval(function () { if (S.sekme === 'rapor' && !document.hidden) rapor(); }, 30000);
    uygulamaYukle(S.uyg).then(function () { S.adimMap = null; onbellek = {}; Object.keys(S.kartlar).forEach(function (k) { S.kartlar[k].removeAttribute('data-robot'); }); ciz(); listeCiz(); raporCiz(); }).catch(function () {});
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
    if (ad === 'sinif' || ad === 'ogrenciler') yenile();
    if (ad === 'rapor') { yenile(); rapor(); }
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

  /* ---------- ortak yardımcılar ---------- */
  var TERCIH = 'afi-panel';
  function tercihYaz() { try { localStorage.setItem(TERCIH, JSON.stringify({ sinif: S.sinif, goster: S.goster })); } catch (e) {} }
  /* Bir kutunun içeriğini yalnızca gerçekten değiştiyse yeniler: 3 saniyede bir gelen veri ekranı titretmez, kaydırma yerinde kalır. */
  var onbellek = {};
  function degis(id, html) { if (onbellek[id] === html) return false; onbellek[id] = html; $(id).innerHTML = html; return true; }
  function yaz(dugum, metin) { metin = String(metin == null ? '' : metin); if (dugum.textContent !== metin) dugum.textContent = metin; }
  function dk(sn) { var d = Math.round((sn || 0) / 60); return d < 60 ? d + ' dk' : Math.floor(d / 60) + ' sa ' + (d % 60) + ' dk'; }
  function gorulme(o) { return o.cevrimici ? 'bağlı' : o.son ? once(o.son) : 'hiç girmedi'; }
  function tarih(gun) { return String(gun || '').split('-').reverse().join('.'); }
  function adimAdi(id) {
    if (!S.adimMap && window.COURSE) {
      S.adimMap = {};
      window.COURSE.chapters.forEach(function (ch) { ch.lessons.forEach(function (l, li) { l.steps.forEach(function (st, si) {
        S.adimMap[st.id] = ch.num + '. ' + ch.name.tr + ' · ' + (l.title && l.title.tr || ('Ders ' + (li + 1))) + ' · Adım ' + (si + 1); }); }); });
    }
    return S.adimMap && S.adimMap[id] || id || '—';
  }
  /* Takılma: bağlı, bu adımı daha önce başarmamış ve ya 3+ kez üst üste hata almış ya da 8 dakikadır aynı adımda (boşta değilken). */
  function takildi(o) {
    if (!o.cevrimici || o.adim_yildiz) return '';
    if ((o.adim_hata || 0) >= 3) return o.adim_hata + ' kez hata aldı';
    var sn = o.adim_bas ? S.simdi - o.adim_bas : 0;
    if (sn > 480 && (o.bos || 0) < 180) return dk(sn) + '\'dır aynı adımda';
    return '';
  }
  function yardimGerek(o) { return !!(o.yardim || takildi(o)); }
  function sinifUygun(o) { return S.sinif === '*' || (S.sinif === '-' ? !o.kayit : S.sinif === '~' ? (o.kayit && !o.sinif) : (o.kayit && o.sinif === S.sinif)); }
  function sinifSecenekleri() {
    var sinifsiz = S.ogr.some(function (o) { return o.kayit && !o.sinif; }), numarasiz = S.ogr.some(function (o) { return !o.kayit; });
    var sec = [['*', 'Tüm sınıflar']].concat(S.siniflar.map(function (x) { return [x, x]; }));
    if (sinifsiz && S.siniflar.length) sec.push(['~', 'Sınıfı yazılmamış']);
    if (numarasiz) sec.push(['-', 'Numarasızlar']);
    if (!sec.some(function (x) { return x[0] === S.sinif; })) S.sinif = '*';
    var html = sec.map(function (x) { return '<option value="' + esc(x[0]) + '"' + (x[0] === S.sinif ? ' selected' : '') + '>' + esc(x[1]) + '</option>'; }).join('');
    if (onbellek.sinifSec !== html) { onbellek.sinifSec = html; document.querySelectorAll('[data-sinifsec]').forEach(function (e) { e.innerHTML = html; }); }
    degis('sinifListe', S.siniflar.map(function (x) { return '<option value="' + esc(x) + '">'; }).join(''));
  }
  document.querySelectorAll('[data-sinifsec]').forEach(function (e) {
    e.onchange = function () { S.sinif = this.value; onbellek.sinifSec = null; tercihYaz(); sinifSecenekleri(); ciz(); listeCiz(); if (S.sekme === 'rapor') rapor(); };
  });

  /* ---------- sınıf: canlı izleme ---------- */
  function yenile() {
    if (!S.ben) return Promise.resolve();
    return api('sinif?uygulama=' + encodeURIComponent(S.uyg)).then(function (c) {
      S.ogr = c.ogrenciler; S.simdi = c.simdi; S.siniflar = c.siniflar || []; S.kip = c.kip || 'serbest'; S.ses = c.ses || 'acik'; S.cihaz = c.cihaz || { bagli: 0, misafir: 0 };
      var u = c.uygulamalar || [], sec = $('uygSec');
      sec.hidden = u.length < 2;
      if (u.length && !u.some(function (x) { return x.uygulama === S.uyg; })) S.uyg = u[0].uygulama;
      $('uygAcBtn').href = '/' + S.uyg + '/';
      degis('uygSec', u.map(function (x) { return '<option value="' + esc(x.uygulama) + '"' + (x.uygulama === S.uyg ? ' selected' : '') + '>' + esc(x.ad) + ' ' + esc(x.surum) + '</option>'; }).join(''));
      sinifSecenekleri();
      ciz(); listeCiz();
      if (S.secili && !document.hidden) ayrinti(S.secili, true);
    }).catch(function (e) { if (e.kod === 401) location.reload(); });
  }
  $('uygSec').onchange = function () { S.uyg = this.value; S.adimMap = null; uygulamaYukle(S.uyg); yenile(); };
  $('ara').oninput = ciz;
  $('gosterSec').addEventListener('click', function (e) {
    var b = e.target.closest('[data-goster]'); if (!b) return;
    S.goster = b.getAttribute('data-goster'); tercihYaz(); ciz();
  });
  function kartYap(o) {
    var el = document.createElement('button');
    el.className = 'ogr'; el.type = 'button'; el.setAttribute('data-anahtar', o.anahtar);
    el.innerHTML = '<span class="res"></span><b class="ad"></b><small class="kim"></small><span class="rozetler"></span><i class="sesik" title="Sesi kapalı">🔇</i><i class="nokta-d"></i>' +
      '<span class="adim"></span><span class="alt"><span class="hap"></span><span class="sayac"></span><span class="yz"></span></span>' +
      '<span class="alt alt2"><small class="pc"></small><small class="son"></small></span>';
    el.p = {}; ['res', 'ad', 'kim', 'rozetler', 'sesik', 'nokta-d', 'adim', 'hap', 'sayac', 'yz', 'pc', 'son'].forEach(function (k) { el.p[k] = el.querySelector('.' + k); });
    return el;
  }
  /* Kart yerinde güncellenir (baştan çizilmez): kartlar zıplamaz, resimler titremez. */
  function kartGuncelle(el, o) {
    var p = el.p, tk = takildi(o), bosta = o.cevrimici && (o.bos || 0) >= 180;
    var sinifi = (o.cevrimici ? '' : ' kapali') + (o.yardim ? ' yardim' : tk ? ' takildi' : '') + (o.anahtar === S.secili ? ' secili' : '');
    if (el.className !== 'ogr' + sinifi) el.className = 'ogr' + sinifi;
    if (el.getAttribute('data-robot') !== (o.robot || 'afi') || (!p.res.firstChild && window.ROBOTS)) { el.setAttribute('data-robot', o.robot || 'afi'); p.res.innerHTML = avatar(o.robot); }
    yaz(p.ad, o.ad);
    yaz(p.kim, o.kayit ? 'No ' + o.no + (o.sinif ? ' · ' + o.sinif : '') : 'numarasız');
    p.kim.className = 'kim' + (o.kayit ? '' : ' yok');
    var roz = (o.yardim ? '<span class="rz el" title="Yardım istedi">✋ yardım istiyor</span>' : '') + (!o.yardim && tk ? '<span class="rz tk" title="' + esc(tk) + '">⚠ takıldı</span>' : '') +
      (o.cakisma ? '<span class="rz ck" title="Aynı ad ve robotla iki ayrı bilgisayardan giriş var; kayıtları karışabilir. Numara verin.">⚠ aynı adla 2 bilgisayar</span>' : '');
    if (p.rozetler.innerHTML !== roz) p.rozetler.innerHTML = roz;
    p['nokta-d'].className = 'nokta-d' + (o.cevrimici ? ' acik' : '');
    p.sesik.hidden = o.ses !== 'kapali';
    yaz(p.adim, o.son ? (o.adim_ad || o.adim || '—') : 'Henüz hiç girmedi');
    p.adim.title = o.adim_ad || '';
    var durum = !o.cevrimici ? '' : bosta ? 'bosta' : (o.durum || 'hazir');
    yaz(p.hap, !o.cevrimici ? (o.son ? 'bağlı değil' : '—') : bosta ? dk(o.bos) + ' hareketsiz' : (DURUM[o.durum] || 'Düşünüyor'));
    if (p.hap.className !== 'hap ' + durum) p.hap.className = 'hap ' + durum;
    var sn = o.cevrimici && o.adim_bas ? S.simdi - o.adim_bas : 0;
    yaz(p.sayac, o.cevrimici ? 'bu adımda ' + dk(sn) + (o.adim_hata ? ' · ' + o.adim_hata + ' hata' : '') : '');
    p.sayac.className = 'sayac' + (tk ? ' kotu' : '');
    yaz(p.yz, '★ ' + (o.yildiz || 0) + ' · ' + (o.biten || 0) + ' adım');
    yaz(p.pc, [o.cihaz, o.ip].filter(Boolean).join(' · ') + (o.oturum ? ' · 👤 ' + o.oturum : ''));
    yaz(p.son, o.cevrimici ? 'bugün ' + dk(o.bugun && o.bugun.sure) : gorulme(o));
  }
  function ciz() {
    if (!S.ogr) return;
    var q = $('ara').value.trim().toLocaleLowerCase('tr');
    var sinifta = S.ogr.filter(sinifUygun);
    var liste = sinifta.filter(function (o) {
      if (S.goster === 'bagli' && !o.cevrimici) return false;
      if (S.goster === 'yardim' && !yardimGerek(o)) return false;
      return !q || (o.ad + ' ' + o.no + ' ' + o.cihaz + ' ' + o.ip + ' ' + (o.oturum || '')).toLocaleLowerCase('tr').indexOf(q) >= 0;
    });
    document.querySelectorAll('#gosterSec [data-goster]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-goster') === S.goster)); });
    var acik = sinifta.filter(function (o) { return o.cevrimici; }), yardim = sinifta.filter(yardimGerek).length;
    var bugunBiten = sinifta.reduce(function (a, o) { return a + (o.bugun ? o.bugun.basari : 0); }, 0), bugunGelen = sinifta.filter(function (o) { return o.bugun && (o.bugun.sure > 0 || o.cevrimici); }).length;
    var ort = sinifta.length ? Math.round(sinifta.reduce(function (a, o) { return a + (o.biten || 0); }, 0) / sinifta.length) : 0;
    sesDugmesi(sinifta);
    degis('ozet', '<div><b>' + acik.length + ' / ' + sinifta.length + '</b><span>şu an bağlı' + (S.cihaz && S.cihaz.misafir ? ' · ' + S.cihaz.misafir + ' bilgisayarda misafir' : '') + '</span></div>' +
      '<div class="' + (yardim ? 'dikkat' : '') + '"><b>' + yardim + '</b><span>yardım gerekiyor</span></div>' +
      '<div><b>' + bugunGelen + '</b><span>bugün gelen öğrenci</span></div><div><b>' + bugunBiten + '</b><span>bugün başarılan adım</span></div>' +
      '<div><b>' + ort + '</b><span>ortalama biten adım</span></div>');
    var kutu = $('ogrenciler'), gorulen = {};
    liste.forEach(function (o, i) {
      var el = S.kartlar[o.anahtar] || (S.kartlar[o.anahtar] = kartYap(o));
      kartGuncelle(el, o); gorulen[o.anahtar] = 1;
      if (kutu.children[i] !== el) kutu.insertBefore(el, kutu.children[i] || null);
    });
    while (kutu.children.length > liste.length) kutu.removeChild(kutu.lastChild);
    Object.keys(S.kartlar).forEach(function (k) { if (!gorulen[k]) delete S.kartlar[k]; });
    $('bosMesaj').hidden = !!liste.length;
    degis('bosMesaj', S.ogr.length ? (S.goster === 'yardim' ? 'Şu an yardım gereken öğrenci yok. 👍' : S.goster === 'bagli' ? 'Şu an bağlı öğrenci yok.' : 'Aramaya uyan öğrenci yok.')
      : 'Henüz öğrenci yok. <b>Öğrenciler</b> sekmesinden sınıf listenizi ekleyin; öğrenciler <b>Ayarlar</b> sekmesindeki adresi açıp numaralarıyla girer.');
  }
  $('ogrenciler').addEventListener('click', function (e) { var b = e.target.closest('[data-anahtar]'); if (b) ayrinti(b.getAttribute('data-anahtar')); });

  /* ---------- ses ve bilgisayar komutları ---------- */
  function seciliSinif() { return S.sinif !== '*' && S.sinif !== '-' && S.sinif !== '~' ? S.sinif : ''; }
  function sesDugmesi(sinifta) {
    var sn = seciliSinif(), kapali;
    if (sn) kapali = sinifta.length > 0 && sinifta.every(function (o) { return o.ses === 'kapali'; });
    else kapali = S.ses === 'kapali';
    var metin = (kapali ? '🔊 ' : '🔇 ') + (sn ? (kapali ? 'Bu sınıfın sesini aç' : 'Bu sınıfın sesini kapat') : (kapali ? 'Sesleri aç' : 'Sesleri kapat'));
    yaz($('sesBtn'), metin);
    $('sesBtn').className = kapali ? 'kapali' : '';
    $('sesBtn').setAttribute('data-deger', kapali ? 'acik' : 'kapali');
  }
  $('sesBtn').onclick = function () {
    var deger = this.getAttribute('data-deger'), sn = seciliSinif();
    api('ses', { hedef: sn ? 'sinif:' + sn : '*', deger: deger }).then(function () {
      toast(deger === 'kapali' ? 'Ses kapatıldı. Öğrenci bilgisayarlarında birkaç saniye içinde kapanır.' : 'Ses açıldı.'); return yenile();
    }).catch(function (er) { toast(er.message); });
  };
  function menuKapat() { $('pcMenu').hidden = true; $('pcMenuBtn').setAttribute('aria-expanded', 'false'); }
  $('pcMenuBtn').onclick = function (e) { e.stopPropagation(); var ac = $('pcMenu').hidden; $('pcMenu').hidden = !ac; this.setAttribute('aria-expanded', String(ac)); };
  document.addEventListener('click', function (e) { if (!e.target.closest('.menu-kap')) menuKapat(); });
  var KOMUT_ONAY = {
    'duzen-sifirla': 'Bağlı bütün bilgisayarlarda AFİ KOD ekran düzeni varsayılana dönsün mü?\n\nÖğrencilerin çalışmaları silinmez.',
    'misafir-temizle': 'Bağlı bütün bilgisayarlarda misafir çalışmaları silinsin mi?\n\nŞu an misafir olarak çalışan öğrenci de 1. adımdan başlar. Adıyla ya da numarasıyla giren öğrencilerin çalışmaları silinmez.',
    'liste-temizle': 'Bağlı bütün bilgisayarlarda "Kim kodluyor?" listesi temizlensin mi?\n\nŞu an çalışan öğrenciler giriş ekranına döner (önce çalışmaları bu sunucuya gönderilir). Öğrenci kayıtları ve yıldızlar bu sunucuda kalır.'
  };
  var KOMUT_TAMAM = { 'duzen-sifirla': 'Ekran düzeni sıfırlama gönderildi.', 'misafir-temizle': 'Misafir temizliği gönderildi.', 'liste-temizle': 'Liste temizliği gönderildi.' };
  function komut(ad, hedef, sessiz) {
    if (!sessiz && !confirm(KOMUT_ONAY[ad])) return;
    api('komut', { uygulama: S.uyg, hedef: hedef || '*', komut: ad }).then(function () { toast(KOMUT_TAMAM[ad] + ' Bağlı bilgisayarlarda birkaç saniye içinde uygulanır.'); }).catch(function (er) { toast(er.message); });
  }
  $('pcMenu').addEventListener('click', function (e) { var b = e.target.closest('[data-komut]'); if (!b) return; menuKapat(); komut(b.getAttribute('data-komut'), '*'); });

  /* ---------- öğrenci ayrıntısı ---------- */
  function ayrinti(anahtar, sessizYenile) {
    var ilk = S.secili !== anahtar || $('cekmece').hidden;
    S.secili = anahtar;
    return api('ogrenci?uygulama=' + encodeURIComponent(S.uyg) + '&anahtar=' + encodeURIComponent(anahtar)).then(function (d) {
      if (S.secili !== anahtar) return;
      var o = d.ogrenci; S.seciliO = o; S.simdi = d.simdi || S.simdi;
      if (ilk) { $('cekmece').hidden = false; $('cekmece').scrollTop = 0; ciz(); }
      degis('dAd', avatar(o.robot).replace('<img', '<img style="width:40px;height:40px;vertical-align:middle;margin-right:8px"') + esc(o.ad));
      degis('dBilgi', (o.kayit ? '<b>No ' + esc(o.no) + '</b>' + (o.sinif ? ' · ' + esc(o.sinif) : '') : '<b class="kotu">numarasız</b> (adını kendisi yazdı)') + ' · ' +
        (o.cevrimici ? '<b style="color:var(--ok)">bağlı</b>' : o.son ? 'son görülme ' + once(o.son) : 'henüz hiç girmedi') +
        (o.cihaz || o.ip ? ' · ' + esc([o.cihaz, o.ip, o.oturum ? 'Windows kullanıcısı: ' + o.oturum : (o.istemci ? '' : 'tarayıcıdan bağlı')].filter(Boolean).join(' · ')) : '') +
        (o.notu ? '<br>Not: ' + esc(o.notu) : ''));
      degis('dIslem', (o.yardim ? '<button class="ana" data-is="yardim">✋ Yardım ettim (kapat)</button>' : '') +
        (o.ses === 'kapali' ? '<button data-is="sesac">🔊 Sesini aç</button>' : '<button data-is="seskapat">🔇 Sesini kapat</button>') +
        (o.cevrimici ? '<button data-is="duzen" title="Bu öğrencinin ekran düzenini varsayılana döndürür">↺ Ekran düzenini sıfırla</button>' : '') +
        (o.kayit ? '<button data-is="duzenle">✎ Düzenle</button><button data-is="birlestir">⇄ Başka kayıtla birleştir</button><button data-is="sifirla">↺ İlerlemeyi sıfırla</button><button class="tehlike-ince" data-is="sil">🗑 Sil</button>'
          : '<button class="ana" data-is="nover">＃ Numara ver</button><button data-is="birlestir">⇄ Listedeki öğrenciyle birleştir</button><button class="tehlike-ince" data-is="nsil">🗑 Sil</button>'));
      var tk = takildi(o), sn = o.cevrimici && o.adim_bas ? S.simdi - o.adim_bas : 0;
      degis('dUyari', (o.yardim ? '<p class="uyari">✋ <b>Yardım istiyor</b> (' + once(o.yardim) + ').</p>' : '') + (tk ? '<p class="uyari">⚠ <b>Takılmış olabilir:</b> ' + esc(tk) + '.</p>' : '') +
        (o.cakisma ? '<p class="uyari">⚠ Aynı ad ve robotla iki ayrı bilgisayardan giriş yapıldı; iki öğrencinin kaydı karışıyor olabilir. Birine <b>numara verin</b>.</p>' : ''));
      var top = Object.keys(d.adimlar || {}).reduce(function (a, k) { a.h += d.adimlar[k].hata; a.b += d.adimlar[k].basari; return a; }, { h: 0, b: 0 });
      var bugun = (d.gunler || []).filter(function (g) { return g.gun === new Date(S.simdi * 1000).toLocaleDateString('sv-SE'); })[0] || { sure: 0, basari: 0, hata: 0 };
      degis('dOzet', '<div><b>' + (o.biten || 0) + '</b><span>biten adım · ★ ' + (o.yildiz || 0) + '</span></div><div><b>' + dk(o.sure) + '</b><span>toplam çalışma</span></div>' +
        '<div><b>' + (d.gunler || []).length + '</b><span>geldiği gün</span></div><div><b>' + (top.b + top.h ? Math.round(100 * top.b / (top.b + top.h)) + '%' : '—') + '</b><span>başarılı deneme oranı (' + top.b + ' / ' + (top.b + top.h) + ')</span></div>' +
        '<div><b>' + dk(bugun.sure) + '</b><span>bugün · ' + bugun.basari + ' başarı, ' + bugun.hata + ' hata</span></div>' +
        '<div><b>' + (o.cevrimici ? dk(sn) : '—') + '</b><span>' + (o.cevrimici ? 'bu adımda' + (o.adim_hata ? ' · ' + o.adim_hata + ' hata' : '') : 'şu an bağlı değil') + '</span></div>');
      var b = adimlar();
      degis('dBolumler', '<p class="not">Şu an: <b>' + esc(o.adim_ad || adimAdi(o.adim)) + '</b>' + (o.cevrimici ? ' — ' + esc(DURUM[o.durum] || '') : '') + '</p>' + (b ? b.map(function (x) {
        var n = x.adimlar.length, k = x.adimlar.filter(function (s) { return d.yildizlar[s.id]; }).length, y = x.adimlar.reduce(function (a, s) { return a + (d.yildizlar[s.id] || 0); }, 0);
        return '<div class="bolum"><span>' + x.ch.num + '. ' + esc(x.ch.name.tr) + '</span><span class="cubuk"><i style="width:' + Math.round(100 * k / n) + '%"></i></span><span>' + k + ' / ' + n + '</span><span>★ ' + y + '</span></div>';
      }).join('') : '<p class="not">Bölüm listesi yükleniyor...</p>'));
      var zor = Object.keys(d.adimlar || {}).map(function (k) { return { adim: k, hata: d.adimlar[k].hata, basari: d.adimlar[k].basari, son: d.adimlar[k].son }; })
        .filter(function (x) { return x.hata; }).sort(function (a, c) { return c.hata - a.hata; }).slice(0, 8);
      degis('dZor', zor.length ? '<table class="tablo"><thead><tr><th>Adım</th><th class="sayi">Hatalı deneme</th><th>Sonuç</th><th>Son deneme</th></tr></thead><tbody>' + zor.map(function (x) {
        return '<tr><td>' + esc(adimAdi(x.adim)) + '</td><td class="sayi">' + x.hata + '</td><td>' + (d.yildizlar[x.adim] ? '<span class="hap basarili">başardı ★' + d.yildizlar[x.adim] + '</span>' : '<span class="hap hata">henüz başaramadı</span>') + '</td><td>' + once(x.son) + '</td></tr>';
      }).join('') + '</tbody></table>' : '<p class="not">Hiç hatalı denemesi yok.</p>');
      degis('dHatalar', (d.hatalar || []).map(function (h) { return '<li><b>' + h.sayi + ' kez</b><span>' + esc(h.mesaj) + '</span></li>'; }).join('') || '<li>Henüz hata kaydı yok.</li>');
      degis('dGunler', (d.gunler || []).length ? '<table class="tablo"><thead><tr><th>Tarih</th><th>Saat</th><th class="sayi">Çalışma</th><th class="sayi">Başarılı</th><th class="sayi">Hatalı</th></tr></thead><tbody>' + d.gunler.slice(0, 12).map(function (g) {
        var s1 = g.ilk ? new Date(g.ilk * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : '', s2 = g.son ? new Date(g.son * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : '';
        return '<tr><td>' + tarih(g.gun) + '</td><td>' + s1 + ' – ' + s2 + '</td><td class="sayi">' + dk(g.sure) + '</td><td class="sayi">' + g.basari + '</td><td class="sayi">' + g.hata + '</td></tr>';
      }).join('') + '</tbody></table>' : '<p class="not">Henüz hiç girmedi.</p>');
      var an = d.anlik;
      yaz($('dAnlikZaman'), an && an.guncelleme ? '(' + adimAdi(an.adim) + ', ' + once(an.guncelleme) + ')' : '');
      yaz($('dKod'), an && an.kod ? an.kod : 'Henüz kod gelmedi.');
      if (!sessizYenile || !S.wsAnahtar || S.wsAnahtar !== anahtar + (an && an.guncelleme)) { S.wsAnahtar = anahtar + (an && an.guncelleme); bloklariCiz(an); }
      degis('dOlaylar', d.olaylar.map(function (x) {
        var ay = {}; try { ay = JSON.parse(x.ayrinti) || {}; } catch (e) {}
        var isaret = x.tur === 'basari' ? '✓ ' + (ay.yildiz || '') + '★' : x.tur === 'hata' ? '✗' : x.tur === 'yardim' ? '✋' : x.tur === 'sifirla' ? '↺' : '·';
        return '<li><span>' + new Date(x.zaman * 1000).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + '</span><b style="color:' + (x.tur === 'basari' ? 'var(--ok)' : x.tur === 'hata' ? 'var(--bad)' : 'var(--ink-2)') + '">' +
          isaret + '</b><span>' + (x.tur === 'sifirla' ? '' : esc(adimAdi(x.adim))) + (ay.mesaj ? ' — ' + esc(ay.mesaj) : x.tur === 'yardim' ? ' — yardım istedi' : x.tur === 'yardim-iptal' ? ' — yardım isteğinden vazgeçti' : x.tur === 'sifirla' ? 'Kendi çalışmalarını sildi, baştan başladı' : '') + '</span></li>';
      }).join('') || '<li>Henüz olay yok.</li>');
    }).catch(function (e) { if (!sessizYenile) toast(e.message); else if (e.kod === 404) cekmeceKapat(); });
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
  function cekmeceKapat() { $('cekmece').hidden = true; S.secili = null; S.seciliO = null; if (S.ws) { try { S.ws.dispose(); } catch (e) {} S.ws = null; } ciz(); }
  $('dKapat').onclick = cekmeceKapat;
  $('dMesajBtn').onclick = function () {
    var m = $('dMesaj').value.trim(); if (!m || !S.secili) return;
    api('mesaj', { hedef: S.secili, metin: m }).then(function () { $('dMesaj').value = ''; toast('Mesaj gönderildi.'); }).catch(function (e) { toast(e.message); });
  };
  $('dMesaj').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('dMesajBtn').click(); });
  $('dIslem').addEventListener('click', function (e) {
    var b = e.target.closest('[data-is]'), o = S.seciliO; if (!b || !o) return;
    var is = b.getAttribute('data-is');
    if (is === 'yardim') api('yardim-kapat', { uygulama: S.uyg, anahtar: o.anahtar }).then(function () { toast('Yardım isteği kapatıldı.'); return yenile(); }).catch(function (er) { toast(er.message); });
    if (is === 'duzenle') duzenleAc(o);
    if (is === 'seskapat' || is === 'sesac') {
      var deger = is === 'seskapat' ? 'kapali' : (S.ses === 'kapali' ? 'acik' : null);
      api('ses', { uygulama: S.uyg, hedef: o.anahtar, deger: deger }).then(function () { toast(o.ad + (is === 'seskapat' ? ' için ses kapatıldı.' : ' için ses açıldı.')); return yenile(); }).catch(function (er) { toast(er.message); });
    }
    if (is === 'duzen') komut('duzen-sifirla', o.anahtar, true);
    if (is === 'birlestir') birlestirAc(o);
    if (is === 'sifirla') sifirla(o);
    if (is === 'sil') kayitSil(o);
    if (is === 'nover') numaraVer(o.anahtar);
    if (is === 'nsil') numarasizSil(o);
  });

  /* ---------- mesaj ---------- */
  $('herkeseMesajBtn').onclick = function () {
    $('mesajHedef').innerHTML = '<option value="*">Gördüğüm bütün öğrenciler</option>' + S.siniflar.map(function (x) { return '<option value="sinif:' + esc(x) + '"' + (x === S.sinif ? ' selected' : '') + '>Yalnızca ' + esc(x) + '</option>'; }).join('');
    $('mesajModal').hidden = false; $('mesajForm').metin.focus();
  };
  $('mesajForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this;
    api('mesaj', { hedef: f.hedef.value || '*', metin: f.metin.value }).then(function () { f.metin.value = ''; $('mesajModal').hidden = true; toast('Mesaj gönderildi.'); }).catch(function (er) { toast(er.message); });
  });
  ['mesajModal', 'kayitModal', 'birModal'].forEach(function (id) {
    $(id).addEventListener('mousedown', function (e) { if (e.target === this || e.target.hasAttribute('data-kapat')) this.hidden = true; });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var acik = ['mesajModal', 'kayitModal', 'birModal'].filter(function (id) { return !$(id).hidden; });
    if (acik.length) { acik.forEach(function (id) { $(id).hidden = true; }); return; }
    if (!$('cekmece').hidden) cekmeceKapat();
  });

  /* ---------- öğrenciler: sınıf listesi, numaralar, düzenleme ---------- */
  function listeCiz() {
    if (!S.ogr || S.sekme !== 'ogrenciler') return;
    var q = $('listeAra').value.trim().toLocaleLowerCase('tr');
    var kayitli = S.ogr.filter(function (o) { return o.kayit && (S.sinif === '-' ? false : sinifUygun(o)) && (!q || (o.ad + ' ' + o.no + ' ' + o.sinif).toLocaleLowerCase('tr').indexOf(q) >= 0); });
    degis('listeGovde', kayitli.map(function (o) {
      return '<tr data-ac="' + esc(o.anahtar) + '"><td><b class="no">' + esc(o.no) + '</b></td><td>' + esc(o.ad) + '</td><td>' + esc(o.sinif || '—') + '</td><td class="sayi">' + (o.biten || 0) + '</td><td class="sayi">' + (o.yildiz || 0) + '</td><td>' +
        (o.cevrimici ? '<span class="hap basarili">bağlı</span>' : esc(gorulmeKaba(o))) + '</td><td class="soluk">' + esc(o.notu || '') + '</td><td class="islem"><button class="ince" data-duzenle="' + o.kayit + '">Düzenle</button> <button class="ince" data-sil="' + o.kayit + '">Sil</button></td></tr>';
    }).join(''));
    $('listeBos').hidden = !!kayitli.length || S.sinif === '-';
    yaz($('listeBos'), S.ogr.some(function (o) { return o.kayit; }) ? 'Bu sınıfta ya da aramada öğrenci yok.' : 'Listede henüz öğrenci yok. Sağdaki kutudan ekleyin.');
    var numarasiz = S.ogr.filter(function (o) { return !o.kayit; });
    $('numarasizKutu').hidden = !numarasiz.length;
    degis('numarasizGovde', numarasiz.map(function (o) {
      return '<tr data-ac="' + esc(o.anahtar) + '"><td>' + esc(o.ad) + (o.cakisma ? ' <span class="rz ck">⚠ 2 bilgisayar</span>' : '') + '</td><td class="soluk">' + esc([o.cihaz, o.ip].filter(Boolean).join(' · ')) + '</td><td class="sayi">' + (o.biten || 0) + '</td><td class="sayi">' + (o.yildiz || 0) + '</td><td>' +
        (o.cevrimici ? '<span class="hap basarili">bağlı</span>' : esc(gorulmeKaba(o))) + '</td><td class="islem"><button class="ana kucuk" data-nover="' + esc(o.anahtar) + '">Numara ver</button> <button class="ince" data-bir="' + esc(o.anahtar) + '">Birleştir</button> <button class="ince" data-nsil="' + esc(o.anahtar) + '">Sil</button></td></tr>';
    }).join(''));
    document.querySelectorAll('input[name="kip"]').forEach(function (r) { r.checked = r.value === S.kip; });
  }
  /* Tablo her 3 saniyede yeniden çizilmesin diye kaba zaman: dakika ve üstü */
  function gorulmeKaba(o) {
    if (!o.son) return 'hiç girmedi';
    var s = Math.max(0, S.simdi - o.son);
    return s < 3600 ? 'bugün, az önce' : s < 86400 ? Math.round(s / 3600) + ' saat önce' : new Date(o.son * 1000).toLocaleDateString('tr-TR');
  }
  function ogrBul(anahtar) { return S.ogr.filter(function (o) { return o.anahtar === anahtar; })[0]; }
  function kayitBul(id) { return S.ogr.filter(function (o) { return o.kayit === +id; })[0]; }
  $('listeAra').oninput = listeCiz;
  function tabloTik(e) {
    var t = e.target, x;
    if ((x = t.closest('[data-duzenle]'))) return duzenleAc(kayitBul(x.getAttribute('data-duzenle')));
    if ((x = t.closest('[data-sil]'))) return kayitSil(kayitBul(x.getAttribute('data-sil')));
    if ((x = t.closest('[data-nover]'))) return numaraVer(x.getAttribute('data-nover'));
    if ((x = t.closest('[data-bir]'))) return birlestirAc(ogrBul(x.getAttribute('data-bir')));
    if ((x = t.closest('[data-nsil]'))) return numarasizSil(ogrBul(x.getAttribute('data-nsil')));
    if ((x = t.closest('[data-ac]'))) ayrinti(x.getAttribute('data-ac'));
  }
  $('listeTablo').addEventListener('click', tabloTik); $('numarasizTablo').addEventListener('click', tabloTik);
  $('ekleForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this, v = formVeri(f);
    if (!v.no) delete v.no;
    api('kayitlar', v).then(function (c) {
      formHata(f); f.ad.value = ''; f.no.value = ''; f.ad.focus();
      toast(c.kimlik.ad + ' eklendi. Numarası: ' + c.kimlik.no); return yenile();
    }).catch(function (er) { formHata(f, er); });
  });
  $('topluForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this;
    api('kayitlar/toplu', formVeri(f)).then(function (c) {
      var h = c.hatalar || [];
      formHata(f, h.length ? new Error(h.length + ' satır eklenemedi: ' + h.map(function (x) { return x.satir + ' (' + x.hata + ')'; }).join('; ')) : null);
      f.metin.value = h.map(function (x) { return x.satir; }).join('\n');
      toast(c.eklenen.length + ' öğrenci eklendi ve numaraları verildi.'); return yenile();
    }).catch(function (er) { formHata(f, er); });
  });
  function duzenleAc(o) {
    if (!o) return;
    var f = $('kayitForm'); f.id.value = o.kayit; f.ad.value = o.ad; f.sinif.value = o.sinif || ''; f.no.value = o.no; f.notu.value = o.notu || ''; formHata(f);
    $('kayitModal').hidden = false; f.ad.focus();
  }
  $('kayitForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this, v = formVeri(f); v.id = +v.id;
    api('kayitlar', v).then(function () { $('kayitModal').hidden = true; toast('Kaydedildi.'); return yenile(); }).catch(function (er) { formHata(f, er); });
  });
  function kayitSil(o) {
    if (!o || !confirm(o.ad + ' (No ' + o.no + ') listeden silinsin mi?\n\nBütün yıldızları ve çalışmaları da silinir. Bu işlem geri alınamaz.')) return;
    api('kayitlar?id=' + o.kayit, null, 'DELETE').then(function () { if (S.secili === o.anahtar) cekmeceKapat(); toast(o.ad + ' silindi.'); return yenile(); }).catch(function (er) { toast(er.message); });
  }
  function numarasizSil(o) {
    if (!o || !confirm(o.ad + ' adlı numarasız kayıt silinsin mi?\n\nBütün yıldızları ve çalışmaları da silinir.')) return;
    api('ogrenci?uygulama=' + encodeURIComponent(S.uyg) + '&anahtar=' + encodeURIComponent(o.anahtar), null, 'DELETE').then(function () { if (S.secili === o.anahtar) cekmeceKapat(); toast('Silindi.'); return yenile(); }).catch(function (er) { toast(er.message); });
  }
  function sifirla(o) {
    if (!o || !confirm(o.ad + ' adlı öğrencinin bütün yıldızları ve dizdiği bloklar silinsin mi?\n\nÖğrenci 1. adımdan yeniden başlar. Bu işlem geri alınamaz.')) return;
    api('kayitlar/sifirla', { uygulama: S.uyg, anahtar: o.anahtar }).then(function () { toast('İlerleme sıfırlandı.'); return yenile(); }).catch(function (er) { toast(er.message); });
  }
  function numaraVer(anahtar) {
    var sinif = S.sinif !== '*' && S.sinif !== '-' && S.sinif !== '~' ? S.sinif : '';
    api('kayitlar/numara-ver', { uygulama: S.uyg, anahtar: anahtar, sinif: sinif }).then(function (c) {
      var k = c.verilen[0]; if (S.secili === anahtar) S.secili = '#' + k.kayit;
      toast(k.ad + ' için numara: ' + k.no + '. Numara öğrencinin ekranında da görünür.'); return yenile();
    }).catch(function (er) { toast(er.message); });
  }
  $('hepsineNoBtn').onclick = function () {
    var n = S.ogr.filter(function (o) { return !o.kayit; }).length;
    if (!n || !confirm(n + ' numarasız öğrencinin hepsine numara verilsin mi?\n\nİlerlemeleri korunur. Aynı kişi iki kez görünüyorsa önce "Birleştir" ile tek kayıt yapın.')) return;
    api('kayitlar/numara-ver', { uygulama: S.uyg, anahtar: '*' }).then(function (c) { toast(c.verilen.length + ' öğrenciye numara verildi.'); return yenile(); }).catch(function (er) { toast(er.message); });
  };
  function birlestirAc(o) {
    if (!o) return;
    var f = $('birForm'), adaylar = S.ogr.filter(function (x) { return x.kayit && x.anahtar !== o.anahtar; });
    if (!adaylar.length) { toast('Birleştirilecek başka bir listeli öğrenci yok. Önce listeye ekleyin ya da "Numara ver" deyin.'); return; }
    f.setAttribute('data-kaynak', o.anahtar); yaz($('birKaynak'), o.ad + (o.kayit ? ' (No ' + o.no + ')' : ' (numarasız)'));
    var ayni = ortakAd(o.ad);
    f.hedef.innerHTML = '<option value="">Seçin...</option>' + adaylar.map(function (x) { return '<option value="' + x.kayit + '"' + (ortakAd(x.ad) === ayni ? ' selected' : '') + '>' + esc(x.ad) + ' — No ' + esc(x.no) + (x.sinif ? ' · ' + esc(x.sinif) : '') + '</option>'; }).join('');
    formHata(f); $('birModal').hidden = false;
  }
  function ortakAd(ad) { return String(ad || '').toLocaleLowerCase('tr').replace(/\s+/g, ' ').trim(); }
  $('birForm').addEventListener('submit', function (e) {
    e.preventDefault(); var f = this, kaynak = f.getAttribute('data-kaynak');
    api('kayitlar/birlestir', { kaynak: kaynak, hedef: +f.hedef.value }).then(function () {
      $('birModal').hidden = true; if (S.secili === kaynak) S.secili = '#' + f.hedef.value;
      toast('Kayıtlar birleştirildi.'); return yenile();
    }).catch(function (er) { formHata(f, er); });
  });
  document.querySelectorAll('input[name="kip"]').forEach(function (r) {
    r.onchange = function () {
      var kip = this.value, numarasiz = S.ogr.filter(function (o) { return !o.kayit && o.cevrimici; }).length;
      if (kip === 'numara' && numarasiz && !confirm('Şu an bağlı ' + numarasiz + ' numarasız öğrenci var. Yalnızca numarayla girişi açarsanız giriş ekranına dönerler ve numara yazmaları gerekir.\n\nÖnce "Hepsine numara ver" demek ister misiniz? Yine de açmak için Tamam\'a basın.')) { listeCiz(); return; }
      api('giris-kipi', { kip: kip }).then(function () { S.kip = kip; toast(kip === 'numara' ? 'Artık yalnızca numarayla giriliyor.' : 'Serbest giriş açıldı.'); }).catch(function (er) { toast(er.message); listeCiz(); });
    };
  });
  /* Numara kartları: seçili sınıfın öğrencileri için adı ve numarası yazan, kesilip dağıtılabilen kartlar */
  $('kartBtn').onclick = function () {
    var liste = S.ogr.filter(function (o) { return o.kayit && (S.sinif === '-' ? false : sinifUygun(o)); });
    if (!liste.length) { toast('Yazdırılacak öğrenci yok.'); return; }
    $('yazdir').innerHTML = liste.map(function (o) {
      return '<div class="nkart"><div class="nk-ust"><span class="logo">AF<span class="i"><span class="nokta"></span></span></span><span class="etiket">KOD</span><small>' + esc(o.sinif || '') + '</small></div>' +
        '<div class="nk-ad">' + esc(o.ad) + '</div><div class="nk-no">' + esc(o.no) + '</div><div class="nk-alt">Öğrenci numaran. Hangi bilgisayara oturursan otur, bu numarayla gir; kaldığın yerden devam edersin.</div></div>';
    }).join('');
    setTimeout(function () { window.print(); }, 50);
  };

  /* ---------- rapor ---------- */
  function rapor() {
    api('rapor?uygulama=' + encodeURIComponent(S.uyg) + '&sinif=' + encodeURIComponent(S.sinif)).then(function (r) { S.rapor = r; S.simdi = r.simdi; raporCiz(); }).catch(function (e) { toast(e.message); });
  }
  var SIRA = {
    no: function (o) { return +o.no || 1e12; }, ad: function (o) { return ortakAd(o.ad); }, sinif: function (o) { return ortakAd(o.sinif); }, biten: function (o) { return o.biten || 0; },
    yildiz: function (o) { return o.yildiz || 0; }, sure: function (o) { return o.sure || 0; }, gun: function (o) { return o.toplam.gun; }, basari: function (o) { return o.toplam.basari; },
    hata: function (o) { return o.toplam.hata; }, bugun: function (o) { return o.bugun.sure; }, son: function (o) { return o.son || 0; }
  };
  function raporCiz() {
    var r = S.rapor; if (!r) return;
    var f = SIRA[S.raporSira.a] || SIRA.ad, yon = S.raporSira.yon;
    var liste = r.ogrenciler.slice().sort(function (a, b) { var x = f(a), y = f(b); return (x < y ? -1 : x > y ? 1 : 0) * yon; });
    var n = liste.length, gelen = liste.filter(function (o) { return o.toplam.gun; }).length, topSure = liste.reduce(function (a, o) { return a + (o.sure || 0); }, 0);
    var tb = liste.reduce(function (a, o) { return a + o.toplam.basari; }, 0), th = liste.reduce(function (a, o) { return a + o.toplam.hata; }, 0);
    degis('raporOzet', '<div><b>' + n + '</b><span>öğrenci</span></div><div><b>' + gelen + '</b><span>en az bir kez girmiş</span></div>' +
      '<div><b>' + (n ? Math.round(liste.reduce(function (a, o) { return a + (o.biten || 0); }, 0) / n) : 0) + '</b><span>ortalama biten adım</span></div>' +
      '<div><b>' + dk(gelen ? topSure / gelen : 0) + '</b><span>öğrenci başına çalışma</span></div><div><b>' + (tb + th ? Math.round(100 * tb / (tb + th)) + '%' : '—') + '</b><span>başarılı deneme oranı</span></div>');
    document.querySelectorAll('#raporTablo th[data-sira]').forEach(function (th) { th.setAttribute('aria-sort', th.getAttribute('data-sira') === S.raporSira.a ? (yon > 0 ? 'ascending' : 'descending') : 'none'); });
    degis('raporGovde', liste.map(function (o) {
      return '<tr data-ac="' + esc(o.anahtar) + '"><td>' + (o.kayit ? '<b class="no">' + esc(o.no) + '</b>' : '<span class="soluk">numarasız</span>') + '</td><td>' + esc(o.ad) + '</td><td>' + esc(o.sinif || '—') + '</td><td class="sayi">' + (o.biten || 0) +
        '</td><td class="sayi">' + (o.yildiz || 0) + '</td><td class="sayi">' + dk(o.sure) + '</td><td class="sayi">' + o.toplam.gun + '</td><td class="sayi">' + o.toplam.basari + '</td><td class="sayi">' + o.toplam.hata +
        '</td><td class="sayi">' + (o.bugun.sure ? dk(o.bugun.sure) + ' · ' + o.bugun.basari + ' ✓' : '—') + '</td><td>' + (o.cevrimici ? '<span class="hap basarili">bağlı</span>' : esc(gorulmeKaba(o))) + '</td></tr>';
    }).join('') || '<tr><td colspan="11" class="soluk">Bu sınıfta öğrenci yok.</td></tr>');
    degis('zorGovde', r.zor_adimlar.map(function (a) {
      return '<tr><td>' + esc(adimAdi(a.adim)) + '</td><td class="sayi">' + a.deneyen + '</td><td class="sayi">' + a.basaran + '</td><td class="sayi">' + a.hata + '</td><td class="sayi"><b>' + (a.hata / Math.max(1, a.deneyen)).toFixed(1) + '</b></td></tr>';
    }).join('') || '<tr><td colspan="5" class="soluk">Henüz hatalı deneme kaydı yok.</td></tr>');
    degis('gunGovde', r.gunler.map(function (g) {
      return '<tr><td>' + tarih(g.gun) + '</td><td class="sayi">' + g.ogrenci + '</td><td class="sayi">' + dk(g.sure) + '</td><td class="sayi">' + g.basari + '</td><td class="sayi">' + g.hata + '</td></tr>';
    }).join('') || '<tr><td colspan="5" class="soluk">Henüz kayıt yok.</td></tr>');
  }
  $('raporTablo').addEventListener('click', function (e) {
    var th = e.target.closest('th[data-sira]'), tr = e.target.closest('[data-ac]');
    if (th) { var a = th.getAttribute('data-sira'); S.raporSira = { a: a, yon: S.raporSira.a === a ? -S.raporSira.yon : (a === 'ad' || a === 'sinif' || a === 'no' ? 1 : -1) }; raporCiz(); }
    else if (tr) ayrinti(tr.getAttribute('data-ac'));
  });
  $('csvBtn').onclick = function (e) { e.preventDefault(); location.href = '/api/v1/disa-aktar.csv?uygulama=' + encodeURIComponent(S.uyg) + '&sinif=' + encodeURIComponent(S.sinif); };
  $('devamBtn').onclick = function (e) { e.preventDefault(); location.href = '/api/v1/devam.csv?uygulama=' + encodeURIComponent(S.uyg) + '&sinif=' + encodeURIComponent(S.sinif); };

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
    var o = prompt('Bütün öğrencilerin ilerlemeleri silinecek. Onaylamak için büyük harflerle SİL yazın:');
    if (o === null) return;
    var liste = confirm('Sınıf listesi (öğrenci adları ve numaraları) da silinsin mi?\n\nTamam: liste de silinir.\nİptal: liste ve numaralar kalır, yalnızca ilerlemeler silinir.');
    api('temizle', { onay: o.trim(), liste: liste }).then(function () { toast(liste ? 'Öğrenci verileri ve sınıf listesi silindi.' : 'İlerlemeler silindi; sınıf listesi duruyor.'); yenile(); }).catch(function (er) { toast(er.message); });
  };

  ac();
})();
