import type { ObjectDirective } from 'vue'

type DialogOptions = { close: () => void; busy?: boolean }
type DialogState = { options: DialogOptions; previous: HTMLElement | null; keydown: (event: KeyboardEvent) => void }
const states = new WeakMap<HTMLElement, DialogState>()
let activeDialogs = 0
let originalOverflow = ''
const focusable = (element: HTMLElement) => Array.from(element.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], summary, [tabindex="0"]')).filter(item => item.getClientRects().length && item.getAttribute('aria-hidden') !== 'true')

// 所有后台弹窗共用键盘行为：初始焦点、Tab 循环、Escape、关闭后还原焦点。
export const dialogFocus: ObjectDirective<HTMLElement, DialogOptions> = {
  mounted(element, binding) {
    const state: DialogState = {
      options: binding.value,
      previous: document.activeElement instanceof HTMLElement ? document.activeElement : null,
      keydown(event) {
        if (event.key === 'Escape') {
          event.preventDefault()
          if (!state.options.busy) state.options.close()
        }
        if (event.key !== 'Tab') return
        const items = focusable(element)
        const first = items[0], last = items[items.length - 1]
        if (!first) { event.preventDefault(); element.focus(); return }
        if (event.shiftKey && (document.activeElement === first || !element.contains(document.activeElement))) {
          event.preventDefault(); last.focus()
        } else if (!event.shiftKey && (document.activeElement === last || !element.contains(document.activeElement))) {
          event.preventDefault(); first.focus()
        }
      },
    }
    states.set(element, state)
    element.tabIndex = -1
    // 弹窗切换时，新弹窗可能先挂载；只在首个弹窗打开时保存原状态。
    if (activeDialogs++ === 0) originalOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', state.keydown)
    queueMicrotask(() => {
      if (!element.isConnected) return
      const field = element.querySelector<HTMLElement>('input:not(:disabled):not([aria-hidden="true"]), select:not(:disabled):not([aria-hidden="true"]), textarea:not(:disabled)')
      ;(field || focusable(element)[0] || element).focus()
    })
  },
  updated(element, binding) { const state = states.get(element); if (state) state.options = binding.value },
  unmounted(element) {
    const state = states.get(element)
    if (!state) return
    document.removeEventListener('keydown', state.keydown)
    // 仍有其他弹窗时继续锁定页面，最后一个弹窗关闭后才恢复。
    if (--activeDialogs === 0) document.body.style.overflow = originalOverflow
    if (state.previous?.isConnected) state.previous.focus()
    states.delete(element)
  },
}
