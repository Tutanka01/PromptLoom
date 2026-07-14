import { useEffect, useState, type ReactNode } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate, Link } from "react-router-dom";
import { ArrowLeft, ChevronDown, Sparkles, Wand2 } from "lucide-react";
import { Button, Card, SectionLabel } from "../../components/ui";
import { Field, TextInput, TextArea, Select, Segmented, Toggle, RangeField } from "../../components/form";
import { useToast } from "../../components/Toast";
import { useCreateVideo, useVoices } from "../../api/queries";
import { ApiError } from "../../api/client";
import { LanguagePicker } from "./LanguagePicker";
import {
  formSchema,
  defaultValues,
  toRequest,
  LANGUAGES,
  THEME_SUGGESTIONS,
  QUALITY_OPTIONS,
  MODE_OPTIONS,
  ENGINE_OPTIONS,
  STRATEGY_OPTIONS,
  CAPTION_OPTIONS,
  type FormValues,
} from "./schema";
import { formatDuration } from "../../lib/format";

export function CreatePage() {
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
    defaultValues,
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

  // Narration voices: deployment-defined catalog, filtered down to the engine
  // that will actually synthesize under the selected profile (draft forces
  // Kokoro server-side) and to the requested language(s).
  const voicesQuery = useVoices();
  const selectedLanguages = multilang ? languages : [language];
  const voiceEngine =
    voicesQuery.data?.engine_by_profile?.[qualityProfile] ?? voicesQuery.data?.engine;
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

  // Mirror the server's ProductionOptions.resolve_defaults: advanced modes turn
  // research on, prefer hybrid visuals + stock, and forbid Manim for cinematic.
  useEffect(() => {
    const advanced = mode === "editorial" || mode === "cinematic";
    setValue("research_enabled", advanced);
    setValue("visuals_strategy", advanced ? "hybrid" : "diagrams");
    setValue("visuals_allow_stock", advanced);
    if (mode === "cinematic" && getValues("render_engine") === "manim") {
      setValue("render_engine", "remotion");
    }
  }, [mode, setValue, getValues]);

  function onSubmit(values: FormValues) {
    create.mutate(toRequest(values), {
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
          <p className="text-sm text-muted">Décris le sujet, l'API compose la narration et les scènes.</p>
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
            <div className="mt-1 text-right font-mono text-[11px] text-faint">{prompt.length} / 4000</div>
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

        <FormSection label="Langue" title="Langue de sortie">
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
                render={({ field }) => <LanguagePicker value={field.value} onChange={field.onChange} />}
              />
            </Field>
          ) : (
            <Field label="Langue" htmlFor="language">
              <Controller
                control={control}
                name="language"
                render={({ field }) => (
                  <Select id="language" value={field.value} onChange={(e) => field.onChange(e.target.value)}>
                    {LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name} ({l.code})
                      </option>
                    ))}
                  </Select>
                )}
              />
            </Field>
          )}
          {engineVoices.length > 0 && (
            <Field
              label="Voix de narration"
              htmlFor="voice"
              hint={
                compatibleVoices.length === 0
                  ? "Aucune voix du moteur ne couvre ces langues — la voix par défaut du serveur sera utilisée."
                  : `Moteur TTS : ${voiceEngine}. « Automatique » laisse le serveur choisir.`
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
                  min={20}
                  max={900}
                  step={5}
                  readout={formatDuration(field.value)}
                />
              )}
            />
          </Field>
          <Field label="Profil de qualité">
            <Controller
              control={control}
              name="quality_profile"
              render={({ field }) => (
                <Segmented options={QUALITY_OPTIONS} value={field.value} onChange={field.onChange} />
              )}
            />
          </Field>
        </FormSection>

        <FormSection label="Production" title="Mode & moteur de rendu">
          <Field label="Mode de production">
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
            hint={mode === "cinematic" ? "Le mode cinématique impose Remotion." : "Auto laisse le mode décider."}
            error={errors.render_engine?.message}
          >
            <Controller
              control={control}
              name="render_engine"
              render={({ field }) => (
                <Segmented
                  options={ENGINE_OPTIONS}
                  value={field.value}
                  onChange={field.onChange}
                  disabledValues={mode === "cinematic" ? ["manim"] : []}
                />
              )}
            />
          </Field>
        </FormSection>

        <FormSection label="Recherche" title="Ancrage documentaire">
          <Controller
            control={control}
            name="research_enabled"
            render={({ field }) => (
              <Toggle
                checked={field.value}
                onChange={field.onChange}
                label="Activer la recherche"
                description="Source les faits avant d'écrire le blueprint."
              />
            )}
          />
          <Controller
            control={control}
            name="research_required"
            render={({ field }) => (
              <Toggle
                checked={field.value}
                onChange={field.onChange}
                label="Recherche obligatoire"
                description="Échoue si aucun fournisseur de recherche n'est configuré."
              />
            )}
          />
          <Field label="Sources maximum">
            <Controller
              control={control}
              name="research_max_sources"
              render={({ field }) => (
                <RangeField
                  value={field.value}
                  onChange={field.onChange}
                  min={3}
                  max={20}
                  readout={`${field.value}`}
                />
              )}
            />
          </Field>
          {!researchEnabled && (
            <p className="text-xs text-faint">Recherche désactivée — les autres réglages sont ignorés.</p>
          )}
        </FormSection>

        <FormSection label="Visuels" title="Stratégie visuelle">
          <Field label="Stratégie">
            <Controller
              control={control}
              name="visuals_strategy"
              render={({ field }) => (
                <Segmented options={STRATEGY_OPTIONS} value={field.value} onChange={field.onChange} />
              )}
            />
          </Field>
          <Controller
            control={control}
            name="visuals_allow_stock"
            render={({ field }) => (
              <Toggle
                checked={field.value}
                onChange={field.onChange}
                label="Autoriser les médias stock"
                description="Sinon, repli systématique sur des diagrammes."
              />
            )}
          />
          <Field label="Assets maximum">
            <Controller
              control={control}
              name="visuals_max_assets"
              render={({ field }) => (
                <RangeField value={field.value} onChange={field.onChange} min={0} max={12} readout={`${field.value}`} />
              )}
            />
          </Field>
        </FormSection>

        <FormSection label="Sous-titres" title="Piste de sous-titres">
          <Controller
            control={control}
            name="captions"
            render={({ field }) => (
              <Segmented options={CAPTION_OPTIONS} value={field.value} onChange={field.onChange} />
            )}
          />
        </FormSection>

        <Card className="overflow-hidden">
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="flex w-full items-center justify-between px-5 py-4 text-left"
          >
            <span className="flex flex-col">
              <SectionLabel>Avancé</SectionLabel>
              <span className="mt-1 text-sm font-medium text-ink">Webhook de fin de job</span>
            </span>
            <ChevronDown className={`size-4 text-faint transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
          </button>
          {showAdvanced && (
            <div className="border-t border-border px-5 py-4">
              <Field label="Callback URL" htmlFor="callback" hint="POST JSON à la fin du job (completed / failed / cancelled)." error={errors.callback_url?.message}>
                <TextInput id="callback" type="url" placeholder="https://exemple.com/webhook" {...register("callback_url")} />
              </Field>
            </div>
          )}
        </Card>

        <div className="sticky bottom-0 -mx-5 mt-2 flex items-center justify-between gap-3 border-t border-border bg-bg/90 px-5 py-4 backdrop-blur-md">
          <p className="text-xs text-muted">
            {multilang ? "Un batch multilingue sera créé." : "Une vidéo sera mise en file."}
          </p>
          <div className="flex items-center gap-2">
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
