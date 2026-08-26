# CLAUDE.md

Bu depo, Autodesk 3ds Max için Python eklentileri barındırır. Her eklenti
depo kökünde kendi üst düzey Python paketi olarak yaşar.

## Alt uygulamalar

| Paket | Ne yapar | Durum |
|---|---|---|
| `corona_doctor/` | 3ds Max + Chaos Corona teşhis/onarım asistanı | Bootstrap aşaması |
| `revision_guard/` | Sahne revizyon karşılaştırma motoru (RevisionGuard) | V0.1 |

---

## Kullanıcı iletişimi (ZORUNLU)

- **Kullanıcıya verilen tüm geri dönüşler, açıklamalar, raporlar ve sorular
  Türkçe olacaktır.** Bu, sohbet yanıtlarını, `AskUserQuestion` sorularını
  ve son durum raporlarını kapsar.
- **Kod, kod yorumları, commit mesajları, docstring'ler, log satırları ve
  dosya adları İngilizce kalır.** Sadece son kullanıcıya 3ds Max arayüzünde
  veya `messageBox` içinde gösterilen metinler Türkçe olabilir.

## Git akışı (ZORUNLU)

- **Her büyük kodlama için yeni branch AÇMA.** Depoda uygulama başına tek
  bir uzun ömürlü branch kullanılır.
- **RevisionGuard'ın branch'i: `RevisionGuard`.** RevisionGuard ile ilgili
  tüm çalışma bu branch üzerinde geliştirilir ve buraya push edilir.
- **Pull request AÇMA, merge ÖNERME, merge İSTEME.** Kullanıcı branch'i
  bitince kendi bilgisayarına klonlayıp kullanacak. PR/merge hatırlatması
  yapma; sadece `git push -u origin RevisionGuard` yeterlidir.
- Kullanıcı açıkça isterse bu kural değişir; aksi hâlde sorma.

---

## Ortak teknik kurallar

Hedef ortam — sapma yok:

| Bileşen | Gereksinim |
|---|---|
| OS | Windows 10/11 x64 |
| 3ds Max | 2026.2+ |
| Python | 3.11.x (3ds Max'in gömülü runtime'ı) |
| UI | PySide6 (Qt 6.5.x) |
| Max API | `pymxs`, `qtmax` |

Yasak: MaxPlus, PySide2/Qt5, WinForms/WPF, MAXScript rollout UI.

### Bağımlılıklar

Harici Python bağımlılığı ekleme. Standart kütüphane (`hashlib`,
`dataclasses`, `enum`, `time`, …) yeterli olduğu sürece onu kullan.

### Katman kuralları

- `pymxs` **yalnızca** host sınırı modüllerinde import edilir:
  `corona_doctor/adapters/max_adapter.py` ve `revision_guard/max/`
  paketi (`scene_access.py`, `scene_edit.py`). Başka hiçbir modül
  `pymxs` import etmez.
- `qtmax` bir QWidget döndürdüğü için Qt katmanında kalır
  (`revision_guard/ui/dock.py`).
- Bu sayede `core/` katmanı 3ds Max olmadan, düz Python 3.11 ile
  import edilebilir ve `pytest` ile test edilebilir.
- `pymxs` sahne erişimi **yalnızca ana thread**'den yapılır. Worker
  thread'den sahneye dokunma.

### Hata yönetimi

Tek bir hatalı sahne nesnesi tüm taramayı çökertmemeli. Nesne başına
`try/except`, hatayı logla ve taramaya devam et.

### Loglama

- `corona_doctor` → `corona_doctor/logging/logger.py`
- `revision_guard` → 3ds Max Listener'a `[RevisionGuard]` önekiyle yazar.

Vertex/yüz başına log yazma; Listener'ı boğma.

### Testler

```bash
python3 -m pytest revision_guard/tests corona_doctor/tests
```

3ds Max içindeki gerçek doğrulama için `revision_guard` smoke test'i:

```python
from revision_guard.devtools.smoke_test import run_smoke_test
run_smoke_test()
```

**Gerçekten çalıştırılmamış bir testi PASS olarak raporlama.** 3ds Max
içinde koşturulamayan doğrulamalar "doğrulanmadı" olarak bildirilir.

---

## RevisionGuard V0.1 kapsamı

Amaç tek bir soruyu kesin olarak yanıtlamak: *Canlı bir 3ds Max sahnesinde
neyin değiştiğini güvenilir biçimde tespit edebiliyor muyuz?*

Kapsam **içinde**: snapshot alma, transform/geometri parmak izi,
ADDED / REMOVED / GEOMETRY_CHANGED / TRANSFORM_CHANGED /
GEOMETRY_AND_TRANSFORM_CHANGED / UNCHANGED sınıflandırması, dockable
PySide6 paneli, seçim + izolasyon, smoke test.

Kapsam **dışında** (istenmedikçe yazma): FBX/Revit/DWG/IFC entegrasyonu,
dosya izleme, materyal/modifier/UV koruma, GUID veya bulanık eşleştirme,
rename tespiti, revizyon zaman çizelgesi, veritabanı, bulut, telemetri,
lisanslama, updater, installer paketleme, render motoruna özel özellikler.

V0.1'i V1.0'a çevirme.
