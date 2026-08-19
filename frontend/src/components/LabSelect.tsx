import type { Lab } from "../api/client";

/**
 * Lab switcher shown only when more than one lab exists.
 * A single Default Lab is the normal case; extra labs are isolated scenarios.
 */
export function LabSelect({
  labs,
  value,
  onChange,
}: {
  labs: Lab[];
  value: string;
  onChange: (labId: string) => void;
}) {
  if (labs.length <= 1) return null;
  return (
    <label className="block max-w-xs text-sm">
      Lab
      <select
        className="mt-1 block ui-btn-ghost px-3 py-2"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {labs.map((lab) => (
          <option key={lab.id} value={lab.id}>
            {lab.name}
          </option>
        ))}
      </select>
      <span className="mt-1 block text-xs text-ink/55">
        Each lab is a separate set of users, certificates, and RADIUS clients. Most setups
        only need one.
      </span>
    </label>
  );
}
