import React, { useState, useEffect, useRef } from "react";
// ─── CONSTANTS ────────────────────────────────────────────────────────────────
const SERVICE_NAMES = ["auth-service", "payments-api", "db-client", "nginx", "worker"];
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function statusMeta(status) {
  switch (status) {
    case "healthy":  return { color: "#22c55e", label: "● healthy" };
    case "down":     return { color: "#ef4444", label: "● down" };
    case "healing":  return { color: "#38bdf8", label: "↻ healing" };
    case "degraded": return { color: "#f59e0b", label: "⚠ degraded" };
    default:         return { color: "#7d8590", label: "? unknown" };
  }
}

function fmtTime(isoString) {
  if (!isoString) return "--:--";
  const d = new Date(isoString);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function ServiceCard({ name, status, cpu, mem, extra }) {
  const { color, label } = statusMeta(status);
  const isHealing = status === "healing";
  return (
    <div style={{
      background: "#161b22", border: "1px solid #30363d", borderRadius: 8,
      padding: "12px", position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 2,
        background: isHealing ? `linear-gradient(90deg, transparent, ${color}, transparent)` : color,
        backgroundSize: isHealing ? "200% 100%" : undefined,
        animation: isHealing ? "healBar 1.2s linear infinite" : undefined,
      }} />
      <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 12, marginBottom: 6 }}>{name}</div>
      <div style={{ color, fontSize: 11, marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 10, color: "#7d8590" }}>
        cpu <span style={{ color: "#e6edf3" }}>{cpu ?? "—"}%</span>
        {" · "}
        mem <span style={{ color: "#e6edf3" }}>{mem ?? "—"}%</span>
      </div>
      {extra && <div style={{ fontSize: 10, color: "#7d8590", marginTop: 4 }}>{extra}</div>}
    </div>
  );
}

function TimelineEvent({ event }) {
  const dotColor = {
    error:    "#ef4444",
    healing:  "#38bdf8",
    resolved: "#22c55e",
    warning:  "#f59e0b",
    incident_detected: "#ef4444",
  }[event.type] || "#7d8590";
  const glowStyle = (event.type === "error" || event.type === "incident_detected")
    ? { boxShadow: `0 0 6px rgba(239,68,68,0.6)` } : {};
  return (
    <div style={{ display: "flex", gap: 12, padding: "10px 0", borderBottom: "1px solid #30363d" }}>
      <div style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor, marginTop: 4, flexShrink: 0, ...glowStyle }} />
      <div style={{ color: "#7d8590", fontSize: 10, minWidth: 38, paddingTop: 2, flexShrink: 0 }}>{fmtTime(event.timestamp)}</div>
      <div>
        <div style={{ color: "#38bdf8", fontSize: 11, marginBottom: 2 }}>{event.service}</div>
        <div style={{ fontSize: 12, color: "#e6edf3", lineHeight: 1.5 }}>{event.message}</div>
        {event.root_cause && (
          <div style={{ fontSize: 10, color: "#7d8590", marginTop: 2 }}>
            Root cause: {event.root_cause}{event.severity && ` · severity: ${event.severity}`}
          </div>
        )}
        {event.action && <div style={{ fontSize: 10, color: "#7d8590", marginTop: 2 }}>Action: {event.action}</div>}
      </div>
    </div>
  );
}

