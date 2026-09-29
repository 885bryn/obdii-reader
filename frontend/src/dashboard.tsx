import { useEffect, useState } from "react";
import { MotionConfig, motion } from "motion/react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { describeDtc } from "./lib/dtc-descriptions";

type Sample = {
  signal_id: string;
  value: number | string | null;
  unit: string;
  quality: string;
  age_ms: number;
  observed_hz: number | null;
};

type DtcSnapshot = {
  stored: string[] | null;
  pending: string[] | null;
  permanent: string[] | null;
  permanent_reason: string | null;
  status: string;
};

type DashboardState = {
  mode: "live" | "simulated";
  recording?: boolean;
  connection: string;
  halted: boolean;
  acquisition_error: string | null;
  samples: Sample[];
  dtcs: DtcSnapshot;
};

const SIGNALS = {
  coolant_temp: { label: "Coolant temperature", short: "COOLANT", unit: "°C", min: -40, max: 120, code: "PID 05" },
  engine_oil_temp: { label: "Engine oil temperature", short: "ENGINE OIL", unit: "°C", min: -40, max: 210, code: "PID 5C" },
  engine_rpm: { label: "Engine speed", short: "ENGINE SPEED", unit: "RPM", min: 0, max: 7000, code: "PID 0C" },
  vehicle_speed: { label: "Vehicle speed", short: "VEHICLE SPEED", unit: "km/h", min: 0, max: 260, code: "PID 0D" },
  intake_air_temperature: { label: "Intake air temperature", short: "INTAKE TEMP", unit: "°C", min: -40, max: 120, code: "PID 0F" },
  throttle_position: { label: "Throttle position", short: "THROTTLE", unit: "%", min: 0, max: 100, code: "PID 11" },
} as const;

const DTC_GROUPS = [
  { key: "stored", title: "Stored" },
  { key: "pending", title: "Pending" },
  { key: "permanent", title: "Permanent" },
] as const;

