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

CREATE TABLE IF NOT EXISTS fund_holdings (
  id INTEGER PRIMARY KEY,
  fund_asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  report_period TEXT NOT NULL,
  holding_type TEXT NOT NULL CHECK (holding_type IN ('stock', 'bond', 'other')),
  holding_code TEXT NOT NULL,
  holding_name TEXT NOT NULL,
  holding_asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  weight_pct REAL,
  shares REAL,
  market_value REAL,
  rank INTEGER,
  source TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (fund_asset_id, report_period, holding_type, holding_code, source)
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

CREATE TABLE IF NOT EXISTS model_prediction_reliability (
  id INTEGER PRIMARY KEY,
  prediction_id INTEGER NOT NULL REFERENCES model_predictions(id) ON DELETE CASCADE,
  rank_score REAL,
  rank_position INTEGER,
  rank_count INTEGER,
  same_category_key TEXT,
  same_category_rank INTEGER,
  same_category_count INTEGER,
  risk_adjusted_score REAL,
  validation_status TEXT NOT NULL DEFAULT 'unvalidated',
  recent_rank_ic REAL,
  bucket_spread REAL,
  degraded_reason TEXT,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (prediction_id)
);

CREATE TABLE IF NOT EXISTS model_replay_runs (
  id INTEGER PRIMARY KEY,
  run_key TEXT NOT NULL UNIQUE,
  year INTEGER NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  horizons_json TEXT NOT NULL,
  model_versions_json TEXT NOT NULL,
  lookback_days INTEGER NOT NULL,
  asset_scope TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  metrics_json TEXT,
  tuning_recommendations_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS model_replay_predictions (
  id INTEGER PRIMARY KEY,
  replay_run_id INTEGER NOT NULL REFERENCES model_replay_runs(id) ON DELETE CASCADE,
  asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  prediction_date TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  model_version TEXT NOT NULL,
  target TEXT NOT NULL DEFAULT 'return',
  up_probability REAL,
  expected_return REAL,
  expected_return_low REAL,
  expected_return_high REAL,
  downside_risk REAL,
  confidence REAL,
  input_window_start TEXT,
  input_window_end TEXT,
  outcome_date TEXT,
  actual_return REAL,
  benchmark_return REAL,
  benchmark_identity TEXT,
  benchmark_source TEXT,
  prediction_score REAL,
  risk_score REAL,
  advice_score REAL,
  overall_score REAL,
  score_status TEXT NOT NULL CHECK (score_status IN ('matured', 'pending', 'skipped')),
  skip_reason TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (replay_run_id, asset_id, prediction_date, horizon_days, model_version, target)
);

CREATE TABLE IF NOT EXISTS model_health_metrics (
  id INTEGER PRIMARY KEY,
  replay_run_id INTEGER NOT NULL REFERENCES model_replay_runs(id) ON DELETE CASCADE,
  model_version TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  asset_type TEXT NOT NULL,
  same_category_key TEXT NOT NULL,
  prediction_month TEXT NOT NULL,
  evaluation_window TEXT NOT NULL,
  sample_count INTEGER NOT NULL,
  direction_accuracy REAL,
  rank_ic REAL,
  bucket_spread REAL,
  top_bottom_decile_spread REAL,
  mae REAL,
  median_abs_error REAL,
  raw_high_conf_wrong_rate REAL,
  coverage_rate REAL,
  status TEXT NOT NULL,
  output_role TEXT NOT NULL DEFAULT 'observation_only',
  promotion_status TEXT NOT NULL DEFAULT 'not_reviewed',
  degradation_reason TEXT,
  minimum_sample_met INTEGER NOT NULL DEFAULT 0,
  consumer_display_level TEXT NOT NULL DEFAULT 'internal',
  confidence_label TEXT NOT NULL DEFAULT '暂不强调',
  confidence_rationale_json TEXT NOT NULL DEFAULT '{}',
  last_promoted_at TEXT,
  last_demoted_at TEXT,
  metrics_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (
    replay_run_id, model_version, horizon_days, asset_type,
    same_category_key, prediction_month, evaluation_window
  )
);

CREATE TABLE IF NOT EXISTS model_applicability_profiles (
  id INTEGER PRIMARY KEY,
  replay_run_id INTEGER NOT NULL REFERENCES model_replay_runs(id) ON DELETE CASCADE,
  source_metric_id INTEGER NOT NULL REFERENCES model_health_metrics(id) ON DELETE CASCADE,
  model_version TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  asset_type TEXT NOT NULL,
  same_category_key TEXT NOT NULL,
  prediction_month TEXT NOT NULL,
  evaluation_window TEXT NOT NULL,
  output_role TEXT NOT NULL CHECK (output_role IN (
    'primary_forecast',
    'allocation_bias',
    'ranking_signal',
    'risk_reference',
    'observation_only'
  )),
  ranking_disabled INTEGER NOT NULL DEFAULT 0,
  ranking_disable_reason TEXT,
  promotion_status TEXT NOT NULL DEFAULT 'not_reviewed',
  degradation_reason TEXT,
  minimum_sample_met INTEGER NOT NULL DEFAULT 0,
  consumer_display_level TEXT NOT NULL DEFAULT 'internal',
  confidence_label TEXT NOT NULL DEFAULT '暂不强调',
  confidence_rationale_json TEXT NOT NULL DEFAULT '{}',
  rationale_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (
    replay_run_id, model_version, horizon_days, asset_type,
    same_category_key, prediction_month, evaluation_window
  )
);

CREATE TABLE IF NOT EXISTS model_shadow_routes (
  id INTEGER PRIMARY KEY,
  replay_run_id INTEGER NOT NULL REFERENCES model_replay_runs(id) ON DELETE CASCADE,
  route_name TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  prediction_month TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'shadow_only',
  training_cutoff TEXT,
  baseline_floor REAL NOT NULL,
  monthly_turnover_cap REAL NOT NULL,
  realized_turnover REAL NOT NULL,
  weights_json TEXT NOT NULL,
  shadow_metrics_json TEXT NOT NULL DEFAULT '{}',
  baseline_metrics_json TEXT NOT NULL DEFAULT '{}',
  comparison_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (replay_run_id, route_name, horizon_days, prediction_month)
);

CREATE TABLE IF NOT EXISTS model_governance_reviews (
  id INTEGER PRIMARY KEY,
  replay_run_id INTEGER NOT NULL REFERENCES model_replay_runs(id) ON DELETE CASCADE,
  review_month TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'review_only',
  summary_text TEXT NOT NULL,
  report_json TEXT NOT NULL DEFAULT '{}',
  production_defaults_changed INTEGER NOT NULL DEFAULT 0,
  promotion_review_eligible INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (replay_run_id, review_month)
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

CREATE TABLE IF NOT EXISTS agent_runs (
  id INTEGER PRIMARY KEY,
  role_type TEXT NOT NULL CHECK (role_type IN ('expert', 'jarvis')),
  role_key TEXT NOT NULL,
  run_date TEXT NOT NULL,
  target_evidence_date TEXT NOT NULL,
  version TEXT NOT NULL DEFAULT 'codex_agent_runtime_v1',
  trigger_reason TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN (
    'pending',
    'running',
    'completed',
    'failed',
    'submitted',
    'completed_via_artifact',
    'skipped',
    'validation_failed',
    'cancelled',
    'timed_out'
  )),
  overview_skill TEXT NOT NULL,
  skill_bundle_json TEXT NOT NULL DEFAULT '[]',
  prompt_ref_json TEXT NOT NULL DEFAULT '{}',
  tool_manifest_ref_json TEXT NOT NULL DEFAULT '{}',
  output_contract_json TEXT NOT NULL DEFAULT '{}',
  runtime_policy_json TEXT NOT NULL DEFAULT '{}',
  launch_request_json TEXT NOT NULL DEFAULT '{}',
  runtime_metadata_json TEXT NOT NULL DEFAULT '{}',
  submission_result_json TEXT NOT NULL DEFAULT '{}',
  failure_reason TEXT,
  fallback_reason TEXT,
  idempotency_key TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  started_at TEXT,
  finished_at TEXT,
  UNIQUE (role_type, role_key, run_date, target_evidence_date, version)
);

CREATE TABLE IF NOT EXISTS agent_tool_calls (
  id INTEGER PRIMARY KEY,
  agent_run_id INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  tool_name TEXT NOT NULL,
  role_type TEXT NOT NULL,
  role_key TEXT NOT NULL,
  arguments_json TEXT NOT NULL DEFAULT '{}',
  idempotency_key TEXT,
  status TEXT NOT NULL CHECK (status IN ('allowed', 'rejected', 'submitted', 'failed')),
  result_summary_json TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  called_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scheduler_jobs (
  id INTEGER PRIMARY KEY,
  job_key TEXT NOT NULL UNIQUE,
  job_type TEXT NOT NULL,
  enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)) DEFAULT 1,
  cadence TEXT NOT NULL,
  time_window_json TEXT NOT NULL DEFAULT '{}',
  provider_key TEXT,
  policy_json TEXT NOT NULL DEFAULT '{}',
  next_run_at TEXT,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scheduler_runs (
  id INTEGER PRIMARY KEY,
  job_key TEXT NOT NULL,
  scheduled_at TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'skipped', 'deferred', 'failed')),
  updated_counts_json TEXT NOT NULL DEFAULT '{}',
  skipped_reason TEXT,
  deferred_reason TEXT,
  provider_request_counts_json TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS scheduler_watermarks (
  id INTEGER PRIMARY KEY,
  job_key TEXT NOT NULL,
  provider_key TEXT,
  source_key TEXT NOT NULL DEFAULT '',
  scope_key TEXT NOT NULL DEFAULT '',
  last_success_cursor TEXT,
  last_attempted_cursor TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (job_key, provider_key, source_key, scope_key)
);

CREATE TABLE IF NOT EXISTS provider_rate_limits (
  id INTEGER PRIMARY KEY,
  provider_key TEXT NOT NULL UNIQUE,
  backoff_until TEXT,
  hourly_count INTEGER NOT NULL DEFAULT 0,
  daily_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  last_failure_reason TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
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

CREATE TABLE IF NOT EXISTS model_monitoring_reports (
  id INTEGER PRIMARY KEY,
  report_date TEXT NOT NULL,
  model_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok', 'warning', 'degraded')),
  latest_prediction_date TEXT,
  latest_backtest_end_date TEXT,
  prediction_staleness_days INTEGER,
  backtest_staleness_days INTEGER,
  mean_prediction_score REAL,
  mean_risk_score REAL,
  mean_benchmark_excess REAL,
  mean_overall_score REAL,
  score_drift REAL,
  metrics_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (report_date, model_version)
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

CREATE TABLE IF NOT EXISTS capital_flow_observations (
  id INTEGER PRIMARY KEY,
  flow_date TEXT NOT NULL,
  scope TEXT NOT NULL CHECK (scope IN ('market', 'stock', 'sector', 'fund')),
  subject_code TEXT NOT NULL,
  subject_name TEXT NOT NULL,
  asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  close REAL,
  pct_change REAL,
  main_net_inflow REAL,
  main_net_inflow_pct REAL,
  super_large_net_inflow REAL,
  super_large_net_inflow_pct REAL,
  large_net_inflow REAL,
  large_net_inflow_pct REAL,
  medium_net_inflow REAL,
  medium_net_inflow_pct REAL,
  small_net_inflow REAL,
  small_net_inflow_pct REAL,
  source TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (scope, subject_code, flow_date, source)
);

CREATE TABLE IF NOT EXISTS news_items (
  id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL,
  source TEXT NOT NULL,
  provider_news_id TEXT,
  published_at TEXT NOT NULL,
  title TEXT NOT NULL,
  content_excerpt TEXT NOT NULL,
  content TEXT,
  channels_json TEXT NOT NULL,
  url TEXT,
  content_hash TEXT NOT NULL,
  raw_payload TEXT NOT NULL,
  ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (provider, source, provider_news_id),
  UNIQUE (source, published_at, content_hash)
);

CREATE TABLE IF NOT EXISTS news_item_links (
  id INTEGER PRIMARY KEY,
  news_item_id INTEGER NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
  link_key TEXT NOT NULL,
  asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
  theme_key TEXT,
  theme_label TEXT,
  link_type TEXT NOT NULL CHECK (link_type IN ('asset_code', 'asset_name', 'theme_keyword', 'channel')),
  confidence REAL NOT NULL,
  reason TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'deterministic_news_index_v1',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (news_item_id, link_key, source)
);

CREATE TABLE IF NOT EXISTS news_item_tags (
  id INTEGER PRIMARY KEY,
  news_item_id INTEGER NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
  tag_type TEXT NOT NULL CHECK (tag_type IN ('event_type', 'sentiment')),
  tag_value TEXT NOT NULL,
  intensity REAL NOT NULL DEFAULT 0.5,
  freshness_score REAL NOT NULL DEFAULT 1.0,
  confidence REAL NOT NULL DEFAULT 0.5,
  reason TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'deterministic_news_index_v1',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (news_item_id, tag_type, tag_value, source)
);

CREATE TABLE IF NOT EXISTS news_feature_daily (
  id INTEGER PRIMARY KEY,
  feature_date TEXT NOT NULL,
  scope_type TEXT NOT NULL CHECK (scope_type IN ('asset', 'theme')),
  scope_key TEXT NOT NULL,
  window_start TEXT NOT NULL,
  window_end TEXT NOT NULL,
  news_count INTEGER NOT NULL,
  source_count INTEGER NOT NULL,
  positive_count INTEGER NOT NULL,
  negative_count INTEGER NOT NULL,
  neutral_count INTEGER NOT NULL,
  risk_event_count INTEGER NOT NULL,
  policy_count INTEGER NOT NULL,
  freshness_weighted_sentiment REAL NOT NULL,
  evidence_ids_json TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'deterministic_news_feature_v1',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (feature_date, scope_type, scope_key, window_start, window_end, source)
);

CREATE TABLE IF NOT EXISTS asset_classifications (
  id INTEGER PRIMARY KEY,
  asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  classification_date TEXT NOT NULL,
  taxonomy TEXT NOT NULL,
  level TEXT NOT NULL,
  label TEXT NOT NULL,
  code TEXT,
  source TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (asset_id, classification_date, taxonomy, level, label, source)
);

CREATE TABLE IF NOT EXISTS index_constituents (
  id INTEGER PRIMARY KEY,
  index_asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  index_code TEXT NOT NULL,
  constituent_asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  constituent_code TEXT NOT NULL,
  constituent_name TEXT,
  effective_date TEXT NOT NULL,
  weight REAL,
  source TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (index_code, constituent_code, effective_date, source)
);

CREATE TABLE IF NOT EXISTS asset_trading_status (
  id INTEGER PRIMARY KEY,
  asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  status_date TEXT NOT NULL,
  exchange TEXT,
  listing_status TEXT,
  is_trading INTEGER,
  list_date TEXT,
  delist_date TEXT,
  special_treatment TEXT,
  source TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (code, status_date, source)
);

CREATE TABLE IF NOT EXISTS asset_daily_basic (
  id INTEGER PRIMARY KEY,
  asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  close REAL,
  turnover_rate REAL,
  turnover_rate_free_float REAL,
  volume_ratio REAL,
  pe REAL,
  pe_ttm REAL,
  pb REAL,
  ps REAL,
  ps_ttm REAL,
  dividend_yield REAL,
  dividend_yield_ttm REAL,
  total_share REAL,
  float_share REAL,
  free_share REAL,
  total_market_value REAL,
  circulating_market_value REAL,
  source TEXT NOT NULL,
  raw_payload TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (code, trade_date, source)
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

CREATE TABLE IF NOT EXISTS user_preferences (
  id INTEGER PRIMARY KEY,
  profile_name TEXT NOT NULL UNIQUE,
  risk_profile TEXT NOT NULL CHECK (risk_profile IN ('aggressive', 'balanced', 'conservative')),
  investment_horizon_days INTEGER NOT NULL CHECK (investment_horizon_days > 0),
  max_equity_pct REAL NOT NULL CHECK (max_equity_pct >= 0 AND max_equity_pct <= 1),
  min_cash_pct REAL NOT NULL CHECK (min_cash_pct >= 0 AND min_cash_pct <= 1),
  notes TEXT,
  is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS advice_outcome_scores (
  id INTEGER PRIMARY KEY,
  advice_id INTEGER NOT NULL REFERENCES daily_advice(id) ON DELETE CASCADE,
  horizon_days INTEGER NOT NULL,
  outcome_date TEXT NOT NULL,
  portfolio_return REAL,
  benchmark_return REAL,
  benchmark_identity TEXT,
  benchmark_source TEXT,
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

CREATE TABLE IF NOT EXISTS experts (
  id INTEGER PRIMARY KEY,
  expert_key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  short_description TEXT NOT NULL,
  style_label TEXT NOT NULL,
  focus_weights_json TEXT NOT NULL,
  risk_budget_pct REAL NOT NULL CHECK (risk_budget_pct >= 0 AND risk_budget_pct <= 1),
  max_drawdown_tolerance REAL NOT NULL CHECK (max_drawdown_tolerance >= 0 AND max_drawdown_tolerance <= 1),
  allowed_asset_categories_json TEXT NOT NULL,
  default_cash_buffer_pct REAL NOT NULL CHECK (default_cash_buffer_pct >= 0 AND default_cash_buffer_pct <= 1),
  review_cadence_days INTEGER NOT NULL CHECK (review_cadence_days > 0),
  lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('candidate', 'active', 'probation', 'retired')),
  mandate TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'system',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS virtual_portfolios (
  id INTEGER PRIMARY KEY,
  owner_type TEXT NOT NULL CHECK (owner_type IN ('user', 'expert', 'system')),
  owner_id INTEGER,
  name TEXT NOT NULL,
  initial_capital REAL NOT NULL CHECK (initial_capital >= 0),
  cash REAL NOT NULL CHECK (cash >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (owner_type, owner_id)
);

CREATE TABLE IF NOT EXISTS virtual_positions (
  id INTEGER PRIMARY KEY,
  portfolio_id INTEGER NOT NULL REFERENCES virtual_portfolios(id) ON DELETE CASCADE,
  asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  quantity REAL NOT NULL CHECK (quantity >= 0),
  average_cost REAL NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (portfolio_id, asset_id)
);

CREATE TABLE IF NOT EXISTS virtual_transactions (
  id INTEGER PRIMARY KEY,
  portfolio_id INTEGER NOT NULL REFERENCES virtual_portfolios(id) ON DELETE CASCADE,
  asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  trade_date TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell', 'hold', 'no_trade', 'unfilled')),
  quantity REAL NOT NULL DEFAULT 0 CHECK (quantity >= 0),
  price REAL,
  price_date TEXT,
  gross_amount REAL NOT NULL DEFAULT 0,
  cost_basis REAL,
  fee REAL NOT NULL DEFAULT 0,
  cash_delta REAL NOT NULL DEFAULT 0,
  realized_pnl REAL,
  status TEXT NOT NULL CHECK (status IN ('filled', 'unfilled', 'no_trade')),
  reason TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS virtual_cash_ledger (
  id INTEGER PRIMARY KEY,
  portfolio_id INTEGER NOT NULL REFERENCES virtual_portfolios(id) ON DELETE CASCADE,
  transaction_id INTEGER REFERENCES virtual_transactions(id) ON DELETE SET NULL,
  ledger_date TEXT NOT NULL,
  amount REAL NOT NULL,
  balance_after REAL NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS virtual_valuations (
  id INTEGER PRIMARY KEY,
  portfolio_id INTEGER NOT NULL REFERENCES virtual_portfolios(id) ON DELETE CASCADE,
  valuation_date TEXT NOT NULL,
  cash REAL NOT NULL,
  positions_value REAL NOT NULL,
  total_value REAL NOT NULL,
  missing_prices_json TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (portfolio_id, valuation_date)
);

CREATE TABLE IF NOT EXISTS ai_analysis_records (
  id INTEGER PRIMARY KEY,
  analysis_type TEXT NOT NULL CHECK (analysis_type IN ('expert', 'jarvis')),
  analysis_key TEXT NOT NULL,
  analysis_date TEXT NOT NULL,
  expert_id INTEGER REFERENCES experts(id) ON DELETE CASCADE,
  jarvis_brief_id INTEGER REFERENCES jarvis_daily_briefs(id) ON DELETE SET NULL,
  version TEXT NOT NULL DEFAULT 'ai_analysis_v1',
  evidence_packet_json TEXT NOT NULL,
  output_json TEXT NOT NULL,
  validation_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('valid', 'fallback', 'failed')),
  source TEXT NOT NULL DEFAULT 'deterministic_ai_analysis_v1',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (analysis_type, analysis_date, analysis_key, version)
);

CREATE TABLE IF NOT EXISTS expert_plans (
  id INTEGER PRIMARY KEY,
  expert_id INTEGER NOT NULL REFERENCES experts(id) ON DELETE CASCADE,
  portfolio_id INTEGER NOT NULL REFERENCES virtual_portfolios(id) ON DELETE CASCADE,
  ai_analysis_id INTEGER REFERENCES ai_analysis_records(id) ON DELETE SET NULL,
  plan_date TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('buy', 'sell', 'rebalance', 'hold', 'no_trade')),
  target_asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  target_weight REAL CHECK (target_weight IS NULL OR (target_weight >= 0 AND target_weight <= 1)),
  target_amount REAL CHECK (target_amount IS NULL OR target_amount >= 0),
  rationale TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  risk_checks_json TEXT NOT NULL,
  risk_warnings TEXT NOT NULL,
  execution_status TEXT NOT NULL CHECK (execution_status IN ('pending', 'filled', 'unfilled', 'no_trade')),
  transaction_id INTEGER REFERENCES virtual_transactions(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (expert_id, plan_date)
);

CREATE TABLE IF NOT EXISTS expert_plan_items (
  id INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL REFERENCES expert_plans(id) ON DELETE CASCADE,
  asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  action TEXT NOT NULL CHECK (action IN ('buy', 'sell', 'rebalance', 'hold', 'no_trade')),
  target_weight REAL CHECK (target_weight IS NULL OR (target_weight >= 0 AND target_weight <= 1)),
  target_amount REAL CHECK (target_amount IS NULL OR target_amount >= 0),
  rationale TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expert_scorecards (
  id INTEGER PRIMARY KEY,
  expert_id INTEGER NOT NULL REFERENCES experts(id) ON DELETE CASCADE,
  portfolio_id INTEGER NOT NULL REFERENCES virtual_portfolios(id) ON DELETE CASCADE,
  score_date TEXT NOT NULL,
  window_days INTEGER NOT NULL CHECK (window_days > 0),
  valuation_count INTEGER NOT NULL DEFAULT 0,
  mature_enough INTEGER NOT NULL CHECK (mature_enough IN (0, 1)),
  portfolio_return REAL,
  benchmark_return REAL,
  benchmark_excess REAL,
  max_drawdown REAL,
  volatility REAL,
  cash_drag REAL,
  turnover REAL,
  win_rate REAL,
  evidence_completeness REAL,
  mandate_adherence REAL,
  overall_score REAL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (expert_id, score_date, window_days)
);

CREATE TABLE IF NOT EXISTS expert_reviews (
  id INTEGER PRIMARY KEY,
  expert_id INTEGER NOT NULL REFERENCES experts(id) ON DELETE CASCADE,
  scorecard_id INTEGER REFERENCES expert_scorecards(id) ON DELETE SET NULL,
  review_date TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('keep', 'warn', 'probation', 'retire', 'hire_replacement')),
  previous_lifecycle_state TEXT,
  new_lifecycle_state TEXT,
  rationale TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expert_lessons (
  id INTEGER PRIMARY KEY,
  expert_id INTEGER REFERENCES experts(id) ON DELETE SET NULL,
  review_id INTEGER REFERENCES expert_reviews(id) ON DELETE SET NULL,
  lesson_date TEXT NOT NULL,
  lesson_type TEXT NOT NULL CHECK (lesson_type IN ('failure', 'success', 'hiring')),
  summary TEXT NOT NULL,
  overweighted_signals TEXT NOT NULL,
  ignored_signals TEXT NOT NULL,
  failed_controls TEXT NOT NULL,
  avoid_hiring_patterns TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jarvis_daily_briefs (
  id INTEGER PRIMARY KEY,
  brief_date TEXT NOT NULL,
  version TEXT NOT NULL DEFAULT 'jarvis_v1',
  focus_directions_json TEXT NOT NULL,
  one_line_stance TEXT NOT NULL,
  model_summary_json TEXT NOT NULL,
  expert_summary_json TEXT NOT NULL,
  combined_recommendation TEXT NOT NULL,
  risk_warnings TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  missing_evidence_json TEXT NOT NULL DEFAULT '[]',
  stale_evidence_json TEXT NOT NULL DEFAULT '[]',
  source TEXT NOT NULL DEFAULT 'system',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (brief_date, version)
);

CREATE TABLE IF NOT EXISTS communication_recipients (
  id INTEGER PRIMARY KEY,
  recipient_key TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  channel TEXT NOT NULL,
  address TEXT NOT NULL,
  allowlisted INTEGER NOT NULL DEFAULT 0 CHECK (allowlisted IN (0, 1)),
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
  min_severity TEXT NOT NULL DEFAULT 'info' CHECK (min_severity IN ('info', 'warning', 'critical')),
  quiet_hours_start TEXT,
  quiet_hours_end TEXT,
  rate_limit_per_hour INTEGER NOT NULL DEFAULT 6 CHECK (rate_limit_per_hour >= 0),
  retry_limit INTEGER NOT NULL DEFAULT 2 CHECK (retry_limit >= 0),
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS communication_adapter_configs (
  id INTEGER PRIMARY KEY,
  channel TEXT NOT NULL UNIQUE,
  enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  dry_run_default INTEGER NOT NULL DEFAULT 1 CHECK (dry_run_default IN (0, 1)),
  config_json TEXT NOT NULL DEFAULT '{}',
  setup_status TEXT NOT NULL DEFAULT 'unverified',
  last_verified_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outbound_messages (
  id INTEGER PRIMARY KEY,
  channel TEXT NOT NULL,
  recipient_id INTEGER REFERENCES communication_recipients(id) ON DELETE SET NULL,
  recipient_key TEXT NOT NULL,
  template_key TEXT NOT NULL,
  subject TEXT,
  body TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical')),
  payload_summary TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'skipped', 'dry_run', 'failed', 'permission_required', 'recipient_not_allowed', 'rate_limited')),
  adapter_result_json TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  requested_at TEXT NOT NULL DEFAULT (datetime('now')),
  sent_at TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_price_daily_asset_date ON price_daily(asset_id, trade_date);
CREATE INDEX IF NOT EXISTS idx_fund_holdings_fund_period ON fund_holdings(fund_asset_id, report_period DESC);
CREATE INDEX IF NOT EXISTS idx_fund_holdings_holding_code ON fund_holdings(holding_type, holding_code);
CREATE INDEX IF NOT EXISTS idx_features_daily_asset_date ON features_daily(asset_id, feature_date);
CREATE INDEX IF NOT EXISTS idx_model_predictions_date ON model_predictions(prediction_date, horizon_days);
CREATE INDEX IF NOT EXISTS idx_model_prediction_reliability_prediction ON model_prediction_reliability(prediction_id);
CREATE INDEX IF NOT EXISTS idx_model_health_metrics_run ON model_health_metrics(replay_run_id, model_version, horizon_days, status);
CREATE INDEX IF NOT EXISTS idx_model_applicability_profiles_run ON model_applicability_profiles(replay_run_id, model_version, horizon_days, output_role);
CREATE INDEX IF NOT EXISTS idx_model_shadow_routes_run ON model_shadow_routes(replay_run_id, route_name, horizon_days, status);
CREATE INDEX IF NOT EXISTS idx_model_governance_reviews_run ON model_governance_reviews(replay_run_id, review_month, status);
CREATE INDEX IF NOT EXISTS idx_daily_advice_date ON daily_advice(advice_date);
CREATE INDEX IF NOT EXISTS idx_task_logs_name_date ON task_logs(task_name, run_date);
CREATE INDEX IF NOT EXISTS idx_agent_runs_role_date ON agent_runs(role_type, role_key, run_date DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status_date ON agent_runs(status, run_date DESC);
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_run ON agent_tool_calls(agent_run_id, called_at DESC);
CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_next_run ON scheduler_jobs(enabled, next_run_at);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_job_started ON scheduler_runs(job_key, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scheduler_watermarks_job ON scheduler_watermarks(job_key, provider_key, source_key, scope_key);
CREATE INDEX IF NOT EXISTS idx_experts_lifecycle ON experts(lifecycle_state, expert_key);
CREATE INDEX IF NOT EXISTS idx_virtual_transactions_portfolio_date ON virtual_transactions(portfolio_id, trade_date);
CREATE INDEX IF NOT EXISTS idx_virtual_valuations_portfolio_date ON virtual_valuations(portfolio_id, valuation_date);
CREATE INDEX IF NOT EXISTS idx_ai_analysis_records_date ON ai_analysis_records(analysis_type, analysis_date, analysis_key);
CREATE INDEX IF NOT EXISTS idx_ai_analysis_records_expert ON ai_analysis_records(expert_id, analysis_date);
CREATE INDEX IF NOT EXISTS idx_expert_plans_date ON expert_plans(plan_date, expert_id);
CREATE INDEX IF NOT EXISTS idx_expert_scorecards_date ON expert_scorecards(score_date, expert_id);
CREATE INDEX IF NOT EXISTS idx_expert_reviews_date ON expert_reviews(review_date, expert_id);
CREATE INDEX IF NOT EXISTS idx_model_calibration_reports_date ON model_calibration_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_model_monitoring_reports_date ON model_monitoring_reports(report_date DESC, model_version);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_date ON market_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_macro_observations_series_date ON macro_observations(series_id, observation_date);
CREATE INDEX IF NOT EXISTS idx_capital_flow_scope_date ON capital_flow_observations(scope, flow_date DESC);
CREATE INDEX IF NOT EXISTS idx_capital_flow_asset_date ON capital_flow_observations(asset_id, flow_date DESC);
CREATE INDEX IF NOT EXISTS idx_news_items_source_time ON news_items(source, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_items_hash ON news_items(content_hash);
CREATE INDEX IF NOT EXISTS idx_news_item_links_asset ON news_item_links(asset_id, news_item_id);
CREATE INDEX IF NOT EXISTS idx_news_item_links_theme ON news_item_links(theme_key, news_item_id);
CREATE INDEX IF NOT EXISTS idx_news_item_tags_value ON news_item_tags(tag_type, tag_value, news_item_id);
CREATE INDEX IF NOT EXISTS idx_news_feature_daily_scope ON news_feature_daily(scope_type, scope_key, feature_date);
CREATE INDEX IF NOT EXISTS idx_data_quality_reports_date ON data_quality_reports(report_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_preferences_active ON user_preferences(is_active) WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS idx_advice_outcome_scores_advice ON advice_outcome_scores(advice_id);
CREATE INDEX IF NOT EXISTS idx_jarvis_daily_briefs_date ON jarvis_daily_briefs(brief_date DESC, version);
CREATE INDEX IF NOT EXISTS idx_communication_recipients_channel ON communication_recipients(channel, allowlisted, enabled);
CREATE INDEX IF NOT EXISTS idx_outbound_messages_recipient_date ON outbound_messages(recipient_key, requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbound_messages_status ON outbound_messages(status, requested_at DESC);
