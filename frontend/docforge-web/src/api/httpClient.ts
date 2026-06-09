import axios, { AxiosError } from "axios";

import type { ApiErrorResponse } from "@/api/apiTypes";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api";

export class DocForgeApiError extends Error {
  readonly errorCode: string;
  readonly recoverable: boolean;
  readonly suggestedAction: string;
  readonly status?: number;

  constructor(payload: ApiErrorResponse, status?: number) {
    super(payload.message);
    this.name = "DocForgeApiError";
    this.errorCode = payload.error_code;
    this.recoverable = payload.recoverable;
    this.suggestedAction = payload.suggested_action;
    this.status = status;
  }
}

export const apiBaseUrl =
  import.meta.env.VITE_DOCFORGE_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;

export const useMockApi = import.meta.env.VITE_DOCFORGE_USE_MOCK === "true";

export const httpClient = axios.create({
  baseURL: apiBaseUrl,
  timeout: 30_000,
});

httpClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorResponse>) => {
    const payload = error.response?.data;
    if (isApiErrorResponse(payload)) {
      return Promise.reject(new DocForgeApiError(payload, error.response?.status));
    }

    const fallback: ApiErrorResponse = {
      error_code: "network_error",
      message: "无法连接 DocForge API，请确认 FastAPI 服务已启动。",
      recoverable: true,
      suggested_action: "启动 python -m uvicorn api.main:app --reload 后重试。",
    };
    return Promise.reject(new DocForgeApiError(fallback, error.response?.status));
  },
);

function isApiErrorResponse(value: unknown): value is ApiErrorResponse {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<ApiErrorResponse>;
  return (
    typeof candidate.error_code === "string" &&
    typeof candidate.message === "string" &&
    typeof candidate.recoverable === "boolean" &&
    typeof candidate.suggested_action === "string"
  );
}
