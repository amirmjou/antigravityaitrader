"""
Unit tests for visual balance chart generator.
"""
import os
from pathlib import Path
from core.visualization.chart_generator import generate_balance_chart


def test_generate_balance_chart(tmp_path):
    output_file = tmp_path / "test_chart.png"
    result = generate_balance_chart(
        output_path=output_file,
        current_eth=0.00035,
        current_weth=0.00050,
        current_usdc=1.00,
        eth_price=3130.0,
    )
    assert result is not None
    assert os.path.exists(result)
    assert os.path.getsize(result) > 1000  # Valid non-empty PNG
