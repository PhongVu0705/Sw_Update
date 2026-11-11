import { useEffect, useState } from "react";
import { Box, IconButton, Paper, Stack, Tooltip } from "@mui/material";
import LockOpenIcon from "@mui/icons-material/LockOpen";
import LockIcon from "@mui/icons-material/Lock";
import useDeviceSession from "../hooks/useDeviceSession";
import useFirmwareUpdate from "../hooks/useFirmwareUpdate";
import ScreenLayout from "../components/ScreenLayout";
import ConnectionControls from "../components/ConnectionControls";
import Terminal from "../components/Terminal";
import MassStats from "../components/MassStats";
import FocusLockDialog from "../components/FocusLockDialog";
import FirmwareControls, {
  FirmwareActions,
} from "../components/FirmwareControls";
import FirmwareProgress from "../components/FirmwareProgress";
import PcbaSimulation from "../components/PcbaSimulation";

export default function MassUpdatePage({ onBack }) {
  const session = useDeviceSession();
  const update = useFirmwareUpdate(session, { autoPcba: true });
  const [locked, setLocked] = useState(false);
  const [lockDialog, setLockDialog] = useState(false);
  const [lockPassword, setLockPassword] = useState("");
  const { state, start } = update;

  useEffect(() => {
    const onKeyDown = (event) => {
      if (
        event.key !== " " ||
        event.repeat ||
        event.ctrlKey ||
        event.altKey ||
        event.metaKey ||
        lockDialog
      )
        return;
      if (
        event.target instanceof Element &&
        event.target.closest(
          'button, a, input, select, textarea, [role="button"], [role="dialog"], [role="combobox"], [contenteditable="true"]',
        )
      )
        return;
      event.preventDefault();
      start();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  });

  const footer = (
    <Paper
      square
      component="footer"
      sx={{
        px: { xs: 2, md: 4 },
        py: locked ? 1.5 : 2.5,
        borderTop: 1,
        borderColor: "divider",
      }}
    >
      <FirmwareProgress
        state={state}
        hint="Auto PCBA · Start once, Stop to end"
      />
    </Paper>
  );

  return (
    <ScreenLayout
      title="Mass Update"
      connection={session.connection}
      onBack={() => session.leave(onBack)}
      backDisabled={locked || state.running || session.busy}
      error={session.error}
      footer={footer}
      fitViewport
      compact={locked}
      titleAction={
        <Tooltip
          title={locked ? "Unlock Focus Mode" : "Lock controls in Focus Mode"}
        >
          <IconButton
            color="inherit"
            aria-label={locked ? "Unlock Focus Mode" : "Lock Focus Mode"}
            aria-pressed={locked}
            onClick={() => setLockDialog(true)}
          >
            {locked ? <LockIcon /> : <LockOpenIcon />}
          </IconButton>
        </Tooltip>
      }
    >
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "minmax(0, 1fr)", md: locked ? "minmax(0, 1fr)" : "repeat(2, minmax(0, 1fr))" },
          gridTemplateRows: locked ? "minmax(0, 1fr)" : { xs: "minmax(0, 3fr) minmax(120px, 2fr)", md: "minmax(0, 1fr)" },
          gap: 2,
          flex: 1,
          minWidth: 0,
          minHeight: 0,
          alignItems: "stretch",
        }}
      >
        <Stack aria-label={locked ? "Focus workspace" : "Mass update controls"} spacing={2} sx={{ minWidth: 0, minHeight: 0, height: "100%", overflowY: locked ? "hidden" : "auto", ...(!locked && { '& > *': { flexShrink: 0 } }) }}>
          {!locked && (
            <FirmwareControls
              session={session}
              update={update}
              connectionControls={
                <ConnectionControls
                  session={update.connectionSession}
                  disabled={state.running}
                />
              }
            />
          )}
          {!locked && <PcbaSimulation session={session} />}
          <MassStats state={state} focus={locked} />
          {locked && (
            <Box sx={{ flexShrink: 0 }}><FirmwareActions update={update} busy={session.busy} focus /></Box>
          )}
        </Stack>
        {!locked && (
          <Box
            aria-label="Mass update terminal"
            sx={{
              minWidth: 0,
              minHeight: 0,
              height: "100%",
            }}
          >
            <Terminal
              logs={session.logs}
              onClear={session.clearLogs}
              minHeight={0}
              fillContainer
            />
          </Box>
        )}
      </Box>
      {lockDialog && (
        <FocusLockDialog
          locked={locked}
          password={lockPassword}
          onClose={() => setLockDialog(false)}
          onAccept={(value) => {
            setLockPassword(locked ? "" : value);
            setLocked(!locked);
            setLockDialog(false);
            session.addLog(
              locked
                ? "Page unlocked."
                : "Focus Mode active — setup controls and terminal hidden.",
            );
          }}
        />
      )}
    </ScreenLayout>
  );
}
