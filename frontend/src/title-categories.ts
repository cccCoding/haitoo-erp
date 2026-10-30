export type CategoryChoice = { source_key: string; target_id: number | null; new_name: string | null; save_alias: boolean }
export type CategoryEdit = { source_key: string; selection: number | 'new' | ''; newName: string; saveAlias: boolean }

export function categoryEdits(items: any[]): CategoryEdit[] {
  return items.map(item => ({ source_key: item.source_key,
    selection: item.target_id || (item.new_name ? 'new' : ''),
    newName: item.new_name || item.source, saveAlias: item.save_alias ?? true }))
}

export function categoryChoices(edits: CategoryEdit[]): CategoryChoice[] {
  return edits.map(edit => {
    if (!edit.selection || (edit.selection === 'new' && !edit.newName.trim())) throw new Error('请为每个陌生分类选择已有分类或填写新分类名称')
    return { source_key: edit.source_key, target_id: typeof edit.selection === 'number' ? edit.selection : null,
      new_name: edit.selection === 'new' ? edit.newName.trim() : null, save_alias: edit.saveAlias }
  })
}

export function parseCategoryAliases(value: string): string[] {
  return [...new Set(value.split(/\r?\n/).map(name => name.trim()).filter(Boolean))]
}
