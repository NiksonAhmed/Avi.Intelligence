import { useMe } from '../api/hooks'
import type { SopDocument, TaskCategory } from '../api/types'

const CATEGORY_ORDER: TaskCategory[] = ['study', 'sop', 'vendor', 'system', 'general']

/** Approved SOPs and their forms, as Select options (forms indented under their SOP). */
export function sopOptions(docs: SopDocument[]) {
  return docs
    .filter((d) => d.status === 'Effective' && (d.kind === 'sop' || d.kind === 'form'))
    .map((d) => {
      const number = d.sop_number ?? 'Unnumbered'
      const version = d.version ? ` v${d.version}` : ''
      return {
        value: d.id,
        label: `${number}${version} · ${d.title}`,
        kind: d.kind,
      }
    })
}

/** What the current user may do with tasks, from their permissions (the server checks again). */
export function useTaskRights(): { create: TaskCategory[]; assign: TaskCategory[]; meId: string | null } {
  const { data: me } = useMe()
  const permissions = me?.permissions ?? []
  const admin = permissions.includes('work.manage')
  const assign = CATEGORY_ORDER.filter((c) => admin || permissions.includes(`task.assign.${c}`))
  const own = permissions.includes('task.create_own')
  // Own tasks: any category except Procedures and SOPs.
  const create = CATEGORY_ORDER.filter((c) => assign.includes(c) || (own && c !== 'sop'))
  return { create, assign, meId: me?.id ?? null }
}

/** Categories the current user may create tasks in. */
export function useCreatableCategories(): TaskCategory[] {
  return useTaskRights().create
}

/** "Demo CRA One", "Demo CRA One and Demo CRA Two", "Demo CRA One +2". */
export function assigneeSummary(names: string[]): string {
  if (names.length <= 2) return names.join(' and ')
  return `${names[0]} +${names.length - 1}`
}
