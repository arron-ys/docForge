import { httpClient } from "@/api/httpClient";
import { mapSourceItem } from "@/api/viewModelMapper";
import type { FileUploadResultApi } from "@/api/apiTypes";
import type { SourceItem } from "@/types/workspace";

export type SourceUploadType = "reference" | "product" | "screenshots";

export async function uploadSource(
  runId: string,
  uploadType: SourceUploadType,
  file: File,
): Promise<SourceItem> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await httpClient.post<FileUploadResultApi>(
    `/runs/${encodeURIComponent(runId)}/sources/${uploadType}`,
    formData,
  );
  return mapSourceItem(response.data.source);
}
