#!/usr/bin/env python3
"""Unit test for the dual-analysis engine with mock data."""
import sys
import os
import json
import unittest
from datetime import datetime

# Test the analysis functions only (skip akshare dependency)
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TEST_DIR)

# Mock akshare module before importing market_push
import types
akshare = types.ModuleType('akshare')

def mock_index_daily(symbol):
    import pandas as pd
    import numpy as np
    dates = pd.date_range(end='20260626', periods=10, freq='D')
    # Make a realistic-looking index with slight up trend
    closes = np.linspace(3100, 3150, 10) + np.random.RandomState(42).normal(0, 10, 10)
    df = pd.DataFrame({
        'date': dates,
        'close': closes,
        'open': closes - np.random.RandomState(42).uniform(-5, 5, 10),
        'high': closes + np.random.RandomState(42).uniform(0, 10, 10),
        'low': closes - np.random.RandomState(42).uniform(0, 10, 10),
        'volume': np.random.RandomState(42).uniform(5e9, 8e9, 10),
    })
    return df

def mock_zt_pool(date):
    import pandas as pd
    import numpy as np
    rs = np.random.RandomState(42)
    n_stocks = rs.randint(50, 90)
    names_pool = ['东方财富', '贵州茅台', '宁德时代', '东百集团', '步步高',
                  '华电能源', '粤电力A', '深南电A', '中国平安', '招商银行',
                  '中信证券', '五粮液', '比亚迪', '隆基绿能', '药明康德']
    industries = ['电力', '零售', '白酒', '金融', '新能源', '医药', '半导体']

    rows = []
    for i in range(n_stocks):
        name = names_pool[i % len(names_pool)] + str(i // len(names_pool) + 1) if i >= len(names_pool) else names_pool[i % len(names_pool)]
        ban_count = rs.randint(1, 6)
        rows.append({
            '代码': '60{:04d}'.format(rs.randint(1000, 9999)),
            '名称': name,
            '连板数': ban_count,
            '所属行业': industries[rs.randint(0, len(industries))],
            '换手率': rs.uniform(1, 30),
            '涨停统计': '{}天{}板'.format(ban_count + rs.randint(0, 3), ban_count),
            '成交额': rs.uniform(1e8, 5e9),
        })
    df = pd.DataFrame(rows)
    df['连板数'] = df['连板数'].astype(int)
    return df

akshare.stock_zh_index_daily = mock_index_daily
akshare.stock_zt_pool_em = mock_zt_pool
akshare.stock_zt_pool_strong_em = lambda date: None

sys.modules['akshare'] = akshare

# Now import market_push
import importlib.util
spec = importlib.util.spec_from_file_location("market_push", os.path.join(TEST_DIR, "market_push.py"))
mp = importlib.util.module_from_spec(spec)
# Don't exec yet, we need to set up the module first
spec.loader.exec_module(mp)

class TestAnalysisFunctions(unittest.TestCase):
    """Test the analysis pipeline with mock data."""

    def setUp(self):
        self.date_str = "20260626"
        self.data = mp.fetch_market_data(self.date_str)

    def test_fetch_market_data(self):
        """Test data fetching returns expected structure."""
        data = self.data
        self.assertIn('date', data)
        self.assertEqual(data['date'], self.date_str)
        self.assertIn('index', data)
        self.assertIn('limit_up_board', data)
        self.assertIn('sentiment', data)
        print("[OK] fetch_market_data returns correct structure")
        print("    Index close: {:.2f}".format(data['index'].get('close', 0)))
        print("    Limit up: {} stocks".format(data['sentiment'].get('total_limit_up', 0)))

    def test_analyze_taoguba(self):
        """Test TaoGuBa analysis generates valid markdown."""
        result = mp.analyze_taoguba(self.data)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 100)
        self.assertIn("淘股吧超短", result)
        self.assertIn("情绪周期", result)
        self.assertIn("连板天梯", result)
        print("[OK] analyze_taoguba produces valid markdown ({} chars)".format(len(result)))

    def test_analyze_oute(self):
        """Test OuTe dragon strategy analysis."""
        result = mp.analyze_oute(self.data)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 100)
        self.assertIn("欧特慢慢龙头", result)
        self.assertIn("真龙四条件", result)
        self.assertIn("防守纪律", result)
        print("[OK] analyze_oute produces valid markdown ({} chars)".format(len(result)))

    def test_generate_tomorrow_plan(self):
        """Test tomorrow's trading plan generation."""
        result = mp.generate_tomorrow_plan(self.data)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 50)
        self.assertIn("明日操作预案", result)
        self.assertIn("风控红线", result)
        print("[OK] generate_tomorrow_plan produces valid markdown ({} chars)".format(len(result)))

    def test_build_report(self):
        """Test full report assembly."""
        result = mp.build_report(self.data)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 500)
        self.assertIn("双体系日报", result)
        self.assertIn("淘股吧超短", result)
        self.assertIn("欧特慢慢龙头", result)
        self.assertIn("明日操作预案", result)
        self.assertIn("明日买入建议", result)
        print("[OK] build_report produces complete report ({} chars)".format(len(result)))

    def test_report_formatting(self):
        """Test report has proper markdown formatting."""
        result = mp.build_report(self.data)
        lines = result.split('\n')
        # Check headers
        headers = [l for l in lines if l.startswith('#')]
        self.assertGreater(len(headers), 3, "Should have multiple headers")
        # Check tables
        tables = [l for l in lines if l.startswith('|')]
        self.assertGreater(len(tables), 10, "Should have multiple table rows")
        print("[OK] Report has {} headers and {} table rows".format(len(headers), len(tables)))

    def test_trading_day_detection(self):
        """Test trading day detection (without date override)."""
        # Will just return a date - verify it's 8 digits
        # We use override to avoid time-dependency
        date = mp.get_latest_trading_day("20260626")
        self.assertEqual(len(date), 8)
        self.assertTrue(date.isdigit())
        print("[OK] get_latest_trading_day returns valid date: {}".format(date))


class TestCLIArgs(unittest.TestCase):
    """Test command-line argument parsing."""

    def test_has_arguments(self):
        """Verify main() has argparse support."""
        import inspect
        source = inspect.getsource(mp.main)
        self.assertIn("argparse", source)
        self.assertIn("--no-push", source)
        self.assertIn("--date", source)
        print("[OK] CLI args parse test passed")


if __name__ == '__main__':
    print("=" * 60)
    print("A股超短双体系分析引擎 - 单元测试")
    print("时间: {}".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    print("=" * 60)

    suite = unittest.TestSuite()
    suite.addTest(TestAnalysisFunctions('test_fetch_market_data'))
    suite.addTest(TestAnalysisFunctions('test_analyze_taoguba'))
    suite.addTest(TestAnalysisFunctions('test_analyze_oute'))
    suite.addTest(TestAnalysisFunctions('test_generate_tomorrow_plan'))
    suite.addTest(TestAnalysisFunctions('test_build_report'))
    suite.addTest(TestAnalysisFunctions('test_report_formatting'))
    suite.addTest(TestAnalysisFunctions('test_trading_day_detection'))
    suite.addTest(TestCLIArgs('test_has_arguments'))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("")
    print("=" * 60)
    print("测试完成: {} passed, {} failed".format(
        result.testsRun - len(result.failures) - len(result.errors),
        len(result.failures) + len(result.errors)
    ))
    sys.exit(0 if result.wasSuccessful() else 1)
