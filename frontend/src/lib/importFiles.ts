/**
 * Turning a browser file/folder pick into something importable.
 *
 * The browser hands over *everything* the person selected. Choosing a real
 * project folder means tens of thousands of `File` objects, the overwhelming
 * majority of them inside `node_modules`. Reading those to text would freeze
 * the tab long before the upload was ever attempted, so this filters on path
 * first and only reads what survives.
 *
 * The server applies the same rules again (`import_skip_reason`). This copy is
 * there to keep the browser responsive, not to enforce anything — a limit that
 * only exists in the client is a suggestion.
 */

/** Directories that are never worth importing into an editor. */
const SKIP_DIRS = new Set([
  "node_modules", ".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__",
  ".pytest_cache", ".mypy_cache", ".ruff_cache", "venv", ".venv", "env",
  "dist", "build", "out", "target", "coverage", ".next", ".nuxt", ".cache",
  "vendor", "Pods", ".terraform", "bin", "obj", ".gradle", ".tox", "site-packages",
]);

const SKIP_SUFFIXES = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svgz", ".tiff",
  ".pdf", ".zip", ".gz", ".tar", ".rar", ".7z", ".jar", ".war", ".bz2", ".xz",
  ".exe", ".dll", ".so", ".dylib", ".bin", ".class", ".pyc", ".pyo", ".o", ".a",
  ".mp3", ".mp4", ".mov", ".avi", ".wav", ".flac", ".webm", ".mkv", ".ogg",
  ".ttf", ".otf", ".woff", ".woff2", ".eot",
  ".db", ".sqlite", ".sqlite3", ".pkl", ".npy", ".parquet", ".wasm",
  ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
]);

const SKIP_NAMES = new Set([
  "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
  "Cargo.lock", "composer.lock", "Gemfile.lock", ".DS_Store", "Thumbs.db",
]);

const MAX_FILE_BYTES = 512_000;
/** Read at most this many files, so a mis-click on a huge folder still ends. */
export const MAX_IMPORT_FILES = 400;

export interface Skipped { path: string; reason: string }
export interface Prepared {
  files: { path: string; content: string }[];
  skipped: Skipped[];
  /** Folder name the browser reported, usable as a project name. */
  rootName: string;
}

/** The path a File should be stored under: its folder-relative path if the
 *  directory picker gave one, otherwise just its name. */
function relPath(f: File): string {
  const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath;
  return (rel && rel.length > 0 ? rel : f.name).replace(/\\/g, "/");
}

function suffixOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i <= 0 ? "" : name.slice(i).toLowerCase();
}

/** Why this file should not be imported, judged from its path alone — no read. */
function skipByPath(path: string, size: number): string | null {
  const parts = path.split("/");
  for (const seg of parts.slice(0, -1)) {
    if (SKIP_DIRS.has(seg)) return `inside ${seg}/`;
  }
  const name = parts[parts.length - 1];
  if (SKIP_NAMES.has(name)) return "generated file";
  if (SKIP_SUFFIXES.has(suffixOf(name))) return "not a text file";
  if (size > MAX_FILE_BYTES) return `larger than ${MAX_FILE_BYTES / 1000} KB`;
  return null;
}

/**
 * Filter, read and package a browser file selection.
 *
 * `onProgress` fires as files are read so a large folder can show progress
 * rather than looking hung.
 */
export async function prepareImport(
  fileList: FileList | File[],
  onProgress?: (done: number, total: number) => void,
): Promise<Prepared> {
  const all = Array.from(fileList);
  const skipped: Skipped[] = [];
  const keep: File[] = [];

  // Pass one: paths only. This is what keeps a node_modules pick survivable.
  for (const f of all) {
    const path = relPath(f);
    const reason = skipByPath(path, f.size);
    if (reason) skipped.push({ path, reason });
    else keep.push(f);
  }

  // The folder the person actually picked — first segment of any nested path.
  const firstNested = keep.concat(all).map(relPath).find((p) => p.includes("/"));
  const rootName = firstNested ? firstNested.split("/")[0] : "";

  const over = keep.slice(MAX_IMPORT_FILES);
  for (const f of over) skipped.push({ path: relPath(f), reason: "over the import limit" });
  const toRead = keep.slice(0, MAX_IMPORT_FILES);

  const files: { path: string; content: string }[] = [];
  let done = 0;
  for (const f of toRead) {
    const path = relPath(f);
    try {
      const content = await f.text();
      // Extension checks miss a compiled artefact named .dat or with no
      // extension at all; a NUL byte is the reliable tell.
      if (content.includes("\u0000")) skipped.push({ path, reason: "looks binary" });
      else files.push({ path, content });
    } catch {
      skipped.push({ path, reason: "could not be read" });
    }
    onProgress?.(++done, toRead.length);
  }

  return { files, skipped, rootName };
}

/** Pull every file out of a drag-and-drop, walking into dropped folders.
 *
 *  `DataTransfer.files` is flat and omits folder contents entirely, so a
 *  dropped directory would silently import nothing. The entries API is the
 *  only way to descend into it. */
export async function filesFromDrop(dt: DataTransfer): Promise<File[]> {
  const items = Array.from(dt.items || []);
  const entries = items
    .map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null))
    .filter((e): e is FileSystemEntry => e !== null);

  if (entries.length === 0) return Array.from(dt.files || []);

  const out: File[] = [];
  const walk = async (entry: FileSystemEntry, prefix: string): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File | null>((res) =>
        (entry as FileSystemFileEntry).file((f) => res(f), () => res(null)));
      if (file) {
        // Carry the folder-relative path the same way the directory picker does,
        // so both routes produce identical paths downstream.
        Object.defineProperty(file, "webkitRelativePath", {
          value: prefix + file.name, configurable: true,
        });
        out.push(file);
      }
      return;
    }
    if (!entry.isDirectory) return;
    if (SKIP_DIRS.has(entry.name)) return;        // never descend into node_modules
    if (out.length > MAX_IMPORT_FILES * 4) return; // a runaway tree still terminates

    const reader = (entry as FileSystemDirectoryEntry).createReader();
    // readEntries returns at most ~100 per call and must be drained.
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((res) =>
        reader.readEntries((e) => res(e), () => res([])));
      if (batch.length === 0) break;
      for (const child of batch) await walk(child, `${prefix}${entry.name}/`);
    }
  };

  for (const e of entries) await walk(e, "");
  return out;
}
