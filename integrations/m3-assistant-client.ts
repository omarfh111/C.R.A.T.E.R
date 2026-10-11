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
  experience?: { enabled: true; workerAlive: boolean; imageInference: false; capacity: number };
}

export interface ExperienceEvent {
  eventId: string;
  roverId: string;
  capturedAt: string;
  kind: 'telemetry_stale' | 'link_changed' | 'tracking_warning' | 'calibration_missing' | 'operator_note';
  provenance: 'measured' | 'simulated' | 'operator';
  summary: string;
  question?: string;
  decision?: { action: string; reason: string };
  frame?: Record<string, unknown>;
  images?: { relativePath: string; mediaType: 'image/png' | 'image/jpeg'; sha256: string }[];
}

export interface RecordedEvent extends ExperienceEvent {
  recordedAt: string;
  imageAnalysis: 'not_performed';
}

export interface ExperienceAnalysis {
  analysisId: string;
  eventId: string;
  state: 'queued' | 'running' | 'completed' | 'failed';
  question: string;
  submittedAt: string;
  startedAt?: string;
  finishedAt?: string;
  attempt: number;
  result: AssistantAnswer | null;
  error: string | null;
}

function identifier(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
}

function parseEvent(value: unknown): RecordedEvent {
  if (!record(value) || !identifier(value.eventId) || typeof value.roverId !== 'string'
      || typeof value.capturedAt !== 'string' || typeof value.recordedAt !== 'string'
      || typeof value.summary !== 'string' || value.imageAnalysis !== 'not_performed'
      || typeof value.kind !== 'string' || typeof value.provenance !== 'string'
      || !['telemetry_stale', 'link_changed', 'tracking_warning', 'calibration_missing', 'operator_note'].includes(String(value.kind))
      || !['measured', 'simulated', 'operator'].includes(String(value.provenance))) {
    throw new Error('Invalid recorded experience event');
  }
  return value as unknown as RecordedEvent;
}

function parseAnalysis(value: unknown): ExperienceAnalysis {
  if (!record(value) || !identifier(value.analysisId) || !identifier(value.eventId)
      || typeof value.state !== 'string' || !['queued', 'running', 'completed', 'failed'].includes(value.state)
      || typeof value.question !== 'string' || typeof value.submittedAt !== 'string'
      || !Number.isInteger(value.attempt) || Number(value.attempt) < 1 || Number(value.attempt) > 5
      || !(value.error === null || typeof value.error === 'string')) {
    throw new Error('Invalid experience analysis');
  }
  if (value.state === 'completed') parseAnswer(value.result);
  else if (value.result !== null) throw new Error('Invalid unfinished analysis result');
  return value as unknown as ExperienceAnalysis;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function officialUrl(value: unknown): boolean {
  if (typeof value !== 'string' || /\s/.test(value)) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password && !url.port
      && (url.hostname === 'arxiv.org' || ['nasa.gov', 'esa.int'].some(domain =>
        url.hostname === domain || url.hostname.endsWith(`.${domain}`)));
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
      if (value.experience !== undefined && (!record(value.experience)
          || value.experience.enabled !== true || typeof value.experience.workerAlive !== 'boolean'
          || value.experience.imageInference !== false || !Number.isInteger(value.experience.capacity)
          || Number(value.experience.capacity) < 1 || Number(value.experience.capacity) > 16)) {
        throw new Error('Invalid experience health response');
      }
      return value as unknown as AssistantHealth;
    },
    async ask(question: string, topK = 4): Promise<AssistantAnswer> {
      if (typeof question !== 'string' || !question.trim() || question.length > 2000) throw new Error('Invalid question');
      if (!Number.isInteger(topK) || topK < 1 || topK > 8) throw new Error('Invalid topK');
      return parseAnswer(await request('/ask', { question, topK }));
    },
    async recordEvent(event: ExperienceEvent, analyze = false): Promise<{event: RecordedEvent; analysis: ExperienceAnalysis | null}> {
      if (!identifier(event.eventId) || typeof analyze !== 'boolean') throw new Error('Invalid event identifier or analyze flag');
      const value = await request('/experience/events', {event, analyze});
      if (!record(value)) throw new Error('Invalid experience response');
      const saved = parseEvent(value.event);
      const job = value.analysis === null ? null : parseAnalysis(value.analysis);
      if (saved.eventId !== event.eventId || (job && job.eventId !== saved.eventId)) throw new Error('Experience identifier mismatch');
      return {event: saved, analysis: job};
    },
    async events(): Promise<RecordedEvent[]> {
      const value = await request('/experience/events');
      if (!record(value) || !Array.isArray(value.events)) throw new Error('Invalid events response');
      return value.events.map(parseEvent);
    },
    async event(eventId: string): Promise<RecordedEvent> {
      if (!identifier(eventId)) throw new Error('Invalid event identifier');
      const saved = parseEvent(await request('/experience/events/' + eventId));
      if (saved.eventId !== eventId) throw new Error('Experience identifier mismatch');
      return saved;
    },
    async analyzeEvent(eventId: string, retry = false): Promise<ExperienceAnalysis> {
      if (!identifier(eventId) || typeof retry !== 'boolean') throw new Error('Invalid event identifier or retry flag');
      const job = parseAnalysis(await request('/experience/analyses', {eventId, retry}));
      if (job.eventId !== eventId) throw new Error('Experience identifier mismatch');
      return job;
    },
    async analysis(analysisId: string): Promise<ExperienceAnalysis> {
      if (!identifier(analysisId)) throw new Error('Invalid analysis identifier');
      const job = parseAnalysis(await request('/experience/analyses/' + analysisId));
      if (job.analysisId !== analysisId) throw new Error('Analysis identifier mismatch');
      return job;
    },
  };
}
