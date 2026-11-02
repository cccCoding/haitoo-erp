<script setup lang="ts">
import {computed,ref} from 'vue'
type Shop={id:number;name:string;container_code:string;group:string;shop_name?:string;account_names?:string[]}
const props=defineProps<{modelValue:number[];options:Shop[];loading:boolean;error:string}>()
const emit=defineEmits<{'update:modelValue':[ids:number[]];retry:[]}>()
const search=ref('')
const selected=computed(()=>new Set(props.modelValue))
const unavailable=computed(()=>props.modelValue.filter(id=>!props.options.some(e=>e.id===id)))
const visible=computed(()=>{
 const q=search.value.trim().toLocaleLowerCase()
 return props.options.filter(e=>[e.name,e.shop_name,e.container_code,e.group,...(e.account_names||[])].join(' ').toLocaleLowerCase().includes(q))
})
const groups=computed(()=>{
 const result=new Map<string,Shop[]>()
 for(const env of visible.value){const list=result.get(env.group)||[];list.push(env);result.set(env.group,list)}
 return [...result].map(([name,items])=>({name,items,count:items.filter(e=>selected.value.has(e.id)).length}))
})
function choose(items:Shop[],checked:boolean){
 const ids=new Set(props.modelValue)
 for(const item of items){if(checked)ids.add(item.id);else ids.delete(item.id)}
 if(ids.size>1000){limitError.value='最多选择 1000 个店铺，请缩小选择范围';return}
 limitError.value='';emit('update:modelValue',[...ids])
}
const limitError=ref('')
function clear(){limitError.value='';emit('update:modelValue',[])}
</script>

<template>
<details class="shop-select">
 <summary>已选 {{modelValue.length}} 个店铺 <span>选择店铺 ▾</span></summary>
 <div class="shop-menu">
  <input v-model="search" type="search" aria-label="搜索定时店铺" placeholder="搜索店铺、环境编号或分组"/>
  <div class="shop-actions"><button type="button" :disabled="loading||!!error||!visible.length" @click="choose(visible,true)">全选搜索结果</button><button type="button" :disabled="loading||!!error" @click="choose(visible,false)">取消搜索结果</button><button type="button" :disabled="!modelValue.length" @click="clear">清空全部</button></div>
  <p v-if="loading" role="status">正在加载店铺…</p>
  <p v-else-if="error" role="alert">{{error}} <button type="button" @click="emit('retry')">重新加载</button></p>
  <template v-else>
   <p v-if="unavailable.length" role="alert">{{unavailable.length}} 个已选店铺当前不可用。<button type="button" @click="emit('update:modelValue',modelValue.filter(id=>!unavailable.includes(id)))">移除不可用店铺</button></p>
   <p v-if="!visible.length">{{options.length?'没有匹配的店铺':'该设备暂无店铺，请先同步环境'}}</p>
   <div class="shop-list">
    <section v-for="group in groups" :key="group.name">
     <div class="shop-group"><b>{{group.name||'未分组'}}（{{group.count}} / {{group.items.length}}）</b><div><button type="button" @click="choose(group.items,true)">全选本组</button><button type="button" @click="choose(group.items,false)">取消本组</button></div></div>
     <label v-for="env in group.items" :key="env.id" class="shop-option"><input type="checkbox" :checked="selected.has(env.id)" @change="choose([env],($event.target as HTMLInputElement).checked)"/><span><b>{{env.shop_name||env.name}}</b><small>{{env.shop_name?env.name+' · ':''}}{{env.container_code}}</small></span></label>
    </section>
   </div>
  </template>
  <p v-if="limitError" role="alert">{{limitError}}</p>
 </div>
</details>
</template>

<style scoped>
.shop-select{border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#50586b;font-size:12px}
summary{display:flex;justify-content:space-between;gap:12px;padding:10px 12px;cursor:pointer;list-style:none}summary::-webkit-details-marker{display:none}summary span{color:#7964b4}
summary:focus-visible{outline:2px solid #7256e7;outline-offset:2px;border-radius:6px}
.shop-menu{padding:10px;border-top:1px solid #ececf3}.shop-menu input[type=search]{width:100%;box-sizing:border-box;border:1px solid #dfe2eb;border-radius:6px;padding:8px 10px;font:inherit}
.shop-actions,.shop-group,.shop-group>div{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.shop-actions{margin:8px 0}.shop-group{justify-content:space-between;padding:7px 8px;background:#f7f5fc;position:sticky;top:0;z-index:1}
button{border:1px solid #e4dfef;border-radius:5px;background:#fff;padding:4px 7px;font:inherit;color:#7059a5;cursor:pointer}button:disabled{opacity:.5;cursor:default}
.shop-list{max-height:250px;overflow:auto;overscroll-behavior:contain}
.shop-option{display:flex;flex-direction:row;align-items:center;gap:8px;padding:8px;cursor:pointer}.shop-option:hover{background:#faf9fd}.shop-option input{width:14px;height:14px;accent-color:#6043d4}.shop-option span{display:flex;flex-direction:column;gap:3px;min-width:0;overflow-wrap:anywhere}.shop-option b{font-weight:500}.shop-option small{color:#8a92a2;font-size:11px}
p{font-size:12px;line-height:1.6}p[role=alert]{color:#b84a51}
</style>
