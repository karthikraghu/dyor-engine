export type ServiceHealth = {
  status: string;
  service: string;
  model_provider?: string;
  model_name?: string;
};

export type RiskProfile = "conservative" | "balanced" | "aggressive";

export type DecisionAction = "enter_long" | "reduce_risk" | "wait" | "hold_cash";

export type MarketAnalysis = {
  regime: "bullish" | "bearish" | "ranging";
  trend_score: number;
  momentum: number;
  annualized_volatility: number;
  confidence: number;
};

export type SentimentAnalysis = {
  bias: "positive" | "negative" | "neutral";
  score: number;
  confidence: number;
  headlines_analyzed: number;
};

export type RiskPlan = {
  risk_profile: RiskProfile;
  position_size_pct: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_open_positions: number;
};

export type StrategyPlan = {
  name: string;
  summary: string;
  code: string;
};

export type TradingDecision = {
  action: DecisionAction;
  confidence: number;
  score: number;
  rationale: string[];
};

export type OrchestrationResult = {
  timestamp: string;
  symbol: string;
  timeframe: string;
  market: MarketAnalysis;
  sentiment: SentimentAnalysis;
  risk: RiskPlan;
  strategy: StrategyPlan;
  decision: TradingDecision;
};

export type DecisionRequest = {
  symbol: string;
  timeframe: string;
  risk_profile: RiskProfile;
  headlines: string[];
  parquet_file?: string;
};

export type DecisionResponse = {
  success: boolean;
  result: OrchestrationResult;
};

export type Trade = {
  type: "BUY" | "SELL";
  timestamp: string;
  price: number;
  units: number;
  pnl_pct?: number;
  pnl_dollar?: number;
  forced_close?: boolean;
};

export type BacktestResult = {
  strategy_name: string;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  total_candles: number;
  total_trades: number;
  win_rate: number;
  total_return_pct: number;
  buy_hold_return_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown_pct: number;
  profit_factor: number;
  final_equity: number;
  initial_equity: number;
  slippage_pct: number;
  commission_pct: number;
  equity_curve: number[];
  trades: Trade[];
};

export type ExecuteResponse = {
  success: boolean;
  result?: BacktestResult;
  error?: string;
  stdout?: string;
  execution_time_ms?: number;
};

export type ExecuteRequest = {
  code: string;
  symbol: string;
  timeframe: string;
  initial_equity: number;
  parquet_file?: string;
};

export type BuiltinBacktestRequest = {
  strategy: "macd" | "rsi";
  symbol: string;
  timeframe: string;
  initial_equity: number;
  parquet_file?: string;
};
