# PisGo Product Design v2

PisGo adalah instrumen presisi untuk penentuan waktu panen, pengiriman, dan estimasi kematangan tiba pisang Cavendish. PisGo menggabungkan kejelasan lembar manifest operasional dengan ketelitian instrumen grading buah dan analisis logistik rute.

Dokumen ini adalah kriteria penerimaan visual (*visual acceptance criteria*) implementasi antarmuka PisGo.

---

## 1. Karakter Produk

- **Instrumen keputusan terkalibrasi:** PisGo dirancang sebagai alat kerja presisi (*precision instrument*), bukan dasbor analitik, bukan panel admin SaaS, dan bukan brosur pemasaran.
- **Kejelasan operasional (*operational clarity*):** Setiap piksel, garis bagi, dan angka tabular melayani alur keputusan operator kebun dan logistik: data buah → inspeksi spesimen → target kematangan → rute pengiriman → rekomendasi panen/kirim/tiba.
- **Pertanian teknis tanpa ornamen rustik:** Nuansa agrikultur dihadirkan secara fungsional melalui warna botani terkalibrasi dan hierarki bernomor, tanpa tekstur kertas usang, ilustrasi dekoratif, atau grafis vintage.
- **Bahasa antarmuka:** Seluruh teks antarmuka (*UI copy*) menggunakan Bahasa Indonesia secara konsisten.

---

## 2. Pengalaman Inti (*Core Experience*)

Alur kerja PisGo bertumpu pada satu transformasi terukur:

```
[DATA BUAH & DAF] + [FOTO SPESIMEN] + [TARGET KEMATANGAN] + [RUTE PENGIRIMAN]
                                ↓ (Analisis)
[TANGGAL KIRIM UTAMA] + [INSTRUMEN 1–7: KINI → TARGET → TIBA] + [GARIS WAKTU PANEN–KIRIM–TIBA] + [PETA RUTE]
```

Operator memasukkan parameter lapangan, sistem memproyeksikan laju kematangan selama masa tunggu dan transit logistik, lalu menetapkan tanggal aksi panen dan pengiriman agar buah tiba pada target kematangan yang tepat.

---

## 3. Tanda Tangan Visual (*Visual Signature*)

Tanda tangan visual utama PisGo adalah **Instrumen Kematangan 1–7 Bersama (*Shared Maturity Instrument*)**.

Skala kematangan 1–7 bukan sekadar slider atau label teks terpisah, melainkan satu instrumen fisik digital yang menampilkan:
- Spektrum 7 segmen warna diskret terkalibrasi dari hijau panen (`#34683A`) hingga kuning bintik (`#C48E18`).
- Garis tanda (*numeric tick*) 1 sampai 7 di setiap langkah agar skala terbaca sempurna pada mode monokrom atau gangguan penglihatan warna (*color-vision deficiency*).
- Sebelum analisis: instrumen bertindak sebagai pemilih `TARGET` dengan indikator nilai target aktif.
- Setelah analisis: instrumen yang sama menampilkan tiga penanda sekaligus pada satu garis bacaan:
  1. Penanda **KEMATANGAN SAAT INI (`KINI`)** dari pembacaan foto.
  2. Penanda **TARGET KEMATANGAN (`TARGET`)** yang ditentukan operator.
  3. Penanda **KEMATANGAN SAAT TIBA (`TIBA`)** hasil perhitungan model dan durasi transit.

---

## 4. Hierarki Informasi

### Sebelum Analisis (Desktop & Mobile)
1. Kolom Alur Kerja Bernomor: `01 DATA BUAH`, `02 SPESIMEN`, `03 TARGET`, `04 PERJALANAN`.
2. Instrumen Kematangan Siaga (menampilkan posisi target dan penjelasan peran instrumen).
3. Tombol Eksekusi: `Analisis rencana panen`.

