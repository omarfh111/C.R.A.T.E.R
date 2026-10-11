import assert from 'node:assert/strict';
import test from 'node:test';
import { AssistantError, createAssistantClient, parseAssistantAnswer } from './m3-assistant-client.ts';
const source = { sourceId: 'S1', path: 'docs/knowledge/nasa.md', lineStart: 1, lineEnd: 3, digest: 'a'.repeat(64), score: .8, text: 'NASA describes an autonomous navigation system.', sourceUrl: 'https://science.nasa.gov/example', verifiedOn: '2026-10-10' };
const answer = () => ({status: 'answered', answer: 'NASA provides autonomous navigation context [S1].', sources: [{...source}], citedSourceIds: ['S1'], facts: null, models: {embedding:'embeddinggemma:300m',llm:'qwen3:4b'},roles:['explainer'],limitations:'Generated text is unverified and is not a rover measurement.'});
const reply = (value, status = 200) => new Response(JSON.stringify(value), {status, headers:{'Content-Type':'application/json'}});
const code = expected => e => e instanceof AssistantError && e.code === expected;
test('client is inert until an explicit call and sends only the science question', async () => {
  let calls = 0;
  const client = createAssistantClient({fetch: async (url, options) => {
    calls++; assert.equal(url,'http://127.0.0.1:8766/ask'); assert.equal(options.credentials,'omit'); assert.equal(options.redirect,'error');
    assert.deepEqual(JSON.parse(options.body),{question:'Explain navigation',topK:3}); return reply(answer());
  }});
  assert.equal(calls,0); assert.equal((await client.ask('Explain navigation')).status,'answered'); assert.equal(calls,1);
});
test('health separates HTTP readiness from cached model availability', async () => {
  const value = {status:'ready',httpReady:true,modelStatus:'unavailable',busy:false,indexedChunks:12,llm:'qwen',embedding:'gemma'};
  assert.equal((await createAssistantClient({fetch:async()=>reply(value)}).health()).modelStatus,'unavailable');
  await assert.rejects(createAssistantClient({fetch:async()=>reply({...value, modelStatus:'loaded'})}).health(),code('invalid_response'));
});
test('unsafe service URLs are rejected before making a request', () => {
  for (const baseUrl of ['https://127.0.0.1:8766','http://example.com','http://127.0.0.1.evil.test','http://user:secret@localhost','http://localhost/ask','http://localhost?x=1','http://localhost#x','file:///tmp/a']) assert.throws(()=>createAssistantClient({baseUrl}),code('invalid_request'));
});
test('citations must exactly match inline mentions and returned evidence', () => {
  for (const change of [
    {answer:'Invented reading [S99].'}, {citedSourceIds:['S2']}, {answer:'No citation.'},
    {citedSourceIds:['S1','S1']}, {sources:[source,source]}, {answer:'Claim [S1] and claim [S2].'},
  ]) assert.throws(()=>parseAssistantAnswer({...answer(),...change}),code('invalid_response'));
});
test('invalid response shapes, metadata, links and bounds fail closed', () => {
  for (const change of [{facts:[]},{answer:'x'.repeat(32001)},{roles:[null]},{models:{llm:'qwen'}},{sources:[{...source,lineEnd:0}]},
    {sources:[{...source,score:Infinity}]},{sources:[{...source,verifiedOn:'2026-02-30'}]},
    {sources:[{...source,sourceUrl:'https://nasa.gov.evil.test/x'}]},{sources:[{...source,sourceUrl:'javascript:alert(1)'}]},
    {sources:[{...source,sourceUrl:'https://user@nasa.gov/x'}]}, {sources:[{...source,digest:'bad'}]}])
    assert.throws(()=>parseAssistantAnswer({...answer(),...change}),code('invalid_response'));
});
test('insufficient evidence is a normal result without fabricated facts', async () => {
  const value = {...answer(),status:'insufficient_evidence',answer:'The sources do not contain rover temperature.',sources:[],citedSourceIds:[]};
  assert.equal((await createAssistantClient({fetch:async()=>reply(value)}).ask('Rover temperature?')).status,'insufficient_evidence');
});
test('known errors are predictable and ignore injected error messages', async () => {
  for (const [status,errorCode] of [[429,'busy'],[504,'timeout'],[503,'unavailable'],[502,'invalid_response'],[400,'invalid_request']]) {
    await assert.rejects(createAssistantClient({fetch:async()=>reply({code:errorCode,error:'<script>run()</script>'},status)}).ask('Question?'), e => code(errorCode)(e) && !e.message.includes('script'));
  }
});
test('network errors report unavailable and malformed output reports invalid response', async () => {
  await assert.rejects(createAssistantClient({fetch:async()=>{throw new TypeError('fetch failed');}}).health(),code('unavailable'));
  await assert.rejects(createAssistantClient({fetch:async()=>new Response('<html>bad</html>')}).ask('Question?'),code('invalid_response'));
});
const pendingFetch = (_url, options) => new Promise((_resolve,reject) => options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
test('timeout and caller cancellation have distinct states', async () => {
  await assert.rejects(createAssistantClient({fetch:pendingFetch,timeoutMs:5}).ask('Question?'),code('timeout'));
  const controller = new AbortController();
  const pending = createAssistantClient({fetch:pendingFetch}).ask('Question?',3,controller.signal); controller.abort();
  await assert.rejects(pending,e=>code('cancelled')(e) && e.message.includes('may continue'));
});
test('an already-cancelled request never starts a network call', async () => {
  const controller = new AbortController(); controller.abort(); let calls=0;
  await assert.rejects(createAssistantClient({fetch:async()=>{calls++;return reply(answer());}}).ask('Question?',3,controller.signal),code('cancelled'));
  assert.equal(calls,0);
});
test('streamed response size is bounded without Content-Length', async () => {
  await assert.rejects(createAssistantClient({fetch:async()=>new Response('x'.repeat(600000))}).ask('Question?'),code('invalid_response'));
});
test('citation validation does not claim semantic truth verification', () => {
  // The model text remains unverified even when its IDs are valid. The UI never imports it into mission state.
  const result = parseAssistantAnswer({...answer(),answer:'An unsupported rover temperature is 999 K [S1].'});
  assert.equal(result.facts,null); assert.match(result.limitations,/unverified/);
});
