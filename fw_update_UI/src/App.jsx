import { lazy, Suspense, useState } from 'react'
import { Box, CircularProgress } from '@mui/material'
import HomePage from './pages/HomePage'

const ManualPage = lazy(() => import('./pages/ManualPage'))
const MassUpdatePage = lazy(() => import('./pages/MassUpdatePage'))

export default function App() {
  const [page, setPage] = useState('home')
  return (
    <Suspense fallback={<Box role="status" aria-label="Loading screen" sx={{ display: 'grid', placeItems: 'center', minHeight: '100vh' }}><CircularProgress /></Box>}>
      {page === 'manual' ? <ManualPage onBack={() => setPage('home')} />
        : page === 'mass' ? <MassUpdatePage onBack={() => setPage('home')} />
          : <HomePage onNavigate={setPage} />}
    </Suspense>
  )
}