### Setelah Analisis
1. **Rekomendasi Utama:** Tanggal Kirim yang Direkomendasikan (`Kirim pada [TANGGAL]`) sebagai angka mono dominan.
2. **Status Rekomendasi:** Indikator kesesuaian target (`Sesuai target`, `Lebih hijau`, atau `Lebih matang`).
3. **Instrumen Kematangan 1–7 Bersama:** Tiga penanda posisi (`KINI`, `TARGET`, `TIBA`).
4. **Garis Waktu Keputusan:** Hubungan sekuensial `Panen` → `Kirim` → `Tiba` dengan durasi jeda.
5. **Rute & Peta:** Fakta logistik (jarak, estimasi durasi truk ringan) dan peta jalur berkendara.
6. **Data Pendukung (*Evidence*):** Rincian DAF, nilai kematangan numerik, dan tingkat keyakinan model.
7. **Pengungkapan Pengembangan (*Disclosure*):** Catatan transparan versi model dasar (*baseline*).

---

## 5. Tata Letak Desktop Sebelum Analisis (*Desktop Before-Analysis*)

- **Header Produk:** Tinggi tetap `56px` (`3.5rem`), garis batas bawah `1px solid var(--line)`, memuat brand mark PisGo dan label kerja `Perencanaan panen`.
- **Struktur Grid Workspace:** Dua kolom berdampingan sejak halaman pertama dimuat:
  - **Rail Kiri (Formulir Alur Kerja):** Lebar `420px` (rentang `380–440px`), latar belakang `var(--surface)`. Berisi 4 bagian bernomor bergaris pemisah tipis dan tombol analisis.
  - **Panel Kanan (Instrumen Siaga / Standby Instrument):** Mengisi sisa lebar layar, latar belakang `var(--canvas)`.
- **Konten Panel Kanan Sebelum Analisis:**
  - **DILARANG** menampilkan peta kosong atau rute palsu sebelum asal dan tujuan dianalisis.
  - **DILARANG** menampilkan garis waktu atau tanggal rekomendasi tiruan.
  - Menampilkan **Instrumen Kematangan Siaga**: Skala 1–7 aktif dengan penanda `TARGET` yang terhubung langsung ke nilai input rail kiri, slot `KINI` dan `TIBA` bertanda kosong (`—`), disertai teks panduan teknis yang menjelaskan bagaimana foto dan rute akan menggerakkan penanda saat dianalisis.

---

## 6. Tata Letak Desktop Setelah Analisis (*Desktop Result Layout*)

- **Grid Workspace:** Grid 2 kolom tetap aktif:
  - **Rail Kiri:** Berfungsi sebagai panel kontrol aktif untuk mengubah input atau menghitung ulang. Menempel (*sticky*) dengan scroll mandiri bila tinggi layar terbatas.
  - **Workspace Hasil Kanan:** Area keputusan terpadu tanpa pemisahan kartu bertumpuk (*no cards inside cards*).
- **Struktur Workspace Hasil:**
  1. **Blok Rekomendasi Utama:** Garis batas atas aksen hijau `3px`, tanggal kirim raksasa `font-mono` (`clamp(2.75rem, 4vw, 4rem)`), label stempel status.
  2. **Instrumen Kematangan 3-Penanda:** Terintegrasi tepat di bawah blok rekomendasi, menampilkan sebaran `KINI`, `TARGET`, dan `TIBA` pada bilah spektrum bersama.
  3. **Garis Waktu Keputusan:** Jadwal horizontal `Panen` → `Kirim` → `Tiba` dengan penekanan visual pada tahap `Kirim`.
  4. **Bagian Rute & Peta:** Header ringkasan asal → tujuan, jarak, durasi, diikuti peta Leaflet setinggi `clamp(18rem, 36vh, 24rem)`.
  5. **Daftar Bukti Pendukung & Footer Model:** Tabel data teknis dua kolom bergaris tipis dan catatan versi model baseline.

---

## 7. Tata Letak Mobile (*Mobile Layout*)

Mobile menggunakan alur satu kolom linier tanpa meniru bilah samping desktop.

