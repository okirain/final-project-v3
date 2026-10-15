# Skripsi DTNTF UGM (Quarto)

Kerangka skripsi yang mengikuti **Template Skripsi 2023/2025** Departemen Teknik Nuklir dan
Teknik Fisika, FT UGM (acuan utama). *Panduan TA dan Skripsi 2018* dipakai hanya untuk hal yang
tidak dicontohkan templat (mis. format skripsi/tesis di Daftar Pustaka).

## Render

```bash
quarto render skripsi.qmd      # hasil: _output/skripsi.pdf
```

Prasyarat: Quarto ≥ 1.4 dan TeX Live/TinyTeX dengan `xelatex`
(paket: titlesec, titletoc, fancyhdr, caption, setspace, etoolbox, enumitem, lmodern).
Bila memakai TinyTeX: `quarto install tinytex`.

## Yang perlu diisi

| Berkas | Isi |
|---|---|
| `meta.tex` | **Semua data diri**: judul, nama, NIM, prodi, pembimbing, penguji, tanggal, Ketua Departemen |
| `fig/logo-ugm.png` | Logo UGM (diambil dari templat; dicetak 5,5 cm) |
| `front/*.qmd` | Kata pengantar, daftar lambang, intisari, abstract (halaman judul/pernyataan/pengesahan otomatis dari `meta.tex`) |
| `01-…06-*.qmd` | Bab I–VI (berisi teks panduan dari templat; ganti dengan isi sendiri) |
| `references.bib` | Pustaka (ekspor dari Zotero/Mendeley); isi contoh = Daftar Pustaka di templat |
| `lampiran-a.qmd`, `lampiran-b.qmd` | Lampiran (`lampiran-a.qmd` memuat halaman "LAMPIRAN" dan perintah `\appendix`) |

## Aturan format yang sudah diterapkan (dari templat)

* A4, margin atas 4 / bawah 3 / kiri 4 / kanan 3 cm; 12 pt; spasi 1,5 (setara Word); awal alinea menjorok 1,27 cm.
* Nomor halaman **tengah bawah** di semua halaman; bagian awal angka Romawi kecil (i, ii, …), mulai Bab I angka Arab 1.
* Judul bab: `BAB I` lalu judul huruf kapital, tebal, rata tengah. Subbab tebal rata kiri: `I.1.`, `I.2.1.`
* Gambar/Tabel/Persamaan bernomor Arab per bab (`Gambar 5.1`, `Tabel 5.1`, `(5.1)`); di lampiran `Tabel B.1`.
  Judul gambar di bawah, judul tabel di atas; sumber tabel di bawah tabel.
* Sitasi `[n]` menurut urutan kemunculan; beberapa acuan `[2-4, 6, 10]`.
* Daftar Pustaka: inisial penulis, semua penulis ditulis ("dan"), judul buku/laporan/web miring,
  `Kota, Penerbit, Tahun`; artikel `"Judul" Jurnal, vol. x, no. y, pp. a-b, tahun.`
* Daftar Isi memuat entri `LAMPIRAN` dengan `LAMPIRAN A`, `LAMPIRAN B` menjorok di bawahnya.

## Konvensi di berkas `.qmd`

* Judul bab: `# JUDUL BAB DALAM HURUF KAPITAL` → dicetak `BAB I` + judul.
  Bab tanpa nomor (Kata Pengantar, Daftar Pustaka): `# JUDUL {.unnumbered}`.
* Subbab `##`, `###` ditulis Title Case secara manual.
* Gambar: `![Judul ... [@kunci].](fig/x.png){#fig-x fig-scap="Judul pendek untuk Daftar Gambar"}`; rujuk `@fig-x`.
* Tabel: tabel markdown + `: Judul {#tbl-x}`; rujuk `@tbl-x`. Sumber: `\noindent Sumber: [@kunci]`.
* Persamaan: `$$ ... $$ {#eq-x}`; rujuk `Persamaan ([-@eq-x])` → "Persamaan (5.1)".
* Garis bawah: `` `\underline{teks}`{=latex} ``.
* Jangan merujuk bab dengan `@sec-…` (label bab berisi kata "BAB").

## Perbedaan kecil dari templat

* Tabel memakai garis horizontal (atas, bawah judul kolom, bawah); templat memakai garis kotak penuh.
* Rentang sitasi tercetak dengan en-dash (`[2–4]`), templat dengan tanda hubung.
* Gambar di Bab III pada templat bernomor `III.1`, sedangkan seluruh contoh lain (Bab V, Daftar Gambar)
  bernomor Arab; scaffold ini konsisten memakai Arab.
* Daftar Isi pada templat tidak memuat Halaman Pengesahan; di sini dimuat.
* Halaman Abstract pada templat mengulang judul berbahasa Indonesia; di sini memakai `\judulinggris`.

## Font

`_quarto.yml` memakai *TeX Gyre Termes* (metrik hampir identik dengan Times New Roman; templat
memakai Liberation Serif/Times). Di komputer dengan Times New Roman, ganti `mainfont: "Times New Roman"`.
