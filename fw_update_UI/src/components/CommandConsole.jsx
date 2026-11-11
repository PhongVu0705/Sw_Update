import { useRef, useState } from 'react'
import { Box, Button, Divider, Paper, TextField, Typography } from '@mui/material'
import SendIcon from '@mui/icons-material/Send'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import { api } from '../api'
import ResultDialog from './ResultDialog'

const quickCommands = [
  ['target_m18', 'Target M18'], ['target_m12', 'Target M12'],
  ['metco_password', 'Send Default METCO Password'], ['calibration', 'Get Calibration Data'],
  ['fw_version', 'Read FW Version'], ['fw_pn', 'Read FW P/N'],
  ['mpbid', 'Read MPBID'], ['wipe_counters', 'Wipe Counters And Histograms'],
]

export default function CommandConsole({ session, disabled = false, isBlocked, onExecute, connectionControls, compact = false }) {
  const [command, setCommand] = useState('')
  const [result, setResult] = useState(null)
  const commandInput = useRef(null)
  const unavailable = disabled || !session.ready || session.busy || !session.connection.connected
  const checkConnection = () => {
    if (disabled || isBlocked?.()) throw new Error('Stop the firmware update before sending commands.')
    if (!session.connection.connected) throw new Error('Connect to a COM port first.')
  }
  const send = (event) => {
    event.preventDefault()
    session.perform(async () => {
      checkConnection()
      const value = command.trim()
      if (!value || !/^(?:[0-9a-fA-F]{2}\s*)+$/.test(value)) throw new Error('Enter hexadecimal bytes, for example: 01 00 03 00 0D 04 00 15.')
      onExecute?.()
      const response = await api.call('run_hex_command', value)
      if (!response.cancelled) setCommand('')
      commandInput.current?.focus()
    })
  }
  const quick = (key, label) => session.perform(async () => {
    checkConnection()
    onExecute?.()
    const response = await api.call('run_quick_command', key)
    if (response.cancelled) return
    if (response.status === 'NO_DATA') session.addLog(`${response.title}: ${response.result}`)
    else setResult({ ...response, command: label })
  })

  return (
    <>
      <Paper variant="outlined" component="form" aria-labelledby="command-title" onSubmit={send} sx={{ p: { xs: 2, md: compact ? 2 : 3 } }}>
        {connectionControls && <>{connectionControls}<Divider sx={{ my: 3 }} /></>}
        <Typography variant="h3" component="h2" id="command-title" sx={{ mb: compact ? 1.5 : 2 }}>Command</Typography>
        <Box sx={compact ? { display: 'flex', alignItems: 'flex-start', gap: 1 } : {}}>
          <TextField label="Hex command" placeholder="01 00 03 00 0D 04 00 15" value={command} onChange={(event) => setCommand(event.target.value)} inputRef={commandInput} disabled={disabled || session.busy} autoComplete="off" slotProps={{ htmlInput: { spellCheck: false }, input: { sx: { fontFamily: 'Consolas, monospace' } } }} helperText={compact ? undefined : 'Send raw hexadecimal bytes directly to the connected device.'} sx={{ minWidth: 0 }} />
          <Button type="submit" variant="contained" startIcon={<SendIcon />} disabled={unavailable || !command.trim()} fullWidth={!compact} sx={compact ? { px: 2, flexShrink: 0 } : { mt: 2 }}>Send</Button>
        </Box>
      </Paper>
      <Paper variant="outlined" component="section" aria-labelledby="quick-title" sx={{ p: { xs: 2, md: compact ? 2 : 3 } }}>
        <Typography variant="h3" component="h2" id="quick-title" sx={{ mb: compact ? 1.5 : 2 }}>Quick Commands</Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: compact ? 1 : 1.5 }}>
          {quickCommands.map(([key, label]) => <Button key={key} variant="outlined" color="inherit" endIcon={<ChevronRightIcon />} disabled={unavailable} onClick={() => quick(key, label)} sx={{ justifyContent: 'space-between', textAlign: 'left', px: compact ? 1.5 : 2, py: compact ? 1 : 1.5, borderColor: 'divider', fontSize: 13 }}>{label}</Button>)}
        </Box>
      </Paper>
      <ResultDialog result={result} onClose={() => setResult(null)} />
    </>
  )
}