### Urutan Layar Sebelum Analisis:
1. Header produk ringkas (`48px`).
2. Bagian `01 DATA BUAH` (Tanggal berbunga & DAF terhitung).
3. Bagian `02 SPESIMEN` (Bingkai foto tandan).
4. Bagian `03 TARGET` (Target kematangan & instrumen 1–7 sentuh).
5. Bagian `04 PERJALANAN` (Asal, tujuan, moda truk ringan).
6. Tombol `Analisis rencana panen` (lebar penuh, tinggi sentuh minimal `48px`).

### Urutan Layar Setelah Analisis:
1. Blok Keputusan Utama (Tanggal kirim rekomendasi & status).
2. Instrumen Kematangan 1–7 (dengan 3 penanda: Kini, Target, Tiba).
3. Garis Waktu Keputusan Panen → Kirim → Tiba (sekuens vertikal / horizontal kompak).
4. Ringkasan Rute, jarak, durasi, dan Peta Leaflet (`height: 16–18rem`).
5. Data Pendukung (DAF, Kematangan saat ini, Target, Keyakinan model).
6. Tombol ubah / hitung ulang input.

---

## 8. Tipografi (*Typography*)

Sistem tipografi menggunakan keluarga **IBM Plex** untuk menghasilkan karakter instrumen teknis yang terbaca jelas dan operasional:

```css
--font-sans: var(--font-ibm-plex-sans), sans-serif;
--font-condensed: var(--font-ibm-plex-sans-condensed), sans-serif;
--font-mono: var(--font-ibm-plex-mono), monospace;
```

### Aturan Peran Tipografi:
1. **IBM Plex Sans Condensed:**
   - Digunakan untuk: Label bagian bernomor (`01 DATA BUAH`, `02 SPESIMEN`), judul grup instrumen, tag status huruf besar terlacak (*tracked uppercase*, `letter-spacing: 0.05em–0.08em`).
   - Bobot: `600 (SemiBold)` atau `700 (Bold)`.
   - **DILARANG** digunakan untuk paragraf panjang, nilai input formulir, atau teks bantuan.
2. **IBM Plex Sans:**
   - Digunakan untuk: Teks antarmuka utama, label input, teks bantuan, placeholder, pesan kesalahan, dan teks deskriptif.
   - Bobot: `400 (Regular)` dan `500 (Medium)`.
   - Ukuran dasar: `14px` (`0.875rem`) dengan `line-height: 1.45`; label `12–13px`.
3. **IBM Plex Mono:**
   - Digunakan untuk: Semua nilai numerik, tanggal keputusan panen/kirim/tiba, DAF, jarak kilometer, durasi jam/menit, persentase keyakinan, dan penomoran skala 1–7.
   - Angka wajib menggunakan format tabular (*tabular figures*).
   - Ukuran tanggal keputusan rekomendasi: `clamp(2.75rem, 4vw, 4.25rem)`.

---

## 9. Token Warna (*Color Tokens*)

### Palet Dasar & Permukaan
```css
--canvas: #f3f1ea;          /* Latar belakang utama workspace */
--surface: #faf9f4;         /* Permukaan panel kerja dan input */
--surface-muted: #eae7dc;   /* Area bingkai spesimen dan pemisah */
--ink: #18221b;             /* Teks utama (grafit kehijauan pekat) */
--muted: #5e6860;           /* Teks sekunder, label unit, instruksi */
--line: #d5d1c5;            /* Garis pemisah standar 1px */
--line-strong: #a4a195;     /* Garis batas fokus/aktif */

--accent: #215437;          /* Hijau aksi operasional utama */
--accent-deep: #163b26;     /* Status aktif / hover tombol */
--accent-soft: #dbe7dc;     /* Seleksi aktif & cincin fokus */

--gold-arrival: #b88219;    /* Emas penanda tiba & aksen waktu */
--gold-soft: #f4ebd4;       /* Latar status kematangan tiba */

--error: #9a3f38;           /* Peringatan kesalahan & batas gagal */
--error-soft: #f4e5e1;      /* Latar kotak kesalahan */
```

