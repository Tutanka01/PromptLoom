import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate, Link } from "react-router-dom";
import { ArrowLeft, ChevronDown, Info, Sparkles, Wand2 } from "lucide-react";
import { Button, Card, SectionLabel } from "../../components/ui";
import { Field, TextInput, TextArea, Select, Segmented, Toggle, RangeField, type SegOption } from "../../components/form";
import { useToast } from "../../components/Toast";
import { useCapabilities, useCreateVideo, useVoices } from "../../api/queries";
import { ApiError } from "../../api/client";
import type { QualityProfile, RenderEngine } from "../../api/types";
import { allowedLanguages, engineLabel, normalizeCaps, type EffectiveCaps } from "../../lib/capabilities";
import { LanguagePicker } from "./LanguagePicker";
import {
  formSchema,
  makeDefaults,
  toRequest,
  THEME_SUGGESTIONS,
  MODE_OPTIONS,
  STRATEGY_OPTIONS,
  CAPTION_OPTIONS,
  type FormValues,
} from "./schema";
import { formatDuration } from "../../lib/format";

// The form's defaults and available options come from the deployment itself
// (GET /v1/capabilities), so we only mount it once that state is known — an
// error (older API) falls back to the permissive built-in contract.
export function CreatePage() {
  const capsQuery = useCapabilities();
  const caps = useMemo(() => normalizeCaps(capsQuery.data), [capsQuery.data]);
  if (capsQuery.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted animate-fade-up">
        Lecture de la configuration du serveur…
      </div>
    );
  }
  return <CreateForm caps={caps} />;
}

