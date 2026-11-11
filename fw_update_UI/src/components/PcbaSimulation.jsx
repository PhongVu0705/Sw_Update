import { Button, Paper, Stack, Typography } from '@mui/material'
import { api } from '../api'

export default function PcbaSimulation({ session }) {
  if (api.mode !== 'mock') return null
  const feedback = (target, version) => session.perform(() => api.call('set_pcba_feedback', target, version))
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography variant="caption" sx={{ fontWeight: 700 }}>SIM PCBA</Typography>
        <Button size="small" variant="outlined" disabled={!session.ready || session.busy} onClick={() => feedback(0x80, 0x81)}>Insert PCBA</Button>
        <Button size="small" variant="outlined" disabled={!session.ready || session.busy} onClick={() => feedback(0x82, 0x83)}>Remove PCBA</Button>
      </Stack>
    </Paper>
  )
}
