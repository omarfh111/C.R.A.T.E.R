/** Local read-only assistant. Separate from M3's canonical telemetry v1. */
export interface AssistantSource {
  sourceId: string;
  path: string;
  lineStart: number;
  lineEnd: number;
  digest: string;
  score: number | null;
  text: string;
  sourceUrl?: string;
  verifiedOn?: string;
}

export interface AssistantAnswer {
  status: 'answered' | 'insufficient_evidence';
  answer: string;
  sources: AssistantSource[];
  citedSourceIds: string[];
  facts: Record<string, unknown> | null;
  models: { embedding: string; llm: string };
  roles: string[];
  limitations: string;
}

export interface AssistantHealth {
  status: 'ready'; // HTTP service ready; does not certify loaded Ollama models.
  indexedChunks: number;
  llm: string;
  embedding: string;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function officialUrl(value: unknown): boolean {
  if (typeof value !== 'string' || /\s/.test(value)) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password && !url.port
      && (url.hostname === 'nasa.gov' || url.hostname.endsWith('.nasa.gov'));
  } catch { return false; }
}

function source(value: unknown): value is AssistantSource {
  return record(value) && typeof value.sourceId === 'string' && typeof value.path === 'string'
    && typeof value.lineStart === 'number' && typeof value.lineEnd === 'number'
    && Number.isInteger(value.lineStart) && value.lineStart >= 1
    && Number.isInteger(value.lineEnd) && value.lineEnd >= value.lineStart
    && typeof value.digest === 'string' && /^[a-f0-9]{64}$/.test(value.digest) && typeof value.text === 'string'
    && (value.score === null || (typeof value.score === 'number' && Number.isFinite(value.score)))
    && (value.sourceUrl === undefined || officialUrl(value.sourceUrl))
    && (value.verifiedOn === undefined || typeof value.verifiedOn === 'string');
}

function parseAnswer(value: unknown): AssistantAnswer {
  if (!record(value) || (value.status !== 'answered' && value.status !== 'insufficient_evidence')
      || typeof value.answer !== 'string' || !Array.isArray(value.sources) || !value.sources.every(source)
      || !Array.isArray(value.citedSourceIds) || !value.citedSourceIds.every(id => typeof id === 'string')
      || !record(value.models) || typeof value.models.embedding !== 'string' || typeof value.models.llm !== 'string'
      || !Array.isArray(value.roles) || !value.roles.every(role => typeof role === 'string')
      || !(value.facts === null || record(value.facts)) || typeof value.limitations !== 'string') {
    throw new Error('Invalid assistant response');
  }
  const sources = value.sources;
  if (value.citedSourceIds.some(id => !sources.some(s => s.sourceId === id))
      || (value.status === 'answered' && value.citedSourceIds.length === 0)) {
    throw new Error('Invalid assistant response citations');
  }
  return value as unknown as AssistantAnswer;
}

export function createAssistantClient(options: { baseUrl?: string; timeoutMs?: number; fetch?: typeof fetch } = {}) {
  const base = new URL(options.baseUrl ?? 'http://127.0.0.1:8766');
  if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname)
      || base.username || base.password || base.pathname !== '/' || base.search || base.hash) {
    throw new Error('Assistant requires a loopback HTTP base URL');
  }
  const timeoutMs = options.timeoutMs ?? 240_000;
  if (!Number.isFinite(timeoutMs) || timeoutMs < 1 || timeoutMs > 600_000) {
    throw new Error('Invalid assistant timeout');
  }
  const send = options.fetch ?? globalThis.fetch;
  async function request(path: string, body?: object): Promise<unknown> {
    const response = await send(base.origin + path, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'omit', redirect: 'error',
      headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) throw new Error(`Assistant HTTP ${response.status}`);
    return response.json();
  }
  return {
    async health(): Promise<AssistantHealth> {
      const value = await request('/health');
      if (!record(value) || value.status !== 'ready' || !Number.isInteger(value.indexedChunks)
          || typeof value.llm !== 'string' || typeof value.embedding !== 'string') {
        throw new Error('Invalid assistant health response');
      }
      return value as unknown as AssistantHealth;
    },
    async ask(question: string, topK = 4): Promise<AssistantAnswer> {
      if (typeof question !== 'string' || !question.trim() || question.length > 2000) throw new Error('Invalid question');
      if (!Number.isInteger(topK) || topK < 1 || topK > 8) throw new Error('Invalid topK');
      return parseAnswer(await request('/ask', { question, topK }));
    },
  };
}
