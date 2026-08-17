import { predictBanana } from "@/lib/prediction";

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

export async function POST(request: Request) {
  try {
    const form = await request.formData();
    const floweringDate = form.get("flowering_date");
    const photoDate = form.get("photo_date");
    const targetMaturity = Number(form.get("target_maturity"));
    const image = form.get("image");

    if (typeof floweringDate !== "string" || typeof photoDate !== "string") {
      return Response.json({ error: "Flowering date and photo date are required." }, { status: 400 });
    }
    if (!Number.isFinite(targetMaturity) || targetMaturity < 1 || targetMaturity > 7) {
      return Response.json({ error: "Target maturity must be between 1 and 7." }, { status: 400 });
    }
    if (!(image instanceof File) || image.size === 0 || !image.type.startsWith("image/")) {
      return Response.json({ error: "Upload a valid banana image." }, { status: 400 });
    }
    if (image.size > MAX_IMAGE_BYTES) {
      return Response.json({ error: "Image must be 10 MB or smaller." }, { status: 413 });
    }

    return Response.json(await predictBanana({ floweringDate, photoDate, targetMaturity }));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Prediction failed.";
    return Response.json({ error: message }, { status: 400 });
  }
}