### Spektrum Kematangan 7-Langkah Terkalibrasi (*Calibrated Maturity Scale*)
Setiap langkah mewakili fase kematangan komersial pisang Cavendish:

```css
--maturity-1: #34683a;  /* 1: Hijau matang (Harvest Green) */
--maturity-2: #4f833b;  /* 2: Matang hijau (Light Green) */
--maturity-3: #759d33;  /* 3: Kuning hijau (Yellowish Green) */
--maturity-4: #9eb52d;  /* 4: Lebih hijau dari kuning (More Green than Yellow) */
--maturity-5: #c7a726;  /* 5: Kuning ujung hijau (Yellow with Green Tips) */
--maturity-6: #d6981f;  /* 6: Kuning penuh (Full Yellow) */
--maturity-7: #c48e18;  /* 7: Kuning bintik cokelat (Aromatic Spotted Yellow) */
```

### Aturan Penggunaan Warna:
- Warna adalah sinyal fungsional pembawa data, bukan dekorasi latar belakang.
- Tidak boleh ada gradien dekoratif acak, efek pendar (*glow*), atau aksen ungu/biru SaaS.
- Satu-satunya spektrum multi-warna yang diizinkan di seluruh aplikasi adalah Spektrum Kematangan 7-Langkah di atas.

---

## 10. Spesifikasi Instrumen Kematangan (*Maturity Instrument Spec*)

Instrumen kematangan dirender sebagai bilah terkalibrasi modular:

1. **Struktur Bilah:**
   - Terdiri dari 7 segmen warna diskret berdampingan (`--maturity-1` s.d. `--maturity-7`), tinggi `12px` (desktop) atau `14px` (mobile), sudut `2px`.
   - Di atas atau di bawah setiap segmen terdapat nomor `1` sampai `7` dalam `font-mono` dan garis tick pemisah `1px`.
2. **Keterbacaan Non-Warna (*A11y Grayscale Safeguard*):**
   - Setiap posisi memiliki label teks fase resmi (misal `4: Lebih hijau dari kuning`).
   - Penanda posisi memuat simbol bentuk yang berbeda:
     - Penanda `KINI`: Segitiga runcing ke bawah (`▼`) dengan garis tepi gelap.
     - Penanda `TARGET`: Persegi berkontur tegas (`■`) dengan cincin putih/gelap.
     - Penanda `TIBA`: Belah ketupat emas (`◆`) dengan sorotan nilai tiba (misal `5.2`).
3. **Interaksi Input Target (Sebelum Analisis):**
   - Operator dapat mengklik segmen atau menggeser penanda TARGET.
   - Input berbasis native range yang tersembunyi secara visual namun tetap mendukung kontrol keyboard (ArrowLeft, ArrowRight, Home, End) dengan `aria-valuetext` lengkap.
4. **Tampilan Hasil (Setelah Analisis):**
   - Penanda `KINI` berada di nilai prediksi model (misal `3.0`).
   - Penanda `TARGET` tetap di posisi target pilihan operator (misal `4.0`).
   - Penanda `TIBA` meluncur ke posisi estimasi kedatangan (misal `5.0`).
   - Jika `TIBA` melebihi toleransi `TARGET`, status teks menunjukkan deviasi secara eksplisit.

---

## 11. Perlakuan Foto Spesimen (*Specimen Image Treatment*)

Unggahan foto diperlakukan sebagai **panggung inspeksi spesimen buah**, bukan dropzone file umum:

1. **Bingkai Spesimen (*Specimen Frame*):**
   - Rasio aspek `16:9` atau `4:3`, batas solid `1px solid var(--line-strong)`, latar belakang `var(--surface-muted)`.
   - Sudut bingkai diberi aksen garis pengunci presisi (*corner register marks* `2px`).
2. **Kondisi Kosong (*Empty State*):**
   - Ikon kamera/inspeksi garis tegas.
   - Label instruksi: `Pasang foto tandan pisang`.
   - Panduan pengambilan: `Foto satu tandan utuh, pencahayaan alami/terang`.
