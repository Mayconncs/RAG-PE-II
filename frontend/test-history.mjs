import {test} from 'node:test';
import assert from 'node:assert/strict';
import {loadHistory, saveHistory} from './src/history.ts';

function storage(){const data=new Map();return {getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v)};}
test('conversas e fontes sobrevivem a uma nova leitura',()=>{
 const s=storage();
 const conversations=[{id:'1',title:'Consulta',updated:'2026-11-04',messages:[{role:'user',content:'Pergunta'},{role:'assistant',content:'Resposta',dados:{fontes:[{fonte:'lei.pdf',paginas:'2'}]}}]}];
 saveHistory(s,conversations);
 assert.deepEqual(loadHistory(s),conversations);
 saveHistory(s,[]);
 assert.deepEqual(loadHistory(s),[]);
});
test('armazenamento vazio e dados corrompidos',()=>{
 assert.deepEqual(loadHistory(storage()),[]);
 assert.throws(()=>loadHistory({getItem:()=>'{'}));
 assert.throws(()=>loadHistory({getItem:()=>'[{"id":"1"}]'}));
});
test('falha de armazenamento chega ao chamador para mostrar aviso',()=>{
 assert.throws(()=>saveHistory({setItem:()=>{throw Error('QuotaExceeded');}},[]));
});
