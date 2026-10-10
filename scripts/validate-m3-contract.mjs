// Node >= 22.18: imports M3's real TypeScript parser with built-in type stripping.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

if (process.argv.length !== 4) {
  throw new Error('Usage: node scripts/validate-m3-contract.mjs PATH_TO_M3_CONTRACT_TS RECEIVED_JSONL');
}
const { parseTelemetryFrame } = await import(pathToFileURL(resolve(process.argv[2])).href);
const lines = readFileSync(process.argv[3], 'utf8').split(/\r?\n/).filter(Boolean);
if (!lines.length) throw new Error('No received telemetry frames to validate');
const lastByRover = new Map();
for (const [index, line] of lines.entries()) {
  const frame = parseTelemetryFrame(JSON.parse(line));
  const previous = lastByRover.get(frame.roverId);
  if (previous !== undefined && frame.sequence <= previous) {
    throw new Error(`Non-increasing sequence at line ${index + 1}`);
  }
  lastByRover.set(frame.roverId, frame.sequence);
}
console.log(`${lines.length} decoded frames accepted by M3's actual Zod parser; ordered per rover.`);
