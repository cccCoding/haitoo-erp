import {ref} from 'vue'

// 每次切换都建立独立请求代次，旧请求不能写入新的查看范围。
export function createRunViewer(fetchRun:(id:number)=>Promise<any>,fetchEvents:(id:number,params:Record<string,number>)=>Promise<any[]>,unauthorized:()=>void=()=>{}){
 const run=ref<any>(null),events=ref<any[]>([]),itemId=ref<number|null>(null)
 const loading=ref(false),error=ref(''),more=ref(false)
 let generation=0,active=false
 async function load(reset=false){
  if(!active||!run.value||loading.value)return
  const request=generation,id=run.value.id,scope=itemId.value
  loading.value=true;error.value=''
  try{
   const params:Record<string,number>={after_seq:reset?0:events.value[events.value.length-1]?.seq||0}
   if(scope!==null)params.item_id=scope
   const [detail,batch]=await Promise.all([fetchRun(id),fetchEvents(id,params)])
   if(!active||request!==generation)return
   run.value=detail
   const seen=new Set(reset?[]:events.value.map(event=>event.seq))
   events.value=[...(reset?[]:events.value),...batch.filter(event=>!seen.has(event.seq))]
   more.value=batch.length===500
  }catch(e:any){
   if(!active||request!==generation)return
   if(e.response?.status===401)unauthorized()
   error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:'加载失败，请重试'
  }finally{if(request===generation)loading.value=false}
 }
 async function open(value:any,scope:number|null=null){
  ++generation;active=true;run.value={id:value.id,items:[],tasks:[]};itemId.value=scope
  events.value=[];more.value=false;loading.value=false
  await load(true)
 }
 async function select(scope:number|null){
  ++generation;itemId.value=scope;events.value=[];more.value=false;loading.value=false
  await load(true)
 }
 function close(){++generation;active=false;loading.value=false}
 return {run,events,itemId,loading,error,more,open,select,load,close}
}
export function formatRunLogs(events:any[]){
 return events.map(e=>`${e.seq} ${e.created_at} 执行项 ${e.item_id??'—'} 第${e.attempt_number??'—'}次 ${JSON.stringify(e.payload)}`).join('\n')
}
