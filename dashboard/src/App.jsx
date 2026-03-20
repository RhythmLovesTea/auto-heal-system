import { useState, useEffect, useRef } from "react";

// ─── CONSTANTS ────────────────────────────────────────────────────────────────
// These match the service names in your docker-compose.yml
const SERVICE_NAMES = ["auth-service", "payments-api", "db-client", "nginx", "worker"];

// The backend URL — in dev this runs on port 8000 (FastAPI)
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── HELPER: status color/label ───────────────────────────────────────────────
function statusMeta(status) {
  switch (status) {
    case "healthy":  return { color: "#22c55e", label: "● healthy" };
    case "down":     return { color: "#ef4444", label: "● down" };
    case "healing":  return { color: "#38bdf8", label: "↻ healing" };
    case "degraded": return { color: "#f59e0b", label: "⚠ degraded" };
    default:         return { color: "#7d8590", label: "? unknown" };
  }
}

// ─── HELPER: format timestamp ─────────────────────────────────────────────────
function fmtTime(isoString) {
  if (!isoString) return "--:--";
  const d = new Date(isoString);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

// ─── COMPONENT: Single service card ──────────────────────────────────────────
function ServiceCard({ name, status, cpu, mem, extra }) {
  const { color, label } = statusMeta(status);
  const isHealing = status === "healing";

  return (
    <div style={{
      background: "#161b22",
      border: "1px solid #30363d",
      borderRadius: 8,
      padding: "12px",
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Top colored bar — animates when healing */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 2,
        background: isHealing
          ? `linear-gradient(90deg, transparent, ${color}, transparent)`
          : color,
        backgroundSize: isHealing ? "200% 100%" : undefined,
        animation: isHealing ? "healBar 1.2s linear infinite" : undefined,
      }} />

      <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 12, marginBottom: 6 }}>
        {name}
      </div>
      <div style={{ color, fontSize: 11, marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 10, color: "#7d8590" }}>
        cpu <span style={{ color: "#e6edf3" }}>{cpu ?? "—"}%</span>
        {" · "}
        mem <span style={{ color: "#e6edf3" }}>{mem ?? "—"}%</span>
      </div>
      {extra && (
        <div style={{ fontSize: 10, color: "#7d8590", marginTop: 4 }}>{extra}</div>
      )}
    </div>
  );
}

