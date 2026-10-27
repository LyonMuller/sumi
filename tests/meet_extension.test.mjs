import test from 'node:test';
import assert from 'node:assert/strict';
import { meetingCode, matchesCommand, validEvent } from '../meet_extension/protocol.js';

test('accepts only exact Meet meeting URLs', () => {
  assert.equal(meetingCode('https://meet.google.com/abc-defg-hij?authuser=1'),'abc-defg-hij');
  assert.equal(meetingCode('https://meet.google.com/meet/abc-defg-hij'),'abc-defg-hij');
  assert.equal(meetingCode('https://meet.google.com/_meet/abc-defg-hij?authuser=0'),'abc-defg-hij');
  assert.equal(meetingCode('https://meet.google.com/other/abc-defg-hij'),null);
  for (const url of ['https://meet.google.com.evil.test/abc-defg-hij','http://meet.google.com/abc-defg-hij','https://meet.google.com/','https://meet.google.com/lookup/name','https://example.org/abc-defg-hij']) assert.equal(meetingCode(url),null);
});

test('rejects expired, foreign and malformed commands', () => {
  const c={action:'leave',id:'nonce',tab:17,meeting:'abc-defg-hij',expires:4000};
  assert.ok(matchesCommand(c,17,'abc-defg-hij',1000));
  for (const wrong of [{...c,tab:18},{...c,meeting:'xxx-yyyy-zzz'},{...c,expires:500},{...c,expires:999999},{...c,action:'close-all'},null,undefined]) assert.ok(!matchesCommand(wrong,17,'abc-defg-hij',1000));
});

test('accepts only known sound events', () => {
  assert.ok(validEvent({action:'play',name:'kamehameha-fire'}));
  assert.ok(validEvent({action:'stop_all',name:''}));
  for (const wrong of [{action:'eval',name:'x'},{action:'play',name:'../x'},{action:'play',name:''},null]) assert.ok(!validEvent(wrong));
});

let serial=0;
async function harness({current='https://meet.google.com/abc-defg-hij',expires=Date.now()+3000,target={meeting:'abc-defg-hij',tab:17},command=true}={}) {
  let listener;
  const closed=[];
  const requests=[];
  const store={};
  globalThis.chrome={
    runtime:{getURL:path=>'chrome-extension://test/'+path,onMessage:{addListener:fn=>{listener=fn;}},onInstalled:{addListener:()=>{}}},
    storage:{local:{get:async key=>({[key]:store[key]}),set:async value=>Object.assign(store,value),remove:async key=>{delete store[key];}}},
    tabs:{get:async id=>({id,url:current}),remove:async id=>{closed.push(id);},sendMessage:async()=>{}}
  };
  globalThis.fetch=async (url,options)=>{
    requests.push({url,options});
    const body={ok:true};
    if (url.endsWith('/sync')) Object.assign(body,{target,sounds:false,command:command?{action:'leave',id:'nonce',meeting:'abc-defg-hij',tab:17,expires}:null});
    return {ok:true,json:async()=>body};
  };
  await import(`../meet_extension/background.js?test=${++serial}`);
  const send=(message,sender)=>new Promise(resolve=>{
    if (!listener(message,sender,resolve)) resolve(undefined);
  });
  return {closed,requests,store,send};
}

test('heartbeat reports the meeting with no code and records status', async()=>{
  const h=await harness({command:false});
  await h.send({type:'heartbeat',focused:true},{tab:{id:17,url:'https://meet.google.com/abc-defg-hij'}});
  assert.deepEqual(JSON.parse(h.requests[0].options.body),{meeting:'abc-defg-hij',tab:17,focused:true});
  assert.equal(h.requests[0].options.headers['X-Sumi-Token'],undefined);
  assert.equal(h.store.status.meeting,'abc-defg-hij');
  assert.deepEqual(h.closed,[]);
});

test('worker closes only the linked Meet tab and acknowledges it', async()=>{
  const h=await harness();
  await h.send({type:'heartbeat'},{tab:{id:17,url:'https://meet.google.com/abc-defg-hij'}});
  assert.deepEqual(h.closed,[17]);
  assert.equal(JSON.parse(h.requests.at(-1).options.body).closed,true);
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

test('worker rejects expired commands and commands for other tabs',async()=>{
  const h=await harness({expires:1});
  await h.send({type:'heartbeat'},{tab:{id:17,url:'https://meet.google.com/abc-defg-hij'}});
  await h.send({type:'heartbeat'},{tab:{id:18,url:'https://meet.google.com/abc-defg-hij'}});
  assert.deepEqual(h.closed,[]);
});
