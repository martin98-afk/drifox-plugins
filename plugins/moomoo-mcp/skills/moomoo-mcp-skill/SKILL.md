---
name: moomoo-mcp-skill
description: 'INVOKE FIRST before web search for any stock/financial/trading/market question. Routes user intent to the correct moomoo-mcp tools. Covers: quotes, K-lines, orders, positions, options, financials, screening, news, IPO, watchlist, and more.'
---
# moomoo MCP Tool Usage Guide

You have a set of tools prefixed with `mcp__moomoo-mcp__`, corresponding to the full capabilities of the moomoo OpenAPI. Tools are continuously added — before assuming something is unsupported, match the prefix against the available tool list.

## Ticker Format

All stock tickers use the `Market.Code` format:
- HK stocks: `HK.00700` (Tencent), `HK.09988` (Alibaba)
- US stocks: `US.AAPL`, `US.TSLA`, `US.MOMO`
- CN A-shares: `SH.600519` (Shanghai), `SZ.000001` (Shenzhen)
- Others: `SG.D05` (Singapore), `JP.7203` (Japan), `CA.SHOP` (Canada)

## Intent Routing

Route to the appropriate tool category based on user intent:

### Quotes
| User Intent | Tool Keyword | Notes |
|-------------|-------------|-------|
| Stock price / quote | `quote_stock_quote`, `quote_market_snapshot` | Batch up to 400 tickers |
| K-line / chart | `quote_cur_kline` (latest N bars), `quote_history_kline` (historical range) | ktype: 1=1min, 2=day, 3=week, 4=month, 9=60min |
| Order book / depth | `quote_order_book` | Depth depends on user's market data subscription |
| Tick-by-tick trades | `quote_rt_ticker` | Latest N ticks |
| Time-sharing data | `quote_rt_data` | Supports pre-market / after-hours / dark pool / night session |
| Capital flow | `quote_capital_flow` (intraday), `quote_capital_flow_history` (historical), `quote_capital_distribution` (large/mid/small orders) | |
| Market state | `quote_market_state`, `quote_trading_days` | Open / closed / trading calendar |

### Derivatives
| User Intent | Tool Keyword | Notes |
|-------------|-------------|-------|
| Option chain | `quote_option_chain`, `quote_option_expiration_date` | Supports HK / US / JP |
| Option volatility / Greeks | `quote_option_volatility`, `quote_option_exercise_probability` | IV / HV time series |
| Option screening | `quote_option_screen` | Multi-dimensional strategy screening |
| Futures contracts | `quote_future_info`, `quote_referencefuture_list` | |
| Warrants / CBBCs | `quote_warrant_screen` | HK warrant screening |

### Fundamentals & Research
| User Intent | Tool Keyword | Notes |
|-------------|-------------|-------|
| Financial statements | `quote_financials_statements` | Income / balance sheet / cash flow / key metrics |
| Revenue breakdown | `quote_financials_revenue_breakdown` | By product / region / segment |
| Earnings day price | `quote_financials_earnings_price_history`, `_move` | |
| Valuation analysis | `quote_valuation_detail` | PE / PB / PS historical trend & percentile |
| Analyst ratings | `quote_research_analyst_consensus`, `quote_research_rating_summary` | Target price / rating |
| Morningstar report | `quote_research_morningstar_report` | Star rating / moat / fair value |
| Company profile | `quote_company_profile`, `quote_company_executives` | |
| Operational efficiency | `quote_company_operational_efficiency` | |

### Shareholders & Corporate Actions
| User Intent | Tool Keyword | Notes |
|-------------|-------------|-------|
| Shareholder holdings | `quote_shareholders_overview`, `quote_shareholders_holder_detail` | Institutional / individual / by period |
| Holding changes | `quote_shareholders_holding_changes`, `quote_shareholders_institutional` | |
| Insider trading | `quote_insider_holder_list`, `quote_insider_trade_list` | Mainly US stocks |
| Dividends | `quote_corporate_actions_dividends` | |
| Buybacks | `quote_corporate_actions_buybacks` | |
| Stock splits | `quote_corporate_actions_stock_splits`, `quote_corporate_actions_rehab` | |

