import { useEffect, useState } from "react";
import { Eye, EyeOff, ShieldCheck } from "lucide-react";
import { Drawer } from "../../components/Drawer";
import { Button } from "../../components/ui";
import { Field, TextInput } from "../../components/form";
import { useToast } from "../../components/Toast";
import { getSettings, setSettings } from "../../lib/settings";
import { useHealth } from "../../api/queries";

export function SettingsDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const [apiKey, setApiKey] = useState(getSettings().apiKey);
  const [reveal, setReveal] = useState(false);
  const health = useHealth();

  useEffect(() => {
    if (open) setApiKey(getSettings().apiKey);
  }, [open]);

  function save() {
    setSettings({ apiKey: apiKey.trim() });
    toast.success("Réglages enregistrés.");
    onClose();
  }

  return (
    <Drawer open={open} onClose={onClose} title="Réglages">
      <div className="flex flex-col gap-6">
        <Field
          label="Clé API"
          htmlFor="api-key"
          hint="Envoyée en en-tête X-API-Key. Laisser vide si l'API n'exige pas d'authentification. Stockée localement dans ce navigateur."
        >
          <div className="relative">
            <TextInput
              id="api-key"
              type={reveal ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="vk_…"
              autoComplete="off"
              spellCheck={false}
              className="pr-10 font-mono"
            />
            <button
              type="button"
              aria-label={reveal ? "Masquer la clé" : "Afficher la clé"}
              onClick={() => setReveal((v) => !v)}
              className="absolute top-1/2 right-2 -translate-y-1/2 text-faint transition-colors hover:text-ink"
            >
              {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </Field>

        <div className="rounded-xl border border-border bg-inset p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-ink">
            <ShieldCheck className="size-4 text-brand" />
            État du service
          </div>
          <HealthRow
            label="API"
            ok={health.data?.status === "ok"}
            pending={health.isLoading}
            failed={health.isError}
          />
          {health.data?.checks
            ? Object.entries(health.data.checks).map(([name, value]) => (
                <HealthRow key={name} label={name} ok={value === "ok"} detail={value !== "ok" ? value : undefined} />
              ))
            : null}
        </div>

        <Button variant="primary" onClick={save} className="self-start">
          Enregistrer
        </Button>
      </div>
    </Drawer>
  );
}

function HealthRow({
  label,
  ok,
  pending,
  failed,
  detail,
}: {
  label: string;
  ok?: boolean;
  pending?: boolean;
  failed?: boolean;
  detail?: string;
}) {
  const tone = pending
    ? "bg-faint"
    : failed || !ok
      ? "bg-danger"
      : "bg-success";
  return (
    <div className="flex items-center justify-between py-1 text-sm">
      <span className="font-mono text-xs text-muted capitalize">{label}</span>
      <span className="flex items-center gap-2 text-xs text-muted">
        {detail ? <span className="font-mono text-danger">{detail}</span> : null}
        <span className={`size-2 rounded-full ${tone}`} />
      </span>
    </div>
  );
}