function CreateForm({ caps }: { caps: EffectiveCaps }) {
  const navigate = useNavigate();
  const toast = useToast();
  const create = useCreateVideo();
  const [showAdvanced, setShowAdvanced] = useState(false);

  const {
    control,
    register,
    handleSubmit,
    watch,
    setValue,
    getValues,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: makeDefaults(caps),
    mode: "onBlur",
  });

  const prompt = watch("prompt");
  const mode = watch("production_mode");
  const multilang = watch("multilang");
  const researchEnabled = watch("research_enabled");
  const qualityProfile = watch("quality_profile");
  const language = watch("language");
  const languages = watch("languages");
  const voice = watch("voice");
  const renderEngine = watch("render_engine");
  const captions = watch("captions");
  const duration = watch("target_duration_seconds");

  // ---- Deployment-driven option sets -------------------------------------

  // Languages the effective TTS engine can speak under the selected profile
  // (draft forces Kokoro server-side, which covers far fewer languages).
  const langOptions = allowedLanguages(caps, qualityProfile);
  const allowedCodes = langOptions.map((l) => l.code).join(",");
  const languagesRestricted = langOptions.length < caps.languages.length;

  // A language invalidated by a profile change falls back to an allowed one
  // instead of shipping a request the pipeline cannot narrate.
  useEffect(() => {
    const allowed = allowedCodes.split(",").filter(Boolean);
    if (allowed.length === 0) return;
    if (!allowed.includes(getValues("language"))) {
      setValue("language", allowed.includes("fr") ? "fr" : allowed[0]);
    }
    const kept = getValues("languages").filter((code) => allowed.includes(code));
    if (kept.length !== getValues("languages").length) {
      setValue("languages", kept.length > 0 ? kept : [allowed[0]]);
    }
  }, [allowedCodes, getValues, setValue]);

  // Narration voices: deployment-defined catalog, filtered down to the engine
  // that will actually synthesize under the selected profile and to the
  // requested language(s).
  const voicesQuery = useVoices();
  const selectedLanguages = multilang ? languages : [language];
  const voiceEngine =
    caps.engineByProfile[qualityProfile] ??
    voicesQuery.data?.engine_by_profile?.[qualityProfile] ??
    voicesQuery.data?.engine;
  const engineVoices = (voicesQuery.data?.voices ?? []).filter((v) => v.engine === voiceEngine);
  const compatibleVoices = engineVoices.filter(
    (v) => v.languages === null || selectedLanguages.every((code) => v.languages!.includes(code)),
  );
  const compatibleIds = compatibleVoices.map((v) => v.id).join(",");

  // A selection invalidated by a profile/language change falls back to auto
  // instead of shipping a voice the server would reject with a 422.
  useEffect(() => {
    if (voice !== "auto" && !compatibleIds.split(",").includes(voice)) {
      setValue("voice", "auto");
    }
  }, [voice, compatibleIds, setValue]);

  // Mirror the server's ProductionOptions.resolve_defaults, gated by what the
  // deployment actually provides: advanced modes turn research on only when a
  // provider exists, prefer hybrid visuals + stock only when stock exists, and
  // forbid Manim for cinematic.
  useEffect(() => {
    const advanced = mode === "editorial" || mode === "cinematic";
    setValue("research_enabled", advanced && caps.research.available);
    setValue("visuals_strategy", advanced ? "hybrid" : "diagrams");
    setValue("visuals_allow_stock", advanced && caps.stockAssets.available);
    if (mode === "cinematic" && getValues("render_engine") === "manim") {
      setValue("render_engine", "remotion");
    }
  }, [mode, caps.research.available, caps.stockAssets.available, setValue, getValues]);

  const qualityOptions: SegOption<QualityProfile>[] = [
    {
      value: "draft",
      label: "Brouillon",
      hint: `Itération rapide : demi-résolution, voix ${engineLabel(caps.engineByProfile["draft"] ?? "kokoro")}, contrôles allégés.`,
    },
    { value: "standard", label: "Standard", hint: "Profil de production complet." },
    {
      value: "high",
      label: "Élevé",
      hint: caps.visualReview.available
        ? "Standard + revue visuelle par un modèle vision."
        : "Indisponible : aucun modèle vision configuré côté serveur (VIDEO_API_VISION_MODEL).",
    },
  ];

  const advancedMode = mode === "editorial" || mode === "cinematic";
  const autoEngine: RenderEngine = advancedMode ? "remotion" : caps.defaults.renderEngine;
  const engineOptions: SegOption<"auto" | RenderEngine>[] = [
    {
      value: "auto",
      label: `Auto (${autoEngine === "remotion" ? "Remotion" : "Manim"})`,
      hint: advancedMode
        ? "Les modes éditorial et cinématique rendent avec Remotion."
        : "Défaut du serveur pour le mode technique.",
    },
    ...caps.renderEngines.map((engine) => ({
      value: engine,
      label: engine === "manim" ? "Manim" : "Remotion",
      hint: engine === "manim" ? "Rendu Python/Manim." : "Rendu React/Remotion.",
    })),
  ];

  // ---- Effective outcome (recap) ------------------------------------------

  const effectiveEngine: RenderEngine = renderEngine === "auto" ? autoEngine : renderEngine;
  const researchOn = caps.research.available && researchEnabled;
  const selectedVoice = compatibleVoices.find((v) => v.id === voice);
  const recapParts = [
    multilang ? `${languages.length} vidéo${languages.length > 1 ? "s" : ""}` : "1 vidéo",
    selectedLanguages
      .map((code) => caps.languages.find((l) => l.code === code)?.name ?? code)
      .join(", "),
    `~${formatDuration(duration)}`,
    qualityProfile === "draft" ? "brouillon" : qualityProfile === "high" ? "qualité élevée" : "standard",
    `rendu ${effectiveEngine === "remotion" ? "Remotion" : "Manim"}`,
    `voix ${selectedVoice ? selectedVoice.label : `auto (${engineLabel(voiceEngine)})`}`,
    researchOn ? "recherche activée" : "sans recherche",
    ...(captions !== "off" ? ["sous-titres"] : []),
  ];

  function onSubmit(values: FormValues) {
    create.mutate(toRequest(values, caps), {
      onSuccess: (res) => {
        if (res.batch_id) {
          toast.success(`Batch de ${res.jobs?.length ?? 0} vidéos lancé.`);
          navigate(`/batches/${res.batch_id}`);
        } else {
          toast.success("Vidéo en file de génération.");
          navigate(`/videos/${res.job_id}`);
        }
      },
      onError: (err) => {
        toast.error(err instanceof ApiError ? err.message : "La création a échoué.");
      },
    });
  }

  return (
    <div className="animate-fade-up">
      <Link to="/" className="mb-5 inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-ink">
        <ArrowLeft className="size-4" /> Tableau de bord
      </Link>
      <div className="mb-7 flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-xl bg-brand-50 text-brand">
          <Wand2 className="size-5" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Nouvelle vidéo</h1>
          <p className="text-sm text-muted">
            Décris le sujet — le reste est réglé automatiquement selon la configuration du serveur.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="grid max-w-3xl gap-4">
        <FormSection label="Sujet" title="Que doit expliquer la vidéo ?">
          <Field label="Prompt" htmlFor="prompt" error={errors.prompt?.message}>
            <TextArea
              id="prompt"
              rows={4}
              placeholder="Explique intuitivement ce qu'est un appel système Linux et pourquoi un programme en a besoin pour lire un fichier."
              {...register("prompt")}
            />
            <div className="mt-1 text-right font-mono text-[11px] text-faint">
              {prompt.length} / {caps.limits.promptMaxChars}
            </div>
          </Field>
          <Field label="Thème" htmlFor="theme" hint="Optionnel — classe le job et nomme les artefacts." error={errors.theme?.message}>
            <TextInput id="theme" placeholder="cs, math, physics…" {...register("theme")} />
            <div className="mt-2 flex flex-wrap gap-1.5">
              {THEME_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setValue("theme", s, { shouldValidate: true })}
                  className="rounded-md bg-surface-2 px-2 py-0.5 font-mono text-xs text-muted transition-colors hover:text-ink"
                >
                  {s}
                </button>
              ))}
            </div>
          </Field>
        </FormSection>

        <FormSection
          label="Langue & voix"
          title="Qui parle, et dans quelle(s) langue(s) ?"
        >
          {languagesRestricted && (
            <InfoNote>
              Le profil « {qualityProfile === "draft" ? "Brouillon" : qualityProfile} » utilise le moteur{" "}
              {engineLabel(voiceEngine)} : seules {langOptions.length} langues sont disponibles.
            </InfoNote>
          )}
          <Controller
            control={control}
            name="multilang"
            render={({ field }) => (
              <Toggle
                checked={field.value}
                onChange={field.onChange}
                label="Plusieurs langues (batch)"
                description="Une vidéo par langue, contenu identique, narration et textes traduits."
              />
            )}
          />
          {multilang ? (
            <Field label="Langues" error={errors.languages?.message as string | undefined}>
              <Controller
                control={control}
                name="languages"
                render={({ field }) => (
                  <LanguagePicker
                    options={langOptions}
                    value={field.value}
                    onChange={field.onChange}
                    max={caps.limits.maxBatchLanguages}
                  />
                )}
              />
            </Field>
          ) : (
            <Field label="Langue" htmlFor="language">
              <Controller
                control={control}
                name="language"
                render={({ field }) => (
                  <Select id="language" value={field.value} onChange={(e) => field.onChange(e.target.value)}>
                    {langOptions.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name} ({l.code})
                      </option>
                    ))}
                  </Select>
                )}
              />
            </Field>
          )}
          {engineVoices.length > 0 ? (
            <Field
              label="Voix de narration"
              htmlFor="voice"
              hint={
                compatibleVoices.length === 0
                  ? "Aucune voix du moteur ne couvre ces langues — la voix par défaut du serveur sera utilisée."
                  : `Moteur TTS : ${engineLabel(voiceEngine)}. « Automatique » laisse le serveur choisir.`
              }
            >
              <Controller
                control={control}
                name="voice"
                render={({ field }) => (
                  <Select
                    id="voice"
                    value={field.value}
                    onChange={(e) => field.onChange(e.target.value)}
                    disabled={compatibleVoices.length === 0}
                  >
                    <option value="auto">Automatique (défaut du moteur)</option>
                    {compatibleVoices.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.label}
                        {v.is_default ? " — défaut" : ""}
                      </option>
                    ))}
                  </Select>
                )}
              />
            </Field>
          ) : (
            <InfoNote>
              Le moteur {engineLabel(voiceEngine)} n'expose pas de voix sélectionnable — la narration
              utilise sa voix intégrée.
            </InfoNote>
          )}
        </FormSection>

        <FormSection label="Format" title="Durée & qualité">
          <Field label="Durée cible" hint="Cible pédagogique ; la durée réelle vient de l'audio généré.">
            <Controller
              control={control}
              name="target_duration_seconds"
              render={({ field }) => (
                <RangeField
                  value={field.value}
                  onChange={field.onChange}
                  min={caps.limits.duration.min}
                  max={caps.limits.duration.max}
                  step={5}
                  readout={formatDuration(field.value)}
                />
              )}
            />
          </Field>
          <Field
            label="Profil de qualité"
            hint={
              caps.visualReview.available
                ? undefined
                : "« Élevé » est désactivé : aucun modèle vision n'est configuré côté serveur."
            }
          >
            <Controller
              control={control}
              name="quality_profile"
              render={({ field }) => (
                <Segmented
                  options={qualityOptions}
                  value={field.value}
                  onChange={field.onChange}
                  disabledValues={caps.visualReview.available ? [] : ["high"]}
                />
              )}
            />
          </Field>
        </FormSection>

        <Card className="overflow-hidden">
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="flex w-full items-center justify-between px-5 py-4 text-left"
          >
            <span className="flex flex-col">
              <SectionLabel>Avancé</SectionLabel>
              <span className="mt-1 text-sm font-medium text-ink">
                Mode, rendu, recherche, visuels, sous-titres — réglés automatiquement
              </span>
              {!showAdvanced && (
                <span className="mt-0.5 text-xs text-muted">
                  {MODE_OPTIONS.find((o) => o.value === mode)?.label} · rendu{" "}
                  {effectiveEngine === "remotion" ? "Remotion" : "Manim"} ·{" "}
                  {researchOn ? "recherche activée" : "sans recherche"} ·{" "}
                  {captions === "off" ? "sans sous-titres" : "sous-titres incrustés"}
                </span>
              )}
            </span>
            <ChevronDown className={`size-4 shrink-0 text-faint transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
          </button>
          {showAdvanced && (
            <div className="flex flex-col gap-6 border-t border-border px-5 py-5">
              <Field label="Mode de production" hint="Détermine le ton, la stratégie visuelle et le moteur par défaut.">
                <Controller
                  control={control}
                  name="production_mode"
                  render={({ field }) => (
                    <Segmented options={MODE_OPTIONS} value={field.value} onChange={field.onChange} />
                  )}
                />
              </Field>
              <Field
                label="Moteur de rendu"
                hint={mode === "cinematic" ? "Le mode cinématique impose Remotion." : undefined}
                error={errors.render_engine?.message}
              >
                <Controller
                  control={control}
                  name="render_engine"
                  render={({ field }) => (
                    <Segmented
                      options={engineOptions}
                      value={field.value}
                      onChange={field.onChange}
                      disabledValues={mode === "cinematic" ? ["manim"] : []}
                    />
                  )}
                />
              </Field>

              <div className="h-px bg-border" />

              {caps.research.available ? (
                <>
                  <Controller
                    control={control}
                    name="research_enabled"
                    render={({ field }) => (
                      <Toggle
                        checked={field.value}
                        onChange={field.onChange}
                        label="Recherche documentaire"
                        description={`Source les faits avant d'écrire le blueprint (fournisseur : ${caps.research.provider ?? "configuré"}).`}
                      />
                    )}
                  />
                  {researchEnabled && (
                    <Field label="Sources maximum">
                      <Controller
                        control={control}
                        name="research_max_sources"
                        render={({ field }) => (
                          <RangeField
                            value={field.value}
                            onChange={field.onChange}
                            min={caps.limits.researchMaxSources.min}
                            max={caps.limits.researchMaxSources.max}
                            readout={`${field.value}`}
                          />
                        )}
                      />
                    </Field>
                  )}
                </>
              ) : (
                <InfoNote>
                  Recherche documentaire indisponible : aucun fournisseur n'est configuré côté serveur
                  (VIDEO_API_RESEARCH_PROVIDER). Les vidéos s'appuient sur les connaissances du modèle.
                </InfoNote>
              )}

              <div className="h-px bg-border" />

              <Field label="Stratégie visuelle">
                <Controller
                  control={control}
                  name="visuals_strategy"
                  render={({ field }) => (
                    <Segmented options={STRATEGY_OPTIONS} value={field.value} onChange={field.onChange} />
                  )}
                />
              </Field>
              {caps.stockAssets.available ? (
                <Controller
                  control={control}
                  name="visuals_allow_stock"
                  render={({ field }) => (
                    <Toggle
                      checked={field.value}
                      onChange={field.onChange}
                      label="Autoriser les médias stock"
                      description={`Images/vidéos sous licence (fournisseur : ${caps.stockAssets.provider ?? "configuré"}) ; sinon, diagrammes.`}
                    />
                  )}
                />
              ) : (
                <InfoNote>
                  Médias stock indisponibles : aucun fournisseur n'est configuré côté serveur
                  (VIDEO_API_ASSET_PROVIDER). Les visuels seront des diagrammes générés.
                </InfoNote>
              )}
              <Field label="Assets maximum" hint="Nombre maximal de médias externes par vidéo.">
                <Controller
                  control={control}
                  name="visuals_max_assets"
                  render={({ field }) => (
                    <RangeField
                      value={field.value}
                      onChange={field.onChange}
                      min={caps.limits.visualsMaxAssets.min}
                      max={caps.limits.visualsMaxAssets.max}
                      readout={`${field.value}`}
                    />
                  )}
                />
              </Field>

              <div className="h-px bg-border" />

              <Field label="Sous-titres">
                <Controller
                  control={control}
                  name="captions"
                  render={({ field }) => (
                    <Segmented
                      options={CAPTION_OPTIONS}
                      value={field.value === "keywords" ? "full" : field.value}
                      onChange={field.onChange}
                    />
                  )}
                />
              </Field>

              <div className="h-px bg-border" />

              <Field
                label="Webhook de fin de job"
                htmlFor="callback"
                hint="POST JSON à la fin du job (completed / failed / cancelled)."
                error={errors.callback_url?.message}
              >
                <TextInput id="callback" type="url" placeholder="https://exemple.com/webhook" {...register("callback_url")} />
              </Field>
            </div>
          )}
        </Card>

        <div className="sticky bottom-0 -mx-5 mt-2 flex items-center justify-between gap-3 border-t border-border bg-bg/90 px-5 py-4 backdrop-blur-md">
          <p className="min-w-0 flex-1 truncate text-xs text-muted" title={recapParts.join(" · ")}>
            {recapParts.join(" · ")}
          </p>
          <div className="flex shrink-0 items-center gap-2">
            <Button type="button" variant="ghost" onClick={() => navigate("/")}>
              Annuler
            </Button>
            <Button type="submit" variant="primary" loading={create.isPending} icon={<Sparkles className="size-4" />}>
              Lancer la génération
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}

function FormSection({ label, title, children }: { label: string; title: string; children: ReactNode }) {
  return (
    <Card className="px-5 py-5">
      <div className="mb-4">
        <SectionLabel>{label}</SectionLabel>
        <h2 className="mt-1 font-display text-lg font-medium tracking-tight">{title}</h2>
      </div>
      <div className="flex flex-col gap-5">{children}</div>
    </Card>
  );
}

function InfoNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-lg bg-surface-2 px-3 py-2.5 text-xs leading-relaxed text-muted">
      <Info className="mt-0.5 size-3.5 shrink-0" />
      <span>{children}</span>
    </p>
  );
}
