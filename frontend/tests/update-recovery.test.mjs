import test from 'node:test'
import assert from 'node:assert/strict'
import {updateRecovery,platformSteps} from '../src/hub/update-recovery.ts'
test('unexplained startup failure is never described as a confirmed system block',()=>{
 const result=updateRecovery({manual_required:true,error_code:'NEW_VERSION_START_FAILED'})
 assert.equal(result.needed,true);assert.equal(result.canRetry,true);assert.match(result.message,/原因尚未确定/)
})
test('package integrity and channel failures require manual installation rather than bypass',()=>{
 for(const error_code of ['NATIVE_SIGNATURE_FAILED','PACKAGE_VALIDATION_FAILED','LAUNCHER_TOO_OLD','UPDATE_CHANNEL_MISMATCH']){
  const result=updateRecovery({manual_required:true,error_code});assert.equal(result.canRetry,false)
 }
 assert.equal(updateRecovery({status:'up_to_date'}).needed,false)
 assert.equal(updateRecovery({status:'rolled_back'}).needed,true)
})
test('guidance describes optional OS permission and keeps security settings intact',()=>{
 assert.match(platformSteps('windows').join(' '),/并非所有拦截/)
 assert.match(platformSteps('macos').join(' '),/隐私与安全性/)
 for(const platform of ['windows','macos',''])assert.match(platformSteps(platform).join(' '),/不要关闭系统防护/)
})

test('integrity failures never suggest granting an OS exception',()=>{const steps=platformSteps('windows','PACKAGE_VALIDATION_FAILED').join(' ');assert.doesNotMatch(steps,/仍要运行|更多信息/);assert.match(steps,/不能通过系统例外/)})
