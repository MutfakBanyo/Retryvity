# CLAUDE.md

Bu dosya, bu depoda çalışan Claude Code oturumları için bağlayıcı
kuralları ve proje bilgilerini içerir.

## 1. Çalışma kuralları (kullanıcı tarafından belirlendi)

1. **Dil:** Kullanıcıya sorulan sorular, ilerleme mesajları ve tüm
   raporlar **Türkçe** yazılır. Kod, kod yorumları, commit mesajları ve
   dağıtılan ürün dosyaları (README.txt, ScriptSpot metni, arayüz
   etiketleri) İngilizce kalır — bunlar uluslararası dağıtım içindir.
2. **Branch:** Max Heavy Finder geliştirmesi **yalnızca `HeavyFinder`**
   branch'inde yapılır ve yalnızca oraya push edilir. Oturum altyapısı
   `claude/...` adında bir branch açsa bile oraya **gönderilmez**; başka
   hiçbir branch'e kopyalanmaz.
3. **Alt dal açılmaz.** Feature/fix/hotfix gibi ara branch'ler
   oluşturulmaz. Her kod güncellemesi doğrudan yukarıdaki branch'e işlenir.
4. **PR açılmaz** — kullanıcı açıkça istemedikçe pull request
   oluşturulmaz.
5. **Test sonuçları dürüst raporlanır.** Gerçekten çalıştırılmamış hiçbir
   test `PASS` olarak yazılmaz; çalıştırılamayan testler `UNVERIFIED`
   olarak işaretlenir. Statik kod incelemesi, 3ds Max içinde çalıştırma
   yerine geçmez.

## 2. Depo içeriği

Depo iki bağımsız 3ds Max aracı barındırır:

| Klasör | Ürün | Teknoloji |
|---|---|---|
| `corona_doctor/`, `install_corona_doctor.ms` | Corona Doctor (teşhis/onarım asistanı, bootstrap aşaması) | Python 3.11 + PySide6 + pymxs |
| `MaxHeavyFinder_v0.1.0/` | Max Heavy Finder v0.1.0 (yayına hazır paket) | Saf MAXScript |
| `max_heavy_finder_dev/` | Max Heavy Finder geliştirici araçları (dağıtılmaz) | MAXScript testleri + Python statik denetleyici |

İki ürün birbirinden bağımsızdır; Max Heavy Finder Corona Doctor'ın hiçbir
modülünü kullanmaz ve hiçbir üçüncü parti bağımlılığı yoktur.

## 3. Max Heavy Finder — değişmez kapsam kuralları

Bu araç bilinçli olarak **çok küçüktür**. Genel bir sahne optimizasyoncusuna
dönüştürülmez.

* **Salt okunur.** Geometri, modifier, materyal, transform, görünürlük,
  katman, isim, hiyerarşi, render ayarları **değiştirilmez**. İzin verilen
  tek sahne etkileşimi: nesneyi incelemek, kullanıcı Select/Zoom'a bastığında
  seçmek ve seçimi viewport'ta çerçevelemek.
* **Eklenmeyecekler:** otomatik optimizasyon, ProOptimizer/Optimize,
  proxy dönüştürme, silme, kopya temizleme, materyal/bitmap analizi,
  asset relink, sahne temizliği, otomatik instance dönüştürme,
  renderer'a özel kod.
* **Renderer bağımsız.** Corona, V-Ray, Arnold kurulu olsa da olmasa da
  çalışır. Renderer API'si çağrılmaz.
* **Bağımlılık yok.** Python paketi, harici exe, internet erişimi yok;
  3ds Max ile birlikte gelenler dışında .NET kütüphanesi kullanılmaz.
* **Kalıcı callback yok.** Sahne izleyici/callback kaydedilmez; güncelleme
  manuel `Refresh` ile yapılır.
* **Öncelik sırası:** güvenilirlik > özellik, basit MAXScript > akıllı
  mimari, manuel Refresh > canlı otomasyon, renderer bağımsızlığı >
  renderer'a özel doğruluk.

## 4. Max Heavy Finder — mimari özet

Tek dosya: `MaxHeavyFinder_v0.1.0/MaxHeavyFinder.mcr`. Dosya normal bir
MAXScript dosyasıdır; değerlendirildiğinde önce global sabitleri, veri
modelini ve fonksiyonları tanımlar, en sonda macroScript'i kaydeder.

Katmanlar (dosyadaki sırayla):

1. **Sabitler** — `MAX_HEAVY_FINDER_VERSION`, `MAX_HEAVY_FINDER_HOMEPAGE_URL`.
   Sürüm ve site adresi yalnızca burada tanımlanır, koda dağıtılmaz.
2. **Veri modeli** — `MHF_GeometryGroup` (bir satır = bir nesne veya bir
   instance ailesi), `MHF_ScanResult`.
3. **Biçimlendirme** — `MHF_FormatInt` (binlik ayraç, Integer64 ile taşma
   güvenli), `MHF_FormatPct` (tek ondalık, sıfıra bölme korumalı).
4. **Üçgen değerlendirme** — `MHF_EvaluateNode`: önce
   `getTriMeshFaceCount` (tüm modifier stack'ini hesaplar, sahneye düğüm
   eklemez), sonuç yoksa/sıfırsa yedek olarak `snapshotAsMesh` (geçici
   TriMesh değeri hemen `delete` ile serbest bırakılır).
5. **Instance tespiti** — `MHF_GetGeometryKey`: anahtar = base object
   handle + node üzerindeki tüm modifier handle'ları. Gerçek instance'lar
   ikisini de paylaşır; kopyanın kendi base object'i olduğu için asla
   gruba girmez; reference ise ancak değerlendirilmiş geometrisi
   gerçekten aynıysa gruba katılır.
6. **Tarama** — `MHF_ScanScene`: `geometry` koleksiyonunu gezer (gizli ve
   dondurulmuş nesneler dahil), her benzersiz pipeline'ı **bir kez**
   değerlendirir (Dictionary ile önbellek), her nesneyi kendi `try`
   bloğunda işler; tek bir bozuk nesne taramayı durduramaz.
7. **Sıralama/filtre** — varsayılan: scene impact'e göre azalan.
   Eşik filtresi de scene impact üzerinden çalışır (sahneyi ağırlaştıran
   sayı budur).
8. **Arayüz** — tek rollout + tek floater. `MaxHeavyFinder_Open()` açık
   pencereyi kapatıp yeniden kurar, böylece pencere veya handler
   çoğalmaz.

## 5. Geliştirme akışı

* Değişiklikten sonra statik denetim:
  `python3 max_heavy_finder_dev/check_maxscript.py MaxHeavyFinder_v0.1.0/MaxHeavyFinder.mcr`
  (parantez/tırnak/yorum dengesi — MAXScript'in çevrimdışı yorumlayıcısı yoktur,
  bu denetim gerçek testin yerine geçmez).
* 3ds Max içi testler: `max_heavy_finder_dev/MaxHeavyFinder_Tests.ms`
  (Scripting > Run Script). **Bu betik sahneyi defalarca sıfırlar**, çalışan
  aracın kendisi sahneye dokunmaz. Sonuç Listener'a ve
  `MaxHeavyFinder_TestReport.txt` dosyasına yazılır.
* MAXScript kaynaklarında satır sonu `\` devam karakteri kullanılmaz;
  çağrılar tek satırda tutulur.
* Dosyalar ASCII tutulur (LICENSE/README'deki isim dışında).