function StatsPanel({ stats }) {
  const rows = [
    { label: "incidents today",  value: stats.total,  color: "#ef4444" },
    { label: "auto-healed",      value: stats.healed, color: "#22c55e" },
    { label: "in progress",      value: stats.active, color: "#38bdf8" },
    { label: "avg heal time",    value: stats.avgHealTime ? `${stats.avgHealTime}s` : "—", color: "#22c55e" },
    { label: "services healthy", value: `${stats.healthyCount} / ${SERVICE_NAMES.length}`, color: "#22c55e" },
  ];
  return (
    <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 14 }}>
      {rows.map(({ label, value, color }) => (
        <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", borderBottom: "1px solid #30363d", paddingBottom: 12 }}>
          <div style={{ fontSize: 11, color: "#7d8590" }}>{label}</div>
          <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 20, color }}>{value ?? "—"}</div>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [services, setServices] = useState(() =>
    Object.fromEntries(SERVICE_NAMES.map(n => [n, { status: "unknown" }]))
  );
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState({ total: 0, healed: 0, active: 0, avgHealTime: null, healthyCount: 0 });
  const [connected, setConnected] = useState(false);
  const [now, setNow] = useState(new Date());
  const esRef = useRef(null);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // ── SSE connection with AUTO-RECONNECT ──────────────────────────────────────
  useEffect(() => {
    let es;
    let retryTimeout;

    const connect = () => {
      es = new EventSource(`${API_BASE}/stream`);
      esRef.current = es;

      es.onopen = () => setConnected(true);

      // Catch plain data: events (incident_detected from monitor)
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          setEvents(prev => [data, ...prev].slice(0, 50));
          if (data.type === "incident_detected") {
            setStats(prev => ({ ...prev, total: prev.total + 1, active: prev.active + 1 }));
            setServices(prev => ({
              ...prev,
              [data.service]: { ...prev[data.service], status: "down" },
            }));
          }
        } catch {}
      };

      es.onerror = () => {
        setConnected(false);
        es.close();
        retryTimeout = setTimeout(connect, 3000); // retry every 3s
      };

      es.addEventListener("status", (e) => {
        const data = JSON.parse(e.data);
        const updated = {};
        data.services.forEach(svc => {
          updated[svc.name] = { status: svc.status, cpu: svc.cpu_percent, mem: svc.mem_percent, extra: svc.extra ?? null };
        });
        setServices(prev => ({ ...prev, ...updated }));
        const healthyCount = Object.values(updated).filter(s => s.status === "healthy").length;
        setStats(prev => ({ ...prev, healthyCount }));
      });

      es.addEventListener("incident", (e) => {
        const data = JSON.parse(e.data);
        setEvents(prev => [data, ...prev].slice(0, 50));
        setStats(prev => ({ ...prev, total: prev.total + 1, active: prev.active + 1 }));
        setServices(prev => ({ ...prev, [data.service]: { ...prev[data.service], status: "down" } }));
      });

      es.addEventListener("healing", (e) => {
        const data = JSON.parse(e.data);
        setEvents(prev => [data, ...prev].slice(0, 50));
        setServices(prev => ({ ...prev, [data.service]: { ...prev[data.service], status: "healing" } }));
      });

      es.addEventListener("resolved", (e) => {
        const data = JSON.parse(e.data);
        setEvents(prev => [data, ...prev].slice(0, 50));
        setServices(prev => ({ ...prev, [data.service]: { ...prev[data.service], status: "healthy" } }));
        setStats(prev => {
          const newHealed = prev.healed + 1;
          const newActive = Math.max(0, prev.active - 1);
          const prevAvg = prev.avgHealTime ?? 0;
          const newAvg = newHealed === 1 ? data.heal_time_seconds : Math.round((prevAvg * (newHealed - 1) + data.heal_time_seconds) / newHealed);
          return { ...prev, healed: newHealed, active: newActive, avgHealTime: newAvg };
        });
      });
    };

    connect();

    return () => {
      if (es) es.close();
      if (retryTimeout) clearTimeout(retryTimeout);
      setConnected(false);
    };
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/incidents/?limit=20`)
      .then(r => r.json())
      .then(data => {
        setEvents(data.reverse());
        setStats(prev => ({
          ...prev,
          total:  data.length,
          healed: data.filter(d => d.type === "resolved").length,
          active: data.filter(d => d.type === "incident" || d.type === "healing").length,
        }));
      })
      .catch(() => console.warn("Could not fetch initial incidents"));
  }, []);

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0d1117; }
        @keyframes healBar { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
      `}</style>

      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color: "#e6edf3", background: "#0d1117", minHeight: "100vh", padding: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20, paddingBottom: 12, borderBottom: "1px solid #30363d" }}>
          <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 18, fontWeight: 700 }}>
            auto<span style={{ color: "#22c55e" }}>heal</span>
            <span style={{ color: "#7d8590", fontSize: 13, fontWeight: 400 }}> // ops dashboard</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: connected ? "#22c55e" : "#ef4444", background: connected ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)", border: `1px solid ${connected ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)"}`, borderRadius: 20, padding: "4px 10px" }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: connected ? "#22c55e" : "#ef4444", animation: "blink 2s infinite" }} />
              {connected ? "SSE LIVE" : "DISCONNECTED"}
            </div>
            <div style={{ fontSize: 11, color: "#7d8590" }}>{now.toLocaleTimeString("en-GB", { timeZone: "UTC" })} UTC</div>
          </div>
        </div>

        <div style={{ fontSize: 10, color: "#7d8590", letterSpacing: 1, textTransform: "uppercase", marginBottom: 10 }}>services</div>
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${SERVICE_NAMES.length}, 1fr)`, gap: 10, marginBottom: 20 }}>
          {SERVICE_NAMES.map(name => <ServiceCard key={name} name={name} {...(services[name] || {})} />)}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
          <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", borderBottom: "1px solid #30363d", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 12, fontWeight: 700, color: "#7d8590", letterSpacing: 0.5, textTransform: "uppercase" }}>incident timeline</div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#22c55e" }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e", animation: "blink 2s infinite" }} /> live
              </div>
            </div>
            <div style={{ padding: "0 14px", maxHeight: 420, overflowY: "auto" }}>
              {events.length === 0 ? (
                <div style={{ padding: "24px 0", color: "#7d8590", fontSize: 12, textAlign: "center" }}>No incidents yet — all quiet</div>
              ) : (
                events.map((evt, i) => <TimelineEvent key={evt.id ?? i} event={evt} />)
              )}
            </div>
          </div>

          <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", borderBottom: "1px solid #30363d" }}>
              <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 12, fontWeight: 700, color: "#7d8590", letterSpacing: 0.5, textTransform: "uppercase" }}>stats</div>
            </div>
            <StatsPanel stats={stats} />
          </div>
        </div>
      </div>
    </>
  );
}
