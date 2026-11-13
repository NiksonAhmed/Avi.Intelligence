import { SyncOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { App, Button } from 'antd'
import { useState } from 'react'

import { useHasPermission, useRefreshSops, useStudiesSync } from '../api/hooks'

/** Where Sync now pulls from. */
export type ReportSync = 'simpletrials' | 'sharepoint' | 'live'

/** Sync now (everyone; read-only towards the source): SimpleTrials, the SharePoint SOP library, or live app data. */
export function SyncNowButton({ kind }: { kind: ReportSync }) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const canSyncStudies = useHasPermission('study.sync')
  const studies = useStudiesSync()
  const sops = useRefreshSops()
  const [refreshing, setRefreshing] = useState(false)
  if (kind === 'simpletrials' && !canSyncStudies) return null

  const fail = (e: Error) => void message.error(e.message)
  const onClick = () => {
    if (kind === 'simpletrials') {
      studies.mutate(undefined, {
        onSuccess: (s) =>
          s.last_sync?.ok
            ? void message.success('Synced from SimpleTrials')
            : void message.error(s.last_sync?.error ?? 'Sync failed'),
        onError: fail,
      })
    } else if (kind === 'sharepoint') {
      sops.mutate(undefined, {
        onSuccess: async () => {
          await queryClient.invalidateQueries({ queryKey: ['reports'] })
          void message.success('Synced from SharePoint')
        },
        onError: fail,
      })
    } else {
      setRefreshing(true)
      void queryClient
        .invalidateQueries({ queryKey: ['reports'] })
        .then(() => void message.success('Figures refreshed'))
        .finally(() => setRefreshing(false))
    }
  }
  const loading = kind === 'simpletrials' ? studies.isPending : kind === 'sharepoint' ? sops.isPending : refreshing
  return (
    <Button icon={<SyncOutlined />} loading={loading} onClick={onClick}>
      Sync now
    </Button>
  )
}
