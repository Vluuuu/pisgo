import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { AiApiError, predictWithAiApi } from "./ai-api.ts";
import type { PredictionRequest } from "../../types/prediction.ts";

describe("predictWithAiApi", () => {
  const sampleRequest: PredictionRequest = {
    floweringDate: "2026-06-01",
    photoDate: "2026-08-20",
    targetMaturity: 4,
    image: new Blob(["fake-image-bytes"], { type: "image/jpeg" }),
  };

  it("throws configuration error when AI_API_BASE_URL is missing and no baseUrl provided", async () => {
    const original = process.env.AI_API_BASE_URL;
    delete process.env.AI_API_BASE_URL;

    try {
      await assert.rejects(
        async () => {
          await predictWithAiApi(sampleRequest);
        },
        (error: unknown) => {
          assert(error instanceof AiApiError);
          assert.equal(error.status, 503);
          assert.equal(error.code, "CONFIG_MISSING");
          return true;
        }
      );
    } finally {
      process.env.AI_API_BASE_URL = original;
    }
  });

  it("forwards correct multipart/form-data field names and image", async () => {
    let capturedUrl = "";
    let capturedMethod = "";
    let capturedBody: unknown = null;

    const mockFetch = (async (url: string | URL | Request, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedMethod = init?.method ?? "";
      capturedBody = init?.body;

      const mockResponse = {
        banana_detected: true,
        cultivar: "cavendish",
        days_after_flowering: 80,
        current_maturity: 3.8,
        confidence: 0.94,
        days_to_target: 12.5,
        model_version: "cavendish-v1",
        adapter_version: "pisgo-ai-api-v1",
        debug: {
          predicted_class: "half_ripe",
          class_probabilities: { unripe: 0.1, half_ripe: 0.8, ripe: 0.08, overripe: 0.02 },
          maturity_class_scale: { unripe: 2.0, half_ripe: 3.5, ripe: 5.5, overripe: 6.5 },
          foreground_proxy_ratio: 0.3,
          banana_detection_threshold: 0.02,
          detection_method: "foreground-color-heuristic-proxy",
          inference_milliseconds: 25.0,
        },
      };

      return new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;

    const result = await predictWithAiApi(sampleRequest, {
      baseUrl: "http://127.0.0.1:8001",
      fetchImpl: mockFetch,
    });

    assert.equal(capturedUrl, "http://127.0.0.1:8001/v1/predict");
    assert.equal(capturedMethod, "POST");
    assert(capturedBody instanceof FormData);
    const form = capturedBody as FormData;
    assert.equal(form.get("flowering_date"), "2026-06-01");
    assert.equal(form.get("photo_date"), "2026-08-20");
    assert.equal(form.get("target_maturity"), "4");
    const forwardedImage = form.get("image");
    assert(forwardedImage !== null);

    assert.equal(result.banana_detected, true);
    if (result.banana_detected) {
      assert.equal(result.current_maturity, 3.8);
      assert.equal(result.confidence, 0.94);
      assert.equal(result.days_to_target, 12.5);
    }
  });

  it("parses no-banana response defensively and preserves null-safety", async () => {
    const mockFetch = (async () => {
      const mockResponse = {
        banana_detected: false,
        cultivar: "cavendish",
        days_after_flowering: 80,
        current_maturity: null,
        confidence: null,
        days_to_target: null,
        model_version: "cavendish-v1",
        adapter_version: "pisgo-ai-api-v1",
        debug: {
          predicted_class: "unripe",
          class_probabilities: { unripe: 0.9, half_ripe: 0.1, ripe: 0.0, overripe: 0.0 },
          maturity_class_scale: { unripe: 2.0, half_ripe: 3.5, ripe: 5.5, overripe: 6.5 },
          foreground_proxy_ratio: 0.005,
          banana_detection_threshold: 0.02,
          detection_method: "foreground-color-heuristic-proxy",
          inference_milliseconds: 10.0,
        },
      };

      return new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;

    const result = await predictWithAiApi(sampleRequest, {
      baseUrl: "http://127.0.0.1:8001",
      fetchImpl: mockFetch,
    });

    assert.equal(result.banana_detected, false);
    if (!result.banana_detected) {
      assert.equal(result.current_maturity, null);
      assert.equal(result.confidence, null);
      assert.equal(result.days_to_target, null);
    }
  });

  it("handles upstream 400 Bad Request error cleanly", async () => {
    const mockFetch = (async () => {
      return new Response(JSON.stringify({ error: "image file is empty." }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;

    await assert.rejects(
      async () => {
        await predictWithAiApi(sampleRequest, {
          baseUrl: "http://127.0.0.1:8001",
          fetchImpl: mockFetch,
        });
      },
      (err: unknown) => {
        assert(err instanceof AiApiError);
        assert.equal(err.status, 400);
        assert.equal(err.code, "BAD_REQUEST");
        assert(err.message.includes("image file is empty"));
        return true;
      }
    );
  });

  it("handles upstream 413 Payload Too Large error cleanly", async () => {
    const mockFetch = (async () => {
      return new Response(JSON.stringify({ error: "image must be 10 MB or smaller." }), {
        status: 413,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;

    await assert.rejects(
      async () => {
        await predictWithAiApi(sampleRequest, {
          baseUrl: "http://127.0.0.1:8001",
          fetchImpl: mockFetch,
        });
      },
      (err: unknown) => {
        assert(err instanceof AiApiError);
        assert.equal(err.status, 413);
        assert.equal(err.code, "PAYLOAD_TOO_LARGE");
        return true;
      }
    );
  });

  it("handles upstream 422 Unprocessable Entity error cleanly", async () => {
    const mockFetch = (async () => {
      return new Response(JSON.stringify({ error: "photo_date must not be earlier than flowering_date." }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;

    await assert.rejects(
      async () => {
        await predictWithAiApi(sampleRequest, {
          baseUrl: "http://127.0.0.1:8001",
          fetchImpl: mockFetch,
        });
      },
      (err: unknown) => {
        assert(err instanceof AiApiError);
        assert.equal(err.status, 422);
        assert.equal(err.code, "UNPROCESSABLE_ENTITY");
        assert(err.message.includes("photo_date must not be earlier than flowering_date"));
        return true;
      }
    );
  });

  it("handles upstream 503 Service Unavailable when model is not loaded", async () => {
    const mockFetch = (async () => {
      return new Response(JSON.stringify({ error: "Model artifact not loaded: [Errno 2] No such file" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;

    await assert.rejects(
      async () => {
        await predictWithAiApi(sampleRequest, {
          baseUrl: "http://127.0.0.1:8001",
          fetchImpl: mockFetch,
        });
      },
      (err: unknown) => {
        assert(err instanceof AiApiError);
        assert.equal(err.status, 503);
        assert.equal(err.code, "SERVICE_UNAVAILABLE");
        return true;
      }
    );
  });

  it("handles network connection failure gracefully without exposing internal URLs", async () => {
    const mockFetch = (async () => {
      throw new Error("fetch failed: ECONNREFUSED 127.0.0.1:8001");
    }) as unknown as typeof fetch;

    await assert.rejects(
      async () => {
        await predictWithAiApi(sampleRequest, {
          baseUrl: "http://127.0.0.1:8001",
          fetchImpl: mockFetch,
        });
      },
      (err: unknown) => {
        assert(err instanceof AiApiError);
        assert.equal(err.status, 502);
        assert.equal(err.code, "CONNECTION_ERROR");
        assert(!err.message.includes("127.0.0.1:8001"));
        return true;
      }
    );
  });

  it("handles timeout abort cleanly", async () => {
    const mockFetch = (async (_url: string | URL | Request, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          const abortError = new Error("The operation was aborted");
          abortError.name = "AbortError";
          reject(abortError);
        });
      });
    }) as unknown as typeof fetch;

    await assert.rejects(
      async () => {
        await predictWithAiApi(sampleRequest, {
          baseUrl: "http://127.0.0.1:8001",
          fetchImpl: mockFetch,
          timeoutMs: 20,
        });
      },
      (err: unknown) => {
        assert(err instanceof AiApiError);
        assert.equal(err.status, 504);
        assert.equal(err.code, "TIMEOUT");
        return true;
      }
    );
  });
});
