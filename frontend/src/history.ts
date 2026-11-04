export type Conversation<T> = {id:string; title:string; messages:T[]; updated:string};
const KEY='consulta-saude.conversas.v1';
export function loadHistory<T>(storage:Pick<Storage,'getItem'>):Conversation<T>[] {
 const raw=storage.getItem(KEY);
 if(!raw)return [];
 const data:unknown=JSON.parse(raw);
 if(!Array.isArray(data) || !data.every(c=>c && typeof c.id==='string' && typeof c.title==='string' && typeof c.updated==='string' && Array.isArray(c.messages) && c.messages.every((m:unknown)=>typeof m==='object' && m!==null && 'role' in m && ['user','assistant'].includes(String(m.role)) && 'content' in m && typeof m.content==='string')))throw new Error('Histórico inválido');
 return data as Conversation<T>[];
}
export function saveHistory<T>(storage:Pick<Storage,'setItem'>, conversations:Conversation<T>[]) {
 storage.setItem(KEY,JSON.stringify(conversations));
}
