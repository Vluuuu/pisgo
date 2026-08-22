import { AiApiError, predictBanana } from "@/lib/prediction";

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

export async function POST(request: Request) {
  try {
    const form = await request.formData();
    const floweringDate = form.get("flowering_date");
    const photoDate = form.get("photo_date");
    const targetMaturity = Number(form.get("target_maturity"));
    const image = form.get("image");

    if (typeof floweringDate !== "string" || typeof photoDate !== "string") {
      return Response.json({ error: "Tanggal berbunga dan tanggal foto wajib diisi." }, { status: 400 });
    }
    if (!Number.isFinite(targetMaturity) || targetMaturity < 1 || targetMaturity > 7) {
      return Response.json({ error: "Target kematangan harus berada di antara 1 dan 7." }, { status: 400 });
    }
    if (!(image instanceof File && image.size > 0 && (image.type.startsWith("image/") || image.name.match(/\.(jpe?g|png|webp)$/i)))) {
      return Response.json({ error: "Unggah berkas foto pisang yang valid (JPG, PNG, WebP)." }, { status: 400 });
    }
    if (image.size > MAX_IMAGE_BYTES) {
      return Response.json({ error: "Ukuran foto tidak boleh lebih dari 10 MB." }, { status: 413 });
    }

    const prediction = await predictBanana({
      floweringDate,
      photoDate,
      targetMaturity,
      image,
    });

    return Response.json(prediction);
  } catch (error) {
    if (error instanceof AiApiError) {
      return Response.json({ error: error.message, code: error.code }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Gagal memproses prediksi.";
    return Response.json({ error: message }, { status: 500 });
  }
}
