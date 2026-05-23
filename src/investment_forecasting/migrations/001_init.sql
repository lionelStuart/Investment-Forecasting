CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  asset_type TEXT NOT NULL CHECK (asset_type IN ('stock', 'index', 'etf', 'fund', 'macro', 'other')),
  market TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'CNY',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  source TEXT NOT NULL DEFAULT 'manual',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (code, asset_type, market, source)
);

CREATE TABLE IF NOT EXISTS price_daily (
  id INTEGER PRIMARY KEY,
  asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  trade_date TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  amount REAL,
  pct_change REAL,
  adjusted_close REAL,
  nav REAL,
  accumulated_nav REAL,
  source TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (asset_id, trade_date, source)
);

CREATE TABLE IF NOT EXISTS fund_info (
  id INTEGER PRIMARY KEY,
  asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  fund_type TEXT,
  fund_company TEXT,
  manager TEXT,
  custodian TEXT,
  management_fee REAL,
  custody_fee REAL,
  purchase_fee REAL,
  scale REAL,
  inception_date TEXT,
  benchmark TEXT,
  strategy TEXT,
  objective TEXT,
  stage_returns_json TEXT,
  source TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (asset_id, source)
);

CREATE TABLE IF NOT EXISTS features_daily (
  id INTEGER PRIMARY KEY,
  asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  feature_date TEXT NOT NULL,
  return_1d REAL,
  return_5d REAL,
  return_20d REAL,
  return_60d REAL,
  volatility_20d REAL,
  max_drawdown_60d REAL,
  sharpe_60d REAL,
  calmar_60d REAL,
  win_rate_60d REAL,
  momentum_20d REAL,
  market_state TEXT,
  source TEXT NOT NULL DEFAULT 'system',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (asset_id, feature_date, source)
);

CREATE TABLE IF NOT EXISTS model_predictions (
  id INTEGER PRIMARY KEY,
  asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  prediction_date TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  model_version TEXT NOT NULL,
  target TEXT NOT NULL,
  up_probability REAL,
  expected_return REAL,
  expected_return_low REAL,
  expected_return_high REAL,
  downside_risk REAL,
  confidence REAL,
  input_window_start TEXT,
  input_window_end TEXT,
  assumptions TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (asset_id, prediction_date, horizon_days, model_version, target)
);

CREATE TABLE IF NOT EXISTS backtest_runs (
  id INTEGER PRIMARY KEY,
  model_version TEXT NOT NULL,
  asset_scope TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  parameters_json TEXT,
  metrics_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (model_version, asset_scope, start_date, end_date, horizon_days)
);

CREATE TABLE IF NOT EXISTS backtest_results (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
  asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  prediction_date TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  predicted_return REAL,
  actual_return REAL,
  predicted_direction TEXT,
  actual_direction TEXT,
  prediction_score REAL,
  risk_score REAL,
  advice_score REAL,
  overall_score REAL,
  details_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (run_id, asset_id, prediction_date, horizon_days)
);

CREATE TABLE IF NOT EXISTS daily_advice (
  id INTEGER PRIMARY KEY,
  advice_date TEXT NOT NULL,
  market_summary TEXT NOT NULL,
  risk_level TEXT NOT NULL,
  aggressive_advice TEXT NOT NULL,
  balanced_advice TEXT NOT NULL,
  conservative_advice TEXT NOT NULL,
  allocation_json TEXT,
  assumptions TEXT NOT NULL,
  risk_warnings TEXT NOT NULL,
  evidence_json TEXT,
  prediction_score REAL,
  risk_score REAL,
  advice_score REAL,
  overall_score REAL,
  model_version TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (advice_date, model_version)
);

CREATE TABLE IF NOT EXISTS task_logs (
  id INTEGER PRIMARY KEY,
  task_name TEXT NOT NULL,
  run_date TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  message TEXT,
  error TEXT,
  duration_ms INTEGER,
  metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS model_calibration_reports (
  id INTEGER PRIMARY KEY,
  report_date TEXT NOT NULL,
  candidate_versions TEXT NOT NULL,
  promoted_version TEXT,
  windows_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  rationale TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (report_date, candidate_versions)
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  id INTEGER PRIMARY KEY,
  snapshot_date TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'system',
  index_trend REAL,
  breadth REAL,
  liquidity_heat REAL,
  stock_bond_proxy REAL,
  sentiment TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (snapshot_date, source)
);

CREATE TABLE IF NOT EXISTS macro_observations (
  id INTEGER PRIMARY KEY,
  series_id TEXT NOT NULL,
  observation_date TEXT NOT NULL,
  value REAL,
  source TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (series_id, observation_date, source)
);

CREATE TABLE IF NOT EXISTS data_quality_reports (
  id INTEGER PRIMARY KEY,
  report_date TEXT NOT NULL,
  scope TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok', 'warning', 'failed')),
  warnings_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (report_date, scope)
);

CREATE TABLE IF NOT EXISTS advice_outcome_scores (
  id INTEGER PRIMARY KEY,
  advice_id INTEGER NOT NULL REFERENCES daily_advice(id) ON DELETE CASCADE,
  horizon_days INTEGER NOT NULL,
  outcome_date TEXT NOT NULL,
  portfolio_return REAL,
  benchmark_return REAL,
  benchmark_excess REAL,
  drawdown_control REAL,
  prediction_score REAL,
  risk_score REAL,
  advice_score REAL,
  overall_score REAL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (advice_id, horizon_days)
);

CREATE INDEX IF NOT EXISTS idx_price_daily_asset_date ON price_daily(asset_id, trade_date);
CREATE INDEX IF NOT EXISTS idx_features_daily_asset_date ON features_daily(asset_id, feature_date);
CREATE INDEX IF NOT EXISTS idx_model_predictions_date ON model_predictions(prediction_date, horizon_days);
CREATE INDEX IF NOT EXISTS idx_daily_advice_date ON daily_advice(advice_date);
CREATE INDEX IF NOT EXISTS idx_task_logs_name_date ON task_logs(task_name, run_date);
CREATE INDEX IF NOT EXISTS idx_model_calibration_reports_date ON model_calibration_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_date ON market_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_macro_observations_series_date ON macro_observations(series_id, observation_date);
CREATE INDEX IF NOT EXISTS idx_data_quality_reports_date ON data_quality_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_advice_outcome_scores_advice ON advice_outcome_scores(advice_id);
