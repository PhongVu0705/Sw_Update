import { Box, Stack } from '@mui/material'
import useDeviceSession from '../hooks/useDeviceSession'
import ScreenLayout from '../components/ScreenLayout'
import ConnectionControls from '../components/ConnectionControls'
import Terminal from '../components/Terminal'
import CommandConsole from '../components/CommandConsole'

export default function ManualPage({ onBack }) {
  const session = useDeviceSession()
  return (
    <ScreenLayout title="Manual Command Send" connection={session.connection} onBack={() => session.leave(onBack)} backDisabled={session.busy} error={session.error}>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 3, flex: 1, minWidth: 0 }}>
        <Stack spacing={3} sx={{ minWidth: 0 }}>
          <CommandConsole session={session} connectionControls={<ConnectionControls session={session} />} />
        </Stack>
        <Terminal logs={session.logs} onClear={session.clearLogs} />
      </Box>
    </ScreenLayout>
  )
}
