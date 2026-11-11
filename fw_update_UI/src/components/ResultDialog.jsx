import { useState } from 'react'
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'

async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return }
  } catch { /* Native webviews may require the legacy clipboard API. */ }
  const field = document.createElement('textarea')
  field.value = text
  field.style.position = 'fixed'
  field.style.opacity = '0'
  document.body.appendChild(field)
  field.select()
  try { if (!document.execCommand('copy')) throw new Error('Unable to copy result. Select and copy the text manually.') }
  finally { field.remove() }
}

export default function ResultDialog({ result, onClose }) {
  const [copyState, setCopyState] = useState('')
  const close = () => { setCopyState(''); onClose() }
  return (
    <Dialog open={Boolean(result)} onClose={close} aria-labelledby="command-result-title">
      <DialogTitle id="command-result-title">{result?.title || 'Command Result'}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">Command: <Box component="code">{result?.command}</Box></Typography>
          {result?.status && result.status !== 'SUCCESS' && <Alert severity="error">{result.status}</Alert>}
          <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: 'Consolas, monospace' }}>{result?.result}</Typography>
          {copyState && <Alert severity={copyState === 'Copied!' ? 'success' : 'error'}>{copyState}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button startIcon={<ContentCopyIcon />} onClick={async () => {
          try { await copyText(String(result?.result || '').replace(/^Data:\s*/, '')); setCopyState('Copied!') }
          catch (err) { setCopyState(err.message) }
        }}>Copy</Button>
        <Button onClick={close} variant="contained">Close</Button>
      </DialogActions>
    </Dialog>
  )
}
