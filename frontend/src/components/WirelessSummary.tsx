import { useEffect, useState } from "react";
import { apiFetch, type RadiusTarget, type WirelessSecurity } from "../api/client";
import { StatusBanner } from "./ui";

export const SECURITY_LABELS: Record<WirelessSecurity, string> = {
  wpa2_enterprise: "WPA2-Enterprise (802.1X)",
  wpa3_enterprise: "WPA3-Enterprise (802.1X, protected management frames)",
};

type Props = {
  labId: string;
  ssid: string;
  security: WirelessSecurity;
  /** How clients prove who they are: "PEAP", "EAP-TLS", or "MAB". */
  methodLabel: string;
  /** What a joining client should enter or present, in one phrase. */
  credential: string;
  vlan: number | null;
  clientName: string | null;
  clientIp: string | null;
};

/**
 * The end of the guided wireless flow: every value an operator has to type into
 * an AP or controller, taken from what this run actually created, so nothing has
 * to be copied out of three other pages.
 */
export function WirelessSummary({
  labId,
  ssid,
  security,
  methodLabel,
  credential,
  vlan,
  clientName,
  clientIp,
}: Props) {
  const [target, setTarget] = useState<RadiusTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [secretRevealed, setSecretRevealed] = useState(false);

  useEffect(() => {
    apiFetch<RadiusTarget>(`/radius-target?lab_id=${labId}`)
      .then(setTarget)
      .catch((err: Error) => setError(err.message));
  }, [labId]);

  const serverIp = target?.effective_ip || "— set one on the Dashboard —";

  const rows: [string, string][] = [
    ["SSID", ssid],
    ["Security", SECURITY_LABELS[security]],
    ["EAP method", methodLabel],
    ["RADIUS server", serverIp],
    ["Auth / acct ports", target ? `UDP ${target.auth_port} / ${target.acct_port}` : "UDP 1812 / 1813"],
    ["VLAN returned", vlan ? String(vlan) : "none — clients land in the SSID's default VLAN"],
    [
      "Registered client",
      clientName && clientIp ? `${clientName} (${clientIp})` : "none registered in this run",
    ],
  ];

  return (
    <div className="border border-ink/10 bg-mist/40 p-4 text-sm">
      <p className="font-medium">Configure this SSID on your AP or WLC</p>

      {error && (
        <div className="mt-3">
          <StatusBanner tone="error">{error}</StatusBanner>
        </div>
      )}
      {target?.warning && (
        <div className="mt-3">
          <StatusBanner tone="info">{target.warning}</StatusBanner>
        </div>
      )}

      <dl className="mt-3 grid gap-3 md:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-ink/50">{label}</dt>
            <dd className="font-mono">{value}</dd>
          </div>
        ))}
        <div>
          <dt className="text-ink/50">Shared secret</dt>
          <dd className="flex items-center gap-2 font-mono">
            {/* Masked by default so the summary is safe to leave on screen. */}
            <span>{secretRevealed ? target?.lab_shared_secret || "—" : "••••••••"}</span>
            <button
              type="button"
              className="font-sans text-xs text-signal underline-offset-2 hover:underline"
              onClick={() => setSecretRevealed((v) => !v)}
            >
              {secretRevealed ? "Hide" : "Reveal"}
            </button>
          </dd>
        </div>
      </dl>

      <ol className="mt-4 list-decimal space-y-1 pl-5 text-ink/75">
        <li>
          Add a RADIUS server on the controller pointing at{" "}
          <span className="font-mono">{serverIp}</span> with the shared secret above.
        </li>
        <li>
          Create SSID <span className="font-mono">{ssid}</span> with security{" "}
          {SECURITY_LABELS[security]}, and set its authentication (AAA) server to that entry.
        </li>
        <li>
          Make sure the controller sources RADIUS from{" "}
          <span className="font-mono">{clientIp || "the address you registered"}</span> — FreeRADIUS
          ignores requests from an address it has no client for.
        </li>
        {vlan ? (
          <li>
            Create VLAN <span className="font-mono">{vlan}</span> on the controller and its uplink,
            and allow AAA override / dynamic VLAN assignment so the Access-Accept is honored.
          </li>
        ) : null}
        <li>Join the SSID with {credential}, then watch Auth Events for the result.</li>
      </ol>

      <a
        className="mt-3 inline-block underline"
        href="https://github.com/danryan06/8021x-lab/blob/main/docs/deploying-to-devices.md#part-c--configure-a-wireless-ssid-for-wpa23-enterprise"
        target="_blank"
        rel="noreferrer"
      >
        Full guide: configuring a wireless SSID →
      </a>
    </div>
  );
}
