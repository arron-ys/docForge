import { httpClient } from "@/api/httpClient";
import { mapWorkspace } from "@/api/viewModelMapper";
import type { WorkspaceApi } from "@/api/apiTypes";
import type { WorkspaceState } from "@/types/workspace";

export async function fetchWorkspace(runId: string): Promise<WorkspaceState> {
  const response = await httpClient.get<WorkspaceApi>(`/workspace/${encodeURIComponent(runId)}`);
  return mapWorkspace(response.data);
}
