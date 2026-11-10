from core.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bull analyst"
        )
        from core.dataflows.symbols import _CRYPTO_BASES, crypto_base
        company_name = state.get("company_of_interest", "")
        clean = company_name.strip().upper() if isinstance(company_name, str) else ""
        asset_type = state.get("asset_type", "stock")
        is_crypto = (
            asset_type == "crypto"
            or clean in _CRYPTO_BASES
            or (crypto_base(clean) is not None and crypto_base(clean) in _CRYPTO_BASES)
        )
        target_label = "asset" if is_crypto else "stock"

        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")

        if is_crypto:
            fundamentals_section = "Asset fundamentals: Not applicable for cryptocurrency assets (corporate financial statements suppressed)."
            focus_points = """Key points to focus on:
- Risks and Challenges: Highlight network vulnerabilities, regulatory headwinds, liquidity risks, or macroeconomic volatility.
- Competitive Weaknesses: Emphasize vulnerabilities such as competing protocols, declining active addresses, or security risks.
- Negative Indicators: Use adverse news, whale outflows, technical breakdown levels, or sentiment deterioration to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts."""
        else:
            fundamentals_report = report_or_absent(state.get("fundamentals_report", ""), "fundamentals")
            fundamentals_section = f"Company fundamentals report: {fundamentals_report}"
            focus_points = """Key points to focus on:
- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts."""

        instrument_context = get_instrument_context_from_state(state)

        prompt = f"""You are a Bear Analyst making the case against investing in the {target_label}. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

{focus_points}

Resources available:

{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_section}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the {target_label}.
""" + get_language_instruction()

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
