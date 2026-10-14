# Skripsi DTNTF UGM (Quarto)

Kerangka skripsi mengikuti *Panduan Tugas Akhir, Skripsi dan Ujian Pendadaran* (2018) dan
*Template Skripsi* (2023/2025) Departemen Teknik Nuklir dan Teknik Fisika, FT UGM.

## Render

```bash
quarto render skripsi.qmd      # hasil: _output/skripsi.pdf
```

Prasyarat: Quarto ≥ 1.4 dan TeX Live/TinyTeX dengan `xelatex`
(paket: titlesec, titletoc, fancyhdr, caption, setspace, etoolbox, indentfirst, lmodern).
Bila memakai TinyTeX: `quarto install tinytex`.

## Yang perlu diisi

| Berkas | Isi |
|---|---|
| `meta.tex` | **Semua data diri**: judul, nama, NIM, prodi, pembimbing, penguji, tanggal, Ketua Departemen |
| `fig/logo-ugm.png` | Logo UGM (sudah diambil dari templat; dicetak 5,5 cm) |
| `front/*.qmd` | Kata pengantar, intisari, abstract, daftar lambang |
| `01-…06-*.qmd` | Isi bab I–VI |
| `references.bib` | Pustaka (ekspor dari Zotero/Mendeley) |
| `lampiran-*.qmd` | Lampiran (opsional; `lampiran-a.qmd` berisi perintah `\appendix`) |

## Konvensi di berkas `.qmd`

* Judul bab: `# JUDUL BAB DALAM HURUF KAPITAL` → dicetak `BAB I` + judul.
  Bab tanpa nomor (Kata Pengantar, Daftar Pustaka): `# JUDUL {.unnumbered}`.
* Subbab `##`, `###` ditulis Title Case secara manual → `I.1.`, `I.2.1.`
* Gambar: `![Judul ... [@kunci].](fig/x.png){#fig-x fig-scap="Judul pendek untuk Daftar Gambar"}`;
  rujuk dengan `@fig-x` → "Gambar 5.1".
* Tabel: tabel markdown + `: Judul {#tbl-x}`; rujuk `@tbl-x`. Sumber di bawah tabel: `\noindent Sumber: [@kunci]`.
* Persamaan: `$$ ... $$ {#eq-x}`; rujuk `@eq-x` → "Persamaan 5.1".
* Sitasi: `[@kunci]` → `[1]`; beberapa: `[@a; @b; @c]` → `[1–3]`. Nomor mengikuti urutan kemunculan.
* Rincian memakai `1)` / `a)`, bukan bullet.
* Jangan merujuk bab dengan `@sec-…` (label bab berisi kata "BAB").

## Bagian yang sengaja berbeda dari Panduan 2018 (mengikuti templat 2023)

Halaman persembahan & motto, "Sarjana" (tanpa "S-1"), e-Meterai Rp 10.000, "Tinjauan Pustaka".
Format daftar pustaka mengikuti **Panduan 2018** (nama lengkap, tanpa "et al.", Penerbit, Kota, Tahun),
sedangkan templat 2023 memakai inisial dan "Kota, Penerbit". Tanyakan ke pembimbing mana yang dipakai;
ubah di `skripsi-ugm.csl`.

## Font

`_quarto.yml` memakai *TeX Gyre Termes* (metrik hampir identik dengan Times New Roman).
Di komputer dengan Times New Roman, ganti `mainfont: "Times New Roman"`.
