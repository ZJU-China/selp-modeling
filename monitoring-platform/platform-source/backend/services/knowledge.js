// Local knowledge base for the AI chat ("ask about the platform"). Loads the
// markdown docs under <repo>/docs (plus README.md) once at startup, splits each
// file into heading-delimited chunks, and does a lightweight keyword-overlap
// search against a user question. The best-matching chunks are passed to the
// LLM (llm-client) alongside the question so answers stay grounded in the docs.
import { readdir, readFile } from "fs/promises"
import { join, dirname } from "path"
import { fileURLToPath } from "url"

const __dirname = dirname(fileURLToPath(import.meta.url))
// Repo root: backend/services/../.. -> <repo>. Docs live at <repo>/docs.
const REPO_ROOT = join(__dirname, "..", "..")
const DOCS_DIR = process.env.MD_DOCS_DIR || join(REPO_ROOT, "docs")

const MAX_CHARS_PER_CHUNK = 4000
const MAX_CHUNKS = 8

// ---- chunking --------------------------------------------------------------

// Split a markdown file into chunks on heading lines, keeping the heading
// hierarchy as context. Returns [{ file, heading, path, text }].
async function chunkMarkdown(file, relPath, content) {
  const lines = content.split("\n")
  const chunks = []
  let heading = ""
  let buffer = []
  const flush = () => {
    const text = buffer.join("\n").trim()
    if (text) chunks.push({ file, path: relPath, heading, text })
  }
  for (const line of lines) {
    if (/^#{1,4}\s/.test(line)) {
      flush()
      heading = line.replace(/^#{1,4}\s+/, "").replace(/[#*`]/g, "").trim()
      buffer = [line]
      continue
    }
    buffer.push(line)
    // Hard cap a single chunk so pathological sections don't blow the prompt.
    if (buffer.join("\n").length >= MAX_CHARS_PER_CHUNK) flush()
  }
  flush()
  return chunks
}

async function loadDocs() {
  const chunks = []
  let files = []
  try {
    files = (await readdir(DOCS_DIR)).filter(f => /\.md$/.test(f)).sort()
  } catch {}
  const extras = []
  try { extras.push({ rel: "README.md", path: join(REPO_ROOT, "README.md") }) } catch {}
  const all = [
    ...files.map(f => ({ rel: f, path: join(DOCS_DIR, f) })),
    ...extras,
  ]
  for (const { rel, path } of all) {
    try {
      const content = await readFile(path, "utf8")
      chunks.push(...await chunkMarkdown(rel, `docs/${rel}`, content))
    } catch {}
  }
  // Fall back to the whole docs dir listing so chat still shows something even
  // if individual files fail to read.
  if (chunks.length === 0) {
    chunks.push({ file: "docs", path: "docs/", heading: "", text: files.join("\n") })
  }
  return chunks
}

let cache = null

async function getChunks() {
  if (!cache) cache = await loadDocs()
  return cache
}

// ---- retrieval -------------------------------------------------------------

// Tokenise a query into meaningful keywords (split on non-alphanumeric,
// lowercase, drop very short/stop-ish words). Good enough for recall on a
// ~4k-line doc corpus without an embedding service.
function tokenize(text) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, " ")
    .split(/\s+/)
    .filter(w => w.length > 1)
}

const STOPWORDS = new Set([
  "the", "and", "for", "are", "how", "what", "why", "with", "that", "this",
  "from", "your", "you", "can", "file", "files", "docs", "please", "about",
  "平台", "如何", "怎么", "什么", "问题", "这个", "那个", "一下", "了解",
])

function normalized(words) {
  return words.filter(w => !STOPWORDS.has(w))
}

// Score a chunk against a query: count overlapping keywords, weighted by
// frequency and by how early the terms appear; headings count double.
function scoreChunk(chunk, tokens) {
  const text = `${chunk.heading}\n${chunk.text}`.toLowerCase()
  let score = 0
  for (const tok of tokens) {
    let count = 0
    let idx = text.indexOf(tok)
    while (idx !== -1) { count++; idx = text.indexOf(tok, idx + tok.length) }
    if (count === 0) continue
    const headingBoost = chunk.heading.toLowerCase().includes(tok) ? 2 : 1
    score += count * headingBoost
  }
  return score
}

// Return up to MAX_CHUNKS chunks best matching the question.
export async function searchChunks(question, max = MAX_CHUNKS) {
  const tokens = normalized(tokenize(question))
  const chunks = await getChunks()
  if (tokens.length === 0) return chunks.slice(0, Math.min(3, chunks.length))
  const scored = chunks
    .map(c => ({ chunk: c, score: scoreChunk(c, tokens) }))
    .filter(s => s.score > 0)
    .sort((a, b) => b.score - a.score)
  return scored.slice(0, max).map(s => s.chunk)
}

export async function listDocs() {
  const chunks = await getChunks()
  const byFile = new Map()
  for (const c of chunks) {
    const e = byFile.get(c.path) || { path: c.path, chunks: 0 }
    e.chunks++
    byFile.set(c.path, e)
  }
  return [...byFile.values()].sort((a, b) => a.path.localeCompare(b.path))
}