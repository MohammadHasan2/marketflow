
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Database,
  RefreshCw,
  Server,
  TrendingUp,
  Workflow,
  XCircle,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { marketApi } from "./api";
import type { MarketPrice, Overview, PipelineRun } from "./api";
import "./App.css";

function number(value: number | null | undefined) {
  return Number(value ?? 0).toLocaleString("en-US", {
    maximumFractionDigits: 2,
  });
}

function dateLabel(value: string | null | undefined) {
  if (!value) return "No data yet";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString();
}

function timeLabel(value: string | null | undefined) {
  if (!value) return "No runs recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString();
}

function Status({ status }: { status: string }) {
  return (
    <span className={`status status-${status.toLowerCase()}`}>
      <span className="status-dot" />
      {status}
    </span>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string;
  detail: string;
  icon: typeof Activity;
  accent: string;
}) {
  return (
    <article className="metric-card">
      <div className="metric-top">
        <span className="metric-label">{label}</span>
        <span className={`metric-icon ${accent}`}>
          <Icon size={19} />
        </span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-detail">{detail}</div>
    </article>
  );
}

function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [prices, setPrices] = useState<MarketPrice[]>([]);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [history, setHistory] = useState<MarketPrice[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const loadDashboard = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true);
    else setLoading(true);

    setError("");

    try {
      const [overviewResult, pricesResult, runsResult] = await Promise.all([
        marketApi.overview(),
        marketApi.prices(1, 8),
        marketApi.pipelineRuns(1, 6),
      ]);

      setOverview(overviewResult);
      setPrices(pricesResult.data);
      setRuns(runsResult.data);

      const symbols = overviewResult.latest_prices.map((item) => item.symbol);
      setSelectedSymbol((current) =>
        current && symbols.includes(current)
          ? current
          : symbols[0] ?? ""
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load dashboard data."
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
    const timer = window.setInterval(() => void loadDashboard(true), 60000);
    return () => window.clearInterval(timer);
  }, [loadDashboard]);

  useEffect(() => {
    if (!selectedSymbol) {
      setHistory([]);
      return;
    }

    let cancelled = false;

    marketApi.history(selectedSymbol, 365)
      .then((result) => {
        if (!cancelled) setHistory(result.data);
      })
      .catch(() => {
        if (!cancelled) setHistory([]);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedSymbol]);

  const latest = overview?.latest_prices.find(
    (item) => item.symbol === selectedSymbol
  );

  const previous = history.length > 1 ? history[history.length - 2] : null;
  const change =
    latest && previous ? Number(latest.close) - Number(previous.close) : null;

  const symbols = overview?.latest_prices.map((item) => item.symbol) ?? [];

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Activity size={24} /></div>
          <div>
            <div className="brand-name">MarketFlow</div>
            <div className="brand-subtitle">DATA INTELLIGENCE</div>
          </div>
        </div>

        <div className="nav-heading">WORKSPACE</div>
        <div className="nav-item active">
          <TrendingUp size={18} /> Market overview
        </div>
        <div className="nav-item">
          <Database size={18} /> Data warehouse
        </div>
        <div className="nav-item">
          <Workflow size={18} /> Pipeline monitor
        </div>

        <div className="sidebar-bottom">
          <div className="connection-indicator">
            <span className="pulse-dot" />
            <div>
              <strong>API connection</strong>
              <span>Local development</span>
            </div>
          </div>
          <div className="sidebar-version">MARKETFLOW · v1.0.0</div>
        </div>
      </aside>

      <section className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span> <strong>Market overview</strong>
          </div>
          <button
            className="refresh-button"
            onClick={() => void loadDashboard(true)}
            disabled={refreshing}
          >
            <RefreshCw size={15} className={refreshing ? "spin" : ""} />
            {refreshing ? "Refreshing" : "Refresh data"}
          </button>
        </header>

        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow"><span /> LIVE DATA PLATFORM</div>
              <h1>Market overview</h1>
              <p className="page-description">
                Market data and pipeline health, powered by your Supabase warehouse.
              </p>
            </div>
            <div className="updated-label">
              <span className="pulse-dot" />
              API polling every 60 seconds
            </div>
          </div>

          {error && (
            <div className="error-banner">
              <AlertCircle size={19} />
              <div>
                <strong>Unable to load dashboard data</strong>
                <p>{error}</p>
                <button onClick={() => void loadDashboard()}>
                  Try again
                </button>
              </div>
            </div>
          )}

          {loading && !overview ? (
            <div className="loading-panel">
              <RefreshCw className="spin" size={25} />
              <span>Loading data...</span>
            </div>
          ) : (
            <>
              <div className="metrics-grid">
                <MetricCard
                  label="Tracked symbols"
                  value={number(overview?.market.tracked_symbols)}
                  detail="Distinct symbols in warehouse"
                  icon={TrendingUp}
                  accent="cyan"
                />
                <MetricCard
                  label="Price records"
                  value={number(overview?.market.price_records)}
                  detail="Stored market observations"
                  icon={Database}
                  accent="violet"
                />
                <MetricCard
                  label="Successful runs"
                  value={number(overview?.pipeline.successful_runs)}
                  detail={`${number(overview?.pipeline.total_runs)} total pipeline runs`}
                  icon={CheckCircle2}
                  accent="green"
                />
                <MetricCard
                  label="Failed runs"
                  value={number(overview?.pipeline.failed_runs)}
                  detail="Recorded pipeline failures"
                  icon={XCircle}
                  accent="red"
                />
              </div>

              <div className="content-grid">
                <section className="panel chart-panel">
                  <div className="panel-header">
                    <div>
                      <div className="panel-kicker">PRICE ANALYTICS</div>
                      <h2>Historical closing price</h2>
                      <p>Daily observations from your market data table.</p>
                    </div>
                    <select
                      className="symbol-select"
                      value={selectedSymbol}
                      onChange={(event) => setSelectedSymbol(event.target.value)}
                      disabled={symbols.length === 0}
                      aria-label="Select market symbol"
                    >
                      {symbols.length === 0 && <option value="">No symbols</option>}
                      {symbols.map((symbol) => (
                        <option key={symbol} value={symbol}>{symbol}</option>
                      ))}
                    </select>
                  </div>

                  <div className="chart-summary">
                    <div>
                      <span className="muted-label">LATEST CLOSE</span>
                      <div className="chart-price">
                        {latest ? number(Number(latest.close)) : "—"}
                      </div>
                    </div>
                    <div className={`change-indicator ${change === null ? "" : change >= 0 ? "positive" : "negative"}`}>
                      {change !== null && (
                        change >= 0
                          ? <ArrowUpRight size={16} />
                          : <ArrowDownRight size={16} />
                      )}
                      {change === null
                        ? "Not enough history"
                        : `${change >= 0 ? "+" : ""}${number(change)} vs previous record`}
                    </div>
                  </div>

                  <div className="chart-area">
                    {history.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart
                          data={history}
                          margin={{ top: 10, right: 12, left: 0, bottom: 0 }}
                        >
                          <defs>
                            <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="#00f5d4" stopOpacity={0.25} />
                              <stop offset="95%" stopColor="#00f5d4" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid stroke="#202838" strokeDasharray="4 5" vertical={false} />
                          <XAxis
                            dataKey="trading_date"
                            tickFormatter={(value: string) => value.slice(5)}
                            stroke="#657187"
                            tick={{ fill: "#8792a6", fontSize: 11 }}
                            tickLine={false}
                            axisLine={false}
                            minTickGap={32}
                          />
                          <YAxis
                            stroke="#657187"
                            tick={{ fill: "#8792a6", fontSize: 11 }}
                            tickLine={false}
                            axisLine={false}
                            width={60}
                            domain={["auto", "auto"]}
                          />
                          <Tooltip
                            contentStyle={{
                              background: "#111824",
                              border: "1px solid #293548",
                              borderRadius: 10,
                              color: "#f4f7fc",
                            }}
                            labelStyle={{ color: "#9caac0" }}
                            formatter={(value) => [number(Number(value)), "Close"]}
                            labelFormatter={(label) => `Date: ${label}`}
                          />
                          <Area
                            type="monotone"
                            dataKey="close"
                            stroke="#00f5d4"
                            strokeWidth={2}
                            fill="url(#priceGradient)"
                            dot={false}
                            activeDot={{ r: 4, fill: "#00f5d4", stroke: "#08111a", strokeWidth: 2 }}
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="empty-state">
                        <Activity size={27} />
                        <strong>No historical records available</strong>
                        <span>History will appear when records exist for a symbol.</span>
                      </div>
                    )}
                  </div>
                  <div className="chart-footer">
                    <span><span className="legend-dot" /> Closing price</span>
                    <span>{number(history.length)} observations</span>
                  </div>
                </section>

                <section className="panel system-panel">
                  <div className="panel-header">
                    <div>
                      <div className="panel-kicker">SYSTEM HEALTH</div>
                      <h2>Data infrastructure</h2>
                      <p>Latest warehouse and orchestration activity.</p>
                    </div>
                    <Server size={20} className="subtle-icon" />
                  </div>

                  <div className="health-row">
                    <div className="health-icon cyan"><Database size={18} /></div>
                    <div className="health-text">
                      <strong>Supabase warehouse</strong>
                    </div>
                  </div>

                  <div className="health-row">
                    <div className="health-icon violet"><Workflow size={18} /></div>
                    <div className="health-text">
                      <strong>Airflow pipeline</strong>
                    </div>
                  </div>

                  <div className="health-row">
                    <div className="health-icon green"><Clock3 size={18} /></div>
                    <div className="health-text">
                      <strong>Latest trading date</strong>
                      <span>Most recent market observation</span>
                    </div>
                    <span className="health-value">
                      {dateLabel(overview?.market.latest_trading_date)}
                    </span>
                  </div>

                  <div className="health-footer">
                    <span className="pulse-dot" />
                    <span>Metrics reflect the data currently stored in the warehouse.</span>
                  </div>
                </section>
              </div>

              <section className="panel table-panel">
                <div className="panel-header">
                  <div>
                    <div className="panel-kicker">WAREHOUSE EXPLORER</div>
                    <h2>Latest market records</h2>
                    <p>Most recent stored observations, ordered by trading date.</p>
                  </div>
                  <span className="record-count">{prices.length} records loaded</span>
                </div>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th>Trading date</th>
                        <th>Open</th>
                        <th>High</th>
                        <th>Low</th>
                        <th>Close</th>
                        <th>Volume</th>
                      </tr>
                    </thead>
                    <tbody>
                      {prices.map((price, index) => (
                        <tr key={`${price.symbol}-${price.trading_date}-${index}`}>
                          <td>
                            <button
                              className="symbol-link"
                              onClick={() => setSelectedSymbol(price.symbol)}
                            >
                              <span className="symbol-avatar">{price.symbol.slice(0, 1)}</span>
                              {price.symbol}
                            </button>
                          </td>
                          <td>{dateLabel(price.trading_date)}</td>
                          <td>{number(Number(price.open))}</td>
                          <td>{number(Number(price.high))}</td>
                          <td>{number(Number(price.low))}</td>
                          <td className="close-cell">{number(Number(price.close))}</td>
                          <td>{number(Number(price.volume))}</td>
                        </tr>
                      ))}
                      {prices.length === 0 && (
                        <tr>
                          <td colSpan={7} className="table-empty">
                            No price records returned by the API.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="panel table-panel pipeline-panel">
                <div className="panel-header">
                  <div>
                    <div className="panel-kicker">ORCHESTRATION</div>
                    <h2>Recent pipeline runs</h2>
                    <p>Execution audit records stored in Supabase.</p>
                  </div>
                  <span className="record-count">{runs.length} runs loaded</span>
                </div>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Status</th>
                        <th>DAG</th>
                        <th>Started</th>
                        <th>Extracted</th>
                        <th>Transformed</th>
                        <th>Loaded</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((run) => (
                        <tr key={run.run_id}>
                          <td><Status status={run.status} /></td>
                          <td className="dag-name">{run.dag_id}</td>
                          <td>{timeLabel(run.started_at)}</td>
                          <td>{number(run.extracted_records)}</td>
                          <td>{number(run.transformed_records)}</td>
                          <td>{number(run.loaded_records)}</td>
                        </tr>
                      ))}
                      {runs.length === 0 && (
                        <tr>
                          <td colSpan={6} className="table-empty">
                            No pipeline audit runs found yet.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {runs.some((run) => run.status === "failed" && run.error_message) && (
                  <div className="pipeline-errors">
                    <AlertCircle size={17} />
                    <div>
                      <strong>Recent pipeline error</strong>
                      {runs
                        .filter((run) => run.status === "failed" && run.error_message)
                        .slice(0, 2)
                        .map((run) => (
                          <p key={run.run_id}>
                            {run.dag_id}: {run.error_message}
                          </p>
                        ))}
                    </div>
                  </div>
                )}
              </section>

              <footer className="page-footer">
                <span>MARKETFLOW DATA PLATFORM</span>
                <span>Market data served by FastAPI · persisted in Supabase</span>
              </footer>
            </>
          )}
        </div>
      </section>
    </main>
  );
}

export default App;
