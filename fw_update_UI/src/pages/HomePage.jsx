import { useState } from "react";
import {
  Avatar,
  Box,
  Button,
  Card,
  CardActionArea,
  Chip,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import LayersIcon from "@mui/icons-material/Layers";
import TerminalIcon from "@mui/icons-material/Terminal";
import BadgeIcon from "@mui/icons-material/Badge";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import SystemUpdateAltIcon from "@mui/icons-material/SystemUpdateAlt";
import avatar from "../assets/creator.jpg";

const actions = [
  {
    key: "mass",
    title: "Mass Update",
    description:
      "Production-line flow: connect a PCBA, flash firmware and verify each board.",
    icon: <LayersIcon />,
  },
  {
    key: "manual",
    title: "Manual Command Send",
    description:
      "Execute raw commands directly to devices for debugging and testing.",
    icon: <TerminalIcon />,
  },
  {
    key: "about",
    title: "About this software",
    description:
      "Simplifies firmware deployment and updates across target devices.",
    icon: <BadgeIcon />,
  },
];

export default function HomePage({ onNavigate }) {
  const [aboutOpen, setAboutOpen] = useState(false);
  return (
    <Box sx={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <Box
        component="header"
        sx={{
          bgcolor: "primary.main",
          color: "white",
          py: { xs: 4, md: 5 },
          px: 3,
          textAlign: "center",
          backgroundImage: "linear-gradient(120deg, #ffffff0d, #00000014)",
        }}
      >
        <Stack
          direction="row"
          spacing={1.5}
          sx={{ justifyContent: "center", alignItems: "center" }}
        >
          <SystemUpdateAltIcon sx={{ fontSize: 36 }} />
          <Typography variant="h1">FW Update Tool</Typography>
        </Stack>
      </Box>
      <Container
        maxWidth="lg"
        component="main"
        id="main-content"
        sx={{ py: { xs: 3, md: 5 }, flex: 1 }}
      >
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
            gap: 3,
          }}
        >
          {actions.map((action) => (
            <Card
              variant="outlined"
              key={action.key}
              sx={{
                transition: "border-color 150ms, box-shadow 150ms",
                "&:hover": {
                  borderColor: "primary.main",
                  boxShadow: "0 6px 20px #d01b2e12",
                },
              }}
            >
              <CardActionArea
                onClick={() =>
                  action.key === "about"
                    ? setAboutOpen(true)
                    : onNavigate(action.key)
                }
                sx={{
                  height: "100%",
                  p: 3.5,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  gap: 2,
                  minHeight: 225,
                }}
              >
                <Avatar
                  variant="rounded"
                  sx={{ bgcolor: "primary.main", width: 48, height: 48 }}
                >
                  {action.icon}
                </Avatar>
                <Stack
                  direction="row"
                  sx={{
                    alignItems: "center",
                    justifyContent: "space-between",
                    width: "100%",
                  }}
                >
                  <Typography component="h2" variant="h3">
                    {action.title}
                  </Typography>
                  <ArrowForwardIcon
                    sx={{ fontSize: 19, color: "text.secondary" }}
                  />
                </Stack>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ lineHeight: 1.7 }}
                >
                  {action.description}
                </Typography>
              </CardActionArea>
            </Card>
          ))}
        </Box>
      </Container>
      <Box
        component="footer"
        sx={{
          py: 2.5,
          textAlign: "center",
          bgcolor: "background.paper",
          borderTop: 1,
          borderColor: "divider",
        }}
      >
        <Typography variant="caption" color="text.secondary">
          © FW Update Tool · v2.0.0
          <br />
          Made By Grey Le Phong Vu
        </Typography>
      </Box>
      <Dialog
        open={aboutOpen}
        onClose={() => setAboutOpen(false)}
        aria-labelledby="home-dialog-title"
        maxWidth="sm"
      >
        <DialogTitle id="home-dialog-title">About this software</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={3}>
            <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
              <Avatar
                src={avatar}
                alt="Grey Le Phong Vu"
                sx={{
                  width: 64,
                  height: 64,
                  border: "3px solid",
                  borderColor: "primary.main",
                }}
              />
              <Box>
                <Typography variant="overline" color="text.secondary">
                  Creator
                </Typography>
                <Typography variant="h2" color="primary">
                  Grey Le Phong Vu
                </Typography>
              </Box>
            </Stack>
            <Divider />
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Stack
                direction="row"
                sx={{ justifyContent: "space-between", alignItems: "center" }}
              >
                <Typography>FW Update Tool</Typography>
                <Chip label="2.0.0" color="primary" variant="outlined" />
              </Stack>
            </Paper>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAboutOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
