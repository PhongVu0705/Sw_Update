import { useEffect, useRef } from 'react'
import { Box, Button, Paper, Stack, Typography } from '@mui/material'
import TerminalIcon from '@mui/icons-material/Terminal'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'

function logColor(message) {
  if (/ERROR|FAIL\b|aborted|mismatch/i.test(message)) return '#ff9b9b'
  if (/WARN|TIMEOUT|no response/i.test(message)) return '#f6d280'
  if (/SUCCESS|PASS\b|verified/i.test(message)) return '#8fe0b2'
  return '#c7d2e4'
}

export default function Terminal({ logs, onClear, minHeight = { xs: 320, md: 520 }, fillContainer = false }) {
  const viewport = useRef(null)
  useEffect(() => {
    if (viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight
  }, [logs])
  return (
    <Paper component="section" aria-labelledby="terminal-title" sx={{ bgcolor: '#121925', color: '#e6edf7', display: 'flex', flexDirection: 'column', height: '100%', minHeight, overflow: 'hidden' }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, px: 2.5, py: 1.5, bgcolor: '#1b2534', borderBottom: '1px solid #2c384a' }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}><TerminalIcon fontSize="small" /><Typography variant="h3" component="h2" id="terminal-title">Terminal</Typography></Stack>
        <Button size="small" startIcon={<DeleteOutlineIcon />} onClick={onClear} sx={{ color: '#bac6d8' }}>Clear</Button>
      </Stack>
      <Box ref={viewport} role="log" aria-live="polite" aria-label="Session logs" tabIndex={0} sx={{ p: 2.5, minHeight: 0, overflowY: 'scroll', overflowX: 'hidden', scrollbarGutter: 'stable', height: fillContainer ? 0 : { xs: 320, md: 'calc(100vh - 260px)' }, flex: 1, fontFamily: 'Consolas, monospace', fontSize: 13, lineHeight: 1.8, overflowWrap: 'anywhere' }}>
        {!logs.length && <Box sx={{ color: '#8b9bb0' }}>Waiting for session activity…</Box>}
        {logs.map((line) => <Box key={line.id} sx={{ color: logColor(line.message), whiteSpace: 'pre-wrap' }}><Box component="span" sx={{ color: '#8191a8' }}>[{line.time}] </Box>{line.message}</Box>)}
      </Box>
    </Paper>
  )
}
