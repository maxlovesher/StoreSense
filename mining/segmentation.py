"""
Customer segmentation (K-Means on RFM-style features).

Owner: Member 4 (Customer Segmentation)
Spec:  docs/PROJECT_BRIEF.md, section 6.4

Build per-user features, standardise them, pick k (elbow + silhouette),
cluster, name each segment and write it back to dim_user.segment.

Run from the project root:
    python mining/segmentation.py
"""
