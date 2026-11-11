import { Box, Button, Divider, Paper, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import StopIcon from '@mui/icons-material/Stop'
import FirmwarePicker from './FirmwarePicker'

export function FirmwareActions({ update, busy, focus = false, startLabel = 'Start' }) {
  return (
    <Stack direction="row" spacing={2}>
      <Button fullWidth variant="contained" startIcon={<PlayArrowIcon />} onClick={update.start} disabled={update.disabled || Boolean(update.invalid)} sx={{ py: focus ? 1.2 : 1.3, fontSize: focus ? 18 : 15 }}>{startLabel}</Button>
      <Button fullWidth variant="outlined" color="inherit" startIcon={<StopIcon />} onClick={update.stop} disabled={!update.state.running || busy} sx={{ py: focus ? 1.2 : 1.3, fontSize: focus ? 18 : 15 }}>Stop</Button>
    </Stack>
  )
}

export default function FirmwareControls({ session, update, connectionControls, startLabel, children, compact = false }) {
  return (
    <Paper variant="outlined" component="section" aria-labelledby="firmware-title" sx={{ p: { xs: 2, md: compact ? 2 : 3 } }}>
      {connectionControls && <>{connectionControls}<Divider sx={{ my: 2.5 }} /></>}
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: compact ? 1.5 : 2.5 }}>
        <Typography variant="body2" sx={{ fontWeight: 650 }}>Tool Type:</Typography>
        <ToggleButtonGroup exclusive size="small" value={update.toolType} onChange={(_, value) => { if (value) update.setToolType(value) }} disabled={update.disabled} aria-label="Tool type" color="primary">
          <ToggleButton value="M12" sx={{ px: 3 }}>M12</ToggleButton><ToggleButton value="M18" sx={{ px: 3 }}>M18</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <Typography component="h2" variant="h3" id="firmware-title" sx={{ mb: 1.5 }}>{compact ? 'Firmware' : 'Select Firmware File'}</Typography>
      <FirmwarePicker session={session} file={update.file} onChange={update.setFile} disabled={update.disabled} compact={compact} />
      <TextField required label="Expected firmware version" placeholder="e.g. 1.4.2" value={update.expectedFw} onChange={(event) => update.setExpectedFw(event.target.value)} disabled={update.disabled} helperText={compact ? undefined : 'Decimal version to verify after flashing (required).'} sx={{ mt: compact ? 1.5 : 2.5 }} />
      <Box sx={{ mt: compact ? 1.5 : 2.5 }}><FirmwareActions update={update} busy={session.busy} startLabel={startLabel} /></Box>
      {children}
    </Paper>
  )
}
