"""
财报侦察官 - 核心评分引擎
所有指标计算和评分逻辑由代码完成，不依赖LLM。
"""

import json
from pathlib import Path
from typing import Any


def load_financial_data(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 衍生指标计算
# ---------------------------------------------------------------------------

def calc_roe(net_profit_parent: float, equity_begin: float, equity_end: float,
             method: str = "weighted_avg") -> float:
    """
    计算ROE。
    method="endpoint": 归母净利润 / 期末归母权益
    method="weighted_avg": 归母净利润 / ((期初+期末)归母权益 / 2)
    """
    if method == "endpoint":
        return net_profit_parent / equity_end if equity_end else 0
    else:
        avg_equity = (equity_begin + equity_end) / 2
        return net_profit_parent / avg_equity if avg_equity else 0


def calc_gross_margin(revenue: float, cost: float) -> float:
    """毛利率 = (营业收入 - 营业成本) / 营业收入"""
    return (revenue - cost) / revenue if revenue else 0


def calc_period_expense_ratio(selling: float, admin: float, rd: float,
                               finance: float, revenue: float) -> float:
    """期间费用率(四费) = (销售+管理+研发+财务费用) / 营业收入"""
    return (selling + admin + rd + finance) / revenue if revenue else 0


def calc_debt_ratio(total_liabilities: float, total_assets: float) -> float:
    """资产负债率 = 负债合计 / 资产总计"""
    return total_liabilities / total_assets if total_assets else 0


def calc_interest_coverage(profit_before_tax: float, interest_expense: float) -> float:
    """利息保障倍数 = 息税前利润 / 利息费用 = (利润总额 + 利息费用) / 利息费用"""
    ebit = profit_before_tax + interest_expense
    return ebit / interest_expense if interest_expense else float('inf')


def calc_current_ratio(current_assets: float, current_liabilities: float) -> float:
    """流动比率 = 流动资产合计 / 流动负债合计"""
    return current_assets / current_liabilities if current_liabilities else 0


def calc_cash_to_short_debt(cash: float, short_borrowing: float,
                             current_non_current: float,
                             notes_payable: float = 0,
                             trading_liabilities: float = 0,
                             scope: str = "narrow") -> float:
    """
    货币资金与短期有息负债比。
    narrow: 短期借款 + 一年内到期的非流动负债
    wide: 上述 + 应付票据 + 交易性金融负债
    """
    if scope == "narrow":
        debt = short_borrowing + current_non_current
    else:
        debt = short_borrowing + current_non_current + notes_payable + trading_liabilities
    return cash / debt if debt else float('inf')


def calc_ocf_to_net_profit(ocf: float, net_profit: float) -> float:
    """经营现金流与净利润比 = 经营活动现金流量净额 / 净利润"""
    return ocf / net_profit if net_profit else 0


def calc_fcf_ratio(ocf: float, capex: float, revenue: float) -> float:
    """自由现金流率 = (经营现金流净额 - 资本性支出) / 营业收入"""
    fcf = ocf - capex
    return fcf / revenue if revenue else 0


def calc_yoy_growth(current: float, prior: float) -> float:
    """同比增速 = (本期 - 上期) / |上期|"""
    return (current - prior) / abs(prior) if prior else 0


# ---------------------------------------------------------------------------
# 评分规则
# ---------------------------------------------------------------------------

def score_roe(roe: float) -> tuple[int, str]:
    pct = f"{roe*100:.2f}%"
    if roe >= 0.20:
        return 10, f"ROE={pct}，≥20%，满分10分"
    elif roe >= 0.15:
        return 8, f"ROE={pct}，落入区间15%-20%，得8分"
    elif roe >= 0.10:
        return 5, f"ROE={pct}，落入区间10%-15%，得5分"
    elif roe >= 0.05:
        return 2, f"ROE={pct}，落入区间5%-10%，得2分"
    else:
        return 0, f"ROE={pct}，<5%，得0分"


def score_gross_margin(gm: float) -> tuple[int, str]:
    pct = f"{gm*100:.2f}%"
    if gm >= 0.40:
        return 8, f"毛利率={pct}，≥40%，满分8分"
    elif gm >= 0.25:
        return 6, f"毛利率={pct}，落入区间25%-40%，得6分"
    elif gm >= 0.15:
        return 3, f"毛利率={pct}，落入区间15%-25%，得3分"
    else:
        return 0, f"毛利率={pct}，<15%，得0分"


def score_gross_margin_change(abs_change: float) -> tuple[int, str]:
    pct = f"{abs_change*100:.2f}%"
    if abs_change <= 0.05:
        return 6, f"毛利率变化绝对值={pct}，≤5%，满分6分"
    elif abs_change <= 0.10:
        return 3, f"毛利率变化绝对值={pct}，落入区间5%-10%，得3分"
    else:
        return 0, f"毛利率变化绝对值={pct}，>10%，得0分"


def score_expense_trend(current_ratio: float, prior_ratio: float) -> tuple[int, str]:
    cur_pct = f"{current_ratio*100:.2f}%"
    pri_pct = f"{prior_ratio*100:.2f}%"
    if current_ratio < prior_ratio:
        return 6, f"期间费用率从{pri_pct}降至{cur_pct}，趋势下降，满分6分"
    elif current_ratio == prior_ratio:
        return 3, f"期间费用率{cur_pct}与上期持平，得3分"
    else:
        return 0, f"期间费用率从{pri_pct}升至{cur_pct}，趋势上升，得0分"


def score_debt_ratio(dr: float) -> tuple[int, str]:
    pct = f"{dr*100:.2f}%"
    if dr < 0.40:
        return 8, f"资产负债率={pct}，<40%，满分8分"
    elif dr <= 0.60:
        return 5, f"资产负债率={pct}，落入区间40%-60%，得5分"
    elif dr <= 0.75:
        return 2, f"资产负债率={pct}，落入区间60%-75%，得2分"
    else:
        return 0, f"资产负债率={pct}，>75%，得0分"


def score_interest_coverage(ic: float) -> tuple[int, str]:
    val = f"{ic:.2f}" if ic != float('inf') else "∞"
    if ic >= 8:
        return 7, f"利息保障倍数={val}，≥8，满分7分"
    elif ic >= 4:
        return 4, f"利息保障倍数={val}，落入区间4-8，得4分"
    elif ic >= 1.5:
        return 2, f"利息保障倍数={val}，落入区间1.5-4，得2分"
    else:
        return 0, f"利息保障倍数={val}，<1.5，得0分"


def score_current_ratio(cr: float) -> tuple[int, str]:
    val = f"{cr:.4f}"
    if cr >= 1.5:
        return 5, f"流动比率={val}，≥1.5，满分5分"
    elif cr >= 1.0:
        return 3, f"流动比率={val}，落入区间1.0-1.5，得3分"
    else:
        return 0, f"流动比率={val}，<1.0，得0分"


def score_cash_to_short_debt(ratio: float) -> tuple[int, str]:
    val = f"{ratio:.4f}" if ratio != float('inf') else "∞"
    if ratio >= 1.2:
        return 5, f"货币资金/短期有息负债={val}，≥1.2，满分5分"
    elif ratio >= 0.8:
        return 3, f"货币资金/短期有息负债={val}，落入区间0.8-1.2，得3分"
    else:
        return 0, f"货币资金/短期有息负债={val}，<0.8，得0分"


def score_ocf_to_profit(ratio: float) -> tuple[int, str]:
    val = f"{ratio:.4f}"
    if ratio >= 1.0:
        return 10, f"经营现金流/净利润={val}，≥1.0，满分10分"
    elif ratio >= 0.8:
        return 6, f"经营现金流/净利润={val}，落入区间0.8-1.0，得6分"
    elif ratio >= 0.6:
        return 3, f"经营现金流/净利润={val}，落入区间0.6-0.8，得3分"
    else:
        return 0, f"经营现金流/净利润={val}，<0.6，得0分"


def score_fcf_ratio(ratio: float) -> tuple[int, str]:
    pct = f"{ratio*100:.2f}%"
    if ratio >= 0.10:
        return 6, f"自由现金流率={pct}，≥10%，满分6分"
    elif ratio >= 0.05:
        return 3, f"自由现金流率={pct}，落入区间5%-10%，得3分"
    else:
        return 0, f"自由现金流率={pct}，<5%，得0分"


def score_ar_vs_revenue_growth(diff: float) -> tuple[int, str]:
    pct = f"{diff*100:.2f}%"
    if diff <= 0:
        return 5, f"应收增速-营收增速={pct}，≤0，满分5分"
    elif diff <= 0.10:
        return 3, f"应收增速-营收增速={pct}，落入区间0-10%，得3分"
    elif diff <= 0.20:
        return 1, f"应收增速-营收增速={pct}，落入区间10%-20%，得1分"
    else:
        return 0, f"应收增速-营收增速={pct}，>20%，得0分"


def score_inventory_vs_revenue_growth(diff: float) -> tuple[int, str]:
    pct = f"{diff*100:.2f}%"
    if diff <= 0:
        return 4, f"存货增速-营收增速={pct}，≤0，满分4分"
    elif diff <= 0.10:
        return 2, f"存货增速-营收增速={pct}，落入区间0-10%，得2分"
    else:
        return 0, f"存货增速-营收增速={pct}，>10%，得0分"


def score_revenue_growth(growth: float) -> tuple[int, str]:
    pct = f"{growth*100:.2f}%"
    if growth >= 0.15:
        return 7, f"营收增速={pct}，≥15%，满分7分"
    elif growth >= 0.08:
        return 4, f"营收增速={pct}，落入区间8%-15%，得4分"
    elif growth >= 0:
        return 2, f"营收增速={pct}，落入区间0-8%，得2分"
    else:
        return 0, f"营收增速={pct}，<0，得0分"


def score_profit_growth(growth: float) -> tuple[int, str]:
    pct = f"{growth*100:.2f}%"
    if growth >= 0.15:
        return 7, f"净利润增速={pct}，≥15%，满分7分"
    elif growth >= 0.08:
        return 4, f"净利润增速={pct}，落入区间8%-15%，得4分"
    elif growth >= 0:
        return 2, f"净利润增速={pct}，落入区间0-8%，得2分"
    else:
        return 0, f"净利润增速={pct}，<0，得0分"


def score_double_growth(rev_growth: float, profit_growth: float) -> tuple[int, str]:
    rev_ok = rev_growth > 0
    prof_ok = profit_growth > 0
    if rev_ok and prof_ok:
        return 3, f"营收增速{rev_growth*100:.2f}%>0且净利润增速{profit_growth*100:.2f}%>0，双增达标，得3分"
    else:
        parts = []
        if not rev_ok:
            parts.append(f"营收增速{rev_growth*100:.2f}%≤0")
        if not prof_ok:
            parts.append(f"净利润增速{profit_growth*100:.2f}%≤0")
        return 0, f"{'，'.join(parts)}，双增不达标，得0分"


def score_roe_trend(roe_current: float, roe_prior: float) -> tuple[int, str]:
    cur_pct = f"{roe_current*100:.2f}%"
    pri_pct = f"{roe_prior*100:.2f}%"
    if roe_current > roe_prior:
        return 3, f"ROE从{pri_pct}升至{cur_pct}，趋势上升，满分3分"
    elif roe_current == roe_prior:
        return 1, f"ROE维持{cur_pct}不变，趋势平稳，得1分"
    else:
        return 0, f"ROE从{pri_pct}降至{cur_pct}，趋势下降，得0分"


# ---------------------------------------------------------------------------
# 红线规则
# ---------------------------------------------------------------------------

def apply_red_lines(total_score: int,
                    audit_opinion_clean: bool,
                    net_profit_current: float, net_profit_prior: float,
                    ocf_current: float, ocf_prior: float,
                    debt_ratio: float, interest_coverage: float) -> tuple[int, list[dict]]:
    """
    应用红线规则，返回 (调整后总分, 红线检查详情列表)。
    每条红线包含：rule, triggered, values, cap, explanation。
    不论是否触发都返回，方便用户了解离红线的距离。
    """
    def _fmt_pct(v: float) -> str:
        return f"{v*100:.2f}%"

    def _fmt_val(v: float) -> str:
        return f"{v/1e8:.2f}亿" if abs(v) >= 1e6 else f"{v:.2f}"

    checks = []

    # 1. 审计意见非标准无保留
    checks.append({
        "rule": "审计意见非标准无保留",
        "triggered": not audit_opinion_clean,
        "values": {"审计意见是否标准无保留": audit_opinion_clean},
        "cap": 59,
        "explanation": "审计意见非标准无保留 → 总分上限59分" if not audit_opinion_clean
                       else "审计意见为标准无保留，未触发红线"
    })

    # 2. 连续两年净利润为正且经营现金流为负
    cash_red = (net_profit_current > 0 and net_profit_prior > 0
                and ocf_current < 0 and ocf_prior < 0)
    checks.append({
        "rule": "连续两年净利润为正且经营现金流为负",
        "triggered": cash_red,
        "values": {
            "本期净利润": _fmt_val(net_profit_current),
            "上期净利润": _fmt_val(net_profit_prior),
            "本期经营现金流": _fmt_val(ocf_current),
            "上期经营现金流": _fmt_val(ocf_prior),
        },
        "cap": 54,
        "explanation": (
            f"本期净利润={_fmt_val(net_profit_current)}(>0)，上期净利润={_fmt_val(net_profit_prior)}(>0)，"
            f"本期经营现金流={_fmt_val(ocf_current)}{'(<0)' if ocf_current < 0 else '(≥0)'}，"
            f"上期经营现金流={_fmt_val(ocf_prior)}{'(<0)' if ocf_prior < 0 else '(≥0)'}，"
            + ("四项条件均满足，触发红线 → 总分上限54分" if cash_red else "条件未全部满足，未触发红线")
        )
    })

    # 3. 资产负债率>75%且利息保障倍数<1.5
    debt_red = debt_ratio > 0.75 and interest_coverage < 1.5
    ic_display = f"{interest_coverage:.2f}" if interest_coverage != float('inf') else "∞"
    checks.append({
        "rule": "资产负债率>75%且利息保障倍数<1.5",
        "triggered": debt_red,
        "values": {
            "资产负债率": _fmt_pct(debt_ratio),
            "利息保障倍数": ic_display,
        },
        "cap": 49,
        "explanation": (
            f"资产负债率={_fmt_pct(debt_ratio)}{'(>75%)' if debt_ratio > 0.75 else '(≤75%)'}，"
            f"利息保障倍数={ic_display}{'(<1.5)' if interest_coverage < 1.5 else '(≥1.5)'}，"
            + ("两项条件均满足，触发红线 → 总分上限49分" if debt_red else "条件未全部满足，未触发红线")
        )
    })

    # 取最严格的上限
    caps = [c["cap"] for c in checks if c["triggered"]]
    if caps:
        total_score = min(total_score, min(caps))

    return total_score, checks


def get_rating(score: int) -> str:
    if score >= 85:
        return "A级（高质量低风险）"
    elif score >= 70:
        return "B级（质量尚可可跟踪）"
    elif score >= 55:
        return "C级（中性需重点核验）"
    elif score >= 40:
        return "D级（高风险）"
    else:
        return "E级（回避）"


# ---------------------------------------------------------------------------
# 主评分函数
# ---------------------------------------------------------------------------

def run_scoring(data: dict,
                roe_method: str = "weighted_avg",
                debt_scope: str = "narrow",
                audit_opinion_clean: bool = True) -> dict[str, Any]:
    """
    执行完整评分流程。
    返回包含所有指标、得分、红线、评级的字典。
    """
    cur = data["current_period"]
    pri = data["prior_period"]
    cb = cur["balance_sheet"]
    ci = cur["income_statement"]
    cc = cur["cash_flow"]
    pb = pri["balance_sheet"]
    pi = pri["income_statement"]
    pc = pri["cash_flow"]

    # --- 计算衍生指标 ---

    # ROE (两种口径都算)
    roe_endpoint = calc_roe(ci["归属于母公司股东的净利润"],
                            pb["归属于母公司所有者权益合计"],
                            cb["归属于母公司所有者权益合计"],
                            method="endpoint")
    roe_weighted = calc_roe(ci["归属于母公司股东的净利润"],
                            pb["归属于母公司所有者权益合计"],
                            cb["归属于母公司所有者权益合计"],
                            method="weighted_avg")
    roe_selected = roe_weighted if roe_method == "weighted_avg" else roe_endpoint

    # 上期ROE (用于趋势判断，与当期保持同一口径)
    # 上期ROE的期初权益无法从数据中获取，使用期末口径作为上期ROE近似
    roe_prior = calc_roe(pi["归属于母公司股东的净利润"],
                         pb["归属于母公司所有者权益合计"],
                         pb["归属于母公司所有者权益合计"],
                         method="endpoint")

    # 毛利率
    gm_current = calc_gross_margin(ci["营业收入"], ci["营业成本"])
    gm_prior = calc_gross_margin(pi["营业收入"], pi["营业成本"])
    gm_change = abs(gm_current - gm_prior)

    # 期间费用率 (四费)
    expr_current = calc_period_expense_ratio(
        ci["销售费用"], ci["管理费用"], ci["研发费用"], ci["财务费用"], ci["营业收入"])
    expr_prior = calc_period_expense_ratio(
        pi["销售费用"], pi["管理费用"], pi["研发费用"], pi["财务费用"], pi["营业收入"])

    # 资产负债率
    debt_ratio = calc_debt_ratio(cb["负债合计"], cb["资产总计"])

    # 利息保障倍数
    interest_coverage = calc_interest_coverage(ci["利润总额"], ci["其中_利息费用"])

    # 流动比率
    current_ratio = calc_current_ratio(cb["流动资产合计"], cb["流动负债合计"])

    # 货币资金/短期有息负债 (两种口径都算)
    cash_debt_narrow = calc_cash_to_short_debt(
        cb["货币资金"], cb["短期借款"], cb["一年内到期的非流动负债"],
        scope="narrow")
    cash_debt_wide = calc_cash_to_short_debt(
        cb["货币资金"], cb["短期借款"], cb["一年内到期的非流动负债"],
        cb["应付票据"], cb["交易性金融负债"],
        scope="wide")
    cash_debt_selected = cash_debt_narrow if debt_scope == "narrow" else cash_debt_wide

    # 经营现金流/净利润
    ocf_profit = calc_ocf_to_net_profit(cc["经营活动产生的现金流量净额"], ci["净利润"])

    # 自由现金流率
    fcf_ratio = calc_fcf_ratio(
        cc["经营活动产生的现金流量净额"],
        cc["购建固定资产_无形资产和其他长期资产支付的现金"],
        ci["营业收入"])

    # 增速
    rev_growth = calc_yoy_growth(ci["营业收入"], pi["营业收入"])
    profit_growth = calc_yoy_growth(ci["归属于母公司股东的净利润"], pi["归属于母公司股东的净利润"])
    ar_growth = calc_yoy_growth(cb["应收账款"], pb["应收账款"])
    inv_growth = calc_yoy_growth(cb["存货"], pb["存货"])

    ar_minus_rev = ar_growth - rev_growth
    inv_minus_rev = inv_growth - rev_growth

    # --- 辅助函数：格式化金额 ---
    def fmt(v: float) -> str:
        """将金额格式化为亿元"""
        return f"{v / 1e8:.2f}亿"

    def pct(v: float) -> str:
        """将比率格式化为百分比"""
        return f"{v * 100:.2f}%"

    # --- 逐项评分 ---
    scores = {}

    # 一、商业质量 (30分)
    _eq_begin = pb["归属于母公司所有者权益合计"]
    _eq_end = cb["归属于母公司所有者权益合计"]
    _eq_avg = (_eq_begin + _eq_end) / 2
    _np_parent = ci["归属于母公司股东的净利润"]

    _roe_score, _roe_rule = score_roe(roe_selected)
    scores["ROE当期值"] = {
        "value": roe_selected,
        "value_endpoint": roe_endpoint,
        "value_weighted": roe_weighted,
        "method": roe_method,
        "score": _roe_score,
        "matched_rule": _roe_rule,
        "max": 10,
        "category": "商业质量",
        "description": "净资产收益率，衡量股东投入资本的回报效率。ROE越高说明公司用股东的钱赚钱的能力越强。",
        "formula": "归母净利润 / ((期初+期末)归母权益 / 2)" if roe_method == "weighted_avg" else "归母净利润 / 期末归母权益",
        "detail": f"归母净利润 = {fmt(_np_parent)}，期初归母权益 = {fmt(_eq_begin)}，期末归母权益 = {fmt(_eq_end)}"
                  + (f"，平均权益 = {fmt(_eq_avg)}，ROE = {fmt(_np_parent)} / {fmt(_eq_avg)} = {pct(roe_weighted)}" if roe_method == "weighted_avg"
                     else f"，ROE = {fmt(_np_parent)} / {fmt(_eq_end)} = {pct(roe_endpoint)}"),
        "thresholds": "≥20%→10分 | 15%-20%→8分 | 10%-15%→5分 | 5%-10%→2分 | <5%→0分"
    }

    _rev = ci["营业收入"]
    _cost = ci["营业成本"]
    _gm_score, _gm_rule = score_gross_margin(gm_current)
    scores["毛利率当期值"] = {
        "value": gm_current,
        "score": _gm_score,
        "matched_rule": _gm_rule,
        "max": 8,
        "category": "商业质量",
        "description": "毛利率反映公司产品或服务的基础盈利能力，越高说明产品附加值越大或成本控制越好。",
        "formula": "(营业收入 - 营业成本) / 营业收入",
        "detail": f"营业收入 = {fmt(_rev)}，营业成本 = {fmt(_cost)}，毛利 = {fmt(_rev - _cost)}，毛利率 = {pct(gm_current)}",
        "thresholds": "≥40%→8分 | 25%-40%→6分 | 15%-25%→3分 | <15%→0分"
    }

    _rev_p = pi["营业收入"]
    _cost_p = pi["营业成本"]
    _gmc_score, _gmc_rule = score_gross_margin_change(gm_change)
    scores["毛利率同比变化绝对值"] = {
        "value": gm_change,
        "score": _gmc_score,
        "matched_rule": _gmc_rule,
        "max": 6,
        "category": "商业质量",
        "description": "毛利率变化幅度越小说明盈利能力越稳定，波动大可能意味着竞争格局或成本结构发生变化。",
        "formula": "|本期毛利率 - 上期毛利率|",
        "detail": f"本期毛利率 = {pct(gm_current)}，上期毛利率 = {pct(gm_prior)}，变化绝对值 = {pct(gm_change)}",
        "thresholds": "≤5%→6分 | 5%-10%→3分 | >10%→0分"
    }

    _sell = ci["销售费用"]
    _admin = ci["管理费用"]
    _rd = ci["研发费用"]
    _fin = ci["财务费用"]
    _sell_p = pi["销售费用"]
    _admin_p = pi["管理费用"]
    _rd_p = pi["研发费用"]
    _fin_p = pi["财务费用"]
    _exp_score, _exp_rule = score_expense_trend(expr_current, expr_prior)
    scores["期间费用率同比趋势"] = {
        "value_current": expr_current,
        "value_prior": expr_prior,
        "trend": "下降" if expr_current < expr_prior else ("持平" if expr_current == expr_prior else "上升"),
        "score": _exp_score,
        "matched_rule": _exp_rule,
        "max": 6,
        "category": "商业质量",
        "description": "期间费用率反映公司运营管理效率。下降说明每单位收入消耗的费用减少，管理效率提升。",
        "formula": "(销售费用 + 管理费用 + 研发费用 + 财务费用) / 营业收入",
        "detail": f"本期：({fmt(_sell)} + {fmt(_admin)} + {fmt(_rd)} + {fmt(_fin)}) / {fmt(_rev)} = {pct(expr_current)}；"
                  f"上期：({fmt(_sell_p)} + {fmt(_admin_p)} + {fmt(_rd_p)} + {fmt(_fin_p)}) / {fmt(_rev_p)} = {pct(expr_prior)}",
        "thresholds": "下降→6分 | 持平→3分 | 上升→0分"
    }

    # 二、财务安全 (25分)
    _liab = cb["负债合计"]
    _asset = cb["资产总计"]
    _dr_score, _dr_rule = score_debt_ratio(debt_ratio)
    scores["资产负债率当期值"] = {
        "value": debt_ratio,
        "score": _dr_score,
        "matched_rule": _dr_rule,
        "max": 8,
        "category": "财务安全",
        "description": "资产负债率衡量公司对债务融资的依赖程度。过高意味着偿债压力大，财务风险高。",
        "formula": "负债合计 / 资产总计",
        "detail": f"负债合计 = {fmt(_liab)}，资产总计 = {fmt(_asset)}，资产负债率 = {pct(debt_ratio)}",
        "thresholds": "<40%→8分 | 40%-60%→5分 | 60%-75%→2分 | >75%→0分"
    }

    _pbt = ci["利润总额"]
    _int = ci["其中_利息费用"]
    _ebit = _pbt + _int
    _ic_score, _ic_rule = score_interest_coverage(interest_coverage)
    scores["利息保障倍数当期值"] = {
        "value": interest_coverage,
        "score": _ic_score,
        "matched_rule": _ic_rule,
        "max": 7,
        "category": "财务安全",
        "description": "利息保障倍数衡量公司利润覆盖利息支出的能力。倍数越高，偿付利息的安全边际越大。",
        "formula": "息税前利润(EBIT) / 利息费用 = (利润总额 + 利息费用) / 利息费用",
        "detail": f"利润总额 = {fmt(_pbt)}，利息费用 = {fmt(_int)}，EBIT = {fmt(_ebit)}，倍数 = {_ebit / _int:.2f}" if _int else "利息费用为0，倍数为无穷大",
        "thresholds": "≥8→7分 | 4-8→4分 | 1.5-4→2分 | <1.5→0分"
    }

    _ca = cb["流动资产合计"]
    _cl = cb["流动负债合计"]
    _cr_score, _cr_rule = score_current_ratio(current_ratio)
    scores["流动比率当期值"] = {
        "value": current_ratio,
        "score": _cr_score,
        "matched_rule": _cr_rule,
        "max": 5,
        "category": "财务安全",
        "description": "流动比率衡量短期偿债能力，即流动资产能否覆盖流动负债。低于1.0意味着短期可能存在流动性风险。",
        "formula": "流动资产合计 / 流动负债合计",
        "detail": f"流动资产 = {fmt(_ca)}，流动负债 = {fmt(_cl)}，流动比率 = {current_ratio:.4f}",
        "thresholds": "≥1.5→5分 | 1.0-1.5→3分 | <1.0→0分"
    }

    _cash = cb["货币资金"]
    _sb = cb["短期借款"]
    _cnc = cb["一年内到期的非流动负债"]
    _np_ = cb["应付票据"]
    _tl = cb["交易性金融负债"]
    _narrow_debt = _sb + _cnc
    _wide_debt = _narrow_debt + _np_ + _tl
    _cd_score, _cd_rule = score_cash_to_short_debt(cash_debt_selected)
    scores["货币资金与短期有息负债比"] = {
        "value": cash_debt_selected,
        "value_narrow": cash_debt_narrow,
        "value_wide": cash_debt_wide,
        "scope": debt_scope,
        "score": _cd_score,
        "matched_rule": _cd_rule,
        "max": 5,
        "category": "财务安全",
        "description": "衡量手头现金能否覆盖短期有息债务。大于1说明现金足以偿还短期借贷，小于1则存在短期偿债缺口。",
        "formula": "货币资金 / 短期有息负债（窄口径=短期借款+一年内到期非流动负债；宽口径再+应付票据+交易性金融负债）",
        "detail": f"货币资金 = {fmt(_cash)}，窄口径负债 = {fmt(_sb)} + {fmt(_cnc)} = {fmt(_narrow_debt)}，比值 = {cash_debt_narrow:.4f}；"
                  f"宽口径负债 = {fmt(_narrow_debt)} + {fmt(_np_)} + {fmt(_tl)} = {fmt(_wide_debt)}，比值 = {cash_debt_wide:.4f}",
        "thresholds": "≥1.2→5分 | 0.8-1.2→3分 | <0.8→0分"
    }

    # 三、盈利质量与现金含量 (25分)
    _ocf = cc["经营活动产生的现金流量净额"]
    _np_total = ci["净利润"]
    _ocfp_score, _ocfp_rule = score_ocf_to_profit(ocf_profit)
    scores["经营现金流与净利润比"] = {
        "value": ocf_profit,
        "score": _ocfp_score,
        "matched_rule": _ocfp_rule,
        "max": 10,
        "category": "盈利质量与现金含量",
        "description": "衡量利润的含金量。大于1说明每1元利润有超过1元的经营现金流支撑，利润质量高；远低于1则说明利润可能是纸面利润。",
        "formula": "经营活动现金流量净额 / 净利润",
        "detail": f"经营现金流 = {fmt(_ocf)}，净利润 = {fmt(_np_total)}，比值 = {ocf_profit:.4f}",
        "thresholds": "≥1.0→10分 | 0.8-1.0→6分 | 0.6-0.8→3分 | <0.6→0分"
    }

    _capex = cc["购建固定资产_无形资产和其他长期资产支付的现金"]
    _fcf = _ocf - _capex
    _fcf_score, _fcf_rule = score_fcf_ratio(fcf_ratio)
    scores["自由现金流率"] = {
        "value": fcf_ratio,
        "score": _fcf_score,
        "matched_rule": _fcf_rule,
        "max": 6,
        "category": "盈利质量与现金含量",
        "description": "自由现金流是公司维持运营和资本投入后真正可自由支配的现金。自由现金流率越高，说明公司赚到手的钱越多。",
        "formula": "(经营现金流净额 - 资本性支出) / 营业收入",
        "detail": f"经营现金流 = {fmt(_ocf)}，资本性支出 = {fmt(_capex)}，自由现金流 = {fmt(_fcf)}，自由现金流率 = {fmt(_fcf)} / {fmt(_rev)} = {pct(fcf_ratio)}",
        "thresholds": "≥10%→6分 | 5%-10%→3分 | <5%→0分"
    }

    _ar_cur = cb["应收账款"]
    _ar_pri = pb["应收账款"]
    _ar_score, _ar_rule = score_ar_vs_revenue_growth(ar_minus_rev)
    scores["应收增速减营收增速"] = {
        "value": ar_minus_rev,
        "ar_growth": ar_growth,
        "rev_growth": rev_growth,
        "score": _ar_score,
        "matched_rule": _ar_rule,
        "max": 5,
        "category": "盈利质量与现金含量",
        "description": "如果应收账款增速远高于营收增速，可能意味着公司通过放宽信用条件来拉动收入，回款风险增大。",
        "formula": "应收账款同比增速 - 营业收入同比增速",
        "detail": f"应收账款：{fmt(_ar_pri)} → {fmt(_ar_cur)}，增速 = {pct(ar_growth)}；"
                  f"营业收入：{fmt(pi['营业收入'])} → {fmt(_rev)}，增速 = {pct(rev_growth)}；差值 = {pct(ar_minus_rev)}",
        "thresholds": "≤0→5分 | 0-10%→3分 | 10%-20%→1分 | >20%→0分"
    }

    _inv_cur = cb["存货"]
    _inv_pri = pb["存货"]
    _inv_score, _inv_rule = score_inventory_vs_revenue_growth(inv_minus_rev)
    scores["存货增速减营收增速"] = {
        "value": inv_minus_rev,
        "inv_growth": inv_growth,
        "rev_growth": rev_growth,
        "score": _inv_score,
        "matched_rule": _inv_rule,
        "max": 4,
        "category": "盈利质量与现金含量",
        "description": "存货增速大幅超过营收增速，可能意味着产品滞销或库存积压，存在跌价减值风险。",
        "formula": "存货同比增速 - 营业收入同比增速",
        "detail": f"存货：{fmt(_inv_pri)} → {fmt(_inv_cur)}，增速 = {pct(inv_growth)}；"
                  f"营业收入增速 = {pct(rev_growth)}；差值 = {pct(inv_minus_rev)}",
        "thresholds": "≤0→4分 | 0-10%→2分 | >10%→0分"
    }

    # 四、成长质量 (20分)
    _revg_score, _revg_rule = score_revenue_growth(rev_growth)
    scores["营收同比增速"] = {
        "value": rev_growth,
        "score": _revg_score,
        "matched_rule": _revg_rule,
        "max": 7,
        "category": "成长质量",
        "description": "营业收入的同比增长率，反映公司业务规模的扩张速度。",
        "formula": "(本期营业收入 - 上期营业收入) / |上期营业收入|",
        "detail": f"本期 = {fmt(_rev)}，上期 = {fmt(pi['营业收入'])}，增速 = {pct(rev_growth)}",
        "thresholds": "≥15%→7分 | 8%-15%→4分 | 0-8%→2分 | <0→0分"
    }

    _np_cur = ci["归属于母公司股东的净利润"]
    _np_pri = pi["归属于母公司股东的净利润"]
    _pg_score, _pg_rule = score_profit_growth(profit_growth)
    scores["净利润同比增速"] = {
        "value": profit_growth,
        "score": _pg_score,
        "matched_rule": _pg_rule,
        "max": 7,
        "category": "成长质量",
        "description": "归母净利润的同比增长率，反映公司盈利能力的变化趋势。",
        "formula": "(本期归母净利润 - 上期归母净利润) / |上期归母净利润|",
        "detail": f"本期 = {fmt(_np_cur)}，上期 = {fmt(_np_pri)}，增速 = {pct(profit_growth)}",
        "thresholds": "≥15%→7分 | 8%-15%→4分 | 0-8%→2分 | <0→0分"
    }

    _dg_score, _dg_rule = score_double_growth(rev_growth, profit_growth)
    scores["营收与净利润双增"] = {
        "rev_growth": rev_growth,
        "profit_growth": profit_growth,
        "score": _dg_score,
        "matched_rule": _dg_rule,
        "max": 3,
        "category": "成长质量",
        "description": "营收和净利润同时增长说明公司增收又增利，成长质量较高。若增收不增利，可能是成本失控。",
        "formula": "营收增速 > 0 且 净利润增速 > 0",
        "detail": f"营收增速 = {pct(rev_growth)}（{'> 0 ✓' if rev_growth > 0 else '≤ 0 ✗'}），"
                  f"净利润增速 = {pct(profit_growth)}（{'> 0 ✓' if profit_growth > 0 else '≤ 0 ✗'}）",
        "thresholds": "均>0→3分 | 否则→0分"
    }

    _rt_score, _rt_rule = score_roe_trend(roe_selected, roe_prior)
    scores["ROE同比趋势"] = {
        "roe_current": roe_selected,
        "roe_prior": roe_prior,
        "trend": "上升" if roe_selected > roe_prior else ("平稳" if roe_selected == roe_prior else "下降"),
        "score": _rt_score,
        "matched_rule": _rt_rule,
        "max": 3,
        "category": "成长质量",
        "description": "ROE趋势反映股东回报效率的变化方向。持续上升说明公司盈利能力不断增强。",
        "formula": "比较本期ROE与上期ROE",
        "detail": f"本期ROE = {pct(roe_selected)}，上期ROE = {pct(roe_prior)}，趋势 = {'上升' if roe_selected > roe_prior else ('平稳' if roe_selected == roe_prior else '下降')}",
        "thresholds": "上升→3分 | 平稳→1分 | 下降→0分"
    }

    # --- 汇总 ---
    raw_total = sum(item["score"] for item in scores.values())
    max_total = sum(item["max"] for item in scores.values())

    # 红线规则
    final_total, red_lines = apply_red_lines(
        raw_total,
        audit_opinion_clean,
        ci["净利润"], pi["净利润"],
        cc["经营活动产生的现金流量净额"],
        pc["经营活动产生的现金流量净额"],
        debt_ratio,
        interest_coverage
    )

    rating = get_rating(final_total)

    # --- 指标分类：优势 / 风险 / 中性（B部分：规则化网络） ---
    insights = []
    for name, item in scores.items():
        ratio = item["score"] / item["max"] if item["max"] > 0 else 0
        if ratio >= 0.8:
            level = "strength"
        elif ratio <= 0.2:
            level = "risk"
        else:
            level = "neutral"
        insights.append({
            "indicator": name,
            "category": item["category"],
            "level": level,
            "score": item["score"],
            "max": item["max"],
            "value_display": item.get("detail", ""),
        })

    # --- 瀑布图分解 ---
    CATEGORY_ORDER = ["商业质量", "财务安全", "盈利质量与现金含量", "成长质量"]
    CATEGORY_MAX = {"商业质量": 30, "财务安全": 25, "盈利质量与现金含量": 25, "成长质量": 20}
    waterfall = []
    for cat in CATEGORY_ORDER:
        cat_items = [(n, s) for n, s in scores.items() if s["category"] == cat]
        earned = sum(s["score"] for _, s in cat_items)
        cat_max = CATEGORY_MAX[cat]
        waterfall.append({
            "category": cat,
            "earned": earned,
            "max": cat_max,
            "lost": cat_max - earned,
            "pct": round(earned / cat_max * 100) if cat_max else 0,
        })
    red_adjustment = final_total - raw_total
    waterfall.append({
        "label": "红线调整",
        "adjustment": red_adjustment,
    })
    waterfall.append({
        "label": "最终得分",
        "total": final_total,
    })

    return {
        "company": data.get("company", ""),
        "report_year": data.get("report_year", ""),
        "scores": scores,
        "raw_total": raw_total,
        "max_total": max_total,
        "final_total": final_total,
        "red_lines": red_lines,
        "waterfall": waterfall,
        "rating": rating,
        "insights": insights,
        "options": {
            "roe_method": roe_method,
            "debt_scope": debt_scope,
            "audit_opinion_clean": audit_opinion_clean
        }
    }


# ---------------------------------------------------------------------------
# 独立运行测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    data_path = Path(__file__).parent.parent / "data" / "financial_data.json"
    data = load_financial_data(data_path)
    result = run_scoring(data)

    print(f"\n{'='*50}")
    print(f"  {result['company']} {result['report_year']}年 财务评分报告")
    print(f"{'='*50}\n")

    categories = {}
    for name, item in result["scores"].items():
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((name, item))

    for cat, items in categories.items():
        cat_score = sum(i["score"] for _, i in items)
        cat_max = sum(i["max"] for _, i in items)
        print(f"[{cat}] {cat_score}/{cat_max}")
        for name, item in items:
            val = item.get("value", item.get("trend", ""))
            if isinstance(val, float):
                val = f"{val:.4f} ({val*100:.2f}%)"
            print(f"  {name}: {val} -> {item['score']}/{item['max']}")
        print()

    print(f"原始总分: {result['raw_total']}/{result['max_total']}")
    for rl in result["red_lines"]:
        tag = "[触发]" if rl["triggered"] else "[未触发]"
        print(f"  {tag} {rl['explanation']}")
    print(f"最终总分: {result['final_total']}")
    print(f"评级: {result['rating']}")

    print(f"\n--- 瀑布图分解 ---")
    for item in result["waterfall"]:
        if "category" in item:
            print(f"  {item['category']}: {item['earned']}/{item['max']} (得分率{item['pct']}%, 丢失{item['lost']}分)")
        elif "adjustment" in item:
            print(f"  {item['label']}: {item['adjustment']:+d}分")
        else:
            print(f"  {item['label']}: {item['total']}分")
