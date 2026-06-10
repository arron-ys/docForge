import { httpClient } from "@/api/httpClient";
import { mapRunListItem, mapWorkspace } from "@/api/viewModelMapper";
import type { CreateRunApi, RunListApi } from "@/api/apiTypes";
import type { RunListItem, WorkspaceState } from "@/types/workspace";

export async function listRuns(): Promise<RunListItem[]> {
  const response = await httpClient.get<RunListApi>("/runs");
  return response.data.runs.map(mapRunListItem);
}

export async function createRun(projectName?: string): Promise<{
  run: RunListItem;
  workspace: WorkspaceState;
}> {
  const response = await httpClient.post<CreateRunApi>("/runs", {
    project_name: projectName?.trim() || undefined,
  });
  return {
    run: mapRunListItem(response.data.run),
    workspace: mapWorkspace(response.data.workspace),
  };
}
