import { useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Plus, Settings, Clapperboard } from "lucide-react";
import { Button, IconButton } from "./ui";
import { SettingsDrawer } from "../features/settings/SettingsDrawer";
import { useHealth } from "../api/queries";
import { cn } from "../lib/cn";

export function AppShell() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const health = useHealth();
  const onCreate = location.pathname === "/create";

  const healthTone = health.isLoading
    ? "bg-faint"
    : health.data?.status === "ok"
      ? "bg-success"
      : "bg-danger";
  const healthText = health.isLoading
    ? "vérification"
    : health.data?.status === "ok"
      ? "opérationnel"
      : health.isError
        ? "injoignable"
        : "dégradé";

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-border bg-bg/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-5">
          <Link to="/" className="flex items-center gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-xl bg-brand text-white">
              <Clapperboard className="size-5" />
            </span>
            <span className="flex flex-col leading-none">
              <span className="font-display text-[15px] font-semibold tracking-tight text-ink">
                PromptLoom <span className="text-brand">Studio</span>
              </span>
              <span className="mt-0.5 font-mono text-[10px] tracking-[0.12em] text-faint uppercase">
                générateur vidéo
              </span>
            </span>
          </Link>

          <button
            onClick={() => setSettingsOpen(true)}
            className="ml-2 hidden items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-muted transition-colors hover:border-border-strong sm:inline-flex"
            title="État du service"
          >
            <span className={cn("size-1.5 rounded-full", healthTone)} />
            {healthText}
          </button>

          <div className="flex-1" />

          <IconButton label="Réglages" onClick={() => setSettingsOpen(true)}>
            <Settings className="size-[18px]" />
          </IconButton>
          {!onCreate && (
            <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => navigate("/create")}>
              <span className="hidden sm:inline">Nouvelle vidéo</span>
              <span className="sm:hidden">Créer</span>
            </Button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-8">
        <Outlet />
      </main>

      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
