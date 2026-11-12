// LLM client for the task guard. Talks to any OpenAI-compatible chat
// completions endpoint (llama.cpp server, vLLM, Ollama, ...).
//
// Default endpoint is the iGEM-facing llama.cpp on the wanglab server:
//   http://127.0.0.1:8080  (model Nemotron-3-Nano-30B-A3B)
//
// Nemotron is chosen as the default because it reliably returns `content`
// with the requested JSON. The Qwen3.5 / DeepSeek-R1 models on the same
// server are heavy reasoning models that spend the whole token budget on
// thinking, often leaving `content` empty for structured tasks.
//
// Override via backend/llm.json (git-ignored):
//   {
//     "baseUrl": "http://127.0.0.1:8080",
//     "apiKey": "",                        // llama.cpp: none
//     "model": "Nemotron-3-Nano-30B-A3B",
//     "timeoutMs": 120000
//   }
import { readFileSync, existsSync } from "fs"
import { dirname, join } from "path"
import { fileURLToPath } from "url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const CONFIG_PATH = process.env.MD_LLM_CONFIG || join(__dirname, "..", "llm.json")

const DEFAULTS = {
  baseUrl: "http://127.0.0.1:8080",
  apiKey: "",
  model: "Nemotron-3-Nano-30B-A3B",
  timeoutMs: 120000,
  // The wanglab llama.cpp server can unload the model from VRAM after a period
  // of inactivity (e.g. 300s). The first request after idle has to reload the
  // model into VRAM (cold start), which can take well over the normal timeout.
  // Retrying once with the same timeout gives the cold start a real chance
  // instead of the guard bailing out to a fail-safe "report".
  retry: 1,
}

function loadConfig() {
  try {
    if (existsSync(CONFIG_PATH)) {
      return { ...DEFAULTS, ...JSON.parse(readFileSync(CONFIG_PATH, "utf8")) }
    }
  } catch {}
  return { ...DEFAULTS }
}

export function getLlmConfig() {
  return loadConfig()
}

// Chat completion. Returns the assistant text. Throws on HTTP/transport error.
export async function complete({ messages, temperature = 0.2, maxTokens = 512, json = false }) {
  const cfg = loadConfig()
  const url = `${cfg.baseUrl.replace(/\/$/, "")}/v1/chat/completions`

  const body = {
    model: cfg.model,
    messages,
    temperature,
    max_tokens: maxTokens,
    // llama.cpp: keep reasoning separate so `content` carries the answer
    // rather than only reasoning_content (some models think by default).
    think: false,
  }
  if (json) {
    body.response_format = { type: "json_object" }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), cfg.timeoutMs)
  let res
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
  } catch (e) {
    clearTimeout(timer)
    throw new Error(`LLM request failed: ${e.message}`)
  }
  clearTimeout(timer)

  // Non-2xx: give a cold-start retry a shot before giving up. Some servers
  // return 503/connection-reset while the model reloads from idle.
  if (!res.ok && cfg.retry > 0) {
    const text = (await res.text()).slice(0, 300)
    for (let attempt = 1; attempt <= cfg.retry; attempt++) {
      const c2 = new AbortController()
      const t2 = setTimeout(() => c2.abort(), cfg.timeoutMs)
      try {
        const retryRes = await fetch(url, {
          method: "POST", headers: { "Content-Type": "application/json", ...(cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {}) },
          body: JSON.stringify(body), signal: c2.signal,
        })
        if (retryRes.ok) {
          const data = await retryRes.json()
          return (data?.choices?.[0]?.message?.content ?? "").trim()
        }
      } catch {} finally { clearTimeout(t2) }
    }
    throw new Error(`LLM HTTP ${res.status}: ${text}`)
  }

  if (!res.ok) {
    const text = (await res.text()).slice(0, 500)
    throw new Error(`LLM HTTP ${res.status}: ${text}`)
  }

  const data = await res.json()
  const content = data?.choices?.[0]?.message?.content ?? ""
  return content.trim()
}

// Round-trip health check against the configured endpoint.
export async function ping() {
  const cfg = loadConfig()
  const text = await complete({
    messages: [{ role: "user", content: "Reply with exactly: OK" }],
    maxTokens: 256,
    temperature: 0,
  })
  return { ok: text.includes("OK"), reply: text, config: cfg }
}
