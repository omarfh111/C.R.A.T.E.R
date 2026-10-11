/** Read-only local science service. Deliberately independent of telemetry v1. */
export interface AssistantSource {
  sourceId: string; path: string; lineStart: number; lineEnd: number; digest: string;
  score: number | null; text: string; sourceUrl?: string; verifiedOn?: string;
}
export interface AssistantAnswer {
  status: 'answered' | 'insufficient_evidence'; answer: string; sources: AssistantSource[];
  citedSourceIds: string[]; facts: Record<string, unknown> | null;
  models: { embedding: string; llm: string }; roles: string[]; limitations: string;
}
export interface AssistantHealth {
  status: 'ready'; httpReady: true; modelStatus: 'unchecked' | 'available' | 'unavailable'; busy: boolean;
  indexedChunks: number; llm: string; embedding: string;
  inferenceState?: 'idle' | 'running' | 'timeout_requires_restart' | 'capture_blocked';
}
export type AssistantErrorCode = 'unavailable' | 'busy' | 'timeout' | 'invalid_response' | 'failed' | 'cancelled' | 'invalid_request';
export class AssistantError extends Error {
  readonly code: AssistantErrorCode;
  constructor(code: AssistantErrorCode, message: string) { super(message); this.name = 'AssistantError'; this.code = code; }
}
const fail = (message: string): never => { throw new AssistantError('invalid_response', message); };
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const boundedText = (v: unknown, max: number, min = 1): v is string => typeof v === 'string' && v.length >= min && v.length <= max;
function officialUrl(v: unknown): v is string {
  if (!boundedText(v, 2048) || /\s/.test(v)) return false;
  try {
    const u = new URL(v);
    return u.protocol === 'https:' && !u.username && !u.password && !u.port
      && ['nasa.gov', 'esa.int', 'arxiv.org'].some(d => u.hostname === d || (d !== 'arxiv.org' && u.hostname.endsWith(`.${d}`)));
  } catch { return false; }
}
function validDay(v: unknown): v is string {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const ms = Date.parse(`${v}T00:00:00Z`);
  return Number.isFinite(ms) && new Date(ms).toISOString().slice(0, 10) === v;
}
function source(v: unknown): v is AssistantSource {
  return record(v) && typeof v.sourceId === 'string' && /^S[1-9]$/.test(v.sourceId)
    && boundedText(v.path, 1024) && Number.isInteger(v.lineStart) && Number(v.lineStart) >= 1
    && Number.isInteger(v.lineEnd) && Number(v.lineEnd) >= Number(v.lineStart)
    && typeof v.digest === 'string' && /^[a-f0-9]{64}$/.test(v.digest)
    && boundedText(v.text, 32_000) && (v.score === null || typeof v.score === 'number' && Number.isFinite(v.score))
    && (v.sourceUrl === undefined || officialUrl(v.sourceUrl)) && (v.verifiedOn === undefined || validDay(v.verifiedOn));
}
export function parseAssistantAnswer(v: unknown): AssistantAnswer {
  if (!record(v) || !['answered', 'insufficient_evidence'].includes(String(v.status))
    || !boundedText(v.answer, 32_000) || !Array.isArray(v.sources) || v.sources.length > 9 || !v.sources.every(source)
    || !Array.isArray(v.citedSourceIds) || v.citedSourceIds.length > 9 || !v.citedSourceIds.every(id => typeof id === 'string' && /^S[1-9]$/.test(id))
    || !record(v.models) || !boundedText(v.models.embedding, 256) || !boundedText(v.models.llm, 256)
    || !Array.isArray(v.roles) || v.roles.length > 16 || !v.roles.every(role => boundedText(role, 256))
    || !(v.facts === null || record(v.facts)) || !boundedText(v.limitations, 8192)) return fail('The service returned an invalid answer.');
  const ids = v.sources.map(s => s.sourceId);
  const cited = v.citedSourceIds as string[];
  const inline = [...new Set([...v.answer.matchAll(/\[(S\d+)\]/g)].map(m => m[1]))];
  if (new Set(ids).size !== ids.length || new Set(cited).size !== cited.length
    || cited.some(id => !ids.includes(id)) || inline.some(id => !cited.includes(id)) || cited.some(id => !inline.includes(id))
    || (v.status === 'answered' && cited.length === 0)) return fail('Answer citations do not match the returned evidence.');
  return v as unknown as AssistantAnswer;
}
export function createAssistantClient(options: { baseUrl?: string; timeoutMs?: number; fetch?: typeof fetch } = {}) {
  let base: URL;
  try { base = new URL(options.baseUrl ?? 'http://127.0.0.1:8766'); } catch { throw new AssistantError('invalid_request', 'Enter a loopback HTTP service URL.'); }
  if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname)
    || base.username || base.password || base.pathname !== '/' || base.search || base.hash)
    throw new AssistantError('invalid_request', 'The assistant requires a loopback HTTP base URL.');
  const timeoutMs = options.timeoutMs ?? 120_000;
  if (!Number.isFinite(timeoutMs) || timeoutMs < 1 || timeoutMs > 600_000) throw new AssistantError('invalid_request', 'Invalid assistant timeout.');
  const send = options.fetch ?? globalThis.fetch;
  async function request(path: string, body?: object, signal?: AbortSignal, deadline = timeoutMs): Promise<unknown> {
    const controller = new AbortController();
    let timedOut = false;
    const cancel = () => controller.abort();
    if (signal?.aborted) throw new AssistantError('cancelled', 'Request cancelled. Backend inference may continue until its deadline.');
    signal?.addEventListener('abort', cancel, { once: true });
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, deadline);
    try {
      const response = await send(base.origin + path, {
        method: body === undefined ? 'GET' : 'POST', credentials: 'omit', redirect: 'error', cache: 'no-store',
        headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: controller.signal,
      });
      const length = Number(response.headers.get('content-length'));
      if (length > 512_000) return fail('The service response exceeded its size limit.');
      // Bound the streamed body even when Content-Length is missing or incorrect.
      let text = '';
      if (response.body) {
        const reader = response.body.getReader(); const decoder = new TextDecoder(); let size = 0;
        try {
          while (true) {
            const part = await reader.read(); if (part.done) break;
            size += part.value.byteLength;
            if (size > 512_000) { await reader.cancel(); return fail('The service response exceeded its size limit.'); }
            text += decoder.decode(part.value, { stream: true });
          }
          text += decoder.decode();
        } finally { reader.releaseLock(); }
      }
      let value: unknown;
      try { value = JSON.parse(text); } catch { return fail('The service did not return valid JSON.'); }
      if (!response.ok) {
        const known: AssistantErrorCode[] = ['busy', 'timeout', 'unavailable', 'invalid_response', 'invalid_request'];
        const code = record(value) && known.includes(value.code as AssistantErrorCode) ? value.code as AssistantErrorCode
          : response.status === 429 ? 'busy' : response.status === 504 ? 'timeout' : response.status === 503 ? 'unavailable' : 'failed';
        const messages = { busy: 'A local inference is already running. Try again after it completes.', timeout: 'The service deadline expired. Backend inference may continue; recheck the service before retrying.', unavailable: 'The local service or required models are unavailable.', invalid_response: 'The service rejected invalid model output.', invalid_request: 'The service rejected this request.', failed: `Local assistant HTTP ${response.status}.`, cancelled: 'Request cancelled.' };
        throw new AssistantError(code, messages[code]);
      }
      return value;
    } catch (error) {
      if (error instanceof AssistantError) throw error;
      if (timedOut) throw new AssistantError('timeout', 'The request timed out. Backend inference may continue until its deadline.');
      if (signal?.aborted) throw new AssistantError('cancelled', 'Request cancelled. Backend inference may continue until its deadline.');
      throw new AssistantError('unavailable', 'Cannot reach the local assistant. Check the service URL and its allowed dashboard origin.');
    } finally { clearTimeout(timer); signal?.removeEventListener('abort', cancel); }
  }
  return {
    async health(signal?: AbortSignal): Promise<AssistantHealth> {
      const v = await request('/health', undefined, signal, Math.min(timeoutMs, 5000));
      if (!record(v) || v.status !== 'ready' || v.httpReady !== true
        || !['unchecked', 'available', 'unavailable'].includes(String(v.modelStatus)) || typeof v.busy !== 'boolean'
        || (v.inferenceState !== undefined && !['idle', 'running', 'timeout_requires_restart', 'capture_blocked'].includes(String(v.inferenceState)))
        || !Number.isInteger(v.indexedChunks) || Number(v.indexedChunks) < 0
        || !boundedText(v.llm, 256) || !boundedText(v.embedding, 256)) return fail('Invalid assistant health response.');
      return v as unknown as AssistantHealth;
    },
    async ask(question: string, topK = 3, signal?: AbortSignal): Promise<AssistantAnswer> {
      if (!boundedText(question, 2000) || !question.trim()) throw new AssistantError('invalid_request', 'Enter a question of 1–2000 characters.');
      if (!Number.isInteger(topK) || topK < 1 || topK > 8) throw new AssistantError('invalid_request', 'Invalid retrieval passage count.');
      return parseAssistantAnswer(await request('/ask', { question, topK }, signal));
    },
  };
}
