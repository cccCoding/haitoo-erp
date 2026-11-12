export const display=(v:unknown)=>v===null || v===undefined ? '—' : typeof v==='number' ? v.toLocaleString('zh-CN') : String(v)
export const percent=(v:number|null|undefined)=>v===null || v===undefined ? '—' : `${(v*100).toFixed(2)}%`
export const filterParams=(filters:Record<string,unknown>)=>Object.fromEntries(Object.entries(filters).filter(([,value])=>value!==''&&value!==null&&value!==undefined))

type MatrixDeviceStatus = {is_active:boolean;online:boolean;version:string;hub_identity?:string|null;hub_connected:boolean;sync_at?:string|null;paused:boolean;capabilities?:Record<string,string[]>;permissions?:{enabled:boolean;collect_enabled:boolean;listing_enabled:boolean}}
export function deviceSetup(device:MatrixDeviceStatus,config:{enabled:boolean;listing_enabled:boolean},now=Date.now()){
 const result=(code:string,title:string,description:string,canSync=false)=>({code,title,description,canSync})
 if(!device.is_active)return result('revoked','授权已撤销','此电脑需要重新在 ERP 授权后才能连接。')
 if(!device.online)return result('offline','等待电脑上线','请在此电脑启动连接器，保持电脑与网络在线。')
 if(device.version==='协议4')return result('upgrade','需要更新连接器','此电脑使用旧版执行器，请更新为新版连接器。')
 if(device.permissions?.enabled===false)return result('permission','未获得矩阵授权','请联系公司管理员为此账号启用“使用矩阵”。')
 if(!config.enabled)return result('disabled','等待启用矩阵','请联系平台管理员在公司配置中启用 TK 矩阵。')
 if(!device.hub_identity)return result('team','待配置团队 ID','填写当前 HubStudio 团队的稳定 ID，同一团队的电脑保持一致。')
 if(!device.hub_connected)return result('hub','等待连接 HubStudio','请在此电脑启动并登录 HubStudio，确认 Local API 已开启，再点击重新连接。',true)
 if(!device.sync_at)return result('sync','等待同步环境','点击同步环境，完整目录上传后会显示在 ERP 环境列表中。',true)
 const syncTime=Date.parse(device.sync_at)
 if(!Number.isFinite(syncTime)||now-syncTime>300000)return result('stale','环境目录待更新','最近五分钟内没有完成同步，请重新同步环境。',true)
 if(device.paused)return result('paused','已暂停接收新任务','环境仍可同步；恢复后继续接收 ERP 下发的新任务。',true)
 if(device.permissions&&!device.permissions.collect_enabled&&!device.permissions.listing_enabled)return result('operation_permission','仅可查看和同步环境','尚未获得采集或上品授权，请联系公司管理员。',true)
 const collect=device.permissions?.collect_enabled!==false&&!!device.capabilities?.['shop.collect']?.length
 const listing=device.permissions?.listing_enabled!==false&&config.listing_enabled&&!!device.capabilities?.['listing.catalog']?.length
 if(!collect&&!listing)return result('capabilities','环境可同步，执行能力未开放','可先同步和查看环境；采集或上品需设备开放对应站点能力。',true)
 return result('ready','基础连接已就绪','可在环境列表选择环境并创建方案，实际执行以预览校验为准。',true)
}
