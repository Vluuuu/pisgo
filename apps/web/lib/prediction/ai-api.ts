import type { PredictionRequest, PredictionResponse } from "@/types/prediction";

export class AiApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, status = 500, code = "AI_API_ERROR") {
    super(message);
    this.name = "AiApiError";
    this.status = status;
    this.code = code;
  }
}

const DEFAULT_TIMEOUT_MS = 15000;

/**
 * Normalizes base URL by stripping trailing slashes.
 */
function getAiApiBaseUrl(): string {
  const rawUrl = process.env.AI_API_BASE_URL;
  if (!rawUrl || rawUrl.trim() === "") {
    throw new AiApiError(
      "Layanan AI belum dikonfigurasi. Pastikan AI_API_BASE_URL telah disetel pada server.",
      503,
      "CONFIG_MISSING"
    );
  }
  return rawUrl.trim().replace(/\/+$/, "");
}

/**
 * Predicts banana maturity by forwarding specimen image and agronomic dates
 * to the FastAPI maturity inference service.
 */
export async function predictWithAiApi(
  input: PredictionRequest,
  options?: { timeoutMs?: number; fetchImpl?: typeof fetch; baseUrl?: string }
): Promise<PredictionResponse> {
  const baseUrl = options?.baseUrl ?? getAiApiBaseUrl();
  const fetchFn = options?.fetchImpl ?? fetch;
  const timeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const form = new FormData();
  form.set("flowering_date", input.floweringDate);
  form.set("photo_date", input.photoDate);
  form.set("target_maturity", String(input.targetMaturity));

  if (input.image instanceof File) {
    form.set("image", input.image, input.image.name);
  } else if (input.image instanceof Blob) {
    form.set("image", input.image, "specimen.jpg");
  } else {
    clearTimeout(timeoutId);
    throw new AiApiError("Berkas foto pisang tidak valid.", 400, "INVALID_IMAGE");
  }

  let response: Response;
  try {
    response = await fetchFn(`${baseUrl}/v1/predict`, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
  } catch (error: unknown) {
    clearTimeout(timeoutId);
    if (error instanceof Error && error.name === "AbortError") {
      throw new AiApiError(
        "Permintaan inferensi AI melebihi batas waktu (timeout).",
        504,
        "TIMEOUT"
      );
    }
    throw new AiApiError(
      "Gagal terhubung ke layanan inferensi AI.",
      502,
      "CONNECTION_ERROR"
    );
  } finally {
    clearTimeout(timeoutId);
  }

  let rawBody = "";
  try {
    rawBody = await response.text();
  } catch {
    throw new AiApiError("Gagal membaca respons dari layanan AI.", 502, "RESPONSE_READ_ERROR");
  }

  let json: unknown;
  try {
    json = rawBody ? JSON.parse(rawBody) : null;
  } catch {
    throw new AiApiError(
      "Layanan AI mengembalikan respons yang tidak valid.",
      502,
      "INVALID_JSON"
    );
  }

  if (!response.ok) {
    const errorDetail =
      json && typeof json === "object" && "error" in json && typeof (json as { error: unknown }).error === "string"
        ? (json as { error: string }).error
        : json && typeof json === "object" && "detail" in json && typeof (json as { detail: unknown }).detail === "string"
        ? (json as { detail: string }).detail
        : `Layanan AI mengembalikan status ${response.status}.`;

    // Map upstream HTTP status codes cleanly without exposing internal details
    if (response.status === 400) {
      throw new AiApiError(`Data foto atau parameter tidak valid: ${errorDetail}`, 400, "BAD_REQUEST");
    }
    if (response.status === 413) {
      throw new AiApiError("Ukuran foto melebihi batas maksimal 10 MB.", 413, "PAYLOAD_TOO_LARGE");
    }
    if (response.status === 422) {
      throw new AiApiError(`Parameter inferensi tidak valid: ${errorDetail}`, 422, "UNPROCESSABLE_ENTITY");
    }
    if (response.status === 503) {
      throw new AiApiError("Layanan model AI sedang tidak tersedia atau model belum dimuat.", 503, "SERVICE_UNAVAILABLE");
    }

    throw new AiApiError(`Gagal memproses inferensi AI (${response.status}).`, response.status >= 500 ? 502 : response.status, "UPSTREAM_ERROR");
  }

  if (!json || typeof json !== "object") {
    throw new AiApiError("Format data inferensi AI tidak sesuai.", 502, "SCHEMA_MISMATCH");
  }

  const payload = json as Partial<PredictionResponse>;
  if (typeof payload.banana_detected !== "boolean") {
    throw new AiApiError("Data inferensi kehilangan status deteksi pisang.", 502, "SCHEMA_MISMATCH");
  }

  return json as PredictionResponse;
}
