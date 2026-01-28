
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
from stockstats import StockDataFrame

class EtfAnalyzer:
    def __init__(self, etf_code, stock_analyzer_instance):
        self.etf_code = etf_code
        self.analysis_result = {}
        self.hist_df = None # 用于存储历史数据以供后续分析使用
        self.stock_analyzer = stock_analyzer_instance # 复用StockAnalyzer实例
        # 初始化统一数据层
        from app.core.data_provider import get_data_provider
        self.data_provider = get_data_provider()

    def run_analysis(self):
        """
        运行所有分析步骤并返回结果
        """
        self.get_basic_info()
        self.analyze_market_performance()
        self.analyze_fund_flow()
        self.analyze_risk_and_tracking()
        self.analyze_holdings()
        self.analyze_sector()
        self.get_ai_summary()
        
        return self.analysis_result

    def get_basic_info(self):
        """
        1. 基本信息分析
        """
        print("开始获取基本信息...")
        try:
            # 使用akshare获取ETF基金概况
            fund_info_df = ak.fund_etf_fund_info_em(fund=self.etf_code)
            
            if fund_info_df.empty:
                info_dict = {"error": "未能获取到该ETF的基本信息，请检查代码是否正确。"}
            else:
                # 将返回的DataFrame转换成字典，假设第一列是键，第二列是值
                info_dict = {}
                for _, row in fund_info_df.iterrows():
                    if len(row) >= 2:
                        info_dict[row.iloc[0]] = row.iloc[1]

            self.analysis_result['basic_info'] = info_dict
            print("基本信息获取完成。")

        except Exception as e:
            print(f"获取ETF基本信息时出错: {e}")
            self.analysis_result['basic_info'] = {"error": f"获取基本信息失败: {e}"}

    def analyze_market_performance(self):
        """
        2. 市场表现与技术分析 (第一部分：回报率与流动性)
        """
        print("开始分析市场表现...")
        try:
            # 获取近一年的历史数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)
            
            end_date_str = end_date.strftime('%Y%m%d')
            start_date_str = start_date.strftime('%Y%m%d')

            # 使用后复权数据
            hist_df = ak.fund_etf_hist_em(symbol=self.etf_code, start_date=start_date_str, end_date=end_date_str, adjust="hfq")

            if hist_df.empty:
                self.analysis_result['market_performance'] = {"error": "未能获取到该ETF的历史行情数据。"}
                print("未能获取历史行情数据。")
                return

            # --- 数据准备 ---
            hist_df['日期'] = pd.to_datetime(hist_df['日期'])
            hist_df.set_index('日期', inplace=True)
            hist_df['收盘'] = pd.to_numeric(hist_df['收盘'])
            hist_df['成交额'] = pd.to_numeric(hist_df['成交额'], errors='coerce').fillna(0)
            hist_df['换手率'] = pd.to_numeric(hist_df['换手率'], errors='coerce').fillna(0)
            
            # 存储历史数据以供其他方法使用
            self.hist_df = hist_df

            # --- 回报率计算 ---
            returns = {}
            if not hist_df.empty:
                latest_price = hist_df['收盘'].iloc[-1]
                
                periods = {
                    '近1周': 5,
                    '近1个月': 21,
                    '近3个月': 63,
                    '近1年': 252
                }
                
                for name, days in periods.items():
                    if len(hist_df) > days:
                        old_price = hist_df['收盘'].iloc[-days-1]
                        returns[name] = ((latest_price / old_price) - 1) * 100 if old_price != 0 else 0
                    else:
                        # 如果数据不足，则从第一天开始算
                        old_price = hist_df['收盘'].iloc[0]
                        returns[name] = ((latest_price / old_price) - 1) * 100 if old_price != 0 else 0

                # 计算年初至今回报率
                ytd_df = hist_df[hist_df.index.year == end_date.year]
                if not ytd_df.empty:
                    ytd_start_price = ytd_df['收盘'].iloc[0]
                    returns['年初至今'] = ((latest_price / ytd_start_price) - 1) * 100 if ytd_start_price != 0 else 0
                else:
                    # 如果当年没有数据，则计算从开始到现在的总回报
                    start_price = hist_df['收盘'].iloc[0]
                    returns['年初至今'] = ((latest_price / start_price) - 1) * 100 if start_price != 0 else 0

            # --- 流动性分析 ---
            liquidity = {}
            last_month_df = hist_df.tail(21)
            if not last_month_df.empty:
                liquidity['日均成交额(近一月)'] = last_month_df['成交额'].mean()
                liquidity['日均换手率(近一月)'] = last_month_df['换手率'].mean()
            else:
                liquidity['日均成交额(近一月)'] = None
                liquidity['日均换手率(近一月)'] = None

            # --- 技术指标计算 ---
            tech_indicators = {}
            if self.hist_df is not None and not self.hist_df.empty:
                # stockstats需要特定的列名，创建一个副本进行操作
                stock_df_for_ta = self.hist_df.copy()
                stock_df_for_ta.rename(columns={'收盘': 'close', '开盘': 'open', '最高': 'high', '最低': 'low', '成交量': 'volume'}, inplace=True)
                
                # 转换为StockDataFrame
                sdf = StockDataFrame.retype(stock_df_for_ta)
                
                # 计算指标
                sdf[['macd', 'macds', 'macdh']] # MACD
                sdf['rsi_14'] # RSI
                sdf['close_20_sma'] # 20日均线
                sdf['close_60_sma'] # 60日均线

                # 获取最新的指标值
                latest_indicators = sdf.iloc[-1]
                tech_indicators = {
                    'MA20': latest_indicators.get('close_20_sma'),
                    'MA60': latest_indicators.get('close_60_sma'),
                    'MACD': latest_indicators.get('macd'),
                    'MACD_Signal': latest_indicators.get('macds'),
                    'MACD_Hist': latest_indicators.get('macdh'),
                    'RSI_14': latest_indicators.get('rsi_14')
                }
                
                # 注意：不再覆盖 self.hist_df

            self.analysis_result['market_performance'] = {
                "returns": returns,
                "liquidity": liquidity,
                "tech_indicators": tech_indicators,
                "message": "回报率、流动性和技术指标分析完成。"
            }
            print("市场表现分析(回报率、流动性、技术指标)完成。")

            # --- 与基准对比 ---
            benchmark_code = 'sh000300' # 默认使用沪深300作为基准
            print(f"开始与基准 {benchmark_code} 进行对比...")
            
            benchmark_df = ak.stock_zh_index_daily(symbol=benchmark_code)
            benchmark_df['date'] = pd.to_datetime(benchmark_df['date'])
            benchmark_df.set_index('date', inplace=True)
            
            # 截取与ETF相同的时间段
            benchmark_df = benchmark_df.loc[self.hist_df.index[0]:self.hist_df.index[-1]]
            
            benchmark_returns = {}
            alpha = {}

            if not benchmark_df.empty:
                benchmark_latest_price = benchmark_df['close'].iloc[-1]
                
                for name, days in periods.items():
                    if len(benchmark_df) > days:
                        old_price = benchmark_df['close'].iloc[-days-1]
                        benchmark_returns[name] = ((benchmark_latest_price / old_price) - 1) * 100 if old_price != 0 else 0
                    else:
                        old_price = benchmark_df['close'].iloc[0]
                        benchmark_returns[name] = ((benchmark_latest_price / old_price) - 1) * 100 if old_price != 0 else 0
                    
                    # 计算超额收益
                    alpha[name] = returns.get(name, 0) - benchmark_returns.get(name, 0)

                # 年初至今
                benchmark_ytd_df = benchmark_df[benchmark_df.index.year == end_date.year]
                if not benchmark_ytd_df.empty:
                    ytd_start_price = benchmark_ytd_df['close'].iloc[0]
                    benchmark_returns['年初至今'] = ((benchmark_latest_price / ytd_start_price) - 1) * 100 if ytd_start_price != 0 else 0
                else:
                    start_price = benchmark_df['close'].iloc[0]
                    benchmark_returns['年初至今'] = ((benchmark_latest_price / start_price) - 1) * 100 if start_price != 0 else 0
                
                alpha['年初至今'] = returns.get('年初至今', 0) - benchmark_returns.get('年初至今', 0)

            # 更新结果
            self.analysis_result['market_performance']['benchmark_returns'] = benchmark_returns
            self.analysis_result['market_performance']['alpha'] = alpha
            self.analysis_result['market_performance']['message'] = "完整的市场表现分析已完成。"
            print("与基准对比分析完成。")

        except Exception as e:
            print(f"分析市场表现时出错: {e}")
            self.analysis_result['market_performance'] = {"error": f"分析市场表现失败: {e}"}

    def analyze_fund_flow(self):
        """
        3. 资金流向分析
        """
        print("开始分析资金流向...")
        try:
            # 复用已获取的历史数据
            if self.hist_df is None or self.hist_df.empty:
                self.analysis_result['fund_flow'] = {"error": "历史数据缺失，无法进行资金流向分析。"}
                print("历史数据缺失，跳过资金流向分析。")
                return

            df = self.hist_df.copy()
            
            # akshare返回的hist_df中没有直接的份额列，需要重新请求或者寻找其他接口
            # 这里我们假设'成交量'可以作为份额变化的代理指标进行估算，这是一个简化处理
            # 更好的方法是找到直接提供份额历史的接口
            
            # 计算份额变化 (此处使用成交量作为代理)
            # 注意：这是一个估算，并非精确值。真实份额变化需专门接口。
            df['份额变化'] = df['成交量'].diff().fillna(0)
            
            # 估算资金净流入/流出 = 份额变化 * 当日收盘价
            # 正值表示流入，负值表示流出
            df['资金净流入估算'] = df['份额变化'] * df['收盘']

            # --- 汇总统计 ---
            flow_summary = {}
            periods = {
                '近1周': 5,
                '近1个月': 21,
                '近3个月': 63
            }

            for name, days in periods.items():
                if len(df) >= days:
                    flow_summary[name] = df['资金净流入估算'].tail(days).sum()
                else:
                    flow_summary[name] = df['资金净流入估算'].sum()
            
            # 获取最近的资金流数据以供图表使用 (例如最近60天)
            recent_flow_data = df.tail(60)[['资金净流入估算']].copy()
            recent_flow_data.index = recent_flow_data.index.strftime('%Y-%m-%d')
            recent_flow_data['资金净流入估算'] = (recent_flow_data['资金净流入估算'] / 1e8).round(4) # 转换为亿元

            # 准备图表数据，格式为 [ [date_string, value], ... ]
            chart_data_df = recent_flow_data.reset_index()
            chart_data_list = chart_data_df.values.tolist()

            self.analysis_result['fund_flow'] = {
                "summary": flow_summary,
                "daily_flow_chart_data": {"data": chart_data_list},
                "message": "资金流向分析完成 (基于成交量估算)。"
            }
            print("资金流向分析完成。")

        except Exception as e:
            print(f"分析资金流向时出错: {e}")
            self.analysis_result['fund_flow'] = {"error": f"分析资金流向失败: {e}"}

    def analyze_risk_and_tracking(self):
        """
        4. 风险与跟踪能力分析
        """
        print("开始分析风险与跟踪能力...")
        try:
            if self.hist_df is None or self.hist_df.empty:
                self.analysis_result['risk_and_tracking'] = {"error": "历史数据缺失，无法进行风险分析。"}
                print("历史数据缺失，跳过风险分析。")
                return

            df = self.hist_df.copy()
            # 确保返回的是pct_change，而不是整个Series
            df['etf_return'] = df['收盘'].pct_change().fillna(0)

            # 1. 波动率 (年化)
            annualized_volatility = df['etf_return'].std() * np.sqrt(252)

            # 2. 与基准比较 (Beta, 跟踪误差, 夏普比率)
            benchmark_code = 'sh000300'
            benchmark_df = ak.stock_zh_index_daily(symbol=benchmark_code)
            benchmark_df['date'] = pd.to_datetime(benchmark_df['date'])
            benchmark_df.set_index('date', inplace=True)
            benchmark_df = benchmark_df.loc[df.index.min():df.index.max()]
            benchmark_df['benchmark_return'] = benchmark_df['close'].pct_change().fillna(0)

            # 合并数据
            merged_df = pd.merge(df[['etf_return']], benchmark_df[['benchmark_return']], left_index=True, right_index=True, how='inner')

            # 计算 Beta
            covariance = merged_df['etf_return'].cov(merged_df['benchmark_return'])
            variance = merged_df['benchmark_return'].var()
            beta = covariance / variance if variance != 0 else None

            # 计算 跟踪误差 (年化)
            merged_df['difference'] = merged_df['etf_return'] - merged_df['benchmark_return']
            tracking_error = merged_df['difference'].std() * np.sqrt(252)
            
            # 计算 夏普比率 (年化)
            risk_free_rate_daily = (1.02 ** (1/252)) - 1 # 假设年化无风险利率为2%
            avg_daily_return = merged_df['etf_return'].mean()
            std_daily_return = merged_df['etf_return'].std()
            sharpe_ratio = ((avg_daily_return - risk_free_rate_daily) * 252) / (std_daily_return * np.sqrt(252)) if std_daily_return != 0 else None
            
            # 3. 溢价/折价率 (近一个月平均)
            avg_premium_discount = None
            df_for_premium = self.hist_df.copy()
            if '单位净值' in df_for_premium.columns and not df_for_premium['单位净值'].isnull().all():
                df_for_premium['单位净值'] = pd.to_numeric(df_for_premium['单位净值'], errors='coerce')
                df_for_premium.dropna(subset=['单位净值'], inplace=True)
                df_for_premium = df_for_premium[df_for_premium['单位净值'] != 0]
                
                if not df_for_premium.empty:
                    df_for_premium['premium_discount'] = ((df_for_premium['收盘'] / df_for_premium['单位净值']) - 1) * 100
                    avg_premium_discount = df_for_premium.tail(21)['premium_discount'].mean()

            risk_metrics = {
                "annualized_volatility": annualized_volatility,
                "beta": beta,
                "tracking_error": tracking_error,
                "sharpe_ratio": sharpe_ratio,
                "avg_premium_discount_monthly": avg_premium_discount
            }
            
            self.analysis_result['risk_and_tracking'] = risk_metrics
            print("风险与跟踪能力分析完成。")

        except Exception as e:
            print(f"分析风险与跟踪能力时出错: {e}")
            self.analysis_result['risk_and_tracking'] = {"error": f"分析风险与跟踪能力失败: {e}"}

    def analyze_holdings(self):
        """
        5. 持仓分析
        """
        print("开始分析持仓...")
        try:
            # 获取ETF持仓明细
            holdings_df = ak.fund_portfolio_hold_em(symbol=self.etf_code, date=datetime.now().strftime("%Y"))
            
            if holdings_df.empty or '股票代码' not in holdings_df.columns:
                 self.analysis_result['holdings'] = {"error": "未能获取到该ETF的持仓数据。"}
                 print("未能获取持仓数据。")
                 return
            
            # 提取前十大持仓
            top_10_holdings = holdings_df.head(10)[['股票代码', '股票名称', '持仓市值', '占净值比例']].copy()
            top_10_holdings.rename(columns={'占净值比例': '占净值比例(%)'}, inplace=True)
            top_10_holdings['占净值比例(%)'] = pd.to_numeric(top_10_holdings['占净值比例(%)'], errors='coerce')
            
            # 计算前十大持仓集中度
            concentration = top_10_holdings['占净值比例(%)'].sum()

            holdings_data = {
                "top_10_holdings": top_10_holdings.to_dict('records'),
                "concentration": concentration
            }
            
            self.analysis_result['holdings'] = holdings_data
            print("持仓分析完成。")

        except Exception as e:
            print(f"分析持仓时出错: {e}")
            self.analysis_result['holdings'] = {"error": f"分析持仓失败: {e}"}

    def analyze_sector(self):
        """
        6. 板块深度分析
        """
        print("开始进行板块深度分析...")
        try:
            # 1. 识别板块/行业
            basic_info = self.analysis_result.get('basic_info', {})
            tracking_index = basic_info.get('跟踪标的', '')
            
            if not tracking_index or '指数' not in tracking_index:
                self.analysis_result['sector_analysis'] = {"error": "无法从基本信息中确定ETF跟踪的板块或行业指数。"}
                print("无法识别板块，跳过板块分析。")
                return

            # 简化处理：假设跟踪标的名称与akshare中的板块名称直接对应
            # 例如 "中证白酒指数" -> 我们需要找到对应的板块名称 "白酒"
            # 这是一个复杂的映射，这里我们先做一个简化假设，后续可以优化
            sector_name = tracking_index.replace('指数', '').replace('中证', '').replace('国证', '')
            
            # 尝试获取行业板块数据，如果失败，则可能是概念板块
            try:
                sector_df = ak.stock_board_industry_hist_em(symbol=sector_name)
            except Exception:
                try:
                    sector_df = ak.stock_board_concept_hist_em(symbol=sector_name)
                except Exception as e:
                    self.analysis_result['sector_analysis'] = {"error": f"无法获取板块 '{sector_name}' 的行情数据: {e}"}
                    return

            sector_df['日期'] = pd.to_datetime(sector_df['日期'])
            sector_df.set_index('日期', inplace=True)

            # 2. 板块回报率 (景气度)
            sector_returns = {}
            latest_price = sector_df['收盘'].iloc[-1]
            periods = {'近1周': 5, '近1个月': 21, '近3个月': 63, '近1年': 252}
            for name, days in periods.items():
                if len(sector_df) > days:
                    old_price = sector_df['收盘'].iloc[-days-1]
                    sector_returns[name] = ((latest_price / old_price) - 1) * 100 if old_price != 0 else 0
            
            # 3. 板块估值 (PE百分位)
            pe_df = ak.stock_board_industry_pe_em(symbol=sector_name)
            latest_pe = pe_df.iloc[-1]['滚动市盈率']
            pe_percentile = (pe_df['滚动市盈率'] < latest_pe).mean() * 100 if not pe_df.empty else None

            sector_data = {
                "sector_name": sector_name,
                "returns": sector_returns,
                "valuation": {
                    "current_pe": latest_pe,
                    "pe_percentile": pe_percentile
                }
            }
            
            self.analysis_result['sector_analysis'] = sector_data
            print("板块深度分析完成。")

        except Exception as e:
            print(f"分析板块时出错: {e}")
            self.analysis_result['sector_analysis'] = {"error": f"分析板块失败: {e}"}

    def get_ai_summary(self):
        """
        7. AI 综合诊断
        """
        print("开始生成AI综合诊断...")
        try:
            # 1. 整合所有分析结果
            prompt_data = f"请为ETF代码 {self.etf_code} 生成一份全面的投资分析报告。请严格根据以下数据进行分析，不要使用外部知识：\n\n"
            
            # 基本信息
            basic_info = self.analysis_result.get('basic_info', {})
            prompt_data += f"**基本信息**: 跟踪指数: {basic_info.get('跟踪标的', 'N/A')}, 规模: {basic_info.get('基金规模', 'N/A')}, 管理人: {basic_info.get('基金管理人', 'N/A')}.\n"

            # 市场表现
            perf = self.analysis_result.get('market_performance', {})
            returns = perf.get('returns', {})
            alpha = perf.get('alpha', {})
            prompt_data += f"**市场表现**: 近1个月回报率: {returns.get('近1个月', 0):.2f}%, 同期超额收益(相对沪深300): {alpha.get('近1个月', 0):.2f}%. 年初至今回报率: {returns.get('年初至今', 0):.2f}%, 同期超额收益: {alpha.get('年初至今', 0):.2f}%.\n"

            # 风险
            risk = self.analysis_result.get('risk_and_tracking', {})
            prompt_data += f"**风险指标**: 年化波动率: {risk.get('annualized_volatility', 0):.2%}, Beta值: {risk.get('beta', 0):.2f}, 年化跟踪误差: {risk.get('tracking_error', 0):.2%}.\n"

            # 持仓
            holdings = self.analysis_result.get('holdings', {})
            prompt_data += f"**持仓结构**: 前十大持仓集中度: {holdings.get('concentration', 0):.2f}%.\n"

            # 板块
            sector = self.analysis_result.get('sector_analysis', {})
            sector_val = sector.get('valuation', {})
            prompt_data += f"**板块分析**: 所属板块: {sector.get('sector_name', 'N/A')}, 当前滚动PE находится at {sector_val.get('pe_percentile', 0):.2f}% 历史分位点.\n\n"

            # 2. 构建Prompt
            prompt_data += "请根据以上数据，从以下三个方面进行分析，并给出一个最终总结：\n1. **核心优势**: 这只ETF最主要的投资亮点是什么？\n2. **潜在风险**: 投资者需要注意哪些潜在风险？\n3. **板块前景**: 结合板块估值和前景，对该ETF的赛道进行评价。\n4. **最终结论**: 给出一个不超过50字的简明投资结论。"
            
            # 3. 调用AI模型
            if self.stock_analyzer:
                ai_summary = self.stock_analyzer.get_ai_analysis_from_prompt(prompt_data)
            else:
                ai_summary = "AI分析器未初始化，无法生成摘要。"

            self.analysis_result['ai_summary'] = {"message": ai_summary}
            print("AI综合诊断生成完成。")

        except Exception as e:
            print(f"生成AI摘要时出错: {e}")
            self.analysis_result['ai_summary'] = {"error": f"生成AI摘要失败: {e}"}

if __name__ == '__main__':
    # For testing purposes
    test_etf = '510300'  # 沪深300 ETF
    analyzer = EtfAnalyzer(test_etf)
    results = analyzer.run_analysis()
    import json
    print(json.dumps(results, indent=4, ensure_ascii=False))
