// Explicit simulated incident, real local Ollama, real HTTP and M3 client.
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { performance } from 'node:perf_hooks';
import { createAssistantClient } from './m3-assistant-client.ts';

const output = resolve(process.argv[3] ?? 'artifacts/experience-http-smoke.json');
if (existsSync(output)) throw new Error('Output exists; choose a new evidence file');
const client = createAssistantClient({baseUrl: process.argv[2] ?? 'http://127.0.0.1:8766'});
const health = await client.health();
assert.equal(health.experience?.enabled, true);
assert.equal(health.experience?.imageInference, false);
const event = {eventId: randomUUID(), roverId: 'SIMULATED_EXPERIENCE_TEST', capturedAt: new Date().toISOString(),
  kind: 'calibration_missing', provenance: 'simulated',
  summary: "Essai simulé : le producteur n'a fourni aucune pose caméra. Aucune position métrique n'est disponible.",
  question: 'Quelle information manque dans cet événement et peut-on calculer une position ENU fiable ?'};
const start = performance.now();
const recorded = await client.recordEvent(event, true);
assert.ok(recorded.analysis);
const acceptedS = (performance.now() - start) / 1000;
let job = recorded.analysis;
const deadline = Date.now() + 240000;
while (['queued', 'running'].includes(job.state) && Date.now() < deadline) {
  await new Promise(resolve => setTimeout(resolve, 1000));
  job = await client.analysis(job.analysisId);
}
assert.equal(job.state, 'completed', `Analysis state ${job.state}: ${job.error}`);
assert.equal(job.result.status, 'answered');
assert.ok(job.result.sources.some(s => s.path === 'experience:' + event.eventId
  && job.result.citedSourceIds.includes(s.sourceId)));
assert.equal((await client.event(event.eventId)).imageAnalysis, 'not_performed');
for (const source of job.result.sources) {
  if (!source.path.startsWith('experience:')) source.path = source.path.replaceAll('\\', '/').split('/').pop();
}
const proof = {validatedAt: new Date().toISOString(), health, acceptedS,
  totalS: (performance.now()-start)/1000, event: recorded.event, analysis: job,
  limitations: 'One explicitly simulated incident with actual text models; no ONNX, pixel interpretation, motor control or general accuracy claim. Review the answer manually.'};
mkdirSync(dirname(output), {recursive: true});
writeFileSync(output, JSON.stringify(proof, null, 2)+'\n', 'utf8');
console.log(JSON.stringify({acceptedS, totalS: proof.totalS, state: job.state, answer: job.result.answer}));
