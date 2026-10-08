import { ref } from 'vue';
const dialog = ref(null);
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
/** @type {__VLS_StyleScopedClasses['shop-data-info']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-info']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-info']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-help']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-help']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-help']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-help']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-help']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-help-close']} */ ;
// CSS variable injection 
// CSS variable injection end 
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
    ...{ class: "shop-data-heading" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (...[$event]) => {
            __VLS_ctx.dialog?.showModal();
        } },
    type: "button",
    ...{ class: "shop-data-info" },
    'aria-label': "查看店铺数据格式说明",
    'aria-haspopup': "dialog",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.svg, __VLS_intrinsicElements.svg)({
    viewBox: "0 0 20 20",
    fill: "none",
    'aria-hidden': "true",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.circle)({
    cx: "10",
    cy: "10",
    r: "7.5",
    stroke: "currentColor",
    'stroke-width': "1.5",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.path)({
    d: "M10 9v5",
    stroke: "currentColor",
    'stroke-width': "1.5",
    'stroke-linecap': "round",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.circle)({
    cx: "10",
    cy: "6",
    r: "1",
    fill: "currentColor",
});
const __VLS_0 = {}.Teleport;
/** @type {[typeof __VLS_components.Teleport, typeof __VLS_components.Teleport, ]} */ ;
// @ts-ignore
const __VLS_1 = __VLS_asFunctionalComponent(__VLS_0, new __VLS_0({
    to: "body",
}));
const __VLS_2 = __VLS_1({
    to: "body",
}, ...__VLS_functionalComponentArgsRest(__VLS_1));
__VLS_3.slots.default;
__VLS_asFunctionalElement(__VLS_intrinsicElements.dialog, __VLS_intrinsicElements.dialog)({
    ...{ onClick: (...[$event]) => {
            __VLS_ctx.dialog?.close();
        } },
    ref: "dialog",
    ...{ class: "shop-data-help" },
    'aria-label': "店铺数据格式说明",
});
/** @type {typeof __VLS_ctx.dialog} */ ;
__VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (...[$event]) => {
            __VLS_ctx.dialog?.close();
        } },
    type: "button",
    ...{ class: "shop-data-help-close" },
    'aria-label': "关闭店铺数据格式说明",
    autofocus: true,
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
    ...{ class: "shop-data-format" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
var __VLS_3;
/** @type {__VLS_StyleScopedClasses['shop-data-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-info']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-help']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-help-close']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-data-format']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            dialog: dialog,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
