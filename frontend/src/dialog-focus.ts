import type { ObjectDirective } from 'vue'

type DialogOptions = { close: () => void; busy?: boolean }
type DialogState = { options: DialogOptions; previous: HTMLElement | null; overflow: string; keydown: (event: KeyboardEvent) => void }
const states = new WeakMap<HTMLElement, DialogState>()
const focusable = (element: HTMLElement) => Array.from(element.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]')).filter(item => item.getClientRects().length)

// 所有后台弹窗共用键盘行为：初始焦点、Tab 循环、Escape、关闭后还原焦点。
export const dialogFocus: ObjectDirective<HTMLElement, DialogOptions> = {
  mounted(element, binding) {
    const state: DialogState = {
      options: binding.value,
      previous: document.activeElement instanceof HTMLElement ? document.activeElement : null,
      overflow: document.body.style.overflow,
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
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', state.keydown)
    queueMicrotask(() => {
      if (!element.isConnected) return
      const field = element.querySelector<HTMLElement>('input:not(:disabled), select:not(:disabled)')
      ;(field || focusable(element)[0] || element).focus()
    })
  },
  updated(element, binding) { const state = states.get(element); if (state) state.options = binding.value },
  unmounted(element) {
    const state = states.get(element)
    if (!state) return
    document.removeEventListener('keydown', state.keydown)
    document.body.style.overflow = state.overflow
    if (state.previous?.isConnected) state.previous.focus()
    states.delete(element)
  },
}
