import { App, Button, Card, Flex, Select, Skeleton, Typography } from 'antd'
import { useState } from 'react'

import { useSiteAssignments, useUpdateSiteAssignments } from '../../api/hooks'

/**
 * Which sites each CRA covers. SimpleTrials does not record it (its site contacts are site staff), so an
 * administrator sets it here; a CRA's Overview then shows only their sites.
 */
export function SiteAssignmentsCard() {
  const { message } = App.useApp()
  const { data, isLoading } = useSiteAssignments(true)
  const update = useUpdateSiteAssignments()
  const [person, setPerson] = useState<string>()
  const [draft, setDraft] = useState<string[] | null>(null)

  if (isLoading || !data) return <Skeleton active />
  const chosen = person ?? data.people.find((p) => /clinical research/i.test(p.job_title))?.id ?? data.people[0]?.id
  const saved = (chosen && data.assignments[chosen]) || []
  const value = draft ?? saved
  const changed = draft !== null && (draft.length !== saved.length || draft.some((k) => !saved.includes(k)))

  return (
    <Card title="CRA site assignments" data-testid="site-assignments">
      <Flex vertical gap={12}>
        <Typography.Text type="secondary">
          Choose the sites each CRA covers; their Overview then shows only those sites. SimpleTrials does not record which CRA
          covers which site, so it is set here. Until a CRA has sites, their Overview shows all sites.
        </Typography.Text>
        <Flex gap={12} wrap align="flex-end">
          <Flex vertical gap={4}>
            <label htmlFor="assign-person" style={{ fontSize: 12, fontWeight: 600, color: '#5B6B82' }}>
              Person
            </label>
            <Select
              id="assign-person"
              aria-label="Person"
              value={chosen}
              onChange={(v: string) => {
                setPerson(v)
                setDraft(null)
              }}
              options={data.people.map((p) => ({ value: p.id, label: `${p.name} · ${p.job_title}` }))}
              style={{ width: 300, maxWidth: '100%' }}
            />
          </Flex>
          <Flex vertical gap={4} style={{ flex: '1 1 320px' }}>
            <label htmlFor="assign-sites" style={{ fontSize: 12, fontWeight: 600, color: '#5B6B82' }}>
              Sites
            </label>
            <Select
              id="assign-sites"
              aria-label="Sites"
              mode="multiple"
              allowClear
              placeholder="No sites (shows all sites)"
              value={value}
              onChange={(v: string[]) => setDraft(v)}
              options={data.sites.map((s) => ({ value: s.key, label: s.label }))}
              optionFilterProp="label"
            />
          </Flex>
          <Button
            type="primary"
            disabled={!chosen || !changed}
            loading={update.isPending}
            onClick={() =>
              chosen &&
              update.mutate(
                { personId: chosen, sites: value },
                {
                  onSuccess: () => {
                    setDraft(null)
                    void message.success('Sites saved')
                  },
                  onError: (e) => void message.error(e.message),
                },
              )
            }
          >
            Save
          </Button>
        </Flex>
      </Flex>
    </Card>
  )
}
