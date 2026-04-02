import { useCallback, useEffect, useState } from "react";
import "./App.css";

const API = import.meta.env.VITE_API_BASE ?? "";
const DEFAULT_PAIR = "EURUSD";

type PairRow = {
  symbol: string;
  selected: boolean;
  ui_status: string;
  label?: string;
  signal?: string | null;
  entry_time?: string | null;
  entry_at?: string | null;
  expiry_minutes?: number | null;
  updated_at?: string | null;
  timeframe?: string | null;
  strength?: number | null;
  reasons?: string[];
  countdown_seconds?: number | null;
};

type Settings = {
  selected_pairs: string[];
  show_all_pairs: boolean;
};

function fmtTime(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtCountdown(sec: number | null | undefined) {
  if (sec == null || Number.isNaN(sec)) return "—";
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

export default function App() {
  const [rows, setRows] = useState<PairRow[]>([]);
  const [settings, setSettings] = useState<Settings>({
    selected_pairs: [DEFAULT_PAIR],
    show_all_pairs: true,
  });
  const [storage, setStorage] = useState<string>("");
  const [modal, setModal] = useState<{ title: string; body: string } | null>(null);
  /** Локальные переключения до Save; после Save сбрасывается */
  const [draftSel, setDraftSel] = useState<Record<string, boolean>>({});

  const loadPairs = useCallback(async () => {
    const r = await fetch(`${API}/api/pairs`);
    const j = await r.json();
    setSettings(j.settings ?? { selected_pairs: [DEFAULT_PAIR], show_all_pairs: true });
    setDraftSel({});
  }, []);

  const pollSignals = useCallback(async () => {
    const r = await fetch(`${API}/api/signals`);
    const j = await r.json();
    setRows(j.pairs ?? []);
    if (j.settings) setSettings(j.settings);
  }, []);

  const loadStatus = useCallback(async () => {
    const r = await fetch(`${API}/api/status`);
    const j = await r.json();
    setStorage(j.storage ?? "");
  }, []);

  useEffect(() => {
    loadPairs();
    loadStatus();
  }, [loadPairs, loadStatus]);

  useEffect(() => {
    pollSignals();
    const id = setInterval(pollSignals, 2500);
    return () => clearInterval(id);
  }, [pollSignals]);

  function isRowSelected(p: PairRow): boolean {
    if (Object.prototype.hasOwnProperty.call(draftSel, p.symbol)) {
      return draftSel[p.symbol];
    }
    return p.selected;
  }

  async function savePairs() {
    const selected: string[] = [];
    rows.forEach((r) => {
      if (isRowSelected(r)) selected.push(r.symbol);
    });
    await fetch(`${API}/api/pairs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_pairs: selected.filter(Boolean),
        show_all_pairs: settings.show_all_pairs,
      }),
    });
    await loadPairs();
    await pollSignals();
  }

  async function sendTest(sig: "BUY" | "SELL") {
    await fetch(`${API}/api/test-signal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: DEFAULT_PAIR, signal: sig }),
    });
    await pollSignals();
  }

  async function openDetail(sym: string) {
    const r = await fetch(`${API}/api/signals/detail?symbol=${encodeURIComponent(sym)}`);
    const txt = await r.text();
    let pretty = txt;
    try {
      pretty = JSON.stringify(JSON.parse(txt), null, 2);
    } catch {
      /* keep text */
    }
    setModal({ title: sym, body: pretty });
  }

  return (
    <>
      <header className="topbar">
        <div className="brand">trad · TradingView webhook</div>
        <div className="controls">
          <button type="button" className="btn ok" onClick={() => sendTest("BUY")}>
            Test BUY
          </button>
          <button type="button" className="btn danger" onClick={() => sendTest("SELL")}>
            Test SELL
          </button>
          <button type="button" className="btn secondary" onClick={() => savePairs()}>
            Save selected pairs
          </button>
        </div>
        <span className="pill ok">
          API · storage: {storage || "…"} ·{" "}
          <code>POST …/api/webhook/tradingview</code>
        </span>
      </header>

      <main className="layout">
        <section className="panel">
          <div className="panel-head">
            <span>EURUSD</span>
            <span className="hint">
              Сейчас приложение работает только с EURUSD. Позже список пар можно расширить обратно.
            </span>
          </div>
          <div className="table-wrap">
            <table className="pairs-table">
              <thead>
                <tr>
                  <th />
                  <th>Пара</th>
                  <th>Сигнал</th>
                  <th>Entry</th>
                  <th>Expiry</th>
                  <th>Обновлено</th>
                  <th>Таймер</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.filter((p) => p.symbol === DEFAULT_PAIR).map((p) => {
                  const sel = isRowSelected(p);
                  const st = p.ui_status;
                  let rowClass = "";
                  if (sel && st === "BUY") rowClass = "row-signal-buy";
                  if (sel && st === "SELL") rowClass = "row-signal-sell";
                  if (sel && st === "NO_SIGNAL") rowClass = "row-signal-none";

                  return (
                    <tr
                      key={p.symbol}
                      className={`${!sel ? "row-off" : ""} ${rowClass}`.trim()}
                    >
                      <td>
                        <input
                          type="checkbox"
                          className="pair-check"
                          data-symbol={p.symbol}
                          checked={sel}
                          onChange={(e) =>
                            setDraftSel((d) => ({ ...d, [p.symbol]: e.target.checked }))
                          }
                        />
                      </td>
                      <td className="mono">{p.symbol}</td>
                      <td>
                        {!sel ? (
                          <span className="badge none">
                            <span className="dot neutral" />—
                          </span>
                        ) : st === "BUY" ? (
                          <span className="badge buy">
                            <span className="dot buy" />
                            BUY
                          </span>
                        ) : st === "SELL" ? (
                          <span className="badge sell">
                            <span className="dot sell" />
                            SELL
                          </span>
                        ) : (
                          <span className="badge none">
                            <span className="dot neutral" />
                            NO SIGNAL
                          </span>
                        )}
                      </td>
                      <td className="mono">
                        {sel && (st === "BUY" || st === "SELL")
                          ? fmtTime(p.entry_at || p.entry_time)
                          : "—"}
                      </td>
                      <td className="mono">
                        {sel && (st === "BUY" || st === "SELL") && p.expiry_minutes != null
                          ? `${p.expiry_minutes}m`
                          : "—"}
                      </td>
                      <td className="mono">{sel ? fmtTime(p.updated_at) : "—"}</td>
                      <td className="mono">
                        {sel && (st === "BUY" || st === "SELL")
                          ? fmtCountdown(p.countdown_seconds)
                          : "—"}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="linkish"
                          onClick={() => openDetail(p.symbol)}
                        >
                          details
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      <div className={`modal ${modal ? "" : "hidden"}`} role="dialog">
        <div className="modal-backdrop" onClick={() => setModal(null)} />
        <div className="modal-card">
          <div className="modal-head">
            <h2>{modal?.title}</h2>
            <button type="button" className="btn icon" onClick={() => setModal(null)}>
              ×
            </button>
          </div>
          <pre className="modal-pre">{modal?.body}</pre>
        </div>
      </div>
    </>
  );
}
