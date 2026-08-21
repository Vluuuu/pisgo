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
