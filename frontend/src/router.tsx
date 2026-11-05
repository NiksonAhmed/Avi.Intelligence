import { Navigate, createBrowserRouter } from 'react-router'
import type { RouteObject } from 'react-router'

import { ComingSoon } from './components/ComingSoon'
import { AppLayout } from './layout/AppLayout'
import { NotFound } from './pages/NotFound'
import { ConnectorsPage } from './pages/admin/ConnectorsPage'
import { AuditTrailPage } from './pages/audit/AuditTrailPage'
import { SopDetailPage } from './pages/documents/SopDetailPage'
import { SopListPage } from './pages/documents/SopListPage'

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: (
          <ComingSoon
            title="Overview"
            description="Your personalised portfolio dashboard arrives once study data is connected."
          />
        ),
      },
      {
        path: 'portfolio',
        element: <ComingSoon title="Study Portfolio" description="Study list with phase, status and milestones." />,
      },
      {
        path: 'command-centre',
        element: (
          <ComingSoon
            title="Study Command Centre"
            description="A single workspace per study: milestones, tasks, risks, team and documents."
          />
        ),
      },
      {
        path: 'tasks',
        element: <ComingSoon title="My Tasks" description="Your assigned tasks across studies." />,
      },
      {
        path: 'risks',
        element: <ComingSoon title="Risks and Issues" description="Risk and issue registers across studies." />,
      },
      { path: 'documents', element: <Navigate to="/documents/sops" replace /> },
      { path: 'documents/sops', element: <SopListPage /> },
      { path: 'documents/sops/:sopId', element: <SopDetailPage /> },
      {
        path: 'reports',
        element: (
          <ComingSoon title="Reports and Insights" description="Study health and portfolio reporting." />
        ),
      },
      { path: 'admin', element: <Navigate to="/admin/connectors" replace /> },
      { path: 'admin/connectors', element: <ConnectorsPage /> },
      { path: 'audit', element: <AuditTrailPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]

export const createAppRouter = () => createBrowserRouter(routes)
