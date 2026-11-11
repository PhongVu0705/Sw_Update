import { Box, Paper, Stack, Typography } from '@mui/material'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlined'
import HighlightOffIcon from '@mui/icons-material/HighlightOff'
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty'
import { pcbaStatus } from '../state/massUpdate'
import PcbaUpdateAnimation from './PcbaUpdateAnimation'
import PcbaStateAnimation from './PcbaStateAnimation'
import DinosaurRunner from './DinosaurRunner'

function StatCard({ label, value, detail, color, icon, focus }) {
  return (
    <Paper component="article" aria-label={label} variant="outlined" sx={{ p: focus ? 1.5 : 2.5, display: 'flex', alignItems: 'center', minWidth: 0 }}>
      <Stack direction="row" spacing={focus ? { xs: 1, md: 2 } : 2} sx={{ alignItems: 'center' }}>
        <Box sx={{ display: 'flex', p: focus ? 1 : 1.5, borderRadius: 2, bgcolor: `${color}12`, color, '& .MuiSvgIcon-root': { fontSize: focus ? { xs: 24, md: 32 } : 28 } }}>{icon}</Box>
        <Box sx={{ minWidth: 0 }}><Typography variant="overline" color="text.secondary" sx={{ fontWeight: 700, fontSize: 11, ...(focus && { display: 'block', lineHeight: 1.2 }) }}>{label}</Typography><Typography sx={{ fontWeight: 750, color, lineHeight: 1.3, fontSize: focus ? { xs: 22, md: 28 } : 25 }}>{value}</Typography>{detail && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, fontSize: 12 }}>{detail}</Typography>}</Box>
      </Stack>
    </Paper>
  )
}

function PcbaStatusCard({ state, focus }) {
  const status = pcbaStatus(state)
  const color = { success: '#15803d', error: '#c62828', warning: '#a15c00', info: '#1565c0', neutral: '#6b7280' }[status.tone]
  const updating = status.tone === 'info'
  const verified = status.tone === 'success' && state.result?.pass
  const animationKind = status.tone === 'success' ? 'success' : status.tone === 'error' ? 'error' : state.finish?.stopped ? null : 'waiting'
  const indicatorSize = updating ? (focus ? 104 : 64) : (focus ? 80 : 56)

  return (
    <Paper component="article" aria-label="PCBA STATUS" aria-busy={updating} variant="outlined" sx={{
      gridColumn: '1 / -1', minWidth: 0, minHeight: focus ? 0 : 144,
      p: focus ? { xs: 1.5, md: 2 } : 2.5,
      overflow: 'hidden', containerType: focus ? 'size' : 'inline-size',
      display: 'flex', alignItems: 'center', borderColor: color,
      borderWidth: 2, bgcolor: `${color}08`,
    }}>
      <Box sx={{ display: 'grid', gridTemplateColumns: updating ? 'minmax(0, 1fr) minmax(0, 1fr)' : 'minmax(0, 1fr)', alignItems: 'center', gap: updating ? { xs: 1.5, sm: 2 } : 0, width: '100%', minWidth: 0, maxHeight: focus ? '100%' : 'none', overflow: 'hidden' }}>
        <Stack direction="row" spacing={focus ? 3 : 2} sx={{ alignItems: focus ? 'flex-start' : 'center', minWidth: 0, ...(updating && {
          '@container (max-width: 560px)': {
            flexDirection: 'column', alignItems: 'flex-start', gap: 1,
            '& > :not(style) ~ :not(style)': { margin: 0 },
            '& > [role="progressbar"]': { width: focus ? 64 : 40, height: focus ? 64 : 40 },
            '& p': { fontSize: focus ? 'clamp(16px, 5cqh, 24px)' : 16 },
          },
        }) }}>
          {updating ? <PcbaUpdateAnimation size={indicatorSize} /> : animationKind ? <PcbaStateAnimation key={animationKind} kind={animationKind} size={indicatorSize} color={color} /> : <Box sx={{ width: indicatorSize, height: indicatorSize, flexShrink: 0, display: 'grid', placeItems: 'center' }}>
            <Box sx={{ display: 'grid', placeItems: 'center', width: indicatorSize - 12, height: indicatorSize - 12, borderRadius: '50%', bgcolor: `${color}12`, color, '& .MuiSvgIcon-root': { fontSize: focus ? 44 : 30 } }}><HourglassEmptyIcon /></Box>
          </Box>}
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography sx={{ color, fontWeight: 750, lineHeight: 1.25, fontSize: focus ? 'clamp(20px, 7cqh, 48px)' : { xs: 20, md: 24 } }}>{status.value}</Typography>
            {verified && <Stack aria-label="Verified firmware versions" direction="row" spacing={1.5} sx={{ mt: focus ? 2 : 1.5 }}>
              <Box sx={{ flex: 1, minWidth: 0, maxWidth: 240, px: 1.25, py: 1, borderRadius: 1.5, bgcolor: '#dcfce7', border: '1px solid #86efac' }}>
                <Typography variant="overline" sx={{ display: 'block', color: '#166534', fontWeight: 700, fontSize: 11, lineHeight: 1.4 }}>Actual FW</Typography>
                <Typography aria-label="Actual firmware" sx={{ color: '#14532d', fontFamily: 'Consolas, monospace', fontWeight: 700, fontSize: focus ? 22 : 18, overflowWrap: 'anywhere' }}>{state.result.detected ?? 'N/A'}</Typography>
              </Box>
              <Box sx={{ flex: 1, minWidth: 0, maxWidth: 240, px: 1.25, py: 1, borderRadius: 1.5, bgcolor: '#eff6ff', border: '1px solid #bfdbfe' }}>
                <Typography variant="overline" sx={{ display: 'block', color: '#1e40af', fontWeight: 700, fontSize: 11, lineHeight: 1.4 }}>FW setting</Typography>
                <Typography aria-label="Configured firmware" sx={{ color: '#1e3a8a', fontFamily: 'Consolas, monospace', fontWeight: 700, fontSize: focus ? 22 : 18, overflowWrap: 'anywhere' }}>{state.result.expected ?? 'N/A'}</Typography>
              </Box>
            </Stack>}
          </Box>
        </Stack>
        {updating && <DinosaurRunner focus={focus} />}
      </Box>
    </Paper>
  )
}

export default function MassStats({ state, focus }) {
  const { passed, failed } = state
  const total = passed + failed
  const percent = (count) => total ? `${Math.round(count / total * 1000) / 10}%` : '0%'
  return (
    <Box component="section" aria-label="Mass update results" aria-live="polite" sx={{ display: 'grid', gridTemplateColumns: focus ? 'repeat(2, minmax(0, 1fr))' : { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' }, gridTemplateRows: focus ? 'auto minmax(0, 1fr)' : 'auto', minHeight: 0, gap: 2, flex: focus ? '1 1 0%' : 'none' }}>
      <StatCard label="PASS RATE" value={percent(passed)} detail={`Passed ${passed}`} color="#15803d" icon={<CheckCircleOutlineIcon />} focus={focus} />
      <StatCard label="FAIL RATE" value={percent(failed)} detail={`Failed ${failed}`} color="#c62828" icon={<HighlightOffIcon />} focus={focus} />
      <PcbaStatusCard state={state} focus={focus} />
    </Box>
  )
}
