# 7. Insights, limitations and future work

*Author: Member 6 (Dashboard & Integration). Every number below comes from sections 1 to 5 and can be found there with its method.*

## 7.1 Key business insights

1. **Two departments carry the store.** Produce and dairy eggs make up **45.9%** of all order lines (29.2% and 16.7%). Their availability and freshness matter more than any promotion on a small department. *(Section 2)*

2. **Demand is very uneven in time.** Sunday is the busiest day (6.5M order lines) and Thursday the quietest (3.9M), a ratio of **1.66**. The two weekend days carry **33.2%** of all sales, against 28.6% if the week were flat. Sunday baskets are also the largest (11.2 items against 9.3 on Wednesday). Staffing, stock and delivery slots should follow this rhythm, with the peak at **10:00**. *(Section 2)*

3. **Alcohol is the exception to the weekly pattern.** It peaks on **Friday** (28,465 lines) and is lowest on Sunday (18,150), while the store as a whole is busiest on Sunday. Weekend stock for this department may need to arrive earlier in the week. *(Section 2)*

4. **Customers shop for "missions", and the rules show them.** Dry pasta, pasta sauce and packaged cheese form the strongest aisle group (lift up to **4.8**): 27.6% of baskets with dry pasta also contain pasta sauce, against 6.6% by chance. A "pasta night" shelf or bundle is a direct use. Pantry canned goods and the frozen "easy dinner" aisles show the same pattern. *(Section 3)*

5. **At product level, flavours of one line are bought together.** The strongest product rules link flavours of the same skyr yogurt (lift above **60**, about 1 in 5 baskets with one flavour has another). Customers stock up on variety, so mixed-flavour multipacks, and recommending the other flavours when one is out of stock, fit this behaviour. *(Section 3)*

6. **Under a third of the customers produce almost two thirds of the orders.** The **loyal frequent shoppers** are 29.4% of users but place about **62%** of all orders and buy about 65% of all items. They order every 10 days and 66% of their basket is repeat items, so a "buy it again" list, a standing order or a loyalty reward protects the most value. *(Section 4)*

7. **Habit predicts a reorder much more than customer traits do.** 59% of all order lines are products the customer has bought before. In a model that predicts reorders (ROC-AUC 0.83), the most important features are how recently and how often the customer bought the product: **27.9%** of products bought in the last order are bought again, against **2.8%** of those last bought five or more orders ago. A product bought only once comes back in 4.7% of cases. *(Section 5)*

8. **The right algorithm depends on the data.** FP-Growth is the usual favourite, and at product level with a low `min_support` it is about **3 times faster** than Apriori. At aisle level (132 items) Apriori was faster and lighter at every setting we tried. Benchmarking on the real data, not the textbook, settled the choice. *(Section 3)*

## 7.2 Limitations

These apply to the whole project; each section lists its own in more detail.

- **No prices.** Sales are counted as order lines, so a cheap and an expensive item weigh the same. Rankings by revenue could be different, and "basket size" is only a proxy for spending (sections 2, 3 and 4).
- **No calendar dates.** We see the day of the week and hour, but no months, seasons or trends, and "recency" is the gap before the last order, not the time since it (sections 2 and 4).
- **The day-of-week coding is assumed.** If 0 is not Sunday, the day names shift, but the patterns stay the same (section 2).
- **Samples and filters.** Rules come from 500,000 of 3.18M baskets and the top 1,000 products (54% of order lines), and the reorder model from 30,000 of 131,209 users. For the top rule, the sample was within about 7% of the full data, but we did not check every rule (sections 3 and 5).
- **Association is not cause.** A rule or a feature importance says what goes together, not what makes it happen.
- **The segments overlap.** K-Means cuts a continuum of shoppers into four groups (silhouette 0.27), so the borders are soft (section 4).
- **Modest predictive power.** The reorder model finds about half of the real reorders, and only about 37% of its "will reorder" predictions are right. LightGBM beat the simple baseline by a small margin that we did not prove stable (section 5).
- **A snapshot.** The warehouse is built once from a fixed file; there is no live data.

## 7.3 Future work

- **Add prices** to rank rules, segments and recommendations by revenue instead of counts.
- **Add real dates** to study trends and seasons, and to make recency a true recency.
- **Longer and sequential rules.** Allow itemsets of more than 3 items, and look at what is bought *after* what across orders.
- **A richer reorder model.** Add the day, hour and gap of the order being predicted, tune the model, and validate with cross-validation. Extend the candidates beyond products bought before.
- **Refresh automatically.** Re-run the pipeline and the mining scripts on a schedule, and keep segments up to date as customers change habits.
- **Serve recommendations.** Put `frequently_bought_together` and the reorder scores behind an API for a shop front-end, and test them with an A/B experiment.

## 7.4 Conclusion

StoreSense takes a 3.4-million-order grocery history from raw files to a validated star schema, answers when and what people buy with OLAP, finds what is bought together with two mining algorithms and compares them, groups 206,209 customers into four understandable segments, and predicts reorders without leaking the answer. The dashboard puts all of it in one place. Its main limits are the missing prices and dates, and the rest of the report says where each result stands because of them.
