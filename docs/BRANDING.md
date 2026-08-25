# Corona Doctor — Brand Identity

## Concepts explored

Three substantially different directions were built and compared side by
side at 128 / 64 / 32 / 24 / 16px on both dark and light grounds (the
sizes the mark actually has to survive: nav sidebar icon, dock/window
icon, About screen, README/GitHub) before picking a final direction —
see the swatch comparison referenced below.

1. **Diagnostic Pulse Ring** *(selected)* — an open ~270° arc (deliberately
   echoing the in-app Scene Health ring already used in
   `ui/components/health_score.py`, so the brand mark and the product's
   own health indicator read as the same visual idea) with a single ray
   reaching a filled "reading" point outside the ring, plus a filled
   center dot. Territory: scene health, diagnostic scan, precision.
2. **Node Constellation** — three connected scene nodes (a small
   scene-graph triangle), one filled to represent a flagged node.
   Territory: geometry/nodes.
3. **Iris Notch** — a hexagonal camera-aperture/lens iris with an
   inspection-notch cut and a center dot. Territory: render frame/camera.

## Why the Pulse Ring won

- **Small-size legibility.** At 16px, (2) and (3) both degrade —
  Constellation's three thin circles + connecting lines blur into a soft
  triangular smear with no readable detail; Iris Notch's hexagon outline
  and notch cut lose their distinguishing feature and read as a generic
  gear/settings glyph. The Pulse Ring's thick stroke + two filled dots
  keep a clear silhouette even at 16px because the filled shapes carry
  the read, not thin outline detail.
- **Distinctiveness / brand independence.** A closed hexagon iris (3) is
  close to widely-used generic "aperture/settings" iconography — weak
  claim to originality. Corona Renderer's own mark is a full radially
  symmetric sun-burst; Chaos's is an angular chevron. An **open, partial**
  ring with a single **asymmetric** ray is a clearly different silhouette
  from both, and from generic medical (cross/stethoscope) marks the brief
  explicitly ruled out.
- **Relationship to the product.** Sharing its arc language with the
  actual Scene Health widget gives the mark a real, non-arbitrary tie to
  what Corona Doctor does (measures scene health, flags a specific
  reading) rather than decorating an unrelated shape with the product
  name.
- **Professional/precision feel.** A single deliberate ray hitting one
  point reads as "this is what's wrong, precisely," which fits a
  diagnostic tool's tone better than a friendlier, rounder constellation
  motif.

## Files

- `assets/branding/corona_doctor_mark.svg` — icon-only mark. `currentColor`
  strokes/fills so it recolors like every other nav icon (see
  `ui/icons/icon_registry.py`); used for the nav "About" icon, the dock/
  window icon, and the About screen (rendered there at a fixed accent
  color via `ui/branding.py::load_brand_pixmap`).
- `assets/branding/corona_doctor_logo.svg` — full lockup (mark + "Corona
  Doctor" wordmark + tagline) at fixed colors, for README/GitHub branding
  and anywhere the mark appears outside the themed UI. Not
  currentColor-driven — it carries its own palette so it reads correctly
  dropped into a plain README on GitHub's dark or light theme.

Both are hand-authored vector geometry (arcs/lines/circles + one `<text>`
element on the lockup) — no raster, no embedded images, no tracing of any
third-party mark.

## Product authorship

Corona Doctor is developed by **Murat Yüksel** —
[yukselmurat.com](https://yukselmurat.com) ·
[@yuxelmurat](https://instagram.com/yuxelmurat) (Instagram). Represented
in-app on the About screen (`ui/views/about_view.py`), sourced from the
single `core/product.py` metadata module so name/links/version can't drift
out of sync between widgets.
