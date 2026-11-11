import { Box, LinearProgress, Stack, Typography } from '@mui/material'
import { stageLabels } from '../state/massUpdate'

export default function FirmwareProgress({ state, hint = 'One PCBA per Start · Space to start', compact = false }) {
  const label = compact && state.finish?.stopped ? 'Stopped' : compact && state.stage === 'idle' ? 'Idle' : stageLabels[state.stage] || 'Working'
  return (
    <Box>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Box><Typography sx={{ fontWeight: 700 }}>{label}</Typography>{(state.total > 0 || hint) && <Typography variant="caption" color="text.secondary">{state.total ? `${state.current} / ${state.total} commands` : hint}</Typography>}</Box>
        <Typography color="primary" sx={{ fontWeight: 750 }}>{Math.round(state.progress)}%</Typography>
      </Stack>
      <LinearProgress variant="determinate" value={state.progress} aria-label="Firmware flashing progress" sx={{ height: 8, borderRadius: 4, bgcolor: '#f4e5e8' }} />
    </Box>
  )
}
