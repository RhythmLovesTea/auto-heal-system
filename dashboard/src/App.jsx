import React, { useState, useEffect, useRef } from "react";

const SERVICE_NAMES = ["auth-service", "payments-api", "db-client", "nginx-victim", "worker"];
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const STATUS_CONFIG = {
  healthy:  { color: "#22c55e", bg: "rgba(34,197,94,0.08)",  border: "rgba(34,197,94,0.3)",  label: "healthy",  dot: "#22c55e" },
  down:     { color: "#ef4444", bg: "rgba(239,68,68,0.08)",  border: "rgba(239,68,68,0.3)",  label: "down",     dot: "#ef4444" },
  healing:  { color: "#38bdf8", bg: "rgba(56,189,248,0.08)", border: "rgba(56,189,248,0.3)", label: "healing",  dot: "#38bdf8" },
  degraded: { color: "#f59e0b", bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.3)", label: "degraded", dot: "#f59e0b" },
  unknown:  { color: "#6b7280", bg: "rgba(107,114,128,0.05)", border: "rgba(107,114,128,0.2)", label: "unknown", dot: "#6b7280" },
};

function getStatus(s) { return STATUS_CONFIG[s] || STATUS_CONFIG.unknown; }

function fmtTime(iso) {
  if (!iso) return "--:--";
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function ServiceCard({ name, status, onClick, selected }) {
  const cfg = getStatus(status);
  const isHealing = status === "healing";
  const isDown = status === "down";
  return (
    <div onClick={onClick} style={{
      background: selected ? cfg.bg : "#0d1117",
      border: `1px solid ${selected ? cfg.border : isDown ? "rgba(239,68,68,0.4)" : isHealing ? "rgba(56,189,248,0.4)" : "#21262d"}`,
      borderRadius: 10, padding: "14px 16px", cursor: "pointer",
      position: "relative", overflow: "hidden", transition: "all 0.2s ease",
      transform: selected ? "translateY(-2px)" : "none",
      boxShadow: selected ? `0 4px 20px ${cfg.bg}` : "none",
    }}>
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 2,
        background: isHealing ? `linear-gradient(90deg, transparent, ${cfg.color}, transparent)` : cfg.color,
        backgroundSize: isHealing ? "200% 100%" : undefined,
        animation: isHealing ? "healBar 1.4s linear infinite" : isDown ? "pulse 1s ease infinite" : "none",
      }} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <div style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 12, color: "#e6edf3" }}>{name}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 20, padding: "2px 8px" }}>
          <div style={{ width: 5, height: 5, borderRadius: "50%", background: cfg.dot, animation: (isDown || isHealing) ? "blink 1s infinite" : "none" }} />
          <span style={{ fontSize: 10, color: cfg.color, fontFamily: "monospace" }}>{cfg.label}</span>
        </div>
      </div>
      <div style={{ display: "flex", gap: 12 }}>
        <div style={{ fontSize: 10, color: "#7d8590" }}><span style={{ color: "#58a6ff", fontFamily: "monospace" }}>CPU</span> —%</div>
        <div style={{ fontSize: 10, color: "#7d8590" }}><span style={{ color: "#58a6ff", fontFamily: "monospace" }}>MEM</span> —%</div>
      </div>
    </div>
  );
}

function TimelineEvent({ event, isNew }) {
  const typeConfig = {
    incident_detected: { color: "#ef4444", bg: "rgba(239,68,68,0.08)", icon: "▼", label: "incident" },
    resolved:          { color: "#22c55e", bg: "rgba(34,197,94,0.08)",  icon: "✓", label: "resolved" },
    healing:           { color: "#38bdf8", bg: "rgba(56,189,248,0.08)", icon: "↻", label: "healing"  },
  };
  const cfg = typeConfig[event.type] || { color: "#7d8590", bg: "transparent", icon: "·", label: event.type };
  return (
    <div style={{
      display: "flex", gap: 12, padding: "12px 16px", borderBottom: "1px solid #21262d",
      background: isNew ? cfg.bg : "transparent", transition: "background 1s ease",
      animation: isNew ? "slideIn 0.3s ease" : "none",
    }}>
      <div style={{ width: 22, height: 22, borderRadius: "50%", flexShrink: 0, background: cfg.bg, border: `1px solid ${cfg.color}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: cfg.color, marginTop: 2 }}>{cfg.icon}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: "#58a6ff", fontSize: 12, fontFamily: "monospace", fontWeight: 700 }}>{event.service}</span>
            <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 10, background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}22` }}>{cfg.label}</span>
          </div>
          <span style={{ fontSize: 10, color: "#7d8590", fontFamily: "monospace", flexShrink: 0 }}>{fmtTime(event.timestamp)}</span>
        </div>
        <div style={{ fontSize: 12, color: "#c9d1d9", lineHeight: 1.5 }}>{event.message}</div>
        {event.root_cause && <div style={{ fontSize: 11, color: "#7d8590", marginTop: 4 }}>root cause: <span style={{ color: "#f0883e" }}>{event.root_cause}</span></div>}
      </div>
    </div>
  );
}

