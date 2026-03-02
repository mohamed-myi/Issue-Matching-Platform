import axios, { AxiosError } from "axios";
import { ensureMockApiReady } from "@/lib/mocks/runtime";
import { getApiBaseUrl } from "./base-url";
import type { ApiErrorPayload } from "./types";

export const api = axios.create({
  baseURL: getApiBaseUrl(),
  withCredentials: true,
  timeout: 10_000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use(async (config) => {
  await ensureMockApiReady();
  return config;
});

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiErrorPayload>;
    const detail = axiosError.response?.data?.detail;
    if (detail) {
      return detail;
    }
    if (axiosError.message) {
      return axiosError.message;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return "Unknown error";
}
