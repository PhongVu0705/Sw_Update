import { useId, useState } from 'react'
import { Box, Button, Menu, MenuItem, Paper, Stack, Typography } from '@mui/material'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import { api } from '../api'
import { browserFileInfo } from '../api/mock'

export default function FirmwarePicker({ file, session, onChange, disabled, compact = false }) {
  const [dragging, setDragging] = useState(false)
  const [demoAnchor, setDemoAnchor] = useState(null)
  const demoMenuId = useId()
  const accept = (selected) => {
    if (!['bin', 'csv'].includes(selected.ext)) throw new Error('Unsupported file type — choose a .bin or .csv file.')
    if (!selected.size) throw new Error('The firmware file is empty.')
    onChange(selected)
    session.addLog(`Selected firmware: ${selected.name}${selected.simulated ? ' (simulated file)' : ''}`)
  }
  const browse = () => session.perform(async () => {
    const result = await api.call('select_file')
    if (result.status === 'CANCELLED') return
    accept(result)
  })
  const selectDemo = (ext) => {
    setDemoAnchor(null)
    if (disabled) return
    return session.perform(async () => accept(await api.call('select_demo_file', ext)))
  }
  return (
    <Paper component="section" aria-label="Firmware file selection" variant="outlined" onDragOver={(event) => { event.preventDefault(); if (!disabled) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => {
      event.preventDefault()
      setDragging(false)
      if (disabled) return
      session.perform(async () => {
        if (api.mode === 'bridge') throw new Error('Use Browse to select firmware in the desktop app.')
        const dropped = event.dataTransfer.files[0]
        if (dropped) accept(browserFileInfo(dropped))
      })
    }} sx={{ p: compact ? 1.5 : 2, borderStyle: 'dashed', bgcolor: dragging ? '#fcecef' : '#fafbfc', borderColor: dragging ? 'primary.main' : 'divider' }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { xs: 'flex-start', sm: 'center' } }}>
        <UploadFileIcon sx={{ color: 'primary.main', fontSize: 32 }} />
        <Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="body2" sx={{ fontWeight: 650, overflowWrap: 'anywhere' }}>{file?.name || 'No file selected'}</Typography><Typography variant="caption" color="text.secondary">{file ? `${file.simulated ? 'SIMULATED · ' : ''}${file.ext.toUpperCase()} · ${file.size < 1024 ? `${file.size} bytes` : `${(file.size / 1024).toFixed(1)} KB`}` : compact ? '.bin / .csv' : api.mode === 'bridge' ? 'Browse for a .bin or .csv file' : 'Browse, drop a file, or use a demo file'}</Typography></Box>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
          {api.mode === 'mock' && <Button variant="outlined" aria-haspopup="menu" aria-controls={demoAnchor ? demoMenuId : undefined} aria-expanded={Boolean(demoAnchor)} onClick={(event) => setDemoAnchor(event.currentTarget)} disabled={disabled}>Demo file</Button>}
          <Button variant="outlined" startIcon={<FolderOpenIcon />} onClick={browse} disabled={disabled}>Browse</Button>
        </Stack>
      </Stack>
      {api.mode === 'mock' && <Menu id={demoMenuId} anchorEl={demoAnchor} open={Boolean(demoAnchor) && !disabled} onClose={() => setDemoAnchor(null)} slotProps={{ list: { 'aria-label': 'Choose simulated firmware' } }}>
        <MenuItem onClick={() => selectDemo('bin')}>Demo .bin</MenuItem>
        <MenuItem onClick={() => selectDemo('csv')}>Demo .csv</MenuItem>
      </Menu>}
    </Paper>
  )
}