3. **Kondisi Terisi (*Filled State*):**
   - Pratinjau gambar tajam dengan `object-fit: cover`.
   - **Plat Label Metadata Spesimen:** Strip di bagian bawah foto dengan latar semi-transparan `var(--surface)`:
     - Menampilkan identitas: `SPESIMEN BUAH · [NAMA FILE]`.
     - Ukuran file terformat (misal `2.4 MB`).
     - Tanggal inspeksi/foto.
   - Tombol kontrol minimalis: `Ganti` dan `Hapus` dengan target sentuh yang jelas.
4. **Batasan ML:**
   - Jangan menambahkan kotak deteksi (*bounding boxes*) atau label inferensi tiruan sebelum model ML riil terhubung.

---

## 12. Masukan & Formulir (*Inputs & Forms*)

Formulir dirancang sebagai lembar manifest terstruktur bernomor:

- **Penomoran Alur Kerja:**
  - `01 DATA BUAH` (Tanggal berbunga + kalkulasi DAF langsung).
  - `02 SPESIMEN` (Foto tandan & tanggal foto).
  - `03 TARGET` (Target kematangan 1–7).
  - `04 PERJALANAN` (Titik asal, titik tujuan, keterangan moda truk ringan).
- **Gaya Kontrol Input:**
  - Label selalu terlihat di atas kontrol (`font-sans`, `font-medium`, `12–13px`).
  - Bidang input menggunakan batas datar `1px solid var(--line)`, latar `var(--surface)`, sudut `4–6px`.
  - Tinggi kontrol minimal `44px` (mobile) dan `40px` (desktop).
  - Indikator fokus: Batas berubah menjadi `var(--accent)` dengan cincin luar `2px solid var(--accent-soft)` tanpa pergeseran tata letak.
- **Nilai DAF (Hari Setelah Berbunga):**
  - Muncul otomatis saat tanggal berbunga dan tanggal foto valid: `Usia buah: [N] hari setelah berbunga` dalam `font-mono`.
- **Rute Autocomplete:**
  - Menampilkan ikon penanda lokasi, status memuat saat mengetik, daftar saran dengan pemisah tipis, dan dukungan navigasi keyboard lengkap.
  - Teks pembantu rute: `Truk ringan · Estimasi tanpa kemacetan`.

---

## 13. Perlakuan Rute & Peta (*Route & Map*)

Peta berfungsi sebagai alat verifikasi jalur logistik:

1. **Kondisi Sebelum Analisis:**
   - Peta Leaflet **TIDAK** dirender di layar utama untuk menghindari ruang kosong tak bermakna.
   - Ruang desktop sebelah kanan digunakan untuk Instrumen Kematangan Siaga.
2. **Kondisi Setelah Analisis:**
   - Peta dirender di dalam bingkai presisi bergaris batas `1px solid var(--line)`.
   - Jalur rute digambar dengan garis polyline tebal (`color: var(--accent)`, `weight: 4–5`, `opacity: 0.9`).
   - Marker asal: lingkaran hijau tua (`var(--accent)`) dengan garis tepi putih.
   - Marker tujuan: lingkaran grafit pekat (`var(--ink)`) dengan garis tepi putih.
   - Ubin peta (Leaflet tiles) dapat diberikan penyesuaian kontras ringan agar menyatu dengan palet kanvas, namun **TIDAK BOLEH** diubah menjadi monokrom ekstrem yang menghilangkan keterbacaan nama kota, jalan, dan batas pulau.
   - Informasi jarak dan durasi ditampilkan pada strip data di atas atau tepat menempel pada batas peta (misal: `412 km · 9 jam 40 menit`).

---

## 14. Garis Waktu Keputusan (*Harvest → Ship → Arrive Timeline*)

Garis waktu menghubungkan tiga peristiwa logistik sebagai satu rantai waktu bersekuens:

```
[ PANEN ] ─────────────► [ KIRIM ] ═════════════════► [ TIBA ]
20 AGU 2026             22 AGU 2026                  25 AGU 2026
(Jeda kebun: 2 hari)    (Aksi Utama Keputusan)       (Transit: 3 hari)
```

