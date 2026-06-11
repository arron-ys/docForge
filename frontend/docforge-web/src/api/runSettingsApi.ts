import { httpClient } from "@/api/httpClient";
import { mapWorkspace } from "@/api/viewModelMapper";
import type { ActionResultApi } from "@/api/apiTypes";
import type { WorkspaceSettings, WorkspaceState } from "@/types/workspace";

export async function saveRunSettings(
  runId: string,
  settings: WorkspaceSettings,
  restartStrategy: boolean,
): Promise<{ message: string; workspace: WorkspaceState | null }> {
  const endpoint = restartStrategy ? "restart-strategy" : "settings";
  const response = await httpClient.post<ActionResultApi>(
    `/runs/${encodeURIComponent(runId)}/${endpoint}`,
    {
      product_type_hint: settings.productTypeHint,
      doc_output_type: settings.docOutputType,
      reference_style_strength: settings.referenceStyleStrength,
    },
  );
  return {
    message: response.data.message,
    workspace: response.data.workspace ? mapWorkspace(response.data.workspace) : null,
  };
}