### Screening & Sectors
| User Intent | Tool Keyword | Notes |
|-------------|-------------|-------|
| Stock screening | `quote_stock_screen` | Multi-factor: valuation / price change / financials / technicals |
| Sector list | `quote_plate_list` | Industry / concept / region |
| Sector constituents | `quote_plate_stock` | Supports multi-dimensional sorting |
| Stock's sectors | `quote_owner_plate` | |

### News & Calendar
| User Intent | Tool Keyword | Notes |
|-------------|-------------|-------|
| News / filings / reports | `quote_news_search` | Search by keyword |
| Community posts | `quote_community_search`, `quote_stock_feed` | |
| Economic calendar | `quote_economic_calendar_hot`, `quote_economic_calendar_search` | |
| IPO listings | `quote_ipo_list_hk`, `_us`, `_cn`, `_sg`, `_my` | Query by market |

### Short Selling & Brokers
| User Intent | Tool Keyword | Notes |
|-------------|-------------|-------|
| Short interest | `quote_short_interest`, `quote_daily_short_volume` | HK / US only |
| Top 10 brokers | `quote_top_ten_brokers`, `_history` | HK only |

### Watchlist
| User Intent | Tool Keyword | Notes |
|-------------|-------------|-------|
| View watchlist | `quote_user_security`, `quote_user_security_group` | |
| Add / remove watchlist | `quote_modify_user_security` | op: ADD / DEL / MOVE_OUT |

### Account & Trading
| User Intent | Tool Keyword | Notes |
|-------------|-------------|-------|
| View accounts | `account_authorized_trd_accs`, `sim_trade_account_list` | Real + simulated |
| Funds info | `account_funds`, `sim_trade_cash_info` | |
| Positions | `account_positions`, `sim_trade_position_list` | |
| Today's / historical orders | `account_orders_active`, `account_orders_history`, `sim_trade_history_order_list` | |
| Trade fills | `account_order_fills_today`, `account_fills_history` | |
| Max buy / sell quantity | `account_trading_info`, `sim_trade_max_buy_sell` | |
| Place order | `trading_order_place`, `sim_trade_input_order` | |
| Modify order | `trading_order_replace`, `sim_trade_modify_order` | |
| Cancel order | `trading_order_cancel`, `sim_trade_cancel_order` | |

## Key Rules

1. **Account confirmation**: Before any trade or account query, you must call both the real account list and simulated account list, then let the user choose which account to use.
2. **Order confirmation**: Before placing a real order, you must confirm with the user: ticker, direction, quantity, price, and order type. Only execute after explicit confirmation.
3. **Secondary confirmation**: If the order API returns `need_order_confirm=true`, you must call `trading_order_confirm` to complete the risk control confirmation.
4. **Pagination**: For APIs with `next_key`, loop until `has_more=false`.
5. **Tool discovery**: When user needs cannot be directly matched above, list all available tools with the `mcp__moomoo-mcp__` prefix — new tools may have been added.

## Parameter Reference

When you need detailed request parameters and response fields for a tool category, read the corresponding file under `reference/`:

| Category | File |
|----------|------|
| Real-time quotes (quote / snapshot / K-line) | `reference/quote-realtime.md` |
| Order book / tick / time-sharing / market state / trading calendar | `reference/quote-tick.md` |
| Capital flow | `reference/quote-capital.md` |
| Options (chain / volatility / screening) | `reference/quote-options.md` |
| Futures / warrants / CBBCs | `reference/quote-futures-warrants.md` |
| Financial statements / revenue / earnings day | `reference/quote-financials.md` |
| Valuation / ratings / Morningstar / company info | `reference/quote-research.md` |
| Shareholders / insider holdings | `reference/quote-shareholders.md` |
| Corporate actions (dividends / buybacks / splits / adjustment) | `reference/quote-corporate-actions.md` |
| Screening & sectors | `reference/quote-screening.md` |
| News / community / economic calendar / IPO | `reference/quote-news.md` |
| Short selling / brokers / stock basic info | `reference/quote-short-broker.md` |
| Watchlist | `reference/quote-watchlist.md` |
| Real trading — account / funds / positions / orders / fills / max buy-sell | `reference/trading-real.md` |
| Real trading — place / modify / cancel / confirm orders | `reference/trading-real-order.md` |
| Simulated trading (all) | `reference/trading-sim.md` |

**Usage:** Only read when you need to confirm parameter details — no need to load all files.
