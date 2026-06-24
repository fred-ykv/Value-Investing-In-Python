This repository hosts the code of **Value Investing in Python**, a data science tutorial published in Medium. 
This tutorial covers fundamental analysis for US stocks.

## Modular Fundamental Analysis Toolkit

This repository now also includes a modular Python toolkit for US stock
fundamental analysis. The original notebooks are preserved, while the new
package under `fundamental_analysis/` makes the analysis easier to audit,
test, and reuse.

### What the modular toolkit does

* Collects structured annual data from Yahoo Finance.
* Preserves support for notebook-driven Finviz/scraping workflows through an
  adapter layer.
* Normalizes income statement, balance sheet, cash flow, and market data.
* Computes valuation models such as DCF/FCFF, Graham, EVA, Residual Income,
  DDM, and Growth-Tech valuation.
* Scores stocks across valuation, growth, quality, debt, liquidity, and data
  confidence.
* Produces Markdown reports with executive summary, valuation table, score by
  dimension, risk diagnostics, and a final recommendation.

### Quick start

Install dependencies:

```bash
pip install -r requirements.txt
```

Run a single ticker:

```bash
python main.py AAPL
```

Save a Markdown report:

```bash
python main.py AAPL --output AAPL_report.md
```

Run a calibration basket:

```bash
python calibrate.py
```

Or pass your own tickers:

```bash
python calibrate.py MLI AAPL JPM RIVN
```

### Notebook integration

Existing notebooks can send their variables into the modular analysis pipeline by adding a final cell like this:

```python
from fundamental_analysis.notebook_adapter import analyze_from_notebook_globals, print_modular_report

modular_result = analyze_from_notebook_globals(globals())
print_modular_report(modular_result)
```

This keeps the existing notebook collection flow intact while moving final
valuation, scoring, and reporting into auditable Python modules.

### Tests

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

The tests cover traditional industrial companies, big tech, banks/financials,
negative-FCF companies, valuation models, scoring, report generation, Yahoo
statement mapping, and notebook adapter behavior.

## Syllabus
The organization of this tutorial falls into the following parts:

**[1. Collecting financial data for fundamental analysis](https://medium.com/@luo9137/collecting-financial-data-for-fundamental-analysis-115140f5f162)**

Data is the foundation of this project, and all the subsequent analysis will use data collected in this section. In this section, we have 3 learning objectives:
* Understand the basic concept of value investing and intrinsic value
* Understand what data will be needed to calculate intrinsic value
* Learn to collect the financial data needed from future use

**[2. How to Generate these Popular Stock Terms using Python](https://medium.com/@luo9137/how-to-generate-these-popular-stock-terms-using-python-4e69c6acc6b3)**

This section covers the relative simple metrics which will be very useful in fundamental analysis. 
Here we have 4 learning objectives:
* What are some important metrics for value investing
* Learn to load financial data into Pandas
* Learn how to retrieve and calculate the metrics using Pandas

**[3. How to calculate the intrinsic value](https://medium.com/@luo9137/how-to-calculate-the-intrinsic-value-of-a-stock-31c0312586a3)**

This section unveils the definition of intrinsic value, and also provide a step-by-step calculation for intrinsic value. Here we have 2 learning objectives:
* Calculate intrinsic value in 2 ways
* Discuss the downside and remedy for these 2 methods

## Who is the target audience?
If you have been trading stocks for years but conducted your fundamental analysis manually, this is the starting point for you to automate your analysis. Thus, you could conduct a fundamental analysis on a large scale, save a lot of time and avoid human mistakes.

If you have just started to trade stocks, and have no idea about how to evaluate a stock. Then, this tutorial could help you establish a basic framework and hypothetically save you some money for avoiding some obvious mistakes.

If you are a data science newbie, wish to gain some hands-on experience. Then, the finance field can be an ideal starting point since it could offer you tons of organized and relatively clean data.

## Prerequisites
You do not need to know any finance to be able to study this tutorial, as we will introduce Preston Pysh’s videos, who did a great job in teaching financial concepts in an easy-to-understand way.

Python basics and Pandas would be required. If you are not familiar with them, here are some resources could be helpful:

* [Python 3 Tutorial — Learn Python in 30 Minutes](https://www.google.com/url?sa=t&rct=j&q=&esrc=s&source=web&cd=1&ved=2ahUKEwjG64PJ7P_mAhXStVkKHb0WAecQFjAAegQIARAB&url=https%3A%2F%2Fwww.programiz.com%2Fpython-programming%2Ftutorial&usg=AOvVaw20Znr2oKGr-03mkPFz4rZT): What you need to know is the first 6 bullet points, from ‘Run Python on your computer’ to ‘Exceptions (Handling, User-defined Exception, …)’
* [Get Started With Python Pandas In 5 minutes](https://medium.com/bhavaniravi/python-pandas-tutorial-92018da85a33)

You could also try to start without Python and Pandas basics since I am trying to make everything clear. But if you at some point feel hard to understand what the code does, please feel free to leave me a comment and come back to these tutorials.

## Next

I am working with teammates to build a website that hosts tutorials and also provide financial insights, stock recommendation based on the technologies that we learned and taught on the website.

## Acknowledgements
I want to thank [Preston Pysh](https://www.youtube.com/channel/UCLTdCY-fNXc1GqzIuflK-OQ), [Investopedia](http://investopedia.com/), [StatQuest](https://www.youtube.com/user/joshstarmer) and [Towards Data Science](https://towardsdatascience.com/).

Preston Pysh created a fantastic value investing course on YouTube. I would recommend this course to anyone with an interest in investing and finance.

Investopedia is my initial source of financial knowledge. It offers an easy-to-understand explanation for financial terms.
StatQuest and Towards Data Science have great tutorials on Machine Learning and Stats.

I benefited a lot from these resources.

If you have any suggestions or feedback, please feel free to leave me a comment and come back to these tutorials.
