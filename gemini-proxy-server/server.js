require('dotenv').config();
const express = require('express');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

const API_KEY = process.env.GEMINI_API_KEY;
const MODEL = 'gemini-3.8-flash';
const MAX_RETRIES = 3;

function buildPrompt(removedField, candidateFields, siblingFields) {
  return `You are analyzing a schema change in an enterprise integration.

A field was removed from a schema: "${removedField}"
Sibling fields in the same schema (for context): ${JSON.stringify(siblingFields)}

Candidate fields that appeared in the new schema version: ${JSON.stringify(candidateFields)}

Determine if any candidate field represents the SAME business concept as the removed field.

Respond ONLY with valid JSON, no other text, in this exact shape:
{
  "match_type": "exact" | "strong" | "weak" | "ambiguous" | "no_match",
  "matched_field": "<candidate field name or null>",
  "confidence": <integer 0-100>,
  "reasoning": "<one short sentence>"
}

Guidelines:
- "exact": identical meaning, just different casing/formatting
- "strong": clearly the same business concept (e.g. custName -> customerName)
- "weak": plausible but not clearly the same concept
- "ambiguous": could mean different things (e.g. a name vs an identifier)
- "no_match": no candidate represents the same concept
`;
}

async function callGemini(prompt) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${API_KEY}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }),
  });

  if (!response.ok) {
    const errText = await response.text();
    const error = new Error(`Gemini API error: ${response.status} ${errText}`);
    error.status = response.status;
    throw error;
  }

  const data = await response.json();
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error('Gemini response had no text content.');
  return text;
}

app.post('/api/classify', async (req, res) => {
  const { removed_field, candidate_fields, sibling_fields } = req.body;

  if (!removed_field || !Array.isArray(candidate_fields)) {
    return res.status(400).json({ error: 'removed_field and candidate_fields are required.' });
  }

  const prompt = buildPrompt(removed_field, candidate_fields, sibling_fields || []);

  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      const rawText = await callGemini(prompt);
      const cleaned = rawText.trim().replace(/```json/g, '').replace(/```/g, '').trim();
      const parsed = JSON.parse(cleaned);
      return res.json(parsed);
    } catch (err) {
      const isServerError = err.status && err.status >= 500;
      if (isServerError && attempt < MAX_RETRIES - 1) {
        console.log(`Model busy, retrying in 5 seconds... (attempt ${attempt + 1})`);
        await new Promise((r) => setTimeout(r, 5000));
        continue;
      }
      console.error('Classification failed:', err.message);
      return res.status(502).json({ error: 'Gemini classification failed.', detail: err.message });
    }
  }
});

app.get('/health', (req, res) => res.json({ status: 'ok' }));

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`Gemini proxy server running on http://localhost:${PORT}`);
});