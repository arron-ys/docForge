import { httpClient } from "@/api/httpClient";

export async function downloadArtifact(artifactId: string): Promise<void> {
  const response = await httpClient.get<Blob>(
    `/artifacts/${encodeURIComponent(artifactId)}/download`,
    { responseType: "blob" },
  );
  const fileName = filenameFromDisposition(response.headers["content-disposition"]) ?? "docforge.docx";
  const blobUrl = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(blobUrl);
}

function filenameFromDisposition(disposition: string | undefined): string | null {
  if (!disposition) {
    return null;
  }

  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (utf8Match) {
    return decodeURIComponent(utf8Match[1]);
  }

  const asciiMatch = /filename="?([^";]+)"?/i.exec(disposition);
  return asciiMatch?.[1] ?? null;
}
