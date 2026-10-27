import test from 'node:test';
import assert from 'node:assert/strict';
import { meetingCode, matchesCommand } from '../meet_extension/protocol.js';

test('accepts only exact Meet meeting URLs', () => {
  assert.equal(meetingCode('https://meet.google.com/abc-defg-hij?authuser=1'),'abc-defg-hij');
  for (const url of ['https://meet.google.com.evil.test/abc-defg-hij','http://meet.google.com/abc-defg-hij','https://meet.google.com/','https://meet.google.com/lookup/name','https://example.org/abc-defg-hij']) assert.equal(meetingCode(url),null);
});

test('rejects expired, foreign and malformed commands', () => {
  const c={action:'leave',id:'nonce',tab:17,meeting:'abc-defg-hij',expires:4000};
  assert.ok(matchesCommand(c,17,'abc-defg-hij',1000));
  for (const wrong of [{...c,tab:18},{...c,meeting:'xxx-yyyy-zzz'},{...c,expires:500},{...c,expires:999999},{...c,action:'close-all'},null,undefined]) assert.ok(!matchesCommand(wrong,17,'abc-defg-hij',1000));
});

let serial=0;
async function harness({current='https://meet.google.com/abc-defg-hij',expires=Date.now()+3000}={}) {
  let listener;
  const closed=[];
  const requests=[];
  const store={binding:{meeting:'abc-defg-hij',tab:17,token:'x'.repeat(43)}};
  globalThis.chrome={
    runtime:{getURL:path=>'chrome-extension://test/'+path,onMessage:{addListener:fn=>{listener=fn;}}},
    storage:{local:{get:async key=>({[key]:store[key]}),set:async value=>Object.assign(store,value),remove:async key=>{delete store[key];}}},
    tabs:{get:async id=>({id,url:current}),remove:async id=>{closed.push(id);},query:async()=>[{id:17,url:current}]}
  };
  globalThis.fetch=async (url,options)=>{
    requests.push({url,options});
    return {ok:true,json:async()=>url.includes('/command') ? {command:{action:'leave',id:'nonce',meeting:'abc-defg-hij',tab:17,expires}} : {ok:true}};
  };
  await import(`../meet_extension/background.js?test=${++serial}`);
  const send=(message,sender)=>new Promise(resolve=>{
    if (!listener(message,sender,resolve)) resolve(undefined);
  });
  return {closed,requests,store,send};
}

test('worker closes only the bound Meet tab and acknowledges it', async()=>{
  const h=await harness();
  await h.send({type:'heartbeat'},{tab:{id:17,url:'https://meet.google.com/abc-defg-hij'}});
  assert.deepEqual(h.closed,[17]);
  assert.equal(JSON.parse(h.requests.at(-1).options.body).closed,true);
  assert.equal(h.store.binding,undefined);
});

test('worker refuses a tab that navigated elsewhere',async()=>{
  const h=await harness({current:'https://example.org/'});
  await h.send({type:'heartbeat'},{tab:{id:17,url:'https://meet.google.com/abc-defg-hij'}});
  assert.deepEqual(h.closed,[]);
  assert.equal(JSON.parse(h.requests.at(-1).options.body).closed,false);
});

test('worker does not close a different meeting in the same tab',async()=>{
  const h=await harness({current:'https://meet.google.com/xxx-yyyy-zzz'});
  await h.send({type:'heartbeat'},{tab:{id:17,url:'https://meet.google.com/abc-defg-hij'}});
  assert.deepEqual(h.closed,[]);
});

test('worker rejects expired commands and unrelated tabs',async()=>{
  const h=await harness({expires:1});
  await h.send({type:'heartbeat'},{tab:{id:17,url:'https://meet.google.com/abc-defg-hij'}});
  assert.deepEqual(h.closed,[]);
  const requests=h.requests.length;
  await h.send({type:'heartbeat'},{tab:{id:18,url:'https://meet.google.com/abc-defg-hij'}});
  assert.equal(h.requests.length,requests);
});

test('pairing accepts only the extension popup',async()=>{
  const h=await harness();
  await h.send({type:'pair',token:'x'.repeat(43)},{url:'https://example.org/popup.html'});
  assert.equal(h.requests.length,0);
  const result=await h.send({type:'pair',token:'x'.repeat(43)},{url:'chrome-extension://test/popup.html'});
  assert.equal(result.ok,true);
  assert.equal(h.store.binding.tab,17);
});
