<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { dialogFocus as vDialogFocus } from './dialog-focus'

interface GroupMember {
  id: number
  name: string
  user_code?: string | null
  email: string
  is_active: boolean
}

const props = defineProps<{
  group: { id: number; name: string; leader_user_id: number }
  members: GroupMember[]
  roleLabel: (member: GroupMember) => string
  renameLabel: string
}>()
defineEmits<{ rename: []; remove: [] }>()

const showMembers = ref(false)
const dialogId = useId()
const leaderName = computed(() => props.members.find(member => member.id === props.group.leader_user_id)?.name || '—')
const sortedMembers = computed(() => [...props.members].sort((a, b) =>
  Number(b.id === props.group.leader_user_id) - Number(a.id === props.group.leader_user_id) || a.id - b.id))
</script>

<template>
  <article class="member-group-card">
    <button type="button" class="member-group-summary" :aria-label="`查看${group.name}全部成员`" aria-haspopup="dialog" :aria-expanded="showMembers" @click="showMembers=true">
      <span class="member-group-title">{{group.name}}</span>
      <span class="member-group-overview">组长：{{leaderName}} · {{members.length}} 人</span>
      <span class="member-group-view">查看成员 →</span>
    </button>
    <span class="member-group-actions"><button type="button" @click="$emit('rename')">{{renameLabel}}</button><button type="button" class="negative" @click="$emit('remove')">删除</button></span>
  </article>
  <Teleport to="body">
    <div v-if="showMembers" class="modal-backdrop member-group-backdrop" @click.self="showMembers=false">
      <section v-dialog-focus="{close:()=>{showMembers=false}}" class="modal-card member-group-dialog" role="dialog" aria-modal="true" :aria-labelledby="`${dialogId}-title`">
        <div class="member-group-dialog-heading"><div><h2 :id="`${dialogId}-title`">{{group.name}} · 组内成员</h2><p>组长：{{leaderName}} · 共 {{members.length}} 人</p></div><button type="button" class="member-group-close" aria-label="关闭成员列表" @click="showMembers=false">×</button></div>
        <div class="member-group-table-wrap">
          <table :aria-label="`${group.name}全部成员`"><thead><tr><th>成员</th><th>用户代码</th><th>角色</th><th>邮箱</th><th>状态</th></tr></thead><tbody>
            <tr v-for="member in sortedMembers" :key="member.id"><td><strong>{{member.name}}</strong><span v-if="member.id===group.leader_user_id" class="member-group-leader">组长</span></td><td>{{member.user_code || '—'}}</td><td>{{roleLabel(member)}}</td><td class="member-group-email">{{member.email}}</td><td><span class="member-group-status" :class="{inactive:!member.is_active}">{{member.is_active ? '启用中' : '已停用'}}</span></td></tr>
            <tr v-if="!sortedMembers.length"><td colspan="5" class="member-group-empty">暂无组内成员。</td></tr>
          </tbody></table>
        </div>
        <div class="modal-actions"><button type="button" class="primary" @click="showMembers=false">关闭</button></div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.member-group-card{display:flex;align-items:flex-start;min-width:0;background:#fff;border:1px solid #ebe9f3;border-radius:12px;overflow:hidden}
.member-group-summary{display:block;flex:1;min-width:0;padding:16px;text-align:left;cursor:pointer}
.member-group-summary:focus-visible{outline:2px solid #7054e7;outline-offset:-3px;border-radius:12px}
.member-group-title{display:block;margin-bottom:6px;font-size:15px;font-weight:700;overflow-wrap:anywhere}
.member-group-overview{display:block;color:#817d8f;font-size:12px;line-height:1.5}
.member-group-view{display:block;margin-top:10px;color:#6c52ca;font-size:12px}
.member-group-actions{display:flex;gap:10px;flex-shrink:0;padding:18px 16px 0 0;white-space:nowrap}.member-group-actions button{padding:0;color:#5d42d4;font-size:12px}.member-group-actions .negative{color:#bd6546}
.member-group-backdrop{z-index:30;padding:16px}
.member-group-dialog{display:flex;flex-direction:column;width:min(900px,100%);max-height:calc(100dvh - 32px);min-width:0}
.member-group-dialog-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:20px}
.member-group-dialog-heading h2{overflow-wrap:anywhere;font-size:20px}.member-group-dialog-heading p{margin:8px 0 0;color:#817d8f;font-size:13px}
.member-group-close{flex-shrink:0;padding:0 4px;font-size:25px;line-height:1;color:#817d8f}
.member-group-table-wrap{min-height:0;overflow:auto;border:1px solid #ebe9f3;border-radius:10px}
.member-group-table-wrap table{width:100%;min-width:640px;border-collapse:collapse;font-size:13px;text-align:left}
.member-group-table-wrap th{position:sticky;top:0;background:#faf9fc;color:#817d8f;font-size:12px;white-space:nowrap}
.member-group-table-wrap th,.member-group-table-wrap td{padding:14px 16px;border-bottom:1px solid #eeeaf5;vertical-align:middle}
.member-group-table-wrap tbody tr:last-child td{border-bottom:0}
.member-group-table-wrap td:first-child{min-width:140px;overflow-wrap:anywhere}
.member-group-leader{display:inline-block;margin-left:7px;font-size:11px;padding:2px 5px;border-radius:5px;color:#6546ce;background:#f0eaff;white-space:nowrap}
.member-group-email{max-width:280px;overflow-wrap:anywhere}
.member-group-status{display:inline-block;padding:3px 6px;border-radius:5px;background:#eaf4ff;color:#2772bf;font-size:11px;white-space:nowrap}.member-group-status.inactive{background:#fff2df;color:#ad7017}
.member-group-empty{padding:30px!important;color:#817d8f;text-align:center}
@media(max-width:600px){.member-group-dialog{padding:20px}.member-group-dialog-heading h2{font-size:18px}}
</style>
