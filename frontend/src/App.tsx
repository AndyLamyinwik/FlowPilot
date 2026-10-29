import HomePage from './pages/HomePage'
import WorkflowEditorPage from './pages/WorkflowEditorPage'
import DashboardPage from './pages/DashboardPage'

export default function App() {
  if (window.location.pathname === '/home') return <HomePage />
  if (window.location.pathname === '/editor') return <WorkflowEditorPage initialWorkflowId={new URLSearchParams(window.location.search).get('id')} />
  return <DashboardPage />
}