### Spesifikasi Tampilan:
- **Tiga Titik Waktu:**
  1. `PANEN`: Tanggal tandan dipotong dari pohon.
  2. `KIRIM`: Tanggal muatan diberangkatkan dengan truk (titik keputusan terpenting).
  3. `TIBA`: Tanggal estimasi muatan sampai di pasar/tujuan.
- **Pembeda Visual Tahap KIRIM:**
  - Tahap `KIRIM` diberi penanda status utama (`data-primary="true"`), ukuran teks lebih tegas, dan aksen latar lembut.
- **Konektor Waktu:**
  - Garis penghubung padat dengan indikator arah panah dan label jeda hari di antara tahap.
- **Tipografi Tanggal:** Menggunakan format tanggal mono singkat (misal `22 AGU 2026`).

---

## 15. Blok Rekomendasi Utama (*Recommendation Presentation*)

Blok rekomendasi adalah momen visual terpenting dari seluruh aplikasi setelah tombol ditekan:

1. **Label Bagian:** `REKOMENDASI PENGIRIMAN` dalam `font-condensed` huruf besar.
2. **Tanggal Keputusan Hero:**
   - Ditampilkan dalam format besar yang tidak ambigu: `Kirim pada` diikuti tanggal mono raksasa (misal `22 AGUSTUS 2026`).
3. **Lencana Status Kematangan Tiba:**
   - Status ditampilkan secara lugas:
     - `Diperkirakan tiba sesuai target` (Ikon centang hijau).
     - `Diperkirakan tiba lebih hijau dari target` (Ikon peringatan emas).
     - `Diperkirakan tiba lebih matang dari target` (Ikon peringatan emas).
4. **Estimasi Kematangan Tiba:**
   - Nilai angka desimal dalam `font-mono` (misal `5.0 / 7`) dengan deskripsi label fase kematangan tiba.

---

## 16. Data Pendukung (*Supporting Evidence*)

Data pendukung disajikan dalam tabel/daftar dua kolom yang tenang dan terstruktur di bagian bawah workspace hasil:

- **Elemen yang Ditampilkan:**
  1. `Hari setelah berbunga (DAF)`: Nilai bilangan bulat (misal `128 hari`).
  2. `Kematangan saat ini`: Nilai desimal (misal `3.0 / 7`).
  3. `Target kematangan`: Nilai target operator (misal `4.0 / 7`).
  4. `Tingkat keyakinan model`: Persentase (misal `91%`).
- **Gaya Visual:**
  - Label di kolom kiri (`var(--muted)`, `font-sans`, `12–13px`).
  - Nilai di kolom kanan (`var(--ink)`, `font-mono`, rata kanan).
  - Garis pemisah horizontal `1px solid var(--line)`.
  - Tidak boleh menggunakan grafik speedometer, progress bar melingkar (*radial gauges*), atau kartu metrik KPI berulang.
- **Catatan Versi Model:**
  - Teks pengungkapan di bagian footer: `Model baseline [versi] · Prototipe pengembangan`.

---

## 17. Gerakan & Transisi (*Motion*)

Prinsip gerakan: **tenang, bertujuan teknis, dan hemat durasi.**

### Gerakan yang Diizinkan:
- **Transisi Hasil (Result Reveal):** Saat analisis selesai, workspace hasil muncul dengan pergeseran halus ke atas `4px` dan fade-in selama `200–250ms`.
- **Transisi Penanda Kematangan:** Penanda `TIBA` pada bilah instrumen meluncur (*slide transition*) ke posisi nilai tiba selama `400ms ease-out`.
- **Transisi Garis Rute Peta:** Jalur polyline rute memudar masuk (*fade-in*) selama `300ms`.
- **Umpan Balik Tombol:** Tombol analisis berganti label secara langsung sesuai fase (`Menghitung rute…` → `Menganalisis buah…`) dengan indikator putar halus.

