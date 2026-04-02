"""
财报侦察官 - LLM调用模块
职责：审计意见分类 + 综合财务评价生成
原则：LLM只做文本理解和文本生成，不做数字计算。
"""

import json
import os
from openai import OpenAI

# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("请设置环境变量 OPENAI_API_KEY")
    return OpenAI(api_key=api_key)


MODEL = "gpt-4o-mini"  # 轻量任务用mini，快且便宜


# ---------------------------------------------------------------------------
# 1. 审计意见分类
# ---------------------------------------------------------------------------

AUDIT_OPINION_PROMPT = """你是一名专业的财务审计分析师。请阅读以下审计意见段落，提取审计意见类型。

审计意见只有以下5种类型，请严格从中选择一个：
1. 标准无保留意见
2. 带强调事项段的无保留意见
3. 保留意见
4. 否定意见
5. 无法表示意见

请以JSON格式返回，包含两个字段：
- "opinion_type": 上述5种之一的完整文字
- "is_clean": 布尔值，仅当类型为"标准无保留意见"时为true，其余均为false

只返回JSON，不要返回任何其他内容。

审计意见段落如下：
{audit_text}"""


def classify_audit_opinion(audit_text: str) -> dict:
    """
    调用LLM从审计意见文本中提取意见类型。

    容错策略：
    - 如果LLM返回非JSON格式，尝试从文本中提取关键词匹配
    - 如果API调用失败，返回保守默认值（非标准），触发红线保护
    - 限制max_tokens防止冗长输出
    """
    client = get_client()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=200,
            temperature=0,
            messages=[{
                "role": "user",
                "content": AUDIT_OPINION_PROMPT.format(audit_text=audit_text)
            }]
        )
        raw = response.choices[0].message.content.strip()

        # 尝试解析JSON
        try:
            # 处理可能的markdown代码块包裹
            cleaned = raw
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                cleaned = cleaned.rsplit("```", 1)[0]
            result = json.loads(cleaned.strip())
            if "opinion_type" in result and "is_clean" in result:
                return result
        except json.JSONDecodeError:
            pass

        # 回退：关键词匹配
        return _fallback_classify(raw)

    except Exception as e:
        # API失败 → 保守处理，假设非标准意见
        return {
            "opinion_type": "未知（API调用失败）",
            "is_clean": False,
            "error": str(e)
        }


def _fallback_classify(text: str) -> dict:
    """
    关键词回退匹配。当LLM未返回有效JSON时使用。
    按从严格到宽松的顺序匹配。
    """
    text = text.lower().replace(" ", "")

    if "无法表示意见" in text:
        return {"opinion_type": "无法表示意见", "is_clean": False}
    if "否定意见" in text:
        return {"opinion_type": "否定意见", "is_clean": False}
    if "保留意见" in text and "无保留" not in text:
        return {"opinion_type": "保留意见", "is_clean": False}
    if "强调事项" in text:
        return {"opinion_type": "带强调事项段的无保留意见", "is_clean": False}
    if "标准" in text and "无保留" in text:
        return {"opinion_type": "标准无保留意见", "is_clean": True}
    if "无保留" in text:
        return {"opinion_type": "标准无保留意见", "is_clean": True}

    # 完全无法识别 → 保守处理
    return {"opinion_type": "未知（无法识别）", "is_clean": False}


# ---------------------------------------------------------------------------
# 2. 综合财务评价生成
# ---------------------------------------------------------------------------

EVALUATION_PROMPT = """你是一名资深财务分析师。请根据以下已由代码计算完成的财务评分结果和审计意见，生成结构化的综合财务评价。

请严格以JSON格式返回，包含以下字段：
{{
  "summary": "200字左右的综合财务评价文字",
  "observations": [
    {{
      "text": "基于数据的客观事实陈述，如'ROE为19.50%，处于较高水平'",
      "sources": ["该陈述引用的指标名称1", "指标名称2"],
      "type": "factual"
    }}
  ],
  "judgments": [
    {{
      "text": "基于多项数据的综合推断或判断，如'盈利质量较高，利润有充足现金流支撑'",
      "sources": ["该判断依据的指标名称1", "指标名称2"],
      "type": "inference"
    }}
  ]
}}

要求：
- summary：直接给出评价，涵盖主要优势和风险点，语言专业简洁，180-220字
- observations：2-4条客观事实陈述，直接引用指标数值，不含主观判断
- judgments：2-4条综合推断，基于多个指标的交叉分析得出结论
- sources中的指标名称必须来自下方"各项指标得分"中的名称，或使用"审计意见"表示引用了审计报告信息
- 严格区分"事实"和"推断"：事实是对单一指标数值的客观描述，推断是基于多项数据的综合判断
- 严格基于提供的数据，不要编造未提供的数据
- 只返回JSON，不要返回其他内容

公司：{company}
报告年度：{report_year}
最终评分：{final_total}/100
评级：{rating}

各项指标得分：
{scores_text}

红线触发情况：{red_lines}

审计意见摘要：
{audit_summary}"""


