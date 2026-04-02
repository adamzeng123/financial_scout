"""
核心评分逻辑测试用例。
测试用例1：使用立讯精密真实数据验证完整评分流程。
测试用例2：构造极端数据验证红线规则和边界条件。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scorer import (
    calc_roe, calc_gross_margin, calc_period_expense_ratio,
    calc_debt_ratio, calc_interest_coverage, calc_current_ratio,
    calc_cash_to_short_debt, calc_ocf_to_net_profit, calc_fcf_ratio,
    calc_yoy_growth,
    score_roe, score_gross_margin, score_gross_margin_change,
    score_debt_ratio, score_interest_coverage, score_current_ratio,
    score_cash_to_short_debt, score_ocf_to_profit, score_fcf_ratio,
    score_revenue_growth, score_profit_growth, score_double_growth,
    score_ar_vs_revenue_growth, score_inventory_vs_revenue_growth,
    apply_red_lines, get_rating,
    load_financial_data, run_scoring,
)


# ==========================================================================
# 测试用例1：立讯精密真实数据
# ==========================================================================

class TestLuxshareScoring:
    """使用立讯精密2024年真实财务数据验证计算和评分。"""

    def setup_method(self):
        data_path = Path(__file__).parent.parent / "data" / "financial_data.json"
        self.data = load_financial_data(data_path)
        self.result = run_scoring(self.data, roe_method="weighted_avg", debt_scope="narrow")

    def test_total_score(self):
        """总分应为76分，B级。"""
        assert self.result["raw_total"] == 76
        assert self.result["final_total"] == 76
        assert "B级" in self.result["rating"]

    def test_no_red_lines(self):
        """立讯精密2024年不应触发任何红线。"""
        assert all(not rl["triggered"] for rl in self.result["red_lines"])

    def test_roe_weighted_avg(self):
        """加权平均ROE应约为21.28%，满分10分。"""
        roe = self.result["scores"]["ROE当期值"]
        assert abs(roe["value"] - 0.2128) < 0.001
        assert roe["score"] == 10

    def test_roe_endpoint_vs_weighted(self):
        """期末ROE应低于加权平均ROE。"""
        roe = self.result["scores"]["ROE当期值"]
        assert roe["value_endpoint"] < roe["value_weighted"]

    def test_gross_margin(self):
        """毛利率约10.41%，低于15%，应得0分。"""
        gm = self.result["scores"]["毛利率当期值"]
        assert abs(gm["value"] - 0.1041) < 0.001
        assert gm["score"] == 0

    def test_revenue_growth(self):
        """营收增速约15.91%，>=15%，应得7分。"""
        rev = self.result["scores"]["营收同比增速"]
        assert abs(rev["value"] - 0.1591) < 0.001
        assert rev["score"] == 7

    def test_ocf_to_profit(self):
        """经营现金流/净利润约1.86，>=1.0，应得10分。"""
        ocf = self.result["scores"]["经营现金流与净利润比"]
        assert ocf["value"] > 1.0
        assert ocf["score"] == 10

    def test_category_scores(self):
        """验证各分类得分之和。"""
        scores = self.result["scores"]
        cats = {}
        for item in scores.values():
            cat = item["category"]
            cats[cat] = cats.get(cat, 0) + item["score"]
        assert cats["商业质量"] == 22
        assert cats["财务安全"] == 17
        assert cats["盈利质量与现金含量"] == 17
        assert cats["成长质量"] == 20

    def test_switching_roe_method(self):
        """切换ROE口径应改变ROE得分。"""
        result_ep = run_scoring(self.data, roe_method="endpoint", debt_scope="narrow")
        # 期末ROE约19.3%，在15%-20%区间，应得8分
        assert result_ep["scores"]["ROE当期值"]["score"] == 8
        # ROE得分少2分，且ROE趋势判断也可能变化
        assert result_ep["raw_total"] < self.result["raw_total"]

    def test_switching_debt_scope(self):
        """切换负债口径应改变负债比值但不影响评分档位。"""
        result_wide = run_scoring(self.data, roe_method="weighted_avg", debt_scope="wide")
        narrow_val = self.result["scores"]["货币资金与短期有息负债比"]["value_narrow"]
        wide_val = result_wide["scores"]["货币资金与短期有息负债比"]["value_wide"]
        # 宽口径分母更大，比值应更小
        assert wide_val < narrow_val


# ==========================================================================
# 测试用例2：极端数据验证红线规则
# ==========================================================================

class TestRedLineRules:
    """构造极端数据验证红线规则和边界条件。"""

    def test_non_standard_audit_caps_at_59(self):
        """非标准审计意见应将总分限制在59分。"""
        score, checks = apply_red_lines(
            total_score=80,
            audit_opinion_clean=False,
            net_profit_current=100, net_profit_prior=100,
            ocf_current=50, ocf_prior=50,
            debt_ratio=0.5, interest_coverage=10
        )
        assert score == 59
        triggered = [c for c in checks if c["triggered"]]
        assert len(triggered) == 1
        assert "审计意见" in triggered[0]["rule"]

    def test_consecutive_negative_ocf_caps_at_54(self):
        """连续两年正利润负现金流应将总分限制在54分。"""
        score, checks = apply_red_lines(
            total_score=80,
            audit_opinion_clean=True,
            net_profit_current=100, net_profit_prior=100,
            ocf_current=-10, ocf_prior=-20,
            debt_ratio=0.5, interest_coverage=10
        )
        assert score == 54
        triggered = [c for c in checks if c["triggered"]]
        assert any("现金流" in t["rule"] for t in triggered)

    def test_high_debt_low_coverage_caps_at_49(self):
        """高负债率+低利息保障倍数应将总分限制在49分。"""
        score, checks = apply_red_lines(
            total_score=80,
            audit_opinion_clean=True,
            net_profit_current=100, net_profit_prior=100,
            ocf_current=50, ocf_prior=50,
            debt_ratio=0.80, interest_coverage=1.0
        )
        assert score == 49
        triggered = [c for c in checks if c["triggered"]]
        assert any("资产负债率" in t["rule"] for t in triggered)

    def test_multiple_red_lines_take_strictest(self):
        """多条红线同时触发时取最严格上限。"""
        score, checks = apply_red_lines(
            total_score=90,
            audit_opinion_clean=False,
            net_profit_current=100, net_profit_prior=100,
            ocf_current=-10, ocf_prior=-20,
            debt_ratio=0.80, interest_coverage=1.0
        )
        assert score == 49  # 最严格的上限
        triggered = [c for c in checks if c["triggered"]]
        assert len(triggered) == 3

    def test_no_red_lines_score_unchanged(self):
        """不触发红线时总分不变。"""
        score, checks = apply_red_lines(
            total_score=85,
            audit_opinion_clean=True,
            net_profit_current=100, net_profit_prior=100,
            ocf_current=50, ocf_prior=50,
            debt_ratio=0.5, interest_coverage=10
        )
        assert score == 85
        # 所有检查都返回，但没有触发的
        assert len(checks) == 3
        assert all(not c["triggered"] for c in checks)


# ==========================================================================
# 指标计算单元测试
# ==========================================================================

class TestIndicatorCalculations:
    """验证各衍生指标的计算公式。"""

    def test_roe_endpoint(self):
        assert calc_roe(100, 400, 500, method="endpoint") == 0.2

    def test_roe_weighted(self):
        assert calc_roe(100, 400, 600, method="weighted_avg") == 0.2

    def test_gross_margin(self):
        assert calc_gross_margin(1000, 700) == 0.3

    def test_period_expense_ratio(self):
        ratio = calc_period_expense_ratio(10, 20, 30, 5, 1000)
        assert ratio == 0.065

    def test_interest_coverage(self):
        # EBIT = 利润总额 + 利息费用 = 100 + 20 = 120
        assert calc_interest_coverage(100, 20) == 6.0

    def test_interest_coverage_zero_interest(self):
        assert calc_interest_coverage(100, 0) == float('inf')

    def test_cash_to_short_debt_narrow(self):
        ratio = calc_cash_to_short_debt(120, 80, 20, scope="narrow")
        assert ratio == 1.2

    def test_cash_to_short_debt_wide(self):
        ratio = calc_cash_to_short_debt(120, 80, 20, 10, 10, scope="wide")
        assert ratio == 1.0

    def test_fcf_ratio(self):
        # FCF = 100 - 30 = 70, ratio = 70 / 1000 = 0.07
        assert calc_fcf_ratio(100, 30, 1000) == 0.07

    def test_yoy_growth(self):
        assert calc_yoy_growth(115, 100) == 0.15


# ==========================================================================
# 评级映射测试
# ==========================================================================

class TestRatingMapping:

    def test_ratings(self):
        assert "A级" in get_rating(85)
        assert "A级" in get_rating(100)
        assert "B级" in get_rating(70)
        assert "B级" in get_rating(84)
        assert "C级" in get_rating(55)
        assert "C级" in get_rating(69)
        assert "D级" in get_rating(40)
        assert "D级" in get_rating(54)
        assert "E级" in get_rating(39)
        assert "E级" in get_rating(0)
