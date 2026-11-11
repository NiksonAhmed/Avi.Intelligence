import { Navigate, createBrowserRouter } from 'react-router'
import type { RouteObject } from 'react-router'

import { ComingSoon } from './components/ComingSoon'
import { AppLayout } from './layout/AppLayout'
import { NotFound } from './pages/NotFound'
import { ConnectorsPage } from './pages/admin/ConnectorsPage'
import { DataManagementPage } from './modules/data-management/DataManagementPage'
import { AuditTrailPage } from './pages/audit/AuditTrailPage'
import { AskPage } from './pages/documents/AskPage'
import { SopDetailPage } from './pages/documents/SopDetailPage'
import { SopListPage } from './pages/documents/SopListPage'
import { ReportsPage } from './pages/reports/ReportsPage'
import { CommandCentreIndexPage, StudyCommandCentrePage } from './pages/studies/StudyCommandCentrePage'
import { StudyPortfolioPage } from './pages/studies/StudyPortfolioPage'
import { MyTasksPage } from './pages/work/MyTasksPage'
import { RisksPage } from './pages/work/RisksPage'

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
      { path: 'portfolio', element: <StudyPortfolioPage /> },
      { path: 'command-centre', element: <CommandCentreIndexPage /> },
      { path: 'command-centre/:studyId', element: <StudyCommandCentrePage /> },
      { path: 'tasks', element: <MyTasksPage /> },
      { path: 'risks', element: <RisksPage /> },
      { path: 'documents', element: <Navigate to="/documents/sops" replace /> },
      { path: 'documents/sops', element: <SopListPage /> },
      { path: 'documents/sops/:sopId', element: <SopDetailPage /> },
      { path: 'documents/ask', element: <AskPage /> },
      { path: 'reports', element: <ReportsPage /> },
      { path: 'data-management', element: <DataManagementPage /> },
      { path: 'admin', element: <Navigate to="/admin/connectors" replace /> },
      { path: 'admin/connectors', element: <ConnectorsPage /> },
      { path: 'audit', element: <AuditTrailPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]

export const createAppRouter = () => createBrowserRouter(routes)
