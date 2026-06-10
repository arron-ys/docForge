import { httpClient } from "@/api/httpClient";
import type {
  ModelConfigApi,
  SaveModelConfigPayloadApi,
  TestModelConnectionPayloadApi,
  TestModelConnectionResultApi,
} from "@/api/apiTypes";

export async function getModelConfig(): Promise<ModelConfigApi> {
  const response = await httpClient.get<ModelConfigApi>("/model-config");
  return response.data;
}

export async function saveModelConfig(
  payload: SaveModelConfigPayloadApi,
): Promise<ModelConfigApi> {
  const response = await httpClient.post<ModelConfigApi>("/model-config", payload);
  return response.data;
}

export async function testLlmConnection(
  payload: TestModelConnectionPayloadApi,
): Promise<TestModelConnectionResultApi> {
  const response = await httpClient.post<TestModelConnectionResultApi>(
    "/model-config/test-llm",
    payload,
  );
  return response.data;
}

export async function testEmbeddingConnection(
  payload: TestModelConnectionPayloadApi,
): Promise<TestModelConnectionResultApi> {
  const response = await httpClient.post<TestModelConnectionResultApi>(
    "/model-config/test-embedding",
    payload,
  );
  return response.data;
}
