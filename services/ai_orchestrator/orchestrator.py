"""
Deterministic multi-agent orchestration for trading decisions.

This module provides an offline-first orchestration flow:
1. Analyze market structure from OHLCV candles.
2. Score optional headline sentiment.
3. Produce risk controls based on volatility and user profile.
4. Generate sandbox-compatible strategy code.
5. Synthesize a final trading decision with rationale.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from textwrap import dedent
from typing import Literal, Sequence
import re

import numpy as np
import pandas as pd


RiskProfile = Literal["conservative", "balanced", "aggressive"]
DecisionAction = Literal["enter_long", "reduce_risk", "wait", "hold_cash"]

REQUIRED_OHLCV_COLUMNS = {"open", "high", "low", "close", "volume"}
SUPPORTED_RISK_PROFILES = {"conservative", "balanced", "aggressive"}

TIMEFRAME_TO_PERIODS_PER_YEAR = {
    "1m": 525_600,
    "5m": 105_120,
    "15m": 35_040,
    "30m": 17_520,
    "1h": 8_760,
    "4h": 2_190,
    "1d": 365,
    "1w": 52,
}

POSITIVE_SENTIMENT_WORDS = {
    "adoption",
    "approval",
    "beat",
    "breakout",
    "bull",
    "bullish",
    "growth",
    "institutional",
    "profit",
    "record",
    "rebound",
    "rally",
    "strong",
    "surge",
    "upgrade",
}

NEGATIVE_SENTIMENT_WORDS = {
    "ban",
    "bear",
    "bearish",
    "crackdown",
    "crash",
    "downgrade",
    "fear",
    "fraud",
    "hack",
    "lawsuit",
    "liquidation",
    "outflow",
    "recession",
    "selloff",
    "weak",
}


@dataclass(frozen=True)
class MarketAnalysis:
    regime: Literal["bullish", "bearish", "ranging"]
    trend_score: float
    momentum: float
    annualized_volatility: float
    confidence: float


@dataclass(frozen=True)
class SentimentAnalysis:
    bias: Literal["positive", "negative", "neutral"]
    score: float
    confidence: float
    headlines_analyzed: int


@dataclass(frozen=True)
class RiskPlan:
    risk_profile: RiskProfile
    position_size_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    max_open_positions: int


@dataclass(frozen=True)
class StrategyPlan:
    name: str
    summary: str
    code: str


@dataclass(frozen=True)
class TradingDecision:
    action: DecisionAction
    confidence: float
    score: float
    rationale: list[str]


@dataclass(frozen=True)
class OrchestrationResult:
    timestamp: str
    symbol: str
    timeframe: str
    market: MarketAnalysis
    sentiment: SentimentAnalysis
    risk: RiskPlan
    strategy: StrategyPlan
    decision: TradingDecision

    def to_dict(self) -> dict:
        return asdict(self)


class MarketAnalystAgent:
    """Extracts trend, momentum, and volatility from OHLCV candles."""

    def analyze(self, df: pd.DataFrame, timeframe: str) -> MarketAnalysis:
        close = df["close"].astype(float)
        returns = close.pct_change().dropna()

        periods = TIMEFRAME_TO_PERIODS_PER_YEAR.get(timeframe, 8_760)
        annualized_volatility = (
            float(returns.std() * np.sqrt(periods)) if len(returns) > 1 else 0.0
        )

        momentum_lookback = min(14, max(1, len(close) - 1))
        momentum = (
            float((close.iloc[-1] / close.iloc[-(momentum_lookback + 1)]) - 1.0)
            if len(close) > momentum_lookback
            else 0.0
        )

        fast_window = min(20, len(close))
        slow_window = min(50, len(close))
        fast_sma = float(close.rolling(fast_window, min_periods=1).mean().iloc[-1])
        slow_sma = float(close.rolling(slow_window, min_periods=1).mean().iloc[-1])
        trend_score = 0.0 if slow_sma == 0 else (fast_sma - slow_sma) / slow_sma

        if trend_score > 0.004 and momentum >= 0:
            regime: Literal["bullish", "bearish", "ranging"] = "bullish"
        elif trend_score < -0.004 and momentum <= 0:
            regime = "bearish"
        else:
            regime = "ranging"

        confidence = float(
            np.clip(0.25 + (abs(trend_score) * 40.0) + (abs(momentum) * 8.0), 0.1, 0.95)
        )

        return MarketAnalysis(
            regime=regime,
            trend_score=round(float(trend_score), 6),
            momentum=round(float(momentum), 6),
            annualized_volatility=round(float(annualized_volatility), 6),
            confidence=round(confidence, 4),
        )


class SentimentAnalystAgent:
    """Scores headlines with a conservative lexicon-based sentiment model."""

    _token_pattern = re.compile(r"[a-z]+")

    def analyze(self, headlines: Sequence[str]) -> SentimentAnalysis:
        if not headlines:
            return SentimentAnalysis(
                bias="neutral",
                score=0.0,
                confidence=0.2,
                headlines_analyzed=0,
            )

        positive_hits = 0
        negative_hits = 0

        for headline in headlines:
            tokens = self._token_pattern.findall(headline.lower())
            positive_hits += sum(1 for token in tokens if token in POSITIVE_SENTIMENT_WORDS)
            negative_hits += sum(1 for token in tokens if token in NEGATIVE_SENTIMENT_WORDS)

        total_hits = positive_hits + negative_hits
        if total_hits == 0:
            return SentimentAnalysis(
                bias="neutral",
                score=0.0,
                confidence=0.25,
                headlines_analyzed=len(headlines),
            )

        score = (positive_hits - negative_hits) / total_hits
        if score > 0.15:
            bias: Literal["positive", "negative", "neutral"] = "positive"
        elif score < -0.15:
            bias = "negative"
        else:
            bias = "neutral"

        confidence = float(np.clip(0.25 + (0.12 * total_hits), 0.2, 0.95))
        return SentimentAnalysis(
            bias=bias,
            score=round(float(score), 6),
            confidence=round(confidence, 4),
            headlines_analyzed=len(headlines),
        )


class RiskManagerAgent:
    """Converts market conditions into position sizing and risk limits."""

    _base_position = {"conservative": 0.15, "balanced": 0.3, "aggressive": 0.5}
    _base_stop_loss = {"conservative": 0.01, "balanced": 0.015, "aggressive": 0.02}

    def plan(self, market: MarketAnalysis, risk_profile: RiskProfile) -> RiskPlan:
        base_position = self._base_position[risk_profile]
        base_stop = self._base_stop_loss[risk_profile]

        vol_scalar = float(np.clip(1.0 - (market.annualized_volatility * 1.5), 0.35, 1.0))
        position_size_pct = round(base_position * vol_scalar, 4)

        volatility_stop_buffer = float(np.clip(market.annualized_volatility / 4.0, 0.0, 0.015))
        stop_loss_pct = round(float(np.clip(base_stop + volatility_stop_buffer, 0.005, 0.035)), 4)
        take_profit_pct = round(stop_loss_pct * 2.2, 4)

        return RiskPlan(
            risk_profile=risk_profile,
            position_size_pct=position_size_pct,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            max_open_positions=1,
        )


class StrategyCodeAgent:
    """Builds sandbox-compatible strategy code from market and sentiment context."""

    def build(self, market: MarketAnalysis, sentiment: SentimentAnalysis) -> StrategyPlan:
        if market.regime == "bullish" and sentiment.bias != "negative":
            return StrategyPlan(
                name="trend_following_macd",
                summary="Trend-following MACD crossover with transition-only signals.",
                code=self._trend_following_code(),
            )

        if market.regime == "bearish" and sentiment.bias == "negative":
            return StrategyPlan(
                name="defensive_cash",
                summary="Stay defensive in hostile regime by emitting hold signals.",
                code=self._defensive_code(),
            )

        return StrategyPlan(
            name="mean_reversion_rsi",
            summary="RSI mean-reversion for ranging or mixed-conviction environments.",
            code=self._mean_reversion_code(),
        )

    @staticmethod
    def _trend_following_code() -> str:
        return dedent(
            """
            def apply_strategy(df):
                df = df.copy()
                required = {"open", "high", "low", "close", "volume"}
                missing = required.difference(df.columns)
                if missing:
                    raise ValueError(f"Missing required columns: {sorted(missing)}")

                fast = df["close"].ewm(span=12, adjust=False).mean()
                slow = df["close"].ewm(span=26, adjust=False).mean()
                macd = fast - slow
                signal_line = macd.ewm(span=9, adjust=False).mean()

                state = (macd > signal_line).astype(int) - (macd < signal_line).astype(int)
                df["signal"] = state.diff().fillna(0)
                df.loc[df["signal"] > 0, "signal"] = 1
                df.loc[df["signal"] < 0, "signal"] = -1
                df["signal"] = df["signal"].astype(int)
                return df
            """
        ).strip()

    @staticmethod
    def _mean_reversion_code() -> str:
        return dedent(
            """
            import numpy as np

            def apply_strategy(df):
                df = df.copy()
                required = {"open", "high", "low", "close", "volume"}
                missing = required.difference(df.columns)
                if missing:
                    raise ValueError(f"Missing required columns: {sorted(missing)}")

                delta = df["close"].diff()
                gain = delta.clip(lower=0).rolling(window=14, min_periods=14).mean()
                loss = (-delta.clip(upper=0)).rolling(window=14, min_periods=14).mean()
                rs = gain / loss.replace(0, np.nan)
                rsi = 100 - (100 / (1 + rs))

                df["signal"] = 0
                df.loc[rsi < 30, "signal"] = 1
                df.loc[rsi > 70, "signal"] = -1
                df["signal"] = df["signal"].diff().fillna(0)
                df.loc[df["signal"] > 0, "signal"] = 1
                df.loc[df["signal"] < 0, "signal"] = -1
                df["signal"] = df["signal"].astype(int)
                return df
            """
        ).strip()

    @staticmethod
    def _defensive_code() -> str:
        return dedent(
            """
            def apply_strategy(df):
                df = df.copy()
                df["signal"] = 0
                return df
            """
        ).strip()


class DecisionAgent:
    """Combines agent outputs into a single action and rationale."""

    def decide(
        self,
        market: MarketAnalysis,
        sentiment: SentimentAnalysis,
        strategy: StrategyPlan,
    ) -> TradingDecision:
        score = (
            (market.trend_score * 0.55)
            + (sentiment.score * 0.35)
            + (market.momentum * 0.10)
        )

        if strategy.name == "defensive_cash":
            action: DecisionAction = "hold_cash"
        elif score > 0.01:
            action = "enter_long"
        elif score < -0.01:
            action = "reduce_risk"
        else:
            action = "wait"

        confidence = float(
            np.clip(
                0.3
                + (abs(score) * 20.0)
                + (market.confidence * 0.2)
                + (sentiment.confidence * 0.15),
                0.1,
                0.99,
            )
        )

        rationale = [
            f"Market regime={market.regime}, trend_score={market.trend_score:+.4f}, momentum={market.momentum:+.4f}.",
            f"Sentiment bias={sentiment.bias}, score={sentiment.score:+.4f} from {sentiment.headlines_analyzed} headlines.",
            f"Selected strategy={strategy.name}.",
        ]

        return TradingDecision(
            action=action,
            confidence=round(confidence, 4),
            score=round(float(score), 6),
            rationale=rationale,
        )


class TradingOrchestrator:
    """Coordinator that executes the multi-agent decision workflow."""

    def __init__(
        self,
        market_agent: MarketAnalystAgent | None = None,
        sentiment_agent: SentimentAnalystAgent | None = None,
        risk_agent: RiskManagerAgent | None = None,
        strategy_agent: StrategyCodeAgent | None = None,
        decision_agent: DecisionAgent | None = None,
    ):
        self.market_agent = market_agent or MarketAnalystAgent()
        self.sentiment_agent = sentiment_agent or SentimentAnalystAgent()
        self.risk_agent = risk_agent or RiskManagerAgent()
        self.strategy_agent = strategy_agent or StrategyCodeAgent()
        self.decision_agent = decision_agent or DecisionAgent()

    def orchestrate(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        risk_profile: RiskProfile = "balanced",
        headlines: Sequence[str] | None = None,
    ) -> OrchestrationResult:
        if risk_profile not in SUPPORTED_RISK_PROFILES:
            raise ValueError(
                f"Unsupported risk_profile '{risk_profile}'. "
                f"Expected one of: {sorted(SUPPORTED_RISK_PROFILES)}"
            )

        normalized_df = _normalize_ohlcv(df)
        headlines = headlines or []

        market = self.market_agent.analyze(normalized_df, timeframe)
        sentiment = self.sentiment_agent.analyze(headlines)
        risk = self.risk_agent.plan(market, risk_profile)
        strategy = self.strategy_agent.build(market, sentiment)
        decision = self.decision_agent.decide(market, sentiment, strategy)

        return OrchestrationResult(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            sentiment=sentiment,
            risk=risk,
            strategy=strategy,
            decision=decision,
        )


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Input must be a pandas DataFrame.")

    missing_columns = REQUIRED_OHLCV_COLUMNS.difference(df.columns)
    if missing_columns:
        raise ValueError(f"Missing required OHLCV columns: {sorted(missing_columns)}")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("OHLCV DataFrame must use a DatetimeIndex.")

    out = df.copy()
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]

    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")

    for col in REQUIRED_OHLCV_COLUMNS:
        out[col] = out[col].astype(float)

    if len(out) < 20:
        raise ValueError("At least 20 candles are required for orchestration.")

    return out
