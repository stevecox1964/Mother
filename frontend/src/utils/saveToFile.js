export function saveToFile(content, prefix) {
  const now = new Date();
  const dt = now
    .toISOString()
    .replace(/T/, "_")
    .replace(/:/g, "-")
    .split(".")[0];
  const filename = `${prefix}_${dt}.txt`;
  const blob = new Blob([content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
