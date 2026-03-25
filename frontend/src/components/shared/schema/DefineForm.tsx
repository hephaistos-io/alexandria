/**
 * Generic "define a new schema item" form.
 *
 * All three schema tabs (Classification, Attribution, Affiliation) have a form
 * with the same core structure:
 *   1. Name / identity text input
 *   2. Hex color picker with live swatch
 *   3. Description textarea
 *   4. (optional) Extra fields — e.g. the Directed toggle on the Affiliation tab
 *   5. Submit button
 *
 * The caller supplies `onSubmit`, which receives a base payload of
 * `{ name, description, color }`. If you need extra fields (like `directed`),
 * you manage their state outside this component and pass them in via
 * `extraPayload`. The `extraFields` render-prop renders your custom controls
 * between the description textarea and the submit button so they look
 * consistent with the rest of the form.
 *
 * Example — basic (Classification / Attribution):
 *   <DefineForm
 *     title="Define_New_Entity"
 *     namePlaceholder="e.g. CYBER_PROTOCOL"
 *     nameLabel="Label Identity"
 *     onSubmit={(payload) => createLabel(payload)}
 *   />
 *
 * Example — with extra field (Affiliation):
 *   const [directed, setDirected] = useState(true);
 *   <DefineForm
 *     title="Define_Relation_Type"
 *     namePlaceholder="e.g. ALLIED_WITH"
 *     nameLabel="Relation Identity"
 *     extraPayload={{ directed }}
 *     extraFields={
 *       <DirectedToggle directed={directed} onChange={setDirected} />
 *     }
 *     onSubmit={(payload) => createRelationType({ ...payload, directed })}
 *   />
 */

import { useState, type FormEvent, type ReactNode } from "react";
import { randomColor } from "../../../utils/color";

export interface BasePayload {
  name: string;
  description: string;
  color: string;
}

export interface DefineFormProps {
  /** Heading displayed at the top of the form, e.g. "Define_New_Entity" */
  title: string;
  /** Placeholder text for the name input, e.g. "e.g. CYBER_PROTOCOL" */
  namePlaceholder: string;
  /** Label above the name input, e.g. "Label Identity", "Role Identity" */
  nameLabel: string;
  /**
   * Called on submit with the core `{ name, description, color }` payload.
   * Should return `true` on success (clears the form) or `false` on failure
   * (shows an error message).
   *
   * If you need additional fields in the payload (e.g. `directed`), close
   * over them in the function you pass here — this component only manages the
   * three core fields.
   */
  onSubmit: (payload: BasePayload) => Promise<boolean>;
  /**
   * Extra controls rendered between the description textarea and the submit
   * button. Use this for domain-specific toggles or inputs.
   *
   * The caller is responsible for managing state for these extra fields.
   */
  extraFields?: ReactNode;
}

export function DefineForm({
  title,
  namePlaceholder,
  nameLabel,
  onSubmit,
  extraFields,
}: DefineFormProps) {
  const [name, setName] = useState("");
  const [color, setColor] = useState(randomColor);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || !description.trim()) return;

    setSubmitting(true);
    setSubmitError(null);

    const success = await onSubmit({
      name: name.trim().toUpperCase(),
      description: description.trim(),
      color: color.replace(/^#/, ""),
    });

    setSubmitting(false);
    if (success) {
      setName("");
      setColor(randomColor());
      setDescription("");
    } else {
      setSubmitError("DEPLOY_FAILED — check API connection");
    }
  }

  return (
    <section className="bg-surface-container-low p-6 relative">
      {/* Corner debug badge */}
      <div className="absolute top-0 right-0 p-2 text-[10px] font-mono text-outline-variant/40 select-none">
        [SYS_APPEND]
      </div>

      {/* Section heading */}
      <div className="flex items-center gap-2 mb-6">
        <div className="w-1 h-4 bg-primary" />
        <h2 className="font-headline text-lg tracking-tight uppercase">{title}</h2>
      </div>

      <form className="space-y-6" onSubmit={handleSubmit}>
        {/* Name field */}
        <div className="relative">
          <label className="block font-mono text-[10px] text-outline uppercase mb-2">
            {nameLabel}
          </label>
          <span className="absolute top-0 right-0 font-mono text-[8px] text-outline-variant">
            [KEY_STRING]
          </span>
          <input
            className="w-full bg-surface-container-highest border-0 border-b border-outline p-3 font-mono text-xs text-on-surface focus:ring-0 focus:border-primary transition-all placeholder:text-outline/40"
            placeholder={namePlaceholder}
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>

        {/* Hex color picker */}
        <div>
          <label className="block font-mono text-[10px] text-outline uppercase mb-2">
            Hex Color
          </label>
          <div className="flex items-center bg-surface-container-highest border-0 border-b border-outline p-3 gap-2">
            <span className="text-outline-variant font-mono text-xs">#</span>
            <input
              className="flex-1 bg-transparent border-none p-0 font-mono text-xs text-on-surface focus:ring-0"
              placeholder="76A9FA"
              type="text"
              maxLength={6}
              value={color}
              onChange={(e) => setColor(e.target.value.replace(/[^0-9a-fA-F]/g, ""))}
            />
            {/* Live color swatch */}
            <div
              className="w-5 h-5 border border-outline-variant/30 shrink-0"
              style={{ backgroundColor: `#${color}` }}
            />
          </div>
        </div>

        {/* Description textarea */}
        <div>
          <label className="block font-mono text-[10px] text-outline uppercase mb-2">
            Telemetry Description
          </label>
          <textarea
            className="w-full bg-surface-container-highest border-0 border-b border-outline p-3 font-mono text-xs text-on-surface focus:ring-0 focus:border-primary transition-all resize-none placeholder:text-outline/40"
            placeholder="Define the operational parameters..."
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
          />
        </div>

        {/* Extra domain-specific fields (e.g. directed toggle for Affiliation) */}
        {extraFields}

        {submitError !== null && (
          <p className="font-mono text-[9px] text-error uppercase tracking-wider">{submitError}</p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-primary text-on-primary py-4 font-headline font-bold uppercase tracking-widest transition-all hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none"
          style={{ boxShadow: "0 0 12px rgba(169, 199, 255, 0.3)" }}
        >
          {submitting ? "DEPLOYING..." : "INITIATE_DEPLOYMENT"}
        </button>
      </form>
    </section>
  );
}