function useDashboardState() {
  const [data, setData] = useState<DashboardState | null>(null);
  const [apiError, setApiError] = useState(false);

  useEffect(() => {
    let active = true;
    let timer = 0;
    const poll = async () => {
      try {
        const response = await fetch("/api/state", { cache: "no-store" });
        if (!response.ok) throw new Error("Dashboard state unavailable");
        const state = (await response.json()) as DashboardState;
        if (active) {
          setData(state);
          setApiError(false);
        }
      } catch {
        if (active) setApiError(true);
      } finally {
        if (active) timer = window.setTimeout(poll, 500);
      }
    };
    void poll();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, []);

  return { data, apiError };
}

function formatSample(sample: Sample | undefined, unit: string) {
  if (!sample || sample.value === null) return { value: "—", unit };
  return { value: String(sample.value), unit: sample.unit || unit };
}

function freshness(sample: Sample | undefined) {
  if (!sample) return "Awaiting first sample";
  const rate = sample.observed_hz ? ` · ${sample.observed_hz.toFixed(2)} Hz` : "";
  return `${sample.age_ms} ms old${rate}`;
}

function MetricValue({ value, className = "" }: { value: string; className?: string }) {
  return (
    <motion.span
      key={value}
      className={className}
      initial={{ opacity: 0.55, y: 2 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.16, ease: "easeOut" }}
    >
      {value}
    </motion.span>
  );
}

function TemperatureCard({
  signal,
  sample,
  index,
}: {
  signal: (typeof SIGNALS)["coolant_temp"] | (typeof SIGNALS)["engine_oil_temp"];
  sample: Sample | undefined;
  index: number;
}) {
  const shown = formatSample(sample, signal.unit);
  const numeric = typeof sample?.value === "number" ? sample.value : undefined;
  const percent = numeric === undefined
    ? 0
    : Math.max(0, Math.min(100, ((numeric - signal.min) / (signal.max - signal.min)) * 100));
  const sampleStatus = !sample || sample.quality === "simulated" ? "warning"
    : sample.quality === "good" && sample.value !== null ? "success" : "error";
  const sampleLabel = !sample ? "NO SAMPLE"
    : sample.quality === "simulated" ? "DEMO SAMPLE"
      : sampleStatus === "success" ? "VERIFIED SIGNAL" : "SAMPLE ERROR";

  return (
    <motion.section
      className={`temp-shell temp-shell-${index}`}
      initial={{ opacity: 0, x: index === 0 ? -8 : 8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.24, delay: index * 0.04, ease: "easeOut" }}
      aria-labelledby={`heading-${signal.short}`}
    >
      <Card intensity="medium" glowColor={index === 0 ? "primary" : "cyan"} className="temp-card">
        <CardHeader className="temp-head">
          <div>
            <p className="eyebrow">{signal.code} <span>·</span> LIVE SENSOR</p>
            <CardTitle id={`heading-${signal.short}`} className="temp-title">{signal.label}</CardTitle>
          </div>
          <span className="temp-index">0{index + 1}</span>
        </CardHeader>
        <CardContent className="temp-content">
          <div className="temp-reading" aria-label={`${signal.label}: ${shown.value} ${shown.unit}`}>
            <MetricValue value={shown.value} className="temp-value" />
            <span className="temp-unit">{shown.unit}</span>
          </div>
          <div className="temp-meter-row">
            <div className="vital temp-vital" data-k={signal.short.toLowerCase().replace(" ", "-")}>
              <span className="v-ico" aria-hidden="true">{index === 0 ? "C" : "O"}</span>
              <span
                className="v-track"
                role="meter"
                aria-label={`${signal.label} display range`}
                aria-valuemin={signal.min}
                aria-valuemax={signal.max}
                aria-valuenow={numeric}
                aria-valuetext={numeric === undefined ? "Awaiting sample" : `${numeric} degrees Celsius`}
              >
                <span className="v-fill" style={{ width: `${percent}%` }} />
              </span>
            </div>
            <span className="meter-range">DISPLAY RANGE {signal.min}—{signal.max}{signal.unit}</span>
          </div>
          <div className="temp-footer">
            <span className="freshness">{freshness(sample)}</span>
            <Badge variant="outline" status={sampleStatus} intensity="medium" animated={false} className="hud-badge quality-badge">
              {sampleLabel}
            </Badge>
          </div>
        </CardContent>
      </Card>
    </motion.section>
  );
}

function CompactMetric({ id, sample }: { id: keyof typeof SIGNALS; sample: Sample | undefined }) {
  const signal = SIGNALS[id];
  const shown = formatSample(sample, signal.unit);
  const numeric = typeof sample?.value === "number" ? sample.value : undefined;
  const fill = numeric === undefined
    ? 0
    : Math.max(0, Math.min(100, ((numeric - signal.min) / (signal.max - signal.min)) * 100));
  return (
    <article className="support-metric" aria-label={`${signal.label}: ${shown.value} ${shown.unit}`}>
      <div className="support-label"><span>{signal.short}</span><span>{signal.code}</span></div>
      <div className="support-reading">
        <MetricValue value={shown.value} className="support-value" />
        <span className="support-unit">{shown.unit}</span>
      </div>
      <div className="support-meter" aria-hidden="true"><span style={{ width: `${fill}%` }} /></div>
      <div className="support-fresh">{freshness(sample)}</div>
    </article>
  );
}

function CodeGroup({ title, codes, reason }: { title: string; codes: string[] | null; reason?: string | null }) {
  return (
    <div className="code-group">
      <h3>{title}</h3>
      {codes === null ? (
        <span className="code-empty">Unavailable{reason ? ` · ${reason}` : ""}</span>
      ) : codes.length === 0 ? (
        <span className="code-empty">No codes reported</span>
      ) : (
        <ul className="code-list">{codes.map((code) => (
          <li key={code}>
            <span className="code-value">{code}</span>
            <span className="code-description">{describeDtc(code)}</span>
          </li>
        ))}</ul>
      )}
    </div>
  );
}

export function Dashboard() {
  const { data, apiError } = useDashboardState();
  const samples = Object.fromEntries((data?.samples ?? []).map((sample) => [sample.signal_id, sample])) as Record<string, Sample>;
  const mode = data?.mode ?? null;
  const connection = apiError ? "api unavailable" : data?.halted ? "halted" : data?.connection ?? "starting";
  const badgeStatus = apiError || data?.halted ? "error" : mode === "simulated" ? "warning" : mode === "live" ? "success" : "info";
  const notice = mode === "simulated"
    ? "SIMULATED DATA · Values and example fault codes are illustrative. No vehicle connection is opened."
    : mode === "live"
      ? "LIVE DATA · Target intervals: RPM 0.5s, throttle 1s, other sensors 2s. Slow ECU responses may reduce the actual update rate."
      : "CONNECTING · Waiting for the local dashboard state endpoint.";

  return (
    <MotionConfig reducedMotion="user">
      <div className="dashboard-shell">
        <header className="topbar">
          <div className="brand-lockup">
            <div className="brand-mark" aria-hidden="true">S</div>
            <div>
              <p className="brand-name">GR SUPRA <span>/</span> TELEMETRY</p>
              <p className="brand-subtitle">Read-only vehicle overview</p>
            </div>
          </div>
          <div className="topbar-state" aria-label="Dashboard operating state">
            <Badge variant="outline" status={mode === "simulated" ? "warning" : "info"} intensity="medium" animated={false} className="hud-badge mode-badge">
              {mode === "simulated" ? "SIMULATED" : mode === "live" ? "LIVE SESSION" : "CONNECTING"}
            </Badge>
            <Badge variant="outline" status={badgeStatus} intensity="medium" animated={false} className="hud-badge state-badge" aria-live="polite">
              <span className="state-led" aria-hidden="true" />{connection.toUpperCase()}
            </Badge>
          </div>
        </header>

        <main className="dashboard-main">
          <div className="section-kicker"><span className="section-line" /> POWERTRAIN / SENSOR ARRAY <span className="section-line" /></div>
          <div className="primary-layout">
            <section className="temperature-array" aria-label="Primary temperature readings">
              <TemperatureCard signal={SIGNALS.coolant_temp} sample={samples.coolant_temp} index={0} />
              <TemperatureCard signal={SIGNALS.engine_oil_temp} sample={samples.engine_oil_temp} index={1} />
            </section>

            <aside className="engine-rail" aria-label="Engine and acquisition status">
              <Card intensity="medium" variant="terminal" className="rpm-card">
                <CardHeader className="rail-head">
                  <div><p className="eyebrow">{SIGNALS.engine_rpm.code} <span>·</span> SUPPORTING SIGNAL</p><CardTitle className="rail-title">Engine speed</CardTitle></div>
                  <span className="rail-glyph" aria-hidden="true">↗</span>
                </CardHeader>
                <CardContent className="rpm-content">
                  <div className="rpm-reading"><MetricValue value={formatSample(samples.engine_rpm, "rpm").value} className="rpm-value" /><span className="rpm-unit">RPM</span></div>
                  <div className="rpm-meter" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(100, ((Number(samples.engine_rpm?.value) || 0) / 7000) * 100))}%` }} /></div>
                  <p className="rail-fresh">{freshness(samples.engine_rpm)}</p>
                </CardContent>
              </Card>

              <Card intensity="medium" className="acquisition-card">
                <CardContent className="acquisition-content">
                  <div className="acquisition-heading"><span className="eyebrow">ACQUISITION</span>{data?.recording && <span className="eyebrow recording-indicator">RECORDING</span>}<span className={`acquisition-lamp ${data?.halted || apiError ? "is-error" : ""}`} aria-hidden="true" /></div>
                  <p className="acquisition-status">{connection.toUpperCase()}</p>
                  <p className="acquisition-detail">{apiError ? "State endpoint not responding." : data?.halted ? `Monitoring stopped · ${data.acquisition_error ?? "unknown error"}` : mode === "simulated" ? "Local demo data · no ECU connection" : mode === "live" ? "Read-only session · safe values only" : "Waiting for dashboard state"}</p>
                </CardContent>
              </Card>
            </aside>
          </div>

          <section className="support-section" aria-labelledby="support-heading">
            <div className="section-heading"><div><p className="eyebrow">01 / SUPPORTING TELEMETRY</p><h2 id="support-heading">Road & air signals</h2></div><span className="section-note">SAMPLE FRESHNESS · OBSERVED RATE</span></div>
            <div className="support-grid">
              <CompactMetric id="vehicle_speed" sample={samples.vehicle_speed} />
              <CompactMetric id="intake_air_temperature" sample={samples.intake_air_temperature} />
              <CompactMetric id="throttle_position" sample={samples.throttle_position} />
            </div>
          </section>

          <section className="dtc-section" aria-labelledby="dtc-heading">
            <div className="section-heading"><div><p className="eyebrow">02 / DIAGNOSTIC SNAPSHOT</p><h2 id="dtc-heading">Outstanding fault codes</h2></div><Badge variant="outline" status={data?.dtcs.status === "complete" || data?.dtcs.status === "simulated" ? "success" : "warning"} intensity="medium" animated={false} className="hud-badge snapshot-badge">{data?.dtcs.status?.toUpperCase() ?? "WAITING"}</Badge></div>
            <div className="code-grid">
              {DTC_GROUPS.map(({ key, title }) => (
                <CodeGroup key={key} title={title} codes={data?.dtcs[key] ?? null} reason={key === "permanent" ? data?.dtcs.permanent_reason : null} />
              ))}
            </div>
          </section>

          <footer className="safety-note">
            <span className="safety-mark" aria-hidden="true">!</span>
            <div><p className="safety-title">READ-ONLY SYSTEM</p><p className="safety-text">{notice}{mode === "simulated" ? " No vehicle connection is opened; no vehicle commands or controls are available." : mode === "live" ? " Only verified Mode 01 values. No fault clearing or vehicle controls." : " No vehicle command is authorized."}{data?.halted ? ` Acquisition stopped: ${data.acquisition_error ?? "unknown error"}.` : ""}</p></div>
          </footer>
        </main>
      </div>
    </MotionConfig>
  );
}