def generate_evaluation(scoring_result: dict, audit_text: str = "") -> dict:
    """
    调用LLM基于评分结果和审计意见生成结构化综合评价。

    返回格式：
    {{
      "summary": "综合评价文字",
      "claims": [{{"text": "...", "sources": [...]}}]
    }}

    容错策略：
    - LLM返回非JSON时回退为纯文本评价
    - API失败时返回规则化兜底评价
    - 限制max_tokens=800防止过长输出
    """
    scores_text = _format_scores_for_prompt(scoring_result["scores"])
    # red_lines现在是结构化列表，格式化为文本
    red_line_items = scoring_result["red_lines"]
    if isinstance(red_line_items, list) and red_line_items:
        triggered = [rl["explanation"] for rl in red_line_items if isinstance(rl, dict) and rl.get("triggered")]
        red_lines = "；".join(triggered) if triggered else "无"
    else:
        red_lines = "无"

    # 审计意见摘要：截取前500字避免token过多
    audit_summary = audit_text[:500] if audit_text else "未提供"

    prompt = EVALUATION_PROMPT.format(
        company=scoring_result["company"],
        report_year=scoring_result["report_year"],
        final_total=scoring_result["final_total"],
        rating=scoring_result["rating"],
        scores_text=scores_text,
        red_lines=red_lines,
        audit_summary=audit_summary
    )

    client = get_client()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=800,
            temperature=0.3,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        raw = response.choices[0].message.content.strip()

        # 尝试解析JSON
        try:
            cleaned = raw
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                cleaned = cleaned.rsplit("```", 1)[0]
            result = json.loads(cleaned.strip())
            if "summary" in result:
                # 兼容旧格式：如果LLM返回claims而非observations/judgments，自动转换
                if "claims" in result and "observations" not in result:
                    result["observations"] = []
                    result["judgments"] = [
                        {"text": c["text"], "sources": c.get("sources", []), "type": "inference"}
                        for c in result["claims"]
                    ]
                # 确保字段存在
                result.setdefault("observations", [])
                result.setdefault("judgments", [])
                # 保留claims字段供旧前端兼容
                result["claims"] = (
                    [{"text": o["text"], "sources": o.get("sources", []), "type": "factual"} for o in result["observations"]]
                    + [{"text": j["text"], "sources": j.get("sources", []), "type": "inference"} for j in result["judgments"]]
                )
                return result
        except json.JSONDecodeError:
            pass

        # 回退：将纯文本包装为结构
        return {"summary": raw, "observations": [], "judgments": [], "claims": []}

    except Exception as e:
        return _fallback_evaluation(scoring_result, str(e))


def _format_scores_for_prompt(scores: dict) -> str:
    lines = []
    for name, item in scores.items():
        val = item.get("value", item.get("trend", "N/A"))
        if isinstance(val, float):
            val = f"{val*100:.2f}%"
        lines.append(f"- {name}: {val}, 得分{item['score']}/{item['max']}")
    return "\n".join(lines)


def _fallback_evaluation(result: dict, error: str) -> dict:
    """API失败时的规则化兜底评价。"""
    summary = (
        f"{result['company']}{result['report_year']}年度财务评分为"
        f"{result['final_total']}分，评级{result['rating']}。"
        f"（注：综合评价生成失败，原因：{error}。以上为系统自动生成的简要结论。）"
    )
    return {"summary": summary, "observations": [], "judgments": [], "claims": [], "error": error}


# ---------------------------------------------------------------------------
# 独立运行测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path
    from scorer import load_financial_data, run_scoring

    # 读取审计意见
    data_dir = Path(__file__).parent.parent / "data"
    with open(data_dir / "audit_opinion.txt", "r", encoding="utf-8") as f:
        audit_text = f.read()

    # 分类审计意见
    print("=== 审计意见分类 ===")
    opinion = classify_audit_opinion(audit_text)
    print(json.dumps(opinion, ensure_ascii=False, indent=2))

    # 运行评分
    data = load_financial_data(data_dir / "financial_data.json")
    result = run_scoring(data, audit_opinion_clean=opinion["is_clean"])

    # 生成综合评价
    print("\n=== 综合财务评价 ===")
    evaluation = generate_evaluation(result, audit_text)
    print(json.dumps(evaluation, ensure_ascii=False, indent=2))
