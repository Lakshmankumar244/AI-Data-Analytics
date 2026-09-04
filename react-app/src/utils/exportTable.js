function csvEscape(value) {
  const text = String(value ?? "")
    .replace(/\u00a0/g, " ")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .trim();
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function rowsToCsv(rows = []) {
  return rows.map((row) => row.map(csvEscape).join(",")).join("\r\n");
}

export function downloadCsv(filename, csvText) {
  const blob = new Blob([`\uFEFF${csvText}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function exportTable(filename, headers = [], rows = []) {
  downloadCsv(filename, rowsToCsv([headers, ...rows]));
  return true;
}

function cellText(cell) {
  if (cell.querySelector(".records-empty-state, .sr-only")) {
    return [...cell.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => node.textContent)
      .join(" ")
      .trim();
  }
  return (cell.innerText || cell.textContent || "").replace(/\s+\n/g, "\n").trim();
}

export function tableElementToRows(table) {
  if (!table) return [];
  return [...table.querySelectorAll("tr")]
    .filter((row) => !row.querySelector(".records-empty-state"))
    .map((row) => [...row.querySelectorAll("th, td")].map(cellText))
    .filter((row) => row.some(Boolean));
}

function sectionTitle(table) {
  const caption = table.querySelector("caption:not(.sr-only)")?.innerText?.trim();
  if (caption) return caption;
  const section = table.closest("section");
  const heading = section?.querySelector("h2, .eyebrow")?.innerText?.trim();
  return heading || "";
}

export function exportTableElements(tables, basename) {
  const tableList = [...(tables || [])].filter(Boolean);
  const sections = tableList
    .map((table) => {
      const rows = tableElementToRows(table);
      if (!rows.length) return "";
      const title = tableList.length > 1 ? sectionTitle(table) : "";
      return title ? `${csvEscape(title)}\r\n${rowsToCsv(rows)}` : rowsToCsv(rows);
    })
    .filter(Boolean);
  if (!sections.length) return false;
  downloadCsv(basename, sections.join("\r\n\r\n"));
  return true;
}

export function exportVisibleTables(root, basename) {
  const scope = root || document;
  const tables = scope.querySelectorAll("table");
  return exportTableElements(tables, basename || "export");
}
