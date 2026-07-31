import { useState } from "react";

const steps = [
  "Select wired, wireless, or both",
  "Select authentication type (PEAP / EAP-TLS / MAB)",
  "Create users",
  "Create CA",
  "Generate certificates",
  "Configure RADIUS client",
  "Test authentication",
];

export function WizardPage() {
  const [medium, setMedium] = useState<"wired" | "wireless" | "both">("both");
  const [method, setMethod] = useState<"peap" | "eap_tls" | "mab">("peap");

  return (
    <div className="space-y-8">
      <section>
        <h1 className="font-display text-3xl font-bold">Create your first 802.1X lab</h1>
        <p className="mt-1 text-ink/70">
          Guided wizard shell for Phase 0. Steps below are UI placeholders until live RADIUS/CA
          paths are wired.
        </p>
      </section>

      <ol className="space-y-3">
        {steps.map((step, index) => (
          <li
            key={step}
            className="flex gap-4 border border-black/10 bg-white/70 px-4 py-3"
          >
            <span className="font-mono text-signal">{index + 1}</span>
            <span>{step}</span>
          </li>
        ))}
      </ol>

      <section className="grid gap-6 border border-black/10 bg-white/70 p-5 md:grid-cols-2">
        <div>
          <h2 className="font-semibold">1. Medium</h2>
          <div className="mt-3 flex flex-col gap-2">
            {(["wired", "wireless", "both"] as const).map((value) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="medium"
                  checked={medium === value}
                  onChange={() => setMedium(value)}
                />
                {value}
              </label>
            ))}
          </div>
        </div>
        <div>
          <h2 className="font-semibold">2. Authentication type</h2>
          <div className="mt-3 flex flex-col gap-2">
            {(
              [
                ["peap", "PEAP (username / password)"],
                ["eap_tls", "EAP-TLS (certificates)"],
                ["mab", "MAB (MAC authentication bypass)"],
              ] as const
            ).map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="method"
                  checked={method === value}
                  onChange={() => setMethod(value)}
                />
                {label}
              </label>
            ))}
          </div>
        </div>
      </section>

      <button
        type="button"
        className="bg-ink px-4 py-2 text-white opacity-70"
        title="Wired in a later phase"
        disabled
      >
        Continue (coming in Phase 4)
      </button>
    </div>
  );
}
