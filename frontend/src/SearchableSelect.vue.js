import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
const props = withDefaults(defineProps(), {
    valueKey: 'value',
    labelKey: 'label',
    placeholder: '请选择',
    searchPlaceholder: '输入关键词搜索',
    disabled: false,
    maxVisible: 200,
});
const emit = defineEmits();
const root = ref(null);
const listbox = ref(null);
const searchInput = ref(null);
const open = ref(false);
const keyword = ref('');
const activeIndex = ref(0);
const normalizedOptions = computed(() => (props.options || []).map(option => ({
    value: (option?.[props.valueKey] ?? null),
    label: String(option?.[props.labelKey] ?? ''),
})));
const selectedLabel = computed(() => normalizedOptions.value.find(option => option.value === props.modelValue)?.label || '');
const keywordTerms = computed(() => keyword.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean));
const matchedOptions = computed(() => {
    if (!keywordTerms.value.length)
        return normalizedOptions.value;
    return normalizedOptions.value.filter(option => {
        const haystack = option.label.toLocaleLowerCase();
        return keywordTerms.value.every(term => haystack.includes(term));
    });
});
const visibleOptions = computed(() => matchedOptions.value.slice(0, props.maxVisible));
const hiddenCount = computed(() => matchedOptions.value.length - visibleOptions.value.length);
watch(() => props.options, () => {
    keyword.value = '';
    activeIndex.value = 0;
});
watch(matchedOptions, () => {
    if (activeIndex.value >= visibleOptions.value.length)
        activeIndex.value = Math.max(0, visibleOptions.value.length - 1);
});
function highlightSegments(label) {
    const terms = keywordTerms.value;
    if (!terms.length)
        return [{ text: label, match: false }];
    const haystack = label.toLocaleLowerCase();
    const flags = new Array(label.length).fill(false);
    for (const term of terms) {
        let from = 0;
        while (term) {
            const index = haystack.indexOf(term, from);
            if (index < 0)
                break;
            for (let cursor = index; cursor < index + term.length; cursor += 1)
                flags[cursor] = true;
            from = index + term.length;
        }
    }
    const segments = [];
    for (let index = 0; index < label.length; index += 1) {
        const last = segments[segments.length - 1];
        if (last && last.match === flags[index])
            last.text += label[index];
        else
            segments.push({ text: label[index], match: flags[index] });
    }
    return segments;
}
function indexOfSelected() {
    const index = matchedOptions.value.findIndex(option => option.value === props.modelValue);
    return index < 0 ? 0 : Math.min(index, props.maxVisible - 1);
}
async function openPanel() {
    if (props.disabled)
        return;
    keyword.value = '';
    activeIndex.value = indexOfSelected();
    open.value = true;
    await nextTick();
    searchInput.value?.focus();
    scrollActiveIntoView();
}
function closePanel() {
    open.value = false;
    keyword.value = '';
}
function togglePanel() {
    if (open.value)
        closePanel();
    else
        void openPanel();
}
function selectOption(value) {
    emit('update:modelValue', value);
    emit('change', value);
    closePanel();
}
function scrollActiveIntoView() {
    void nextTick(() => {
        const element = listbox.value?.children[activeIndex.value];
        element?.scrollIntoView({ block: 'nearest' });
    });
}
function moveActive(step) {
    if (!visibleOptions.value.length)
        return;
    const total = visibleOptions.value.length;
    activeIndex.value = (activeIndex.value + step + total) % total;
    scrollActiveIntoView();
}
function onSearchKeydown(event) {
    if (event.key === 'ArrowDown') {
        event.preventDefault();
        moveActive(1);
        return;
    }
    if (event.key === 'ArrowUp') {
        event.preventDefault();
        moveActive(-1);
        return;
    }
    if (event.key === 'Enter') {
        event.preventDefault();
        const option = visibleOptions.value[activeIndex.value];
        if (option)
            selectOption(option.value);
        return;
    }
    if (event.key === 'Escape') {
        event.preventDefault();
        closePanel();
    }
}
function onTriggerKeydown(event) {
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        void openPanel();
    }
}
function onDocumentPointerDown(event) {
    if (!open.value)
        return;
    if (!root.value?.contains(event.target))
        closePanel();
}
onMounted(() => document.addEventListener('mousedown', onDocumentPointerDown));
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocumentPointerDown));
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_withDefaultsArg = (function (t) { return t; })({
    valueKey: 'value',
    labelKey: 'label',
    placeholder: '请选择',
    searchPlaceholder: '输入关键词搜索',
    disabled: false,
    maxVisible: 200,
});
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ref: "root",
    ...{ class: "search-select" },
    ...{ class: ({ 'is-open': __VLS_ctx.open, 'is-disabled': __VLS_ctx.disabled }) },
});
/** @type {typeof __VLS_ctx.root} */ ;
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (__VLS_ctx.togglePanel) },
    ...{ onKeydown: (__VLS_ctx.onTriggerKeydown) },
    type: "button",
    ...{ class: "search-select-trigger" },
    disabled: (__VLS_ctx.disabled),
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
    ...{ class: "search-select-value" },
    ...{ class: ({ 'is-placeholder': !__VLS_ctx.selectedLabel }) },
});
(__VLS_ctx.selectedLabel || __VLS_ctx.placeholder);
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
    ...{ class: "search-select-caret" },
    'aria-hidden': "true",
});
if (__VLS_ctx.open) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "search-select-panel" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "search-select-search" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        ...{ onKeydown: (__VLS_ctx.onSearchKeydown) },
        ref: "searchInput",
        value: (__VLS_ctx.keyword),
        type: "text",
        placeholder: (__VLS_ctx.searchPlaceholder),
    });
    /** @type {typeof __VLS_ctx.searchInput} */ ;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.ul, __VLS_intrinsicElements.ul)({
        ref: "listbox",
        ...{ class: "search-select-list" },
        role: "listbox",
    });
    /** @type {typeof __VLS_ctx.listbox} */ ;
    for (const [option, index] of __VLS_getVForSourceType((__VLS_ctx.visibleOptions))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({
            ...{ onMouseenter: (...[$event]) => {
                    if (!(__VLS_ctx.open))
                        return;
                    __VLS_ctx.activeIndex = index;
                } },
            ...{ onMousedown: () => { } },
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.open))
                        return;
                    __VLS_ctx.selectOption(option.value);
                } },
            key: (String(option.value)),
            ...{ class: "search-select-option" },
            ...{ class: ({ 'is-active': index === __VLS_ctx.activeIndex, 'is-selected': option.value === __VLS_ctx.modelValue }) },
            role: "option",
            'aria-selected': (option.value === __VLS_ctx.modelValue),
        });
        for (const [segment, segmentIndex] of __VLS_getVForSourceType((__VLS_ctx.highlightSegments(option.label)))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                key: (segmentIndex),
                ...{ class: ({ 'search-select-hit': segment.match }) },
            });
            (segment.text);
        }
    }
    if (!__VLS_ctx.visibleOptions.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({
            ...{ class: "search-select-empty" },
        });
        (__VLS_ctx.keyword.trim() ? '没有匹配的类目' : '暂无可选类目');
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "search-select-footer" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.matchedOptions.length);
    (__VLS_ctx.normalizedOptions.length);
    if (__VLS_ctx.hiddenCount > 0) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.visibleOptions.length);
    }
}
/** @type {__VLS_StyleScopedClasses['search-select']} */ ;
/** @type {__VLS_StyleScopedClasses['search-select-trigger']} */ ;
/** @type {__VLS_StyleScopedClasses['search-select-value']} */ ;
/** @type {__VLS_StyleScopedClasses['search-select-caret']} */ ;
/** @type {__VLS_StyleScopedClasses['search-select-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['search-select-search']} */ ;
/** @type {__VLS_StyleScopedClasses['search-select-list']} */ ;
/** @type {__VLS_StyleScopedClasses['search-select-option']} */ ;
/** @type {__VLS_StyleScopedClasses['search-select-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['search-select-footer']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            root: root,
            listbox: listbox,
            searchInput: searchInput,
            open: open,
            keyword: keyword,
            activeIndex: activeIndex,
            normalizedOptions: normalizedOptions,
            selectedLabel: selectedLabel,
            matchedOptions: matchedOptions,
            visibleOptions: visibleOptions,
            hiddenCount: hiddenCount,
            highlightSegments: highlightSegments,
            togglePanel: togglePanel,
            selectOption: selectOption,
            onSearchKeydown: onSearchKeydown,
            onTriggerKeydown: onTriggerKeydown,
        };
    },
    __typeEmits: {},
    __typeProps: {},
    props: {},
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
    __typeEmits: {},
    __typeProps: {},
    props: {},
});
; /* PartiallyEnd: #4569/main.vue */
