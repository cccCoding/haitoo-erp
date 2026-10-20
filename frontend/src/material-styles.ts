export type MaterialStyle = {
  id: number
  template_id: number
  name: string
  created_by: number
  created_by_name: string
  source_exists: boolean
  white_image_url: string | null
  material_count: number
}

export function styleOptions(styles: MaterialStyle[], templateId: number | null) {
  return styles.filter(style => templateId == null || style.template_id === templateId).map(style => ({
    value: style.id,
    label: `${style.name} · ${style.created_by_name} · #${style.id}${style.source_exists ? '' : '（白底图已删除）'}`,
  }))
}

export function commonStyleTemplate(items: {template_id: number | null}[]): number | null {
  const first = items[0]?.template_id
  return first && items.every(item => item.template_id === first) ? first : null
}

export function applySelectedStyle(items: {selected: boolean; style_id: number | null}[], styleId: number | null) {
  for (const item of items) if (item.selected) item.style_id = styleId
}
