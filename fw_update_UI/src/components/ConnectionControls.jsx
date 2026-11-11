import { Button, IconButton, MenuItem, Stack, TextField, Tooltip } from '@mui/material'
import RefreshIcon from '@mui/icons-material/Refresh'
import UsbIcon from '@mui/icons-material/Usb'

export default function ConnectionControls({ session, disabled = false }) {
  const { ports, port, setPort, connection, ready, busy, refresh, toggleConnection } = session
  const knownPorts = connection.port && !ports.some((item) => item.port === connection.port)
    ? [...ports, { port: connection.port, description: 'Connected device' }] : ports
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: 'stretch' }}>
      <TextField select label="COM port" value={port} onChange={(event) => setPort(event.target.value)} disabled={disabled || busy || connection.connected || !ready} slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}>
        <MenuItem value="" disabled>{!ready ? 'Waiting for backend…' : ports.length ? 'Select COM port…' : 'No COM ports found'}</MenuItem>
        {knownPorts.map((item) => <MenuItem key={item.port} value={item.port}>{item.port} — {item.description}</MenuItem>)}
      </TextField>
      <Stack direction="row" spacing={1}>
        <Tooltip title="Refresh COM port list"><span><IconButton aria-label="Refresh COM port list" onClick={refresh} disabled={disabled || busy || !ready}><RefreshIcon /></IconButton></span></Tooltip>
        <Button variant={connection.connected ? 'outlined' : 'contained'} startIcon={<UsbIcon />} onClick={toggleConnection} disabled={disabled || busy || !ready || (!connection.connected && !port)} sx={{ minWidth: 132 }}>{connection.connected ? 'Disconnect' : 'Connect'}</Button>
      </Stack>
    </Stack>
  )
}
