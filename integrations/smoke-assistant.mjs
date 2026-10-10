// Real HTTP/Ollama smoke, explicitly invoked after starting the local sidecar.
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { performance } from 'node:perf_hooks';
import { createAssistantClient } from './m3-assistant-client.ts';

const output = resolve(process.argv[3] ?? 'artifacts/assistant-http-smoke.json');
if (existsSync(output)) throw new Error('Output exists; choose a new smoke file');
const client = createAssistantClient({ baseUrl: process.argv[2] ?? 'http://127.0.0.1:8766', timeoutMs: 240000 });
const health = await client.health();
const cases = [];
mkdirSync(dirname(output), { recursive: true });
for (const [name, question] of [
  ['nasa-cadence', 'Pourquoi le FPS de lecture de la vidéo NASA Long Autonomous Drive ne représente-t-il pas la cadence originale de capture ?'],
  ['unknown-rover-temperature', 'Quelle est la température exacte de notre rover C.R.A.T.E.R. maintenant ?'],
]) {
  const started = performance.now();
  const result = await client.ask(question);
  cases.push({ name, question, elapsedS: (performance.now() - started) / 1000, result });
  writeFileSync(output, JSON.stringify({
    scope: 'Two local HTTP examples, not a general accuracy benchmark. Review causal claims manually; citation checks alone do not prove them.',
    health, cases,
  }, null, 2), 'utf8');
  if (name === 'nasa-cadence') {
    assert.equal(result.status, 'answered');
    assert.ok(result.sources.some(s => result.citedSourceIds.includes(s.sourceId)
      && s.sourceUrl === 'https://science.nasa.gov/resource/perseverance-rover-camera-view-of-long-autonomous-drive/'));
  } else {
    assert.equal(result.status, 'insufficient_evidence');
  }
  console.log(`${name}: ${result.status}`);
}
console.log(`Review answers in ${output}`);