// ─── COMPONENT: One event row in the timeline ─────────────────────────────────
function TimelineEvent({ event }) {
  // event shape (from backend SSE):
  // { id, service, type, message, root_cause, action, severity, timestamp }

  const dotColor = {
    error:    "#ef4444",
    healing:  "#38bdf8",
    resolved: "#22c55e",
    warning:  "#f59e0b",
  }[event.type] || "#7d8590";

  const glowStyle = event.type === "error"
    ? { boxShadow: `0 0 6px rgba(239,68,68,0.6)` }
    : {};

  return (
    <div style={{
      display: "flex", gap: 12, padding: "10px 0",
      borderBottom: "1px solid #30363d",
    }}>
      {/* Colored dot */}
      <div style={{
        width: 8, height: 8, borderRadius: "50%",
        background: dotColor, marginTop: 4, flexShrink: 0,
        ...glowStyle,
      }} />

      {/* Time */}
      <div style={{ color: "#7d8590", fontSize: 10, minWidth: 38, paddingTop: 2, flexShrink: 0 }}>
        {fmtTime(event.timestamp)}
      </div>

      {/* Content */}
      <div>
        <div style={{ color: "#38bdf8", fontSize: 11, marginBottom: 2 }}>
          {event.service}
        </div>
        <div style={{ fontSize: 12, color: "#e6edf3", lineHeight: 1.5 }}>
          {event.message}
        </div>
        {event.root_cause && (
          <div style={{ fontSize: 10, color: "#7d8590", marginTop: 2 }}>
            Root cause: {event.root_cause}
            {event.severity && ` · severity: ${event.severity}`}
          </div>
        )}
        {event.action && (
          <div style={{ fontSize: 10, color: "#7d8590", marginTop: 2 }}>
            Action: {event.action}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── COMPONENT: Stats panel ───────────────────────────────────────────────────
function StatsPanel({ stats }) {
  const rows = [
    { label: "incidents today", value: stats.total,   color: "#ef4444" },
    { label: "auto-healed",     value: stats.healed,  color: "#22c55e" },
    { label: "in progress",     value: stats.active,  color: "#38bdf8" },
    { label: "avg heal time",   value: stats.avgHealTime ? `${stats.avgHealTime}s` : "—", color: "#22c55e" },
    { label: "services healthy",value: `${stats.healthyCount} / ${SERVICE_NAMES.length}`, color: "#22c55e" },
  ];

  return (
    <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 14 }}>
      {rows.map(({ label, value, color }) => (
        <div key={label} style={{
          display: "flex", justifyContent: "space-between", alignItems: "baseline",
          borderBottom: "1px solid #30363d", paddingBottom: 12,
        }}>
          <div style={{ fontSize: 11, color: "#7d8590" }}>{label}</div>
          <div style={{
            fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 20, color,
          }}>{value ?? "—"}</div>
        </div>
      ))}
    </div>
  );
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────
export default function App() {
  // services: { [name]: { status, cpu, mem, extra } }
  const [services, setServices] = useState(() =>
    Object.fromEntries(SERVICE_NAMES.map(n => [n, { status: "unknown" }]))
  );

  // timeline events array — newest first
  const [events, setEvents] = useState([]);

  // stats counters
  const [stats, setStats] = useState({
    total: 0, healed: 0, active: 0, avgHealTime: null, healthyCount: 0,
  });

  // SSE connection status
  const [connected, setConnected] = useState(false);

  // Current UTC time (ticks every second)
  const [now, setNow] = useState(new Date());

  // Keep a ref to EventSource so we can close it on unmount
  const esRef = useRef(null);

  // ── Clock tick ──────────────────────────────────────────────────────────────
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // ── SSE connection ──────────────────────────────────────────────────────────
  useEffect(() => {
    // Connect to the SSE stream endpoint on your FastAPI backend (M1's work)
    const es = new EventSource(`${API_BASE}/stream`);
    esRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    // ── Handle "status" events: full snapshot of all container statuses ──────
    // Backend sends: { services: [{ name, status, cpu, mem, ... }] }
    es.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      const updated = {};
      data.services.forEach(svc => {
        updated[svc.name] = {
          status: svc.status,
          cpu:    svc.cpu_percent,
          mem:    svc.mem_percent,
          extra:  svc.extra ?? null,
        };
      });
      setServices(prev => ({ ...prev, ...updated }));

      // Recount healthy services for stats
      const healthyCount = Object.values(updated).filter(s => s.status === "healthy").length;
      setStats(prev => ({ ...prev, healthyCount }));
    });

    // ── Handle "incident" events: new incident detected ───────────────────────
    // Backend sends: { id, service, type, message, root_cause, severity, action, timestamp }
    es.addEventListener("incident", (e) => {
      const data = JSON.parse(e.data);
      // Prepend to timeline (newest first)
      setEvents(prev => [data, ...prev].slice(0, 50)); // keep max 50

      // Update stats
      setStats(prev => ({
        ...prev,
        total:  prev.total + 1,
        active: prev.active + 1,
      }));

      // Mark the affected service as down
      setServices(prev => ({
        ...prev,
        [data.service]: { ...prev[data.service], status: "down" },
      }));
    });

    // ── Handle "healing" events: healer started working on a service ──────────
    es.addEventListener("healing", (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [data, ...prev].slice(0, 50));
      setServices(prev => ({
        ...prev,
        [data.service]: { ...prev[data.service], status: "healing" },
      }));
    });

    // ── Handle "resolved" events: service back to healthy ─────────────────────
    // Backend sends: { ..., heal_time_seconds }
    es.addEventListener("resolved", (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [data, ...prev].slice(0, 50));

      setServices(prev => ({
        ...prev,
        [data.service]: { ...prev[data.service], status: "healthy" },
      }));

      setStats(prev => {
        const newHealed = prev.healed + 1;
        const newActive = Math.max(0, prev.active - 1);
        // Running average of heal time
        const prevAvg   = prev.avgHealTime ?? 0;
        const newAvg    = newHealed === 1
          ? data.heal_time_seconds
          : Math.round((prevAvg * (newHealed - 1) + data.heal_time_seconds) / newHealed);
        return { ...prev, healed: newHealed, active: newActive, avgHealTime: newAvg };
      });
    });

    return () => {
      es.close();
      setConnected(false);
    };
  }, []);

  // ── Load initial incidents from REST endpoint (on mount) ────────────────────
  // This fills the timeline with history before SSE starts streaming new ones
  useEffect(() => {
    fetch(`${API_BASE}/incidents?limit=20`)
      .then(r => r.json())
      .then(data => {
        // data is an array of incident objects
        setEvents(data.reverse()); // API returns oldest-first, we want newest-first
        setStats(prev => ({
          ...prev,
          total:  data.length,
          healed: data.filter(d => d.type === "resolved").length,
          active: data.filter(d => d.type === "incident" || d.type === "healing").length,
        }));
      })
      .catch(() => {
        // Backend not running yet — that's fine during dev
        console.warn("Could not fetch initial incidents");
      });
  }, []);

  // ─── RENDER ──────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Healing bar keyframe animation */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0d1117; }
        @keyframes healBar {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.3; }
        }
      `}</style>

      <div style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 13,
        color: "#e6edf3",
        background: "#0d1117",
        minHeight: "100vh",
        padding: 16,
      }}>
        {/* ── TOP BAR ── */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          marginBottom: 20, paddingBottom: 12, borderBottom: "1px solid #30363d",
        }}>
          <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 18, fontWeight: 700 }}>
            auto<span style={{ color: "#22c55e" }}>heal</span>
            <span style={{ color: "#7d8590", fontSize: 13, fontWeight: 400 }}> // ops dashboard</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {/* SSE live indicator */}
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              fontSize: 11,
              color: connected ? "#22c55e" : "#ef4444",
              background: connected ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
              border: `1px solid ${connected ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)"}`,
              borderRadius: 20, padding: "4px 10px",
            }}>
              <div style={{
                width: 6, height: 6, borderRadius: "50%",
                background: connected ? "#22c55e" : "#ef4444",
                animation: "blink 2s infinite",
              }} />
              {connected ? "SSE LIVE" : "DISCONNECTED"}
            </div>

            <div style={{ fontSize: 11, color: "#7d8590" }}>
              {now.toLocaleTimeString("en-GB", { timeZone: "UTC" })} UTC
            </div>
          </div>
        </div>

        {/* ── SERVICE CARDS ── */}
        <div style={{ fontSize: 10, color: "#7d8590", letterSpacing: 1, textTransform: "uppercase", marginBottom: 10 }}>
          services
        </div>
        <div style={{
          display: "grid",
          gridTemplateColumns: `repeat(${SERVICE_NAMES.length}, 1fr)`,
          gap: 10, marginBottom: 20,
        }}>
          {SERVICE_NAMES.map(name => (
            <ServiceCard key={name} name={name} {...(services[name] || {})} />
          ))}
        </div>

        {/* ── BOTTOM: TIMELINE + STATS ── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>

          {/* Timeline panel */}
          <div style={{
            background: "#161b22", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden",
          }}>
            <div style={{
              padding: "10px 14px", borderBottom: "1px solid #30363d",
              display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
              <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 12, fontWeight: 700, color: "#7d8590", letterSpacing: 0.5, textTransform: "uppercase" }}>
                incident timeline
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#22c55e" }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e", animation: "blink 2s infinite" }} />
                live
              </div>
            </div>

            <div style={{ padding: "0 14px", maxHeight: 420, overflowY: "auto" }}>
              {events.length === 0 ? (
                <div style={{ padding: "24px 0", color: "#7d8590", fontSize: 12, textAlign: "center" }}>
                  No incidents yet — all quiet
                </div>
              ) : (
                events.map((evt, i) => <TimelineEvent key={evt.id ?? i} event={evt} />)
              )}
            </div>
          </div>

          {/* Stats panel */}
          <div style={{
            background: "#161b22", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden",
          }}>
            <div style={{ padding: "10px 14px", borderBottom: "1px solid #30363d" }}>
              <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 12, fontWeight: 700, color: "#7d8590", letterSpacing: 0.5, textTransform: "uppercase" }}>
                stats
              </div>
            </div>
            <StatsPanel stats={stats} />
          </div>

        </div>
      </div>
    </>
  );
}
