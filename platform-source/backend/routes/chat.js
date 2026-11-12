// AI chat ("ask about the platform"): answers questions grounded in the local
// docs/ knowledge base. Uses the same LLM client as the task guard.
import { Router } from "express"
import { complete } from "../services/llm-client.js"
import { searchChunks, listDocs } from "../services/knowledge.js"

const router = Router()

// List knowledge base documents / chunk counts (for the UI source list).
router.get("/docs", async (_req, res) => {
  try {
    res.json({ ok: true, docs: await listDocs() })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// Ask a question. Picks relevant doc chunks, asks the LLM to answer using them.
// Returns { answer, sources }: sources is the list of doc chunks actually used.
router.post("/ask", async (req, res) => {
  const question = String(req.body?.question || "").trim()
  if (!question) return res.status(400).json({ error: "question required" })

  try {
    const chunks = await searchChunks(question)
    if (chunks.length === 0) {
      // No doc chunk matched; still ask the model but tell it docs were empty.
      return answerWith(question, [], res)
    }

    const context = chunks
      .map((c, i) => `### [Source ${i + 1}] ${c.path}${c.heading ? " / " + c.heading : ""}\n${c.text}`)
      .join("\n\n---\n\n")

    const content = await complete({
      json: false,
      temperature: 0.2,
      maxTokens: 1024,
      messages: [
        { role: "system", content: "You are an assistant for the iGEM 2026 molecular dynamics platform (MD). Answer the user's question based ONLY on the provided document excerpts below. If the answer is not in the excerpts, say you don't have that information in the docs. Keep the answer concise, in the user's language, and cite which source you used by its [Source N] label." },
        { role: "user", content: `DOCUMENTS:\n${context}\n\nQUESTION: ${question}\n\nAnswer based on the documents above.` },
      ],
    })

    const sources = chunks.map((c, i) => ({ i: i + 1, path: c.path, heading: c.heading }))
    res.json({ ok: true, answer: content, sources })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

async function answerWith(question, chunks, res) {
  try {
    const content = await complete({
      json: false,
      temperature: 0.2,
      maxTokens: 512,
      messages: [
        { role: "system", content: "You are an assistant for the iGEM 2026 molecular dynamics platform. Answer concisely in the user's language." },
        { role: "user", content: question },
      ],
    })
    res.json({ ok: true, answer: content, sources: [] })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
}

export default router