### Gerakan yang DILARANG:
- Dilarang efek angka berputar (*slot-machine / number ticker*).
- Dilarang animasi scroll berjenjang (*scroll-triggered staggered entrance*).
- Dilarang efek mengambang (*floating elements*), partikel, atau animasi berulang terus-menerus (*looping ambient animations*).
- **Aksesibilitas Gerakan:** Wajib mendukung `@media (prefers-reduced-motion: reduce)` dengan mematikan seluruh durasi transisi menjadi instan (`0.01ms`).

---

## 18. Aksesibilitas (*Accessibility*)

PisGo harus dapat dioperasikan secara penuh dan nyaman oleh semua pengguna:

1. **Navigasi Keyboard:**
   - Tautan lompat langsung (*skip link*): `#controls` ke formulir kerja.
   - Semua input, tombol, dan slider target kematangan dapat diakses dengan tombol Tab, Enter, Space, dan tombol panah arah.
2. **Label & ARIA:**
   - Semua kontrol memiliki `<label>` terkait atau atribut `aria-labelledby`.
   - Slider kematangan memiliki `aria-valuetext` yang menyebutkan angka dan nama fase kematangan (misal `4, Lebih hijau dari kuning`).
   - Status pemuatan dan peringatan menggunakan `aria-live="polite"` dan `role="alert"`.
3. **Kontras & Keterbacaan:**
   - Rasio kontras teks utama (`--ink` di atas `--surface`/`--canvas`) minimal `7:1`.
   - Rasio kontras teks sekunder (`--muted`) minimal `4.5:1` terhadap latar belakang.
   - Warna tidak pernah menjadi satu-satunya pembawa informasi (status selalu didampingi teks deskriptif dan ikon pembeda bentuk).
4. **Indikator Fokus:**
   - Setiap elemen interaktif memiliki `focus-visible` yang jelas (`outline: 2px solid var(--accent); outline-offset: 2px`).

---

## 19. Anti-Pola Eksplisit (*Explicit Anti-Patterns*)

Antarmuka PisGo **TIDAK BOLEH** menerapkan pola-pola berikut:

- ❌ **Fintech Green Dashboard:** Kartu saldo melayang, statistik buatan, grafik garis palsu.
- ❌ **Generic AI Prompt Box:** Chatbot mengambang, ikon bintang gemerlap (*sparkles* AI), atau textarea bebas tanpa parameter lapangan terstruktur.
- ❌ **Bento Grid & Glassmorphism:** Panel kaca buram transparan, kartu tumpang-tindih dengan bayangan tebal, radius sudut raksasa (>16px).
- ❌ **Kartu di dalam Kartu (*Cards inside Cards*):** Pembungkusan berlebih yang memecah hierarki permukaan datar.
- ❌ **Peta Palsu Pra-Analisis:** Menampilkan jalur fiktif atau peta kosong tanpa tujuan sebelum operator memilih rute.
- ❌ **Pembalikan Hasil Senyap (*Silent Clear*):** Menghilangkan hasil analisis secara mendadak tanpa indikasi bahwa input sedang direvisi.

---

## 20. Batasan Produk yang DILARANG Ditambahkan (*Scope Constraints*)

Untuk menjaga fokus tajam pada alur kerja panen dan logistik Cavendish, hal-hal berikut **DILARANG** ditambahkan ke dalam basis kode:

- 🚫 Tidak ada sistem autentikasi, halaman login, atau manajemen profil pengguna.
- 🚫 Tidak ada menu navigasi sidebar besar atau tautan multi-halaman.
- 🚫 Tidak ada modul riwayat panen (*history log*) atau database penyimpanan arsip.
- 🚫 Tidak ada panel analitik KPI, ringkasan mingguan/bulanan, atau grafik tren cuaca buatan.
- 🚫 Tidak ada AI chatbot, asisten percakapan, atau bagian wawasan (*AI insights*) berbasis teks generatif.
- 🚫 Tidak ada halaman arahan pemasaran (*marketing landing sections*), testimonial, atau tabel harga.
