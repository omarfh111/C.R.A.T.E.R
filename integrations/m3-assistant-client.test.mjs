import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createAssistantClient } from './m3-assistant-client.ts';

const answer = { status: 'answered', answer: 'NASA explique la cadence [S1].',
  sources: [{ sourceId: 'S1', path: 'nasa.md', lineStart: 1, lineEnd: 9,
    digest: 'a'.repeat(64), score: .8, text: 'Capture tous les cinq metres.',
    sourceUrl: 'https://science.nasa.gov/resource/example/', verifiedOn: '2026-10-10' }],
  citedSourceIds: ['S1'], facts: null, models: { embedding: 'embeddinggemma:300m', llm: 'qwen3:4b-instruct-2507-q4_K_M' },
  roles: ['retriever', 'explainer'], limitations: 'Aucun controle du rover.' };

test('client sends only question/topK and preserves citations and official URL', async () => {
  const calls = [];
  const client = createAssistantClient({ fetch: async (url, options) => {
    calls.push([url, options]); return new Response(JSON.stringify(answer), { status: 200 });
  }});
  const result = await client.ask('Quelle cadence ?', 3);
  assert.deepEqual(JSON.parse(calls[0][1].body), { question: 'Quelle cadence ?', topK: 3 });
  assert.equal(calls[0][0], 'http://127.0.0.1:8766/ask');
  assert.equal(result.sources[0].sourceUrl, answer.sources[0].sourceUrl);
});

test('unavailable assistant produces an error, never a fabricated answer', async () => {
  const client = createAssistantClient({ fetch: async () => new Response('{}', { status: 503 }) });
  await assert.rejects(client.ask('Question'), /503/);
});

test('abstention is preserved as a distinct result', async () => {
  const client = createAssistantClient({ fetch: async () => new Response(JSON.stringify({
    ...answer, status: 'insufficient_evidence', answer: 'Sources insuffisantes.', citedSourceIds: [] })) });
  assert.equal((await client.ask('Temperature inconnue')).status, 'insufficient_evidence');
});

test('malformed response is rejected', async () => {
  const client = createAssistantClient({ fetch: async () => new Response('{"status":"answered"}') });
  await assert.rejects(client.ask('Question'), /response/i);
});

test('unsafe source links and unknown citation IDs are rejected', async () => {
  for (const value of [
    { ...answer, sources: [{ ...answer.sources[0], sourceUrl: 'javascript:alert(1)' }] },
    { ...answer, citedSourceIds: ['S99'] },
    { ...answer, status: ['answered'] },
  ]) {
    const client = createAssistantClient({ fetch: async () => new Response(JSON.stringify(value)) });
    await assert.rejects(client.ask('Question'), /response/i);
  }
});

test('cloud endpoint and invalid questions are rejected before fetch', async () => {
  assert.throws(() => createAssistantClient({ baseUrl: 'https://example.com' }), /loopback/);
  const client = createAssistantClient({ fetch: async () => { throw new Error('fetch forbidden'); } });
  await assert.rejects(client.ask(''), /question/);
  await assert.rejects(client.ask('x', 9), /topK/);
});