function StatCard({ label, value, color, subtitle }) {
  return (
    <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 10, padding: "14px 16px", flex: 1 }}>
      <div style={{ fontSize: 10, color: "#7d8590", fontFamily: "monospace", marginBottom: 6, textTransform: "uppercase", letterSpacing: 1 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color, fontFamily: "monospace", lineHeight: 1 }}>{value ?? "—"}</div>
      {subtitle && <div style={{ fontSize: 10, color: "#7d8590", marginTop: 4 }}>{subtitle}</div>}
    </div>
  );
}

export default function App() {
  const [services, setServices] = useState(() =>
    Object.fromEntries(SERVICE_NAMES.map(n => [n, { status: "unknown" }]))
  );
  const [events, setEvents] = useState([]);
  const [newEventIds, setNewEventIds] = useState(new Set());
  const [stats, setStats] = useState({ total: 0, healed: 0, active: 0, healthyCount: 0 });
  const [connected, setConnected] = useState(false);
  const [now, setNow] = useState(new Date());
  const [selectedService, setSelectedService] = useState(null);
  const [filter, setFilter] = useState("all");
  const esRef = useRef(null);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let es, retryTimeout;
    const connect = () => {
      es = new EventSource(`${API_BASE}/stream`);
      esRef.current = es;
      es.onopen = () => setConnected(true);
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);

          if (data.type === "status_update") {
            setServices(prev => {
              const updated = { ...prev, [data.service]: { ...prev[data.service], status: data.status } };
              const healthyCount = SERVICE_NAMES.filter(n => updated[n]?.status === "healthy").length;
              setStats(s => ({ ...s, healthyCount }));
              return updated;
            });
            return;
          }

          if (data.type === "incident_detected") {
            const id = Date.now();
            data._id = id;
            setEvents(prev => [data, ...prev].slice(0, 100));
            setNewEventIds(prev => new Set([...prev, id]));
            setTimeout(() => setNewEventIds(prev => { const s = new Set(prev); s.delete(id); return s; }), 2000);
            setStats(prev => ({ ...prev, total: prev.total + 1, active: prev.active + 1 }));
            setServices(prev => ({ ...prev, [data.service]: { ...prev[data.service], status: "down" } }));
            return;
          }

          if (data.type === "resolved") {
            const id = Date.now();
            data._id = id;
            setEvents(prev => [data, ...prev].slice(0, 100));
            setNewEventIds(prev => new Set([...prev, id]));
            setTimeout(() => setNewEventIds(prev => { const s = new Set(prev); s.delete(id); return s; }), 2000);
            setServices(prev => ({ ...prev, [data.service]: { ...prev[data.service], status: "healthy" } }));
            setStats(prev => ({ ...prev, healed: prev.healed + 1, active: Math.max(0, prev.active - 1) }));
            return;
          }

        } catch {}
      };
      es.onerror = () => { setConnected(false); es.close(); retryTimeout = setTimeout(connect, 3000); };
      es.addEventListener("healing", (e) => {
        const data = JSON.parse(e.data);
        const id = Date.now(); data._id = id;
        setEvents(prev => [data, ...prev].slice(0, 100));
        setServices(prev => ({ ...prev, [data.service]: { ...prev[data.service], status: "healing" } }));
      });
    };
    connect();
    return () => { if (es) es.close(); if (retryTimeout) clearTimeout(retryTimeout); };
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/incidents/?limit=50`)
      .then(r => r.json())
      .then(data => {
        const mapped = data.reverse().map((d, i) => ({ ...d, _id: i }));
        setEvents(mapped);
        setStats(prev => ({
          ...prev,
          total: data.length,
          healed: data.filter(d => d.type === "resolved").length,
          active: data.filter(d => d.type === "incident" || d.type === "healing").length,
        }));
      })
      .catch(() => {});
  }, []);

  const filteredEvents = events.filter(e => {
    if (selectedService && e.service !== selectedService) return false;
    if (filter === "incidents") return e.type === "incident_detected";
    if (filter === "resolved") return e.type === "resolved";
    return true;
  });

  const downCount = Object.values(services).filter(s => s.status === "down").length;

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0d1117; font-family: 'JetBrains Mono', monospace; }
        @keyframes healBar { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
        @keyframes slideIn { from{opacity:0;transform:translateY(-8px)} to{opacity:1;transform:translateY(0)} }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #0d1117; }
        ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 2px; }
        .filter-btn { background: transparent; border: 1px solid #30363d; color: #7d8590; padding: 4px 12px; border-radius: 20px; font-size: 11px; cursor: pointer; font-family: monospace; transition: all 0.15s; }
        .filter-btn:hover { border-color: #58a6ff; color: #58a6ff; }
        .filter-btn.active { background: rgba(88,166,255,0.1); border-color: #58a6ff; color: #58a6ff; }
      `}</style>

      <div style={{ background: "#0d1117", minHeight: "100vh", color: "#e6edf3", padding: "16px 20px" }}>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20, paddingBottom: 14, borderBottom: "1px solid #21262d" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ fontFamily: "monospace", fontSize: 20, fontWeight: 700 }}>
              auto<span style={{ color: "#22c55e" }}>heal</span>
              <span style={{ color: "#7d8590", fontSize: 13, fontWeight: 400 }}> // ops</span>
            </div>
            {downCount > 0 && (
              <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 6, padding: "3px 10px", fontSize: 11, color: "#ef4444", animation: "pulse 2s infinite" }}>
                {downCount} service{downCount > 1 ? "s" : ""} down
              </div>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ fontSize: 11, color: "#7d8590", fontFamily: "monospace" }}>
              {now.toLocaleTimeString("en-GB", { timeZone: "UTC" })} UTC
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: connected ? "#22c55e" : "#ef4444", background: connected ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)", border: `1px solid ${connected ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)"}`, borderRadius: 20, padding: "4px 12px" }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: connected ? "#22c55e" : "#ef4444", animation: "blink 2s infinite" }} />
              {connected ? "live" : "disconnected"}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
          <StatCard label="incidents today" value={stats.total} color="#ef4444" />
          <StatCard label="auto-healed" value={stats.healed} color="#22c55e" />
          <StatCard label="in progress" value={stats.active} color="#38bdf8" />
          <StatCard label="services healthy" value={`${stats.healthyCount}/5`} color={stats.healthyCount === 5 ? "#22c55e" : "#f59e0b"} subtitle={stats.healthyCount === 5 ? "all systems go" : `${5 - stats.healthyCount} degraded`} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, marginBottom: 16 }}>
          {SERVICE_NAMES.map(name => (
            <ServiceCard key={name} name={name} status={services[name]?.status || "unknown"} selected={selectedService === name} onClick={() => setSelectedService(prev => prev === name ? null : name)} />
          ))}
        </div>

        {selectedService && (
          <div style={{ background: "rgba(88,166,255,0.05)", border: "1px solid rgba(88,166,255,0.2)", borderRadius: 8, padding: "8px 14px", marginBottom: 12, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 12, color: "#58a6ff", fontFamily: "monospace" }}>filtering timeline for: <strong>{selectedService}</strong></span>
            <button onClick={() => setSelectedService(null)} style={{ background: "transparent", border: "none", color: "#7d8590", cursor: "pointer", fontSize: 12 }}>clear ×</button>
          </div>
        )}

        <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 10, overflow: "hidden" }}>
          <div style={{ padding: "10px 16px", borderBottom: "1px solid #21262d", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11, color: "#7d8590", fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1 }}>incident timeline</span>
              {filteredEvents.length > 0 && (
                <span style={{ fontSize: 10, background: "rgba(88,166,255,0.1)", color: "#58a6ff", padding: "1px 7px", borderRadius: 10, border: "1px solid rgba(88,166,255,0.2)" }}>{filteredEvents.length}</span>
              )}
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              {["all", "incidents", "resolved"].map(f => (
                <button key={f} className={`filter-btn${filter === f ? " active" : ""}`} onClick={() => setFilter(f)}>{f}</button>
              ))}
            </div>
          </div>
          <div style={{ maxHeight: 380, overflowY: "auto" }}>
            {filteredEvents.length === 0 ? (
              <div style={{ padding: "40px 0", textAlign: "center", color: "#7d8590", fontSize: 12 }}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>✓</div>
                no incidents — all systems healthy
              </div>
            ) : (
              filteredEvents.map((evt, i) => <TimelineEvent key={evt._id ?? i} event={evt} isNew={newEventIds.has(evt._id)} />)
            )}
          </div>
        </div>

      </div>
    </>
  );
}
