# Dataset Registry

Dataset besar tidak disimpan di Git. Catat versi, sumber, lokasi, kondisi koleksi, lisensi, dan kebijakan split sebelum training.

## Augmented Banana Variety Dataset

- **Lokasi lokal:** `D:\Augmented Banana Variety Dataset.zip`
- **Ukuran arsip:** 379.047.318 byte
- **Format:** ZIP dengan 8.750 JPG RGB, seluruhnya 384×256
- **Varietas:** Ambon, Cavendish, Mas, Raja, Saba
- **Label filename:** variety, maturity (`unripe`, `half_ripe`, `ripe`, `overripe`), view (`top`, `bottom`, `left`, `right`), specimen ID, dan optional augmentation ID
- **Cavendish:** 1.750 gambar; 380 original + 1.370 augmented; 95 specimen groups
- **Annotation:** image-level classification; tidak ada bounding box atau segmentation mask
- **Lisensi/sumber:** belum dicatat; pemilik proyek harus melengkapi provenance dan izin penggunaan sebelum distribusi/produksi

### YOLO status

`YOLO_DATASET_BLOCKED`: training object detector belum boleh dijalankan karena tidak ada bounding box terverifikasi. Kontrak anotasi satu kelas `banana_bunch` dan acceptance checklist tersedia di [ANNOTATION.md](ANNOTATION.md). Training baru dapat dimulai setelah export anotasi memenuhi kontrak tersebut; classifier kematangan tingkat gambar tetap merupakan pipeline terpisah.

Workflow kandidat menggunakan Wikimedia Commons dengan allowlist lisensi `CC0`, `CC BY`, dan `CC BY-SA`. Jalankan dari folder `ml`:

```powershell
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml collect
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml export-review --review-id reviewer-1
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml import-review --receipt path/to/reviewer-1-receipt.json
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml curate
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml curation-status
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml package
```

`collect` menyimpan gambar dan provenance di `datasets/raw/banana_bunch_detection/`. `export-review` membuat bundle ZIP offline di `datasets/local_review_exports/`; Reviewer 1 mengekstraknya, membuka `index.html` tanpa Python, memasukkan identitas, dan mengunduh receipt JSON untuk dikirim kembali. `import-review` menolak ID asing/duplikat, keputusan atau timestamp invalid, reviewer kosong, digest yang tidak cocok, serta field metadata/provenance; hanya state kurasi yang berubah dan kandidat yang tidak direview tetap unresolved. `curate` membuka UI localhost untuk keputusan Reviewer 2; UI tidak mengklasifikasi dan tidak menghasilkan box. Setelah first pass selesai, semua `needs_review` dan sampel deterministik minimal 10% dari keputusan include masuk second review oleh manusia berbeda. Ketidaksetujuan tetap `needs_review`, tidak pernah diputus otomatis. `curation-status` menampilkan kemajuan; approval eksplisit yang terikat hash receipt wajib sebelum `package` dapat mengemas baris `include`. Kurator juga mengoreksi `specimen_id`/`group_id` untuk view terkait. Candidate role dari search query bukan ground truth. Setelah export YOLO, `review.csv`, dan `human_qa.csv` dikembalikan, jalankan `build` lalu `audit`. Workflow tidak menghasilkan bounding box dan tidak memulai training.

Output audit berada di `datasets/processed/banana_bunch_detection/audit.{json,md}`. Dataset kanonik hanya dibuat setelah provenance, review eksplisit, label, grouped split, dan QA lolos. Arsip 380 original tetap dikecualikan karena sumber/lisensinya belum diketahui.

### Split policy

Group key:

```text
variety + maturity_class + specimen_id
```

Semua view dan augmented descendants dari satu specimen harus berada pada split yang sama. Dengan seed 42:

- Train: 67 specimen groups, 1.233 gambar termasuk augmentasi
- Validation: 15 specimen groups, 60 original images
- Test: 13 specimen groups, 52 original images

File split reproducible dihasilkan sebagai `reports/cv_manifest.csv` ketika training. Validation/test tidak menggunakan gambar augmented.

### Domain limitation

Foto berasal dari satu dataset terkontrol. Evaluasi internal tidak mewakili foto kebun dengan kamera, pencahayaan, background, occlusion, framing, atau kondisi varietas yang berbeda. Kumpulkan external test set dari alur MVP sebelum klaim performa produksi.

## External banana-on-tree validation images

Sepuluh foto berlisensi dari Wikimedia Commons disimpan lokal di `datasets/images/external_validation/banana_on_tree/`:

- 6 foto secara eksplisit dideskripsikan sebagai Cavendish Williams.
- 4 foto banana/plantain on-tree untuk pemeriksaan out-of-distribution umum.
- Attribution, lisensi, URL sumber, SHA-256, dan ukuran file dicatat di `metadata.csv`.
- Seluruh gambar berstatus `external_validation_only` dan `unlabeled`.

Gambar ini tidak otomatis masuk training dan tidak boleh dipakai menghitung supervised accuracy sebelum diberi label kematangan oleh manusia. Folder gambar tetap diabaikan Git untuk mencegah penyimpanan aset eksternal/besar di repository.

## Dataset tabular

Dataset tabular contoh di `data/sample/` bersifat sintetis. Dataset produksi sebaiknya longitudinal per tanaman/tandan dan mencakup setidaknya:

```text
image_id
plant_id
bunch_id
flowering_date
photo_date
days_after_flowering
maturity_stage
maturity_score
harvest_date
arrival_date
```
