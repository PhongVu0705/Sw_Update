import { Alert, Box, Button, Chip, Stack, Typography } from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import { api } from '../api'

export default function ScreenLayout({ title, connection, onBack, backDisabled, error, children, footer, titleAction, compact = false, fitViewport = false }) {
  return (
    <Box sx={{ minHeight: fitViewport ? 0 : '100vh', height: fitViewport ? '100dvh' : 'auto', overflow: fitViewport ? 'hidden' : 'visible', display: 'flex', flexDirection: 'column' }}>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <Box component="header" sx={{ flexShrink: 0, bgcolor: 'primary.main', color: 'white', px: { xs: 2, md: compact ? 3 : 4 }, py: compact ? 1.5 : 2.5 }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Button color="inherit" startIcon={<ArrowBackIcon />} onClick={onBack} disabled={backDisabled} sx={{ '&.Mui-disabled': { color: '#ffffff70' } }}>Main Menu</Button>
            <Typography component="h1" variant="h2">{title}</Typography>
            {titleAction}
          </Stack>
          <Chip role="status" label={connection.connected ? `Connected: ${connection.port}` : 'Not Connected'} sx={{ bgcolor: '#ffffff', color: connection.connected ? 'success.main' : 'text.secondary', fontWeight: 650 }} />
        </Stack>
      </Box>
      <Box component="main" id="main-content" sx={{ flex: 1, minHeight: 0, overflow: fitViewport ? 'hidden' : 'visible', p: { xs: 2, md: compact ? 2 : 3 }, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {api.mode === 'mock' && <Alert severity="warning" sx={{ flexShrink: 0 }}>{compact ? 'SIMULATION' : 'SIMULATION — sample data only. No commands are sent to hardware.'}</Alert>}
        {error && <Alert severity="error" sx={{ flexShrink: 0 }}>{error}</Alert>}
        {children}
      </Box>
      {footer && <Box sx={{ flexShrink: 0 }}>{footer}</Box>}
    </Box>
  )
}
