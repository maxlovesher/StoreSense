# Introduction

*Author: Member 6 (Dashboard & Integration), who assembles the sections of the team into this one report.*

## Problem statement

A grocery retailer has millions of baskets and little idea what they say. StoreSense turns the order history of the **Instacart** online grocery service into a **star-schema data warehouse** and mines it to answer three business questions:

- **When and what do people buy?** (OLAP analysis of the warehouse)
- **Which products are bought together?** (association rules, Apriori and FP-Growth)
- **What kinds of customers are there?** (K-Means segmentation)

A stretch goal asks a fourth question: **will a customer buy a product again?** (reorder prediction). All results are shown in an interactive Streamlit dashboard.

## Objectives

1. Build an **ETL pipeline** that turns the raw CSV files into a clean warehouse (section 1).
2. Design a **star schema** and demonstrate the OLAP operations roll-up, drill-down, slice, dice and pivot (section 2).
3. Mine **association rules** with Apriori and FP-Growth and compare the two algorithms (section 3).
4. **Segment customers** with K-Means on RFM-style features (section 4).
5. *(Stretch)* **Predict reorders** with classification, evaluated without data leakage (section 5).
6. Present everything in an **interactive dashboard** (section 6) and draw the business insights together (section 7).

## The data

The dataset is **Instacart Market Basket Analysis** (Kaggle): **3,421,083 orders** from **206,209 users**, **33,819,106 order lines**, **49,688 products** in **134 aisles** and **21 departments**. Section 1 describes the files in detail.

It has three limits that shape every result in this report:

- **No prices.** A "sale" is one order line (one product in one order), and basket size stands in for spending.
- **No calendar dates.** There are only the day of the week, the hour, and the number of days since the previous order (capped at 30).
- **Day-of-week coding is undocumented.** We assume 0 means Sunday.

## Architecture

```
Raw CSVs ──► ETL (Python + DuckDB) ──► DuckDB warehouse (star schema)
                                            │
          ┌─────────────────────────────────┼──────────────────────────┐
          ▼                                 ▼                          ▼
    OLAP queries                    Association rules            Segmentation
  (ROLLUP / CUBE)                 (Apriori vs FP-Growth)         (K-Means, RFM)
          │                                 │                          │
          │                       Reorder prediction (stretch)         │
          └─────────────────────────────────┼──────────────────────────┘
                                            ▼
                                 Streamlit dashboard
```

The warehouse holds two fact tables (`fact_order_line`, `fact_order`) and three dimensions (`dim_product`, `dim_user`, `dim_time`). The mining modules read it and save small result files, which the dashboard shows.

## The team and the sections

| Section | Topic | Member |
|---|---|---|
| 1 | Data and ETL | Member 1, Data & ETL Lead |
| 2 | Warehouse and OLAP | Member 2, Warehouse & OLAP |
| 3 | Association rules | Member 3, Association Rules |
| 4 | Customer segmentation | Member 4, Customer Segmentation |
| 5 | Reorder prediction | Member 5, Reorder Prediction & Evaluation |
| 6 | Dashboard | Member 6, Dashboard & Integration |
| 7 | Insights, limitations and future work | Member 6 |

The code, the tests and the instructions to reproduce each result are in the repository (`README.md`).
