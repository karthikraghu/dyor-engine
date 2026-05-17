"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Code2,
  LineChart,
  Loader2,
  Play,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  executeStrategy,
  getOrchestratorHealth,
  getSandboxHealth,
  ORCHESTRATOR_API_URL,
  requestDecision,
  runBuiltinBacktest,
  SANDBOX_API_URL,
} from "@/lib/api";
import type {
  BacktestResult,
  ExecuteResponse,
  OrchestrationResult,
  RiskProfile,
  ServiceHealth,
  Trade,
} from "@/lib/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type LoadingAction = "decision" | "execute" | "macd" | "rsi" | null;

type HealthState = {
  sandbox?: ServiceHealth;
  orchestrator?: ServiceHealth;
  sandboxError?: string;
  orchestratorError?: string;
};

const riskProfiles: RiskProfile[] = ["conservative", "balanced", "aggressive"];

export default function DashboardPage() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [riskProfile, setRiskProfile] = useState<RiskProfile>("balanced");
  const [parquetFile, setParquetFile] = useState("");
  const [initialEquity, setInitialEquity] = useState("10000");
  const [headlines, setHeadlines] = useState(
    "Markets rebound as institutional demand strengthens\nBitcoin adoption surges after ETF inflows",
  );

  const [health, setHealth] = useState<HealthState>({});
  const [healthLoading, setHealthLoading] = useState(true);
  const [decision, setDecision] = useState<OrchestrationResult | null>(null);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [lastResponse, setLastResponse] = useState<ExecuteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingAction, setLoadingAction] = useState<LoadingAction>(null);

  const requestBase = useMemo(
    () => ({
      symbol: symbol.trim() || "BTC/USDT",
      timeframe: timeframe.trim() || "1h",
      initial_equity: Number(initialEquity) || 10000,
      ...(parquetFile.trim() ? { parquet_file: parquetFile.trim() } : {}),
    }),
    [initialEquity, parquetFile, symbol, timeframe],
  );

  const refreshHealth = useCallback(async () => {
    setHealthLoading(true);
    const [sandboxResult, orchestratorResult] = await Promise.allSettled([
      getSandboxHealth(),
      getOrchestratorHealth(),
    ]);

    setHealth({
      sandbox:
        sandboxResult.status === "fulfilled" ? sandboxResult.value : undefined,
      sandboxError:
        sandboxResult.status === "rejected"
          ? getErrorMessage(sandboxResult.reason)
          : undefined,
      orchestrator:
        orchestratorResult.status === "fulfilled"
          ? orchestratorResult.value
          : undefined,
      orchestratorError:
        orchestratorResult.status === "rejected"
          ? getErrorMessage(orchestratorResult.reason)
          : undefined,
    });
    setHealthLoading(false);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshHealth();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [refreshHealth]);

  async function handleDecision() {
    setLoadingAction("decision");
    setError(null);

    try {
      const headlineList = headlines
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean);

      const response = await requestDecision({
        symbol: requestBase.symbol,
        timeframe: requestBase.timeframe,
        risk_profile: riskProfile,
        headlines: headlineList,
        ...(parquetFile.trim() ? { parquet_file: parquetFile.trim() } : {}),
      });

      setDecision(response.result);
      setLastResponse(null);
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleExecuteGenerated() {
    if (!decision?.strategy.code) {
      return;
    }

    setLoadingAction("execute");
    setError(null);

    try {
      const response = await executeStrategy({
        ...requestBase,
        code: decision.strategy.code,
      });
      handleBacktestResponse(response);
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleBuiltin(strategy: "macd" | "rsi") {
    setLoadingAction(strategy);
    setError(null);

    try {
      const response = await runBuiltinBacktest({
        ...requestBase,
        strategy,
      });
      handleBacktestResponse(response);
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setLoadingAction(null);
    }
  }

  function handleBacktestResponse(response: ExecuteResponse) {
    setLastResponse(response);
    if (!response.success || !response.result) {
      setBacktest(null);
      setError(response.error ?? "Backtest failed without an error message.");
      return;
    }

    setBacktest(response.result);
  }

  const chartData = useMemo(
    () =>
      backtest?.equity_curve.map((value, index) => ({
        step: index + 1,
        equity: Number(value.toFixed(2)),
      })) ?? [],
    [backtest],
  );

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-4 lg:px-6">
        <header className="flex flex-col gap-3 border-b pb-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal">
              Trader Engine
            </h1>
            <p className="text-sm text-muted-foreground">
              Strategy decisions, sandbox execution, and backtest diagnostics.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refreshHealth()}
            disabled={healthLoading}
            className="w-fit gap-2"
          >
            {healthLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Refresh
          </Button>
        </header>

        <section className="grid gap-3 lg:grid-cols-2">
          <HealthPanel
            title="Sandbox"
            icon={<ShieldCheck className="h-4 w-4" />}
            health={health.sandbox}
            error={health.sandboxError}
            url={SANDBOX_API_URL}
            loading={healthLoading}
          />
          <HealthPanel
            title="Orchestrator"
            icon={<Activity className="h-4 w-4" />}
            health={health.orchestrator}
            error={health.orchestratorError}
            url={ORCHESTRATOR_API_URL}
            loading={healthLoading}
          />
        </section>

        {error ? (
          <Alert variant="destructive">
            <AlertTriangle className="mb-2 h-4 w-4" />
            <AlertTitle>Action failed</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
          <Card className="h-fit">
            <CardHeader>
              <CardTitle>Run Controls</CardTitle>
              <CardDescription>
                Configure the data source and strategy workflow.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Symbol">
                <Input value={symbol} onChange={(event) => setSymbol(event.target.value)} />
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Timeframe">
                  <Input
                    value={timeframe}
                    onChange={(event) => setTimeframe(event.target.value)}
                  />
                </Field>
                <Field label="Initial Equity">
                  <Input
                    type="number"
                    min="0"
                    value={initialEquity}
                    onChange={(event) => setInitialEquity(event.target.value)}
                  />
                </Field>
              </div>

              <Field label="Risk Profile">
                <Select
                  value={riskProfile}
                  onValueChange={(value) => setRiskProfile(value as RiskProfile)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {riskProfiles.map((profile) => (
                      <SelectItem key={profile} value={profile}>
                        {profile}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <Field label="Parquet File">
                <Input
                  placeholder="Blank uses backend default"
                  value={parquetFile}
                  onChange={(event) => setParquetFile(event.target.value)}
                />
              </Field>

              <Field label="Headlines">
                <Textarea
                  value={headlines}
                  onChange={(event) => setHeadlines(event.target.value)}
                />
              </Field>

              <Separator />

              <div className="grid gap-2">
                <Button
                  className="w-full gap-2"
                  onClick={() => void handleDecision()}
                  disabled={loadingAction !== null}
                >
                  {loadingAction === "decision" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <BarChart3 className="h-4 w-4" />
                  )}
                  Generate Decision
                </Button>
                <Button
                  variant="secondary"
                  className="w-full gap-2"
                  onClick={() => void handleExecuteGenerated()}
                  disabled={loadingAction !== null || !decision?.strategy.code}
                >
                  {loadingAction === "execute" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  Run Generated Strategy
                </Button>
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={() => void handleBuiltin("macd")}
                    disabled={loadingAction !== null}
                  >
                    {loadingAction === "macd" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <LineChart className="h-4 w-4" />
                    )}
                    MACD
                  </Button>
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={() => void handleBuiltin("rsi")}
                    disabled={loadingAction !== null}
                  >
                    {loadingAction === "rsi" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <LineChart className="h-4 w-4" />
                    )}
                    RSI
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          <section className="space-y-4">
            <DecisionSection decision={decision} />
            <BacktestSection
              backtest={backtest}
              chartData={chartData}
              lastResponse={lastResponse}
              loading={loadingAction === "execute" || loadingAction === "macd" || loadingAction === "rsi"}
            />
          </section>
        </div>
      </div>
    </main>
  );
}

function HealthPanel({
  title,
  icon,
  health,
  error,
  url,
  loading,
}: {
  title: string;
  icon: React.ReactNode;
  health?: ServiceHealth;
  error?: string;
  url: string;
  loading: boolean;
}) {
  const healthy = health?.status === "ok";

  return (
    <div className="rounded-lg border bg-card p-3 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-secondary">
            {icon}
          </span>
          <div>
            <p className="text-sm font-medium">{title}</p>
            <p className="break-all text-xs text-muted-foreground">{url}</p>
          </div>
        </div>
        {loading ? (
          <Skeleton className="h-6 w-20" />
        ) : (
          <Badge
            variant={healthy ? "default" : "destructive"}
            className={cn("gap-1", healthy && "bg-primary")}
          >
            {healthy ? (
              <CheckCircle2 className="h-3 w-3" />
            ) : (
              <AlertTriangle className="h-3 w-3" />
            )}
            {healthy ? "healthy" : "offline"}
          </Badge>
        )}
      </div>
      {error ? <p className="mt-2 text-xs text-destructive">{error}</p> : null}
      {health?.model_name ? (
        <p className="mt-2 text-xs text-muted-foreground">
          {health.model_provider} / {health.model_name}
        </p>
      ) : null}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function DecisionSection({ decision }: { decision: OrchestrationResult | null }) {
  if (!decision) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Decision</CardTitle>
          <CardDescription>
            Generate a decision to inspect market analysis and strategy code.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState text="No decision has been generated yet." />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle>Decision</CardTitle>
          <CardDescription>
            {decision.symbol} / {decision.timeframe} at{" "}
            {new Date(decision.timestamp).toLocaleString()}
          </CardDescription>
        </div>
        <Badge className="w-fit">{decision.decision.action}</Badge>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="summary">
          <TabsList>
            <TabsTrigger value="summary">Summary</TabsTrigger>
            <TabsTrigger value="strategy">Strategy</TabsTrigger>
          </TabsList>
          <TabsContent value="summary" className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <MetricTile
                label="Decision Confidence"
                value={formatPct(decision.decision.confidence * 100)}
              />
              <MetricTile
                label="Decision Score"
                value={formatNumber(decision.decision.score, 4)}
              />
              <MetricTile
                label="Headlines"
                value={String(decision.sentiment.headlines_analyzed)}
              />
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <InfoBlock
                title="Market"
                rows={[
                  ["Regime", decision.market.regime],
                  ["Trend", formatNumber(decision.market.trend_score, 4)],
                  ["Momentum", formatNumber(decision.market.momentum, 4)],
                  [
                    "Volatility",
                    formatPct(decision.market.annualized_volatility * 100),
                  ],
                ]}
              />
              <InfoBlock
                title="Sentiment"
                rows={[
                  ["Bias", decision.sentiment.bias],
                  ["Score", formatNumber(decision.sentiment.score, 4)],
                  ["Confidence", formatPct(decision.sentiment.confidence * 100)],
                ]}
              />
              <InfoBlock
                title="Risk"
                rows={[
                  ["Profile", decision.risk.risk_profile],
                  ["Position", formatPct(decision.risk.position_size_pct * 100)],
                  ["Stop", formatPct(decision.risk.stop_loss_pct * 100)],
                  ["Take Profit", formatPct(decision.risk.take_profit_pct * 100)],
                ]}
              />
            </div>

            <div className="rounded-lg border p-3">
              <p className="mb-2 text-sm font-medium">Rationale</p>
              <ul className="space-y-1 text-sm text-muted-foreground">
                {decision.decision.rationale.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </TabsContent>
          <TabsContent value="strategy">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-medium">{decision.strategy.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {decision.strategy.summary}
                  </p>
                </div>
                <Code2 className="h-4 w-4 text-muted-foreground" />
              </div>
              <pre className="max-h-[420px] overflow-auto rounded-lg border bg-slate-950 p-3 text-xs leading-5 text-slate-50">
                <code>{decision.strategy.code}</code>
              </pre>
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function BacktestSection({
  backtest,
  chartData,
  lastResponse,
  loading,
}: {
  backtest: BacktestResult | null;
  chartData: { step: number; equity: number }[];
  lastResponse: ExecuteResponse | null;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Backtest Results</CardTitle>
        <CardDescription>
          Sandbox output from generated or built-in strategies.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="grid gap-3 md:grid-cols-4">
            {Array.from({ length: 8 }).map((_, index) => (
              <Skeleton key={index} className="h-20" />
            ))}
          </div>
        ) : backtest ? (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-4">
              <MetricTile
                label="Final Equity"
                value={formatCurrency(backtest.final_equity)}
              />
              <MetricTile
                label="Total Return"
                value={formatPct(backtest.total_return_pct)}
              />
              <MetricTile
                label="Buy and Hold"
                value={formatPct(backtest.buy_hold_return_pct)}
              />
              <MetricTile label="Trades" value={String(backtest.total_trades)} />
              <MetricTile
                label="Sharpe"
                value={formatNumber(backtest.sharpe_ratio, 2)}
              />
              <MetricTile
                label="Sortino"
                value={formatNumber(backtest.sortino_ratio, 2)}
              />
              <MetricTile
                label="Calmar"
                value={formatNumber(backtest.calmar_ratio, 2)}
              />
              <MetricTile
                label="Max Drawdown"
                value={formatPct(backtest.max_drawdown_pct)}
              />
              <MetricTile label="Win Rate" value={formatPct(backtest.win_rate)} />
              <MetricTile
                label="Profit Factor"
                value={formatNumber(backtest.profit_factor, 2)}
              />
              <MetricTile
                label="Commission"
                value={formatPct(backtest.commission_pct * 100)}
              />
              <MetricTile
                label="Slippage"
                value={formatPct(backtest.slippage_pct * 100)}
              />
            </div>

            <div className="rounded-lg border p-3">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-medium">Equity Curve</p>
                  <p className="text-xs text-muted-foreground">
                    {backtest.strategy_name} from {backtest.start_date} to{" "}
                    {backtest.end_date}
                  </p>
                </div>
                {lastResponse?.execution_time_ms ? (
                  <Badge variant="secondary">
                    {lastResponse.execution_time_ms} ms
                  </Badge>
                ) : null}
              </div>
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <RechartsLineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="step"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 12 }}
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 12 }}
                      width={80}
                    />
                    <Tooltip
                      formatter={(value) => formatCurrency(Number(value))}
                      labelFormatter={(label) => `Point ${label}`}
                    />
                    <Line
                      type="monotone"
                      dataKey="equity"
                      stroke="hsl(var(--chart-1))"
                      strokeWidth={2}
                      dot={false}
                    />
                  </RechartsLineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <TradesTable trades={backtest.trades} />
          </div>
        ) : (
          <EmptyState text="Run a generated strategy or a built-in backtest to see results." />
        )}
      </CardContent>
    </Card>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-background p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tracking-normal">{value}</p>
    </div>
  );
}

function InfoBlock({
  title,
  rows,
}: {
  title: string;
  rows: [string, string][];
}) {
  return (
    <div className="rounded-lg border p-3">
      <p className="mb-2 text-sm font-medium">{title}</p>
      <div className="space-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">{label}</span>
            <span className="text-right text-xs font-medium">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TradesTable({ trades }: { trades: Trade[] }) {
  if (trades.length === 0) {
    return <EmptyState text="No trades were emitted for this run." />;
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Type</TableHead>
            <TableHead>Timestamp</TableHead>
            <TableHead className="text-right">Price</TableHead>
            <TableHead className="text-right">Units</TableHead>
            <TableHead className="text-right">P&L</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {trades.map((trade, index) => (
            <TableRow key={`${trade.type}-${trade.timestamp}-${index}`}>
              <TableCell>
                <Badge
                  variant={trade.type === "BUY" ? "secondary" : "outline"}
                  className="gap-1"
                >
                  {trade.type}
                  {trade.forced_close ? " close" : ""}
                </Badge>
              </TableCell>
              <TableCell className="min-w-[180px] text-xs">
                {trade.timestamp}
              </TableCell>
              <TableCell className="text-right">
                {formatCurrency(trade.price)}
              </TableCell>
              <TableCell className="text-right">
                {formatNumber(trade.units, 6)}
              </TableCell>
              <TableCell className="text-right">
                {typeof trade.pnl_dollar === "number"
                  ? `${formatCurrency(trade.pnl_dollar)} / ${formatPct(
                      trade.pnl_pct ?? 0,
                    )}`
                  : "-"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex min-h-[160px] items-center justify-center rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
      {text}
    </div>
  );
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPct(value: number) {
  return `${formatNumber(value, 2)}%`;
}

function formatNumber(value: number, digits = 2) {
  if (!Number.isFinite(value)) {
    return "0";
  }

  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

function getErrorMessage(reason: unknown) {
  if (reason instanceof Error) {
    return reason.message;
  }

  return String(reason);
}